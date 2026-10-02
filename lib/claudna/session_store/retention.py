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
from pathlib import Path
from typing import Callable, Mapping

from . import rollup
from .fsio import atomic_write_json, atomic_write_text, ensure_dir, env_number, epoch_of, read_json
from .project import (HARVEST_CONSUMER, SegmentState, harvest_skip, load_lifecycle, retired_indices, segment_states,
                      session_facts, stale_projections)
from .store import SessionHandle, SessionStore

CAP_ENV, FLOOR_ENV = "CLAUDNA_RETAIN_DAYS", "CLAUDNA_RETAIN_ACKED_DAYS"
CAP_DAYS, ACKED_FLOOR_DAYS = 30.0, 7.0
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
    consumers = doc.get("consumers") if isinstance(doc, dict) and isinstance(doc.get("consumers"), dict) else {}
    cursors = {name: c.get("through_seg", 0) if isinstance(c, dict) else 0 for name, c in consumers.items()}
    if harvest_skip(session_facts(lifecycle), lifecycle) is None:
        cursors.setdefault(HARVEST_CONSUMER, 0)
    return min(cursors.values()) if cursors else None


def due(handle: SessionHandle, env: Mapping[str, str], *, now: float | None = None,
        lifecycle: list[dict] | None = None, states: list[SegmentState] | None = None) -> list[tuple[int, str]]:
    """``(index, reason)`` for each segment of ``handle`` that may be retired now, oldest first.

    ``lifecycle``/``states`` let a caller that already folded them share the work.
    """
    if not handle.paths.segment_indices():
        return []  # fully retired (or never opened): one directory listing, no log read
    now = time.time() if now is None else now
    cap = env_number(env, CAP_ENV, CAP_DAYS) * 86400 or float("inf")  # 0 means no age cap: keep until acked
    floor = env_number(env, FLOOR_ENV, ACKED_FLOOR_DAYS) * 86400
    lifecycle = load_lifecycle(handle.paths).events if lifecycle is None else lifecycle
    acked = _acked_through(handle, lifecycle)
    out = []
    for state in segment_states(handle.paths, lifecycle) if states is None else states:
        if not state.final or state.sealed_at is None:
            continue
        age = now - epoch_of(state.sealed_at)
        if age >= cap:
            out.append((state.index, "age"))
        elif age >= floor and acked is not None and acked >= state.index:
            out.append((state.index, "acked"))
    return out


def retire(handle: SessionHandle, batch: list[tuple[int, str]], *,
           deadline: Callable[[], bool] = lambda: False) -> list[tuple[int, str]]:
    """Retire ``batch`` (``(index, reason)`` pairs from :func:`due`) through :meth:`SessionHandle.retire_segment`.

    Every segment's lock is taken first, so no summarizer is writing while the
    summaries are judged: only a current ``done`` summary is archived (a stale
    one would re-enter the rollup), durably and before the session lock is
    taken, so no hook waits on its fsync. A segment a summarizer holds is left
    for a later sweep, and so is the rest of the batch once ``deadline()``
    says the run's time is up. The projections and the rollup are refreshed
    however the batch ends. Returns the pairs this call retired.
    """
    retired: list[tuple[int, str]] = []
    try:
        with contextlib.ExitStack() as stack:
            held = [(index, reason) for index, reason in batch
                    if stack.enter_context(handle.segment_lock(index)) == "taken"]
            if not held:
                return []
            lifecycle = load_lifecycle(handle.paths).events  # after the locks: authoritative for these segments
            states = {s.index: s for s in segment_states(handle.paths, lifecycle)}
            logged = retired_indices(lifecycle)
            for index, reason in held:
                if deadline():
                    break
                state = states.get(index)
                if state is not None and state.summary == "done":  # the summary's only copy after this
                    target = handle.paths.archived_summary(index)
                    ensure_dir(target.parent)
                    atomic_write_json(target, state.doc, durable=True)
                if handle.retire_segment(index, reason, logged=index in logged):
                    retired.append((index, reason))
    finally:
        if retired:
            handle.rebuild()  # first: the segment count must be right even if the rollup can't be written
            rollup.refresh(handle.paths)
    return retired


def _sweep_husks(handle: SessionHandle) -> None:
    """Remove the husk directories a crashed retirement left (outside the segment namespace already)."""
    for husk in handle.paths.husks():
        shutil.rmtree(husk, ignore_errors=True)


@dataclass
class RetentionReport:
    retired: list[str] = field(default_factory=list)  #: "<sid>/seg-NNN (reason)"
    repaired: list[str] = field(default_factory=list)  #: sessions whose unsealed post-close segment was sealed
    upgraded: list[str] = field(default_factory=list)  #: sessions whose older projections were rebuilt
    errors: list[str] = field(default_factory=list)
    budget_spent: bool = False  #: the run stopped on its time budget; the next one resumes where it stopped

    def as_dict(self) -> dict:
        return asdict(self)


def _resume_point(root: Path) -> Path:
    return root / "hooks" / "retention.next"


def sweep(store: SessionStore, env: Mapping[str, str], *, now: float | None = None,
          budget_s: float = TIME_BUDGET_S, clock: Callable[[], float] = time.monotonic) -> RetentionReport:
    """Retire every due segment within ``budget_s`` seconds; one session's failure never stops the rest.

    A time budget, not a count: a bot fleet's backlog drains as fast as the
    disk allows. A run that runs out of time records where it stopped and the
    next one starts there (and wraps around), so no session is starved behind
    the head of the list; running out is a status (``budget_spent``), not an
    error. The caller holds the sweep lock (single-flight, with the unclosed
    sweep). Each session's lifecycle is loaded once and shared by the repair,
    :func:`due` and :func:`retire`'s judgement.
    """
    report, start = RetentionReport(), clock()

    def spent() -> bool:
        return clock() - start > budget_s

    sids = store.session_ids()
    marker = _resume_point(store.root)
    try:
        first = marker.read_text(encoding="utf-8").strip()
    except OSError:
        first = ""
    begin = next((n for n, sid in enumerate(sids) if sid >= first), 0) if first else 0
    stopped_at = None
    for sid in [*sids[begin:], *sids[:begin]]:
        if spent():
            stopped_at = sid
            break
        handle = store.session(sid)
        try:
            _sweep_husks(handle)
            if not handle.paths.segment_indices():
                continue  # fully retired: a directory listing, no log read
            lifecycle = load_lifecycle(handle.paths).events
            if session_facts(lifecycle).status == "closed" and handle.seal_after_close() is not None:
                report.repaired.append(sid)  # a 0.22 leftover, sealed under the lock: fold the log again
                lifecycle = load_lifecycle(handle.paths).events
            if stale_projections(handle.paths):  # written by an earlier release: rewrite once, not re-fold forever
                handle.rebuild()
                report.upgraded.append(sid)
            batch = due(handle, env, now=now, lifecycle=lifecycle)
            report.retired += [f"{sid}/seg-{index:03d} ({reason})"
                               for index, reason in retire(handle, batch, deadline=spent)]
            if spent():  # cut off inside this session's batch: the next run starts here, not after it
                stopped_at = sid
                break
        except Exception as exc:  # noqa: BLE001 — reported, and the sweep goes on
            report.errors.append(f"{sid}: {type(exc).__name__}: {exc}")
    report.budget_spent = stopped_at is not None or spent()
    try:
        if stopped_at is not None:
            atomic_write_text(ensure_dir(marker.parent) / marker.name, stopped_at + "\n")
        else:
            marker.unlink(missing_ok=True)
    except OSError:
        pass  # the next run starts from the top: slower, never wrong
    return report
