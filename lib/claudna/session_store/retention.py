"""Retention (spec §9, phase 6): retire a segment's directory once it's no longer needed.

A **final** segment (sealed, and either superseded or in a closed session) is
retired when:

* every **registered consumer** (anyone who has ever acked the session in
  ``consumers.json``: harvest, an ``export --ack`` caller) has acked it, and it
  was sealed at least :data:`ACKED_FLOOR_DAYS` ago; or
* it was sealed more than :data:`CAP_DAYS` ago, whatever was acked.

The floor is a deliberate addition to §9, which retires an acked segment at
once. Without it, a harvested segment would vanish right after harvest and
take ``timeline``/``show`` with it, so recent history is kept a week
regardless. Both are configurable (``CLAUDNA_RETAIN_ACKED_DAYS``,
``CLAUDNA_RETAIN_DAYS``); a cap of ``0`` means no age cap, never "retire at once".

Retiring a session's due segments is one batch: each ``done`` summary moves to
``sessions/<sid>/summaries/`` (so the rollup keeps what it said), each segment
gets ``segment.retired`` and loses its directory, then the rollup and the
session's projections are refreshed once. An index is never reused:
``open_segment`` numbers past every index the log has named. Private sessions
follow the same rules. Runs in the detached sweep, bounded by :data:`TIME_BUDGET_S`
of wall time per run.
"""

from __future__ import annotations

import contextlib
import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Mapping

from . import rollup
from .fsio import env_number, epoch_of, file_size, read_json
from .project import harvest_skip, load_lifecycle, segment_states, session_facts, transcript_path_of
from .store import SessionHandle, SessionStore

CAP_ENV, FLOOR_ENV = "CLAUDNA_RETAIN_DAYS", "CLAUDNA_RETAIN_ACKED_DAYS"
CAP_DAYS, ACKED_FLOOR_DAYS = 30.0, 7.0
HARVEST_CONSUMER = "harvest"  #: harvest's cursor name (harvest.CONSUMER; harvest sits a layer above)
TIME_BUDGET_S = 20.0  #: wall time one sweep run spends retiring; the rest waits for the next run


def _acked_through(handle: SessionHandle, lifecycle: list[dict]) -> int | None:
    """The lowest cursor across the session's registered consumers; ``None`` when none is registered.

    A consumer registers by acking, except harvest: a session that opted in
    (and that harvest takes) registers it from the start, at cursor 0, so a
    stalled harvest holds acked retirement instead of losing segments to
    another consumer's acks (owner decision, #387 review Q1). The age cap
    still bounds it.
    """
    doc = read_json(handle.paths.consumers)
    names = set(doc.get("consumers") or {}) if isinstance(doc, dict) and isinstance(doc.get("consumers"), dict) \
        else set()
    if harvest_skip(session_facts(lifecycle), lifecycle) is None:
        names.add(HARVEST_CONSUMER)
    return min(handle.cursor(name) for name in names) if names else None


def due(handle: SessionHandle, env: Mapping[str, str], *, now: float | None = None) -> list[tuple[int, str]]:
    """``(index, reason)`` for each segment of ``handle`` that may be retired now, oldest first."""
    if not handle.paths.segment_indices():
        return []  # fully retired (or never opened): one directory listing, no log read
    now = time.time() if now is None else now
    cap = env_number(env, CAP_ENV, CAP_DAYS) * 86400 or float("inf")  # 0 means no age cap: keep until acked
    floor = env_number(env, FLOOR_ENV, ACKED_FLOOR_DAYS) * 86400
    lifecycle = load_lifecycle(handle.paths).events
    acked = _acked_through(handle, lifecycle)
    out = []
    for state in segment_states(handle.paths, lifecycle):
        if not state.final or state.sealed_at is None:
            continue
        age = now - epoch_of(state.sealed_at)
        if age >= cap:
            out.append((state.index, "age"))
        elif age >= floor and acked is not None and acked >= state.index:
            out.append((state.index, "acked"))
    return out


def retire(handle: SessionHandle, batch: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Retire ``batch`` (``(index, reason)`` pairs from :func:`due`) through :meth:`SessionHandle.retire_segment`.

    Every segment's lock is taken first, so no summarizer is writing while the
    summaries are judged: only a current ``done`` summary is archived (a stale
    one would re-enter the rollup). A segment a summarizer holds is left for a
    later sweep. The projections and the rollup are refreshed however the batch
    ends. Returns the pairs this call retired.
    """
    retired: list[tuple[int, str]] = []
    try:
        with contextlib.ExitStack() as stack:
            held = [(index, reason) for index, reason in batch
                    if stack.enter_context(handle.segment_lock(index)) == "taken"]
            if not held:
                return []
            states = {s.index: s for s in segment_states(handle.paths, load_lifecycle(handle.paths).events)}
            for index, reason in held:
                state = states.get(index)
                doc = state.doc if state is not None and state.summary == "done" else None
                if handle.retire_segment(index, reason, archive=doc):
                    retired.append((index, reason))
    finally:
        if retired:
            handle.rebuild()  # first: the segment count must be right even if the rollup can't be written
            rollup.refresh(handle.paths)
    return retired


def _sweep_husks(handle: SessionHandle) -> None:
    """Remove ``.retired-*`` directories a crashed retirement left (outside the segment namespace already)."""
    for husk in handle.paths.dir.glob(".retired-seg-*"):
        shutil.rmtree(husk, ignore_errors=True)


@dataclass
class RetentionReport:
    retired: list[str] = field(default_factory=list)  #: "<sid>/seg-NNN (reason)"
    repaired: list[str] = field(default_factory=list)  #: sessions whose unsealed post-close segment was sealed
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _repair_unsealed_close(handle: SessionHandle) -> bool:
    """Seal, as ``abandoned``, a closed session's last segment left unsealed (0.22 could open one after a close).

    Such a segment is never final, so it would never be summarized, exported or
    retired. A one-time repair, idempotent: the seal is the transcript's size,
    never before the segment's own start.
    """
    lifecycle = load_lifecycle(handle.paths).events
    if session_facts(lifecycle).status != "closed":
        return False
    index = handle.current_segment()
    if index is None or handle.boundary(index, lifecycle).sealed:
        return False
    handle.seal_segment(file_size(transcript_path_of(lifecycle)), "abandoned", index=index, clamp=True)
    return True


def sweep(store: SessionStore, env: Mapping[str, str], *, now: float | None = None,
          budget_s: float = TIME_BUDGET_S, clock: Callable[[], float] = time.monotonic) -> RetentionReport:
    """Retire every due segment within ``budget_s`` seconds; one session's failure never stops the rest.

    A time budget, not a count: a bot fleet's backlog drains as fast as the
    disk allows, and a run that stops early resumes on the next sweep. The
    caller holds the sweep lock (single-flight, with the unclosed sweep).
    """
    report, start = RetentionReport(), clock()
    for sid in store.session_ids():
        if clock() - start > budget_s:
            report.errors.append(f"time budget ({budget_s:g}s) spent: the rest waits for the next sweep")
            break
        handle = store.session(sid)
        try:
            _sweep_husks(handle)
            if _repair_unsealed_close(handle):
                report.repaired.append(sid)
            batch = due(handle, env, now=now)
            report.retired += [f"{sid}/seg-{index:03d} ({reason})" for index, reason in retire(handle, batch)]
        except Exception as exc:  # noqa: BLE001 — reported, and the sweep goes on
            report.errors.append(f"{sid}: {type(exc).__name__}: {exc}")
    return report
