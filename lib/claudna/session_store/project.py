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

import os
from collections import defaultdict
from dataclasses import dataclass

from . import events as ev
from . import schema
from .fsio import atomic_write_json, epoch_of, file_size, read_json, read_jsonl
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
    "tool.interrupted": "interrupts",
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


@dataclass(frozen=True)
class SessionFacts:
    """What a hook or worker needs to decide, folded straight from the lifecycle log."""

    status: str
    actor: dict | None  # the latest session.opened's: whoever reopened the session last owns it
    private: bool
    chain_id: str | None = None  # the first session.opened's, as session.json has it: a resume records its own sid
    claude_pid: int | None = None  # the latest session.opened's owning Claude Code process
    harvest: dict | None = None  # the latest session.opened's {enabled, vault}: its own consumer choice


def latest_origin(lifecycle: list[dict]) -> dict:
    """The latest ``session.opened``'s origin (a resume can move the session to another cwd)."""
    opened = [e for e in lifecycle if e["kind"] == "session.opened"]
    return opened[-1]["data"].get("origin") or {} if opened else {}


def harvest_skip(facts: SessionFacts, lifecycle: list[dict]) -> str | None:
    """Why harvest never takes this session (``off``, ``no repo``, ``no vault``), or ``None`` if it does.

    The one test: harvest skips on it, and export uses it to know whether
    anyone will ever retry this session's summaries (only harvest does).
    """
    if facts.private or not (facts.harvest or {}).get("enabled"):
        return "off"  # private, or this session never opted in
    origin = latest_origin(lifecycle)
    if not origin.get("repo"):
        return "no repo"  # no project scope: its drafts would land in the vault's shared tree (#373, M4)
    if not facts.harvest.get("vault") and not (origin.get("cwd") and os.path.isdir(origin["cwd"])):
        return "no vault"  # none recorded, and the cwd it would be found from is gone
    return None


HARVEST_CONSUMER = "harvest"  #: harvest's cursor name: one constant for harvest, retention and export


def retired_indices(lifecycle: list[dict]) -> set[int]:
    """The segments the log records as retired: the log, not a directory, says what's retired."""
    return {e["seg"] for e in lifecycle if e["kind"] == "segment.retired"}


#: A summary still ``pending`` this long after its request lost its worker (killed, machine asleep).
STALE_PENDING_S = 15 * 60
#: Summarizer attempts per segment before it is given up on (harvest stops retrying; export passes it).
MAX_ATTEMPTS = 3


def abandoned_at(lifecycle: list[dict]) -> str | None:
    """When the session was closed as ``abandoned``, if that is how it is closed now."""
    _, closed_at, reason = session_status(lifecycle)
    return closed_at if reason == "abandoned" else None


def summary_verdict(events: list[dict], now: float, *, abandoned_at: str | None = None) -> str | None:
    """Does a final segment's summary need another attempt (``"retry"``), or has it had its last (``"give up"``)?

    The one rule for "settled": harvest retries on ``"retry"`` and moves past
    on ``"give up"``; export passes a ``"give up"`` segment (no item) so one
    summary that will never come can't hold a consumer's cursor for good.

    Only events since the segment's **last seal** count: a re-seal starts a
    fresh budget. Stranded means ``none`` or ``pending`` long past the seal or
    the request (the spawn or the worker died), or a retryable failure; each
    gets another attempt, up to :data:`MAX_ATTEMPTS`. A permanent failure, or
    the last attempt spent, is given up so the session isn't stuck.

    ``abandoned_at`` is when the session was closed as ``abandoned`` (the
    sweep, ``seal``): that close summarizes a segment a PreCompact may have
    sealed long before, spawning the worker just after, before it records its
    request — so the seal's age says nothing. Within :data:`STALE_PENDING_S`
    of such a close the summary is waited for rather than retried, by harvest
    and export alike. (Every other close seals at that moment, and the seal's
    own age already covers it.)
    """
    seals = [n for n, e in enumerate(events) if e["kind"] == "segment.sealed"]
    if not seals:
        return None
    since = events[seals[-1]:]
    summary = [e for e in since if e["kind"].startswith("summary.")]
    requested = {e["data"]["job_id"] for e in summary if e["kind"] == "summary.requested"}
    attempts = len(requested) + sum(e["kind"] == "summary.failed" and e["data"]["job_id"] not in requested
                                    for e in summary)
    last = summary[-1] if summary else since[0]  # the seal itself when nothing followed it
    if last["kind"] in ("summary.completed", "summary.skipped"):
        return None
    if last["kind"] == "summary.failed" and not last["data"]["retryable"]:
        return "give up"
    if last["kind"] in ("segment.sealed", "summary.requested") and now - epoch_of(last["ts"]) < STALE_PENDING_S:
        return None  # a worker may still be on it
    if attempts >= MAX_ATTEMPTS:
        return "give up"
    if abandoned_at and now - epoch_of(abandoned_at) < STALE_PENDING_S:
        return None  # the worker the close spawned may not have recorded its request yet
    return "retry"


SUMMARY_ENV = "CLAUDNA_SESSION_SUMMARY"


def summary_gate(facts: SessionFacts, env) -> str | None:
    """The ``summary.skipped`` reason for a session's segments, or ``None`` to summarize (spec §7.1).

    Phase 2 has one reader of summaries, harvest, so a summary is only paid for
    when something will read it: an interactive session that opted into
    harvest (``CLAUDNA_HARVEST=1`` when it opened), or anywhere
    ``CLAUDNA_SESSION_SUMMARY=1`` asks. Headless ``claude -p`` and Claudlobby
    bots need ``=1``; ``=0`` turns them off everywhere; a private session is
    never summarized.
    """
    if facts.private:
        return "private"
    switch = env.get(SUMMARY_ENV)
    if switch == "0":
        return "disabled"
    if switch == "1":
        return None
    if (facts.actor or {}).get("kind") in ("headless", "bot"):
        return "headless"
    if not (facts.harvest or {}).get("enabled"):
        return "disabled"  # nothing reads summaries yet unless this session opted into harvest (#373, M5)
    return None


def session_facts(lifecycle: list[dict]) -> SessionFacts:
    actor, private, chain_id, claude_pid, harvest = None, False, None, None, None
    for e in lifecycle:
        if e["kind"] == "session.opened":
            actor, chain_id = e["data"]["actor"], chain_id or e["data"]["chain_id"]
            claude_pid, harvest = e["data"].get("claude_pid"), e["data"].get("harvest")
        elif e["kind"] == "session.privacy_set":
            private = e["data"]["private"]
    return SessionFacts(status=session_status(lifecycle)[0], actor=actor, private=private, chain_id=chain_id,
                        claude_pid=claude_pid, harvest=harvest)


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
    for e in lifecycle.events:
        if e["kind"] == "session.child_linked" and e["data"]["child_sid"] not in children:
            children.append(e["data"]["child_sid"])
    private = session_facts(lifecycle.events).private

    retired = retired_indices(lifecycle.events)
    segments = [s for s in segments if s["index"] not in retired]  # the log, not a directory, says what's retired
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
        "segments": {"count": len(segments), "open": max(open_segments) if open_segments else None,
                     "retired": len(retired)},
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
    if kind in _COUNTED:  # .get: a 0.22 projection has no "interrupts" yet
        counts = projected["counts"]
        counts[_COUNTED[kind]] = counts.get(_COUNTED[kind], 0) + 1
    pf = projected["projected_from"]
    projected["projected_from"] = {"lines": pf["lines"] + 1, "bytes": paths.segment(seg).events.stat().st_size,
                                   "skipped": pf["skipped"]}
    atomic_write_json(paths.segment(seg).segment_json, projected)


# ── shared reads for the phase 6 consumers (readers, export, retention, rollup) ──


@dataclass(frozen=True)
class SegmentState:
    """One segment as every consumer judges it: final or not, and where its summary stands.

    ``summary`` is ``done`` only for a valid summary that covers the last seal;
    ``stale`` is a done summary the segment has since outgrown (it was re-sealed),
    and ``unreadable`` a done one whose file is missing or invalid. Otherwise
    it is the lifecycle status (``none``/``pending``/``failed``/``skipped``).
    """

    index: int
    final: bool  #: sealed, and superseded or in a closed session: it can't change any more
    summary: str
    doc: dict | None  #: the summary itself, when ``done``
    sealed_at: str | None


def segment_states(paths: SessionPaths, lifecycle: list[dict]) -> list[SegmentState]:
    """Every existing segment's :class:`SegmentState`, in index order — the one place this rule lives."""
    indices = paths.segment_indices()
    closed = session_status(lifecycle)[0] == "closed"
    buckets = by_segment(lifecycle)
    full = schema.load("segment-summary")
    out = []
    for index in indices:
        boundary = fold_boundary(buckets.get(index, []))
        seal = boundary.last_seal
        status, doc = boundary.summary["status"], None
        if status == "done":
            doc = read_json(paths.segment(index).summary)
            if not isinstance(doc, dict) or schema.validate(doc, full):
                status, doc = "unreadable", None
            elif seal is None or doc["input"]["range"]["end"] != seal["data"]["end"]:
                status, doc = "stale", None
        out.append(SegmentState(index, seal is not None and (closed or index < indices[-1]), status, doc,
                                seal["ts"] if seal else None))
    return out


def _current_session_json(paths: SessionPaths) -> dict | None:
    return read_projection(paths.session_json, SESSION_SCHEMA, bytes_before=file_size(paths.lifecycle))


def segment_docs(paths: SessionPaths, lifecycle: Log, *, trusted: bool | None = None) -> list[dict]:
    """Each segment's ``segment.json``, or the same document folded from its logs when the file can't be trusted.

    A ``segment.json`` folds two logs, but its watermark covers only its
    activity log. :func:`refresh` writes the segments before ``session.json``,
    so a current ``session.json`` vouches for every segment's lifecycle side;
    when it isn't current (``trusted`` False: a lost refresh after a seal or a
    summary event), every segment is folded from its logs.
    """
    trusted = _current_session_json(paths) is not None if trusted is None else trusted
    buckets, transcripts = by_segment(lifecycle.events), segment_transcript_paths(lifecycle.events)
    out = []
    for index in paths.segment_indices():
        doc = read_projection(paths.segment(index).segment_json, SEGMENT_SCHEMA,
                              bytes_before=file_size(paths.segment(index).events)) if trusted else None
        out.append(doc if doc is not None else project_segment(
            paths.sid, index, buckets.get(index, []), load_activity(paths, index), transcript_path=transcripts[index]))
    return out


def session_doc(paths: SessionPaths, lifecycle: Log | None = None) -> dict:
    """``session.json``, or the same document folded from the log when the file can't be trusted. Writes nothing."""
    doc = _current_session_json(paths)
    if doc is not None:
        return doc  # valid and current: it covers every byte of its log (a lost refresh falls through)
    lifecycle = load_lifecycle(paths) if lifecycle is None else lifecycle
    return project_session(paths.sid, lifecycle, segment_docs(paths, lifecycle, trusted=False),
                           transcript_path=transcript_path_of(lifecycle.events))
