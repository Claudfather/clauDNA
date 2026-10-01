"""The ops log (spec §12 phase 7): one record per background run, in ``<root>/runs/runs.jsonl``.

The store's detached workers (the summarizer, harvest, the sweep) each leave
one line when they finish, success or not::

    {"run_id", "kind": "summarize"|"harvest"|"sweep", "started_at", "duration_ms",
     "outcome", "sessions": [sid, …], "detail": {…}}

so "what has the store been doing, and did it work?" has one answer, across
sessions. Per-session history is the lifecycle log, which already records each
summary job, retirement and close; a run's ``sessions`` list ties the two
together. The log rotates at 1 MiB like the store's other logs (one generation
kept), and a failure to write it never fails the run.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .fsio import append_jsonl, cap_log, ensure_dir, exclusive_lock, read_jsonl, utc_seconds

KINDS = ("summarize", "harvest", "sweep")


def log_path(root: Path) -> Path:
    return root / "runs" / "runs.jsonl"


def record(root: Path, kind: str, *, started: float, outcome: str, sessions: list[str] | None = None,
           detail: dict | None = None) -> dict | None:
    """Append one run record; return it, or ``None`` when the log couldn't be written.

    An I/O failure never fails the run that is being recorded; only an unknown
    ``kind`` (a programming error) raises.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown run kind: {kind!r}")
    rec = {"run_id": os.urandom(16).hex(), "kind": kind, "started_at": utc_seconds(started),
           "duration_ms": max(0, int((time.time() - started) * 1000)), "outcome": outcome[:200],
           "sessions": sorted(set(sessions or [])), "detail": detail or {}}
    try:
        runs_dir = ensure_dir(root / "runs")
        with exclusive_lock(runs_dir / ".lock"):  # rotate and append as one step: two rotations can't race
            append_jsonl(cap_log(runs_dir / "runs.jsonl"), rec, durable=False)
    except OSError:
        return None
    return rec


@contextmanager
def run(root: Path, kind: str) -> Iterator[dict]:
    """Record one run of ``kind`` however it ends: the body fills in ``outcome``, ``sessions`` and ``detail``.

    A body that raises is recorded as ``error: <exception type>`` and the exception propagates.
    """
    started, rec = time.time(), {"outcome": "done", "sessions": [], "detail": {}}
    try:
        yield rec
    except BaseException as exc:
        rec["outcome"] = f"error: {type(exc).__name__}"
        raise
    finally:
        record(root, kind, started=started, outcome=str(rec["outcome"]), sessions=rec["sessions"],
               detail=rec["detail"])


def runs(root: Path, *, kind: str | None = None, since: str | None = None, limit: int = 50) -> list[dict]:
    """Run records, newest first, optionally one kind and on or after ``since`` (an ISO timestamp)."""
    old = log_path(root).with_name("runs.jsonl.old")  # the generation the last rotation kept
    out = [r for r in [*read_jsonl(old).records, *read_jsonl(log_path(root)).records]
           if (kind is None or r.get("kind") == kind) and (since is None or (r.get("started_at") or "") >= since)]
    out.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return out[:limit]
