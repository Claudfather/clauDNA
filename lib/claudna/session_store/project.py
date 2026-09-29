"""Log → projection folds (spec §6.4–6.5), ``rebuild``, and incremental ``refresh``.

The fold functions are pure: events in, dict out. They never touch the disk,
which is what makes the round-trip test meaningful (fold the logs, delete the
projections, fold again, compare). ``rebuild`` and ``refresh`` do the I/O.

Readers skip lines :func:`session_store.events.classify` marks ``unknown`` or
``invalid``; the count lands in ``projected_from.skipped`` so a damaged log is
visible rather than silently shorter.

``session.json`` depends only on the lifecycle log and each segment's
*projection* (status, summary) — never on activity. That is what lets
:func:`refresh` re-fold just the pieces an append touched.

Which segments exist is answered one way everywhere: the ``seg-NNN``
directories. A ``segment.opened`` event whose directory is gone does not
resurrect it, and nothing here ever creates a directory.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from . import events as ev
from .fsio import atomic_write_json, read_json, read_jsonl
from .paths import SessionPaths

SESSION_SCHEMA = "claudna.session/1"
SEGMENT_SCHEMA = "claudna.segment/1"

_SUMMARY_STATUS = {
    "summary.requested": "pending",
    "summary.completed": "done",
    "summary.failed": "failed",
    "summary.skipped": "skipped",
}
_COUNTED = {
    "prompt.submitted": "prompts",
    "skill.invoked": "skills",
    "tool.failed": "failures",
    "checkpoint.noted": "checkpoints",
}


@dataclass(frozen=True)
class Log:
    """A log's foldable events plus the ``projected_from`` record describing the read."""

    events: list[dict]
    projected_from: dict


def load_log(path, *, sid: str, log: str, seg: int | None = None) -> Log:
    """Read a log and keep only events that are well-formed *and* belong here.

    An event is kept when :func:`~session_store.events.classify` calls it
    ``ok`` and :func:`~session_store.events.placement_errors` finds nothing:
    right session, right log, and (for activity) the right segment. Everything
    else is counted in ``projected_from.skipped``.
    """
    read = read_jsonl(path)
    ok = [r for r in read.records
          if ev.classify(r) == "ok" and not ev.placement_errors(r, sid=sid, log=log, seg=seg)]
    skipped = read.skipped + len(read.records) - len(ok)
    return Log(events=ok, projected_from={"lines": read.lines, "bytes": read.bytes, "skipped": skipped})


def load_lifecycle(paths: SessionPaths) -> Log:
    return load_log(paths.lifecycle, sid=paths.sid, log=ev.LIFECYCLE)


def load_activity(paths: SessionPaths, index: int) -> Log:
    return load_log(paths.segment(index).events, sid=paths.sid, log=ev.ACTIVITY, seg=index)


def by_segment(lifecycle: list[dict]) -> dict[int, list[dict]]:
    """Bucket segment-scoped lifecycle events by index, preserving order."""
    buckets: dict[int, list[dict]] = defaultdict(list)
    for e in lifecycle:
        if e["seg"] is not None:
            buckets[e["seg"]].append(e)
    return buckets


def transcript_path_of(lifecycle: list[dict]) -> str | None:
    """The first non-null ``transcript_path`` any ``session.opened`` recorded."""
    return next((e["data"]["transcript_path"] for e in lifecycle
                 if e["kind"] == "session.opened" and e["data"]["transcript_path"]), None)


def project_segment(sid: str, index: int, boundary: list[dict], activity: Log, *,
                    transcript_path: str | None) -> dict:
    """Fold one segment's lifecycle events (``boundary``) and activity into ``segment.json``.

    A segment directory with no ``segment.opened`` event (a crash between the
    ``mkdir`` and the append) still projects — as ``opened_by: "unknown"``.
    A re-seal (after a blocked compaction) moves the end: last seal wins.
    """
    first_open = last_seal = None
    summary = {"status": "none", "job_id": None}
    for e in boundary:
        if e["kind"] == "segment.opened" and first_open is None:
            first_open = e
        elif e["kind"] == "segment.sealed":
            last_seal = e
        elif e["kind"] in _SUMMARY_STATUS:
            summary = {"status": _SUMMARY_STATUS[e["kind"]], "job_id": e["data"].get("job_id", summary["job_id"])}

    counts = dict.fromkeys(_COUNTED.values(), 0)
    for e in activity.events:
        if e["kind"] in _COUNTED:
            counts[_COUNTED[e["kind"]]] += 1

    return {
        "schema": SEGMENT_SCHEMA,
        "sid": sid,
        "index": index,
        "status": "sealed" if last_seal else "open",
        "opened_at": first_open["ts"] if first_open else None,
        "opened_by": first_open["data"]["opened_by"] if first_open else "unknown",
        "sealed_at": last_seal["ts"] if last_seal else None,
        "sealed_by": last_seal["data"]["sealed_by"] if last_seal else None,
        "transcript": {
            "path": transcript_path,
            "range": {
                "start": first_open["data"]["start"] if first_open else None,
                "end": last_seal["data"]["end"] if last_seal else None,
            },
            "sha256": last_seal["data"].get("sha256") if last_seal else None,
        },
        "counts": counts,
        "summary": summary,
        "projected_from": activity.projected_from,
    }


def project_session(sid: str, lifecycle: Log, segments: list[dict], *, transcript_path: str | None) -> dict:
    """Fold the lifecycle log (plus already-projected segments) into ``session.json``, in one pass."""
    first = None
    status, closed_at, close_reason = "unknown", None, None
    children: list[str] = []
    private = False
    for e in lifecycle.events:
        kind = e["kind"]
        if kind == "session.opened":
            first = first or e
            status, closed_at, close_reason = "open", None, None  # a resume reopens
        elif kind == "session.closed":
            status, closed_at, close_reason = "closed", e["ts"], e["data"]["reason"]
        elif kind == "session.child_linked" and e["data"]["child_sid"] not in children:
            children.append(e["data"]["child_sid"])
        elif kind == "session.privacy_set":
            private = e["data"]["private"]

    tally = dict.fromkeys(_SUMMARY_STATUS.values(), 0)
    for s in segments:
        if s["summary"]["status"] in tally:
            tally[s["summary"]["status"]] += 1
    open_segments = [s["index"] for s in segments if s["status"] == "open"]

    return {
        "schema": SESSION_SCHEMA,
        "sid": sid,
        "parent_sid": first["data"]["parent_sid"] if first else None,
        "chain_id": first["data"]["chain_id"] if first else sid,
        "children": children,
        "status": status,
        "private": private,
        "actor": first["data"]["actor"] if first else None,
        "origin": first["data"]["origin"] if first else None,
        "transcript_path": transcript_path,
        "opened_at": first["ts"] if first else None,
        "opened_by": first["data"]["source"] if first else None,
        "closed_at": closed_at,
        "close_reason": close_reason,
        "segments": {"count": len(segments), "open": max(open_segments) if open_segments else None},
        "summary": {f"segments_{k}": n for k, n in tally.items()},
        "projected_from": lifecycle.projected_from,
    }


@dataclass(frozen=True)
class RebuildReport:
    """What :func:`rebuild` wrote and what it had to skip."""

    sid: str
    segments: list[int]
    skipped_lines: int


def rebuild(paths: SessionPaths) -> RebuildReport:
    """Regenerate every projection for one session from its logs (the repair path)."""
    lifecycle = load_lifecycle(paths)
    buckets = by_segment(lifecycle.events)
    transcript = transcript_path_of(lifecycle.events)
    indices = paths.segment_indices()
    skipped = lifecycle.projected_from["skipped"]

    segments = []
    for index in indices:
        activity = load_activity(paths, index)
        skipped += activity.projected_from["skipped"]
        seg = project_segment(paths.sid, index, buckets[index], activity, transcript_path=transcript)
        atomic_write_json(paths.segment(index).segment_json, seg, durable=False)
        segments.append(seg)

    atomic_write_json(paths.session_json,
                      project_session(paths.sid, lifecycle, segments, transcript_path=transcript), durable=False)
    return RebuildReport(sid=paths.sid, segments=indices, skipped_lines=skipped)


def _current_projection(path, *, bytes_before: int | None) -> dict | None:
    """A segment projection that exactly reflects the log up to ``bytes_before``, else ``None``."""
    projected = read_json(path)
    if not isinstance(projected, dict) or projected.get("schema") != SEGMENT_SCHEMA:
        return None
    pf = projected.get("projected_from")
    if bytes_before is None or not isinstance(pf, dict) or pf.get("bytes") != bytes_before:
        return None
    return projected


def refresh(paths: SessionPaths, event: dict, *, bytes_before: int | None = None) -> None:
    """Re-project only what appending ``event`` touched — the hot path.

    * activity event → bump that segment's counter in place, O(1), when its
      projection is current (``projected_from.bytes == bytes_before``, the log's
      size before the append); otherwise re-fold that segment from its logs.
      ``session.json`` never depends on activity.
    * ``session.opened`` → full :func:`rebuild`: it can change the transcript
      path every segment projection embeds.
    * other segment-scoped lifecycle event → that segment, then ``session.json``.
    * other session-scoped lifecycle event → ``session.json``.

    ``session.json`` is folded from the lifecycle log plus the other segments'
    existing projections; if any is missing or unreadable, fall back to a full
    :func:`rebuild` — the logs are still the truth.
    """
    kind, seg = event["kind"], event["seg"]
    if ev.REGISTRY[kind].log == ev.ACTIVITY:
        seg_json = paths.segment(seg).segment_json
        projected = _current_projection(seg_json, bytes_before=bytes_before)
        if projected is None:
            lifecycle = load_lifecycle(paths)
            projected = project_segment(paths.sid, seg, by_segment(lifecycle.events)[seg],
                                        load_activity(paths, seg),
                                        transcript_path=transcript_path_of(lifecycle.events))
        else:
            if kind in _COUNTED:
                projected["counts"][_COUNTED[kind]] += 1
            pf = projected["projected_from"]
            projected["projected_from"] = {"lines": pf["lines"] + 1,
                                           "bytes": paths.segment(seg).events.stat().st_size,
                                           "skipped": pf["skipped"]}
        atomic_write_json(seg_json, projected, durable=False)
        return
    if kind == "session.opened":
        rebuild(paths)
        return

    lifecycle = load_lifecycle(paths)
    transcript = transcript_path_of(lifecycle.events)
    fresh: dict[int, dict] = {}
    if seg is not None:
        fresh[seg] = project_segment(paths.sid, seg, by_segment(lifecycle.events)[seg],
                                     load_activity(paths, seg), transcript_path=transcript)
        atomic_write_json(paths.segment(seg).segment_json, fresh[seg], durable=False)

    segments = []
    for index in paths.segment_indices():
        projected = fresh.get(index) or read_json(paths.segment(index).segment_json)
        if not isinstance(projected, dict) or projected.get("schema") != SEGMENT_SCHEMA:
            rebuild(paths)
            return
        segments.append(projected)
    atomic_write_json(paths.session_json,
                      project_session(paths.sid, lifecycle, segments, transcript_path=transcript), durable=False)
