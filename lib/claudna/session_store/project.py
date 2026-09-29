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
from . import schema
from .fsio import atomic_write_json, read_json, read_jsonl
from .schema import is_instance
from .paths import SessionPaths

SESSION_SCHEMA = "claudna.session/1"
SEGMENT_SCHEMA = "claudna.segment/1"
_SCHEMA_FILES = {SESSION_SCHEMA: "session", SEGMENT_SCHEMA: "segment"}

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
    """The session's current transcript: the latest non-null ``session.opened`` path."""
    paths = [e["data"]["transcript_path"] for e in lifecycle
             if e["kind"] == "session.opened" and e["data"]["transcript_path"]]
    return paths[-1] if paths else None


def segment_transcript_paths(lifecycle: list[dict]) -> dict[int, str | None]:
    """Each segment's transcript, in one pass: ``index -> path``.

    A segment's path is the latest non-null ``session.opened`` path *before* it
    opened — so a later resume that writes a new transcript file never
    retargets an earlier segment. A segment opened before any path was known
    (a missed SessionStart), or one the log never names, falls back to the
    first path that arrives.
    """
    first = latest = None
    opened_under: dict[int, str | None] = {}
    for e in lifecycle:
        if e["kind"] == "session.opened" and e["data"]["transcript_path"]:
            latest = e["data"]["transcript_path"]
            first = first or latest
        elif e["kind"] == "segment.opened":
            opened_under.setdefault(e["seg"], latest)
    return defaultdict(lambda: first, {i: path or first for i, path in opened_under.items()})


@dataclass(frozen=True)
class Boundary:
    """One segment's lifecycle state, folded from its bucket of lifecycle events.

    The single interpretation of boundary events — :func:`project_segment` and
    the store's write guards both read it, so they can't disagree.
    """

    first_open: dict | None
    last_seal: dict | None  # a re-seal (after a blocked compaction) moves the end: last seal wins
    summary: dict

    @property
    def sealed(self) -> bool:
        return self.last_seal is not None

    @property
    def start(self) -> int | None:
        return self.first_open["data"]["start"] if self.first_open else None


def fold_boundary(events: list[dict]) -> Boundary:
    first_open = last_seal = None
    summary = {"status": "none", "job_id": None}
    for e in events:
        if e["kind"] == "segment.opened" and first_open is None:
            first_open = e
        elif e["kind"] == "segment.sealed":
            last_seal = e
        elif e["kind"] in _SUMMARY_STATUS:
            summary = {"status": _SUMMARY_STATUS[e["kind"]], "job_id": e["data"].get("job_id", summary["job_id"])}
    return Boundary(first_open=first_open, last_seal=last_seal, summary=summary)


def session_status(lifecycle: list[dict]) -> tuple[str, str | None, str | None]:
    """``(status, closed_at, close_reason)`` — ``unknown`` until opened; a resume reopens."""
    status, closed_at, close_reason = "unknown", None, None
    for e in lifecycle:
        if e["kind"] == "session.opened":
            status, closed_at, close_reason = "open", None, None
        elif e["kind"] == "session.closed":
            status, closed_at, close_reason = "closed", e["ts"], e["data"]["reason"]
    return status, closed_at, close_reason


def next_segment_index(paths: SessionPaths) -> int:
    """One past every index the session has *ever* used, so a deleted segment's index is never reused.

    "Used" is read as widely as possible: every directory, and every ``seg``
    any parseable lifecycle line names — including lines from a newer envelope
    version or of an unknown kind, which readers skip but numbering must not.
    """
    named = {r["seg"] for r in read_jsonl(paths.lifecycle).records
             if is_instance(r.get("seg"), int) and r["seg"] >= 1}
    return max([*paths.segment_indices(), *named], default=0) + 1


def project_segment(sid: str, index: int, boundary: list[dict], activity: Log, *,
                    transcript_path: str | None) -> dict:
    """Fold one segment's lifecycle events (``boundary``) and activity into ``segment.json``.

    A segment directory with no ``segment.opened`` event (a crash between the
    ``mkdir`` and the append) still projects — as ``opened_by: "unknown"``.
    """
    b = fold_boundary(boundary)
    counts = dict.fromkeys(_COUNTED.values(), 0)
    for e in activity.events:
        if e["kind"] in _COUNTED:
            counts[_COUNTED[e["kind"]]] += 1

    return {
        "schema": SEGMENT_SCHEMA,
        "sid": sid,
        "index": index,
        "status": "sealed" if b.sealed else "open",
        "opened_at": b.first_open["ts"] if b.first_open else None,
        "opened_by": b.first_open["data"]["opened_by"] if b.first_open else "unknown",
        "sealed_at": b.last_seal["ts"] if b.last_seal else None,
        "sealed_by": b.last_seal["data"]["sealed_by"] if b.last_seal else None,
        "transcript": {
            "path": transcript_path,
            "range": {"start": b.start, "end": b.last_seal["data"]["end"] if b.last_seal else None},
            "sha256": b.last_seal["data"].get("sha256") if b.last_seal else None,
        },
        "counts": counts,
        "summary": b.summary,
        "projected_from": activity.projected_from,
    }


def project_session(sid: str, lifecycle: Log, segments: list[dict], *, transcript_path: str | None) -> dict:
    """Fold the lifecycle log (plus already-projected segments) into ``session.json``, in one pass."""
    first = next((e for e in lifecycle.events if e["kind"] == "session.opened"), None)
    status, closed_at, close_reason = session_status(lifecycle.events)
    children: list[str] = []
    private = False
    for e in lifecycle.events:
        if e["kind"] == "session.child_linked" and e["data"]["child_sid"] not in children:
            children.append(e["data"]["child_sid"])
        elif e["kind"] == "session.privacy_set":
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


def _fold_segment(paths: SessionPaths, index: int, *,
                  buckets: dict[int, list[dict]], transcripts: dict[int, str | None]) -> dict:
    """Re-fold one segment from its logs and write ``segment.json``."""
    seg = project_segment(paths.sid, index, buckets[index], load_activity(paths, index),
                          transcript_path=transcripts[index])
    atomic_write_json(paths.segment(index).segment_json, seg)
    return seg


def rebuild(paths: SessionPaths) -> RebuildReport:
    """Regenerate every projection for one session from its logs (the repair path)."""
    lifecycle = load_lifecycle(paths)
    buckets, transcripts = by_segment(lifecycle.events), segment_transcript_paths(lifecycle.events)
    indices = paths.segment_indices()
    segments = [_fold_segment(paths, i, buckets=buckets, transcripts=transcripts) for i in indices]
    atomic_write_json(paths.session_json, project_session(paths.sid, lifecycle, segments,
                                                          transcript_path=transcript_path_of(lifecycle.events)))
    skipped = lifecycle.projected_from["skipped"] + sum(s["projected_from"]["skipped"] for s in segments)
    return RebuildReport(sid=paths.sid, segments=indices, skipped_lines=skipped)


def read_projection(path, schema_id: str, *, bytes_before: int | None = None) -> dict | None:
    """The projection at ``path`` if it's well-formed (and, given ``bytes_before``, current), else ``None``.

    ``projected_from.bytes`` is the watermark: ``segment.json`` carries its
    activity log's, ``session.json`` its lifecycle log's. When ``bytes_before``
    (the log's size before an append) doesn't match, an earlier append's
    refresh never ran — a killed hook — and the caller re-folds.
    """
    projected = read_json(path)
    if not isinstance(projected, dict) or projected.get("schema") != schema_id:
        return None
    if schema.validate(projected, schema.load(_SCHEMA_FILES[schema_id])):
        return None  # tagged right but malformed (e.g. hand-edited): re-fold rather than trust it
    if bytes_before is not None:
        pf = projected.get("projected_from")
        if not isinstance(pf, dict) or pf.get("bytes") != bytes_before:
            return None
    return projected


def refresh(paths: SessionPaths, event: dict, *, bytes_before: int) -> None:
    """Re-project only what appending ``event`` touched — the hot path.

    ``bytes_before`` is the size of the log ``event`` was appended to, taken
    before the append.

    * activity event → bump that segment's counter in place, O(1), when its
      projection is current; otherwise re-fold that segment from its logs.
      ``session.json`` never depends on activity.
    * lifecycle event → if ``session.json`` doesn't reflect the lifecycle log up
      to ``bytes_before``, a lost refresh left something stale: full
      :func:`rebuild`. Otherwise re-fold every segment whose projection no
      longer agrees with the log — the event's own segment, one that's missing
      or damaged, or one whose transcript path just resolved (a late first
      ``session.opened``) — and then ``session.json``.
    """
    if ev.REGISTRY[event["kind"]].log == ev.ACTIVITY:
        _refresh_activity(paths, event, bytes_before=bytes_before)
        return
    if read_projection(paths.session_json, SESSION_SCHEMA, bytes_before=bytes_before) is None:
        rebuild(paths)
        return

    lifecycle = load_lifecycle(paths)
    buckets, transcripts = by_segment(lifecycle.events), segment_transcript_paths(lifecycle.events)
    segments = []
    for index in paths.segment_indices():
        projected = None if index == event["seg"] else read_projection(paths.segment(index).segment_json,
                                                                         SEGMENT_SCHEMA)
        if projected is None or projected["transcript"]["path"] != transcripts[index]:
            projected = _fold_segment(paths, index, buckets=buckets, transcripts=transcripts)
        segments.append(projected)
    atomic_write_json(paths.session_json, project_session(paths.sid, lifecycle, segments,
                                                          transcript_path=transcript_path_of(lifecycle.events)))


def _refresh_activity(paths: SessionPaths, event: dict, *, bytes_before: int) -> None:
    kind, seg = event["kind"], event["seg"]
    projected = read_projection(paths.segment(seg).segment_json, SEGMENT_SCHEMA, bytes_before=bytes_before)
    if projected is None:
        lifecycle = load_lifecycle(paths)
        _fold_segment(paths, seg, buckets=by_segment(lifecycle.events),
                      transcripts=segment_transcript_paths(lifecycle.events))
        return
    if kind in _COUNTED:
        projected["counts"][_COUNTED[kind]] += 1
    pf = projected["projected_from"]
    projected["projected_from"] = {"lines": pf["lines"] + 1, "bytes": paths.segment(seg).events.stat().st_size,
                                   "skipped": pf["skipped"]}
    atomic_write_json(paths.segment(seg).segment_json, projected)
