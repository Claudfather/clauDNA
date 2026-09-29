"""Log → projection folds (spec §6.4–6.5), and ``rebuild``.

The fold functions are pure: records in, dict out. They never touch the disk,
which is what makes the round-trip test meaningful (fold the logs, delete the
projections, fold again, compare). :func:`rebuild` is the only function here
that does I/O.

Readers skip lines :func:`session_store.events.classify` marks ``unknown`` or
``invalid``; the count lands in ``projected_from.skipped`` so a damaged log is
visible rather than silently shorter.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import events as ev
from .fsio import JsonlRead, atomic_write_json, read_jsonl
from .paths import SessionPaths

SESSION_SCHEMA = "claudna.session/1"
SEGMENT_SCHEMA = "claudna.segment/1"

_SUMMARY_STATUS = {
    "summary.requested": "pending",
    "summary.completed": "done",
    "summary.failed": "failed",
    "summary.skipped": "skipped",
}


def usable(read: JsonlRead) -> tuple[list[dict], int]:
    """Split a log read into foldable events and a count of skipped lines."""
    ok = [r for r in read.records if ev.classify(r) == "ok"]
    return ok, read.skipped + (len(read.records) - len(ok))


def project_segment(
    sid: str,
    index: int,
    lifecycle: list[dict],
    activity: list[dict],
    *,
    transcript_path: str | None,
    activity_read: JsonlRead | None = None,
) -> dict:
    """Fold one segment's boundary, summary, and activity events into ``segment.json``.

    A segment directory with no ``segment.opened`` event (a crash between the
    ``mkdir`` and the append) still projects — as ``opened_by: "unknown"``.
    """
    opened = [e for e in lifecycle if e["kind"] == "segment.opened" and e["seg"] == index]
    sealed = [e for e in lifecycle if e["kind"] == "segment.sealed" and e["seg"] == index]
    summary_events = [e for e in lifecycle if e["kind"] in _SUMMARY_STATUS and e["seg"] == index]

    first_open = opened[0] if opened else None
    last_seal = sealed[-1] if sealed else None  # a re-seal (blocked compaction) moves the end

    summary = {"status": "none", "job_id": None}
    for e in summary_events:
        summary = {"status": _SUMMARY_STATUS[e["kind"]], "job_id": e["data"].get("job_id", summary["job_id"])}

    counts = {"prompts": 0, "skills": 0, "failures": 0, "checkpoints": 0}
    counted = {"prompt.submitted": "prompts", "skill.invoked": "skills", "tool.failed": "failures",
               "checkpoint.noted": "checkpoints"}
    for e in activity:
        if e["seg"] == index and e["kind"] in counted:
            counts[counted[e["kind"]]] += 1

    out = {
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
    }
    if activity_read is not None:
        skipped = activity_read.skipped + (len(activity_read.records) - len(activity))
        out["projected_from"] = {"lines": activity_read.lines, "bytes": activity_read.bytes, "skipped": skipped}
    return out


def project_session(
    sid: str,
    lifecycle: list[dict],
    segments: list[dict],
    *,
    lifecycle_read: JsonlRead | None = None,
) -> dict:
    """Fold ``lifecycle.jsonl`` (plus already-projected segments) into ``session.json``."""
    opened = [e for e in lifecycle if e["kind"] == "session.opened"]
    first = opened[0] if opened else None

    status = "unknown"
    closed_at = close_reason = None
    for e in lifecycle:
        if e["kind"] == "session.opened":
            status, closed_at, close_reason = "open", None, None  # a resume reopens
        elif e["kind"] == "session.closed":
            status, closed_at, close_reason = "closed", e["ts"], e["data"]["reason"]

    children: list[str] = []
    for e in lifecycle:
        if e["kind"] == "session.child_linked" and e["data"]["child_sid"] not in children:
            children.append(e["data"]["child_sid"])

    private = False
    for e in lifecycle:
        if e["kind"] == "session.privacy_set":
            private = e["data"]["private"]

    transcript_path = next((e["data"]["transcript_path"] for e in opened if e["data"]["transcript_path"]), None)
    open_segments = [s["index"] for s in segments if s["status"] == "open"]
    tally = {"done": 0, "pending": 0, "failed": 0, "skipped": 0}
    for s in segments:
        if s["summary"]["status"] in tally:
            tally[s["summary"]["status"]] += 1

    out = {
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
        "summary": {
            "segments_done": tally["done"],
            "segments_pending": tally["pending"],
            "segments_failed": tally["failed"],
            "segments_skipped": tally["skipped"],
        },
    }
    if lifecycle_read is not None:
        skipped = lifecycle_read.skipped + (len(lifecycle_read.records) - len(lifecycle))
        out["projected_from"] = {"lines": lifecycle_read.lines, "bytes": lifecycle_read.bytes, "skipped": skipped}
    return out


@dataclass(frozen=True)
class RebuildReport:
    """What :func:`rebuild` wrote and what it had to skip."""

    sid: str
    segments: list[int]
    skipped_lines: int


def rebuild(paths: SessionPaths) -> RebuildReport:
    """Regenerate every projection for one session from its logs.

    Segment indexes are the union of ``seg-NNN`` directories and indexes named
    by ``segment.opened`` events — the directories are the holder, but a log
    that names a segment whose directory is missing still projects it.
    """
    lifecycle_read = read_jsonl(paths.lifecycle)
    lifecycle, skipped = usable(lifecycle_read)
    named = {e["seg"] for e in lifecycle if e["kind"] == "segment.opened"}
    indices = sorted(set(paths.segment_indices()) | named)

    transcript_path = next(
        (e["data"]["transcript_path"] for e in lifecycle
         if e["kind"] == "session.opened" and e["data"]["transcript_path"]),
        None,
    )
    segments = []
    for index in indices:
        seg_paths = paths.segment(index)
        activity_read = read_jsonl(seg_paths.events)
        activity, seg_skipped = usable(activity_read)
        skipped += seg_skipped
        seg = project_segment(paths.sid, index, lifecycle, activity,
                              transcript_path=transcript_path, activity_read=activity_read)
        atomic_write_json(seg_paths.segment_json, seg)
        segments.append(seg)

    atomic_write_json(paths.session_json,
                      project_session(paths.sid, lifecycle, segments, lifecycle_read=lifecycle_read))
    return RebuildReport(sid=paths.sid, segments=indices, skipped_lines=skipped)
