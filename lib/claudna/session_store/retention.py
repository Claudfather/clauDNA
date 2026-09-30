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
``CLAUDNA_RETAIN_DAYS``).

Retiring a session's due segments is one batch: each ``done`` summary moves to
``sessions/<sid>/summaries/`` (so the rollup keeps what it said), each segment
gets ``segment.retired`` and loses its directory, then the rollup and the
session's projections are refreshed once. An index is never reused:
``open_segment`` numbers past every index the log has named. Private sessions
follow the same rules. Runs in the detached sweep, bounded to :data:`LIMIT`
segments per run.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import Mapping

from . import rollup
from .fsio import ensure_dir, env_number, epoch_of, read_json
from .project import load_lifecycle, segment_states
from .store import SessionHandle, SessionStore

CAP_ENV, FLOOR_ENV = "CLAUDNA_RETAIN_DAYS", "CLAUDNA_RETAIN_ACKED_DAYS"
CAP_DAYS, ACKED_FLOOR_DAYS = 30.0, 7.0
LIMIT = 50  #: segments retired per sweep run


def _acked_through(handle: SessionHandle) -> int | None:
    """The lowest cursor across the session's registered consumers; ``None`` when none is registered."""
    doc = read_json(handle.paths.consumers)
    names = list(doc.get("consumers") or {}) if isinstance(doc, dict) and isinstance(doc.get("consumers"), dict) \
        else []
    return min(handle.cursor(name) for name in names) if names else None


def due(handle: SessionHandle, env: Mapping[str, str], *, now: float | None = None) -> list[tuple[int, str]]:
    """``(index, reason)`` for each segment of ``handle`` that may be retired now, oldest first."""
    if not handle.paths.segment_indices():
        return []  # fully retired (or never opened): one directory listing, no log read
    now = time.time() if now is None else now
    cap = env_number(env, CAP_ENV, CAP_DAYS) * 86400
    floor = env_number(env, FLOOR_ENV, ACKED_FLOOR_DAYS) * 86400
    acked = _acked_through(handle)
    out = []
    for state in segment_states(handle.paths, load_lifecycle(handle.paths).events):
        if not state.final or state.sealed_at is None:
            continue
        age = now - epoch_of(state.sealed_at)
        if age >= cap:
            out.append((state.index, "age"))
        elif age >= floor and acked is not None and acked >= state.index:
            out.append((state.index, "acked"))
    return out


def retire(handle: SessionHandle, batch: list[tuple[int, str]]) -> None:
    """Retire ``batch`` (``(index, reason)`` pairs from :func:`due`): archive, log, remove; refresh once."""
    for index, reason in batch:
        seg = handle.paths.segment(index)
        if seg.summary.is_file():  # the rollup reads a retired segment's summary from the archive
            archived = handle.paths.archived_summary(index)
            ensure_dir(archived.parent)
            os.replace(seg.summary, archived)
        handle.append("segment.retired", {"reason": reason}, seg=index)
        shutil.rmtree(seg.dir)
    if batch:
        rollup.refresh(handle.paths)
        handle.rebuild()  # the directories are the segment count's truth: one re-fold for the whole batch


@dataclass
class RetentionReport:
    retired: list[str] = field(default_factory=list)  #: "<sid>/seg-NNN (reason)"
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def sweep(store: SessionStore, env: Mapping[str, str], *, now: float | None = None,
          limit: int = LIMIT) -> RetentionReport:
    """Retire every due segment, up to ``limit``; one session's failure never stops the rest."""
    report = RetentionReport()
    for sid in store.session_ids():
        if len(report.retired) >= limit:
            break
        handle = store.session(sid)
        try:
            batch = due(handle, env, now=now)[:limit - len(report.retired)]
            retire(handle, batch)
            report.retired += [f"{sid}/seg-{index:03d} ({reason})" for index, reason in batch]
        except Exception as exc:  # noqa: BLE001 — reported, and the sweep goes on
            report.errors.append(f"{sid}: {type(exc).__name__}: {exc}")
    return report
