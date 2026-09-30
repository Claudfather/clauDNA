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

Retiring refreshes the session rollup first (so what the segment summarized
survives it), appends ``segment.retired``, then removes the directory. An
index is never reused: ``open_segment`` numbers past every index the log has
named. Private sessions follow the same rules. Runs in the detached sweep,
bounded to :data:`LIMIT` segments per run.
"""

from __future__ import annotations

import calendar
import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import Mapping

from . import rollup
from .fsio import read_json
from .project import by_segment, fold_boundary, load_lifecycle, session_status
from .store import SessionHandle, SessionStore

CAP_ENV, FLOOR_ENV = "CLAUDNA_RETAIN_DAYS", "CLAUDNA_RETAIN_ACKED_DAYS"
CAP_DAYS, ACKED_FLOOR_DAYS = 30.0, 7.0
LIMIT = 50  #: segments retired per sweep run


def _days(env: Mapping[str, str], name: str, default: float) -> float:
    try:
        value = float(env.get(name) or default)
    except ValueError:
        return default
    return value if value == value and value >= 0 else default  # NaN and negatives fall back


def _epoch(ts: str) -> float:
    return calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))


def _acked_by_all(handle: SessionHandle, index: int) -> bool:
    doc = read_json(handle.paths.consumers)
    consumers = doc.get("consumers") if isinstance(doc, dict) else None
    if not isinstance(consumers, dict) or not consumers:
        return False  # no registered consumer: only the age cap applies
    return all(isinstance(c, dict) and isinstance(c.get("through_seg"), int) and c["through_seg"] >= index
               for c in consumers.values())


def due(handle: SessionHandle, env: Mapping[str, str], *, now: float | None = None) -> list[tuple[int, str]]:
    """``(index, reason)`` for each segment of ``handle`` that may be retired now, oldest first."""
    now = time.time() if now is None else now
    cap, floor = _days(env, CAP_ENV, CAP_DAYS) * 86400, _days(env, FLOOR_ENV, ACKED_FLOOR_DAYS) * 86400
    lifecycle = load_lifecycle(handle.paths).events
    closed = session_status(lifecycle)[0] == "closed"
    indices = handle.paths.segment_indices()
    buckets = by_segment(lifecycle)
    out = []
    for index in indices:
        final = closed or index < indices[-1]
        seal = fold_boundary(buckets.get(index, [])).last_seal
        if not final or seal is None:
            continue
        age = now - _epoch(seal["ts"])
        if age >= cap:
            out.append((index, "age"))
        elif age >= floor and _acked_by_all(handle, index):
            out.append((index, "acked"))
    return out


def retire(handle: SessionHandle, index: int, reason: str) -> None:
    """Keep what the segment summarized in the rollup, log the retirement, then remove the directory."""
    rollup.refresh(handle.paths)
    handle.append("segment.retired", {"reason": reason}, seg=index)
    shutil.rmtree(handle.paths.segment(index).dir)
    handle.rebuild()  # session.json's segment count: the append above re-projected with the directory still there


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
            for index, reason in due(handle, env, now=now)[:limit - len(report.retired)]:
                retire(handle, index, reason)
                report.retired.append(f"{sid}/seg-{index:03d} ({reason})")
        except Exception as exc:  # noqa: BLE001 — reported, and the sweep goes on
            report.errors.append(f"{sid}: {type(exc).__name__}: {exc}")
    return report
