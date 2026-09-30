"""Unclosed sessions (phase 3 plan §3): a session whose SessionEnd never ran.

A crash, a kill or a closed laptop lid leaves a session ``open``. A later
resume seals the old segment; a session that is never resumed stays open for
good, and its last segment is never summarized or harvested. This module
finds those sessions and closes them as ``abandoned``.

A session is **unclosed** when all three hold:

* it is ``open``;
* its lifecycle log hasn't changed for :data:`DEFAULT_AFTER_H` hours
  (``$CLAUDNA_UNCLOSED_AFTER_H``). Appends are the only writes to that log,
  so its mtime is the last event's time, for the cost of one ``stat``. Only
  boundaries write it, so its transcript must be as idle too;
* the ``claude`` process it recorded at open (``claude_pid``) is gone.

A session that recorded no pid is never swept automatically: an idle live
session and a dead one look the same without it. ``session_store seal <sid>``
still closes it by hand. A reused pid reads as alive, which only delays a
sweep.

:func:`abandon` seals the current segment at the transcript's size
(``sealed_by: "abandoned"``) and closes the session. Summarizing the sealed
segment is the hook adapter's (``boundaries.abandon_session``), since the spawn
lives above this layer; :func:`sweep` takes it as ``close``. It closes
at most :data:`SWEEP_LIMIT` sessions, oldest first. The SessionStart hook
starts it detached, at most once per :data:`SWEEP_INTERVAL_H`, so no hook pays
for a walk over the whole store.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from . import lineage, telemetry
from .fsio import ensure_dir, exclusive_lock, read_json
from .project import load_lifecycle, session_facts, transcript_path_of
from .store import SessionHandle, SessionStore, StoreError

AFTER_ENV = "CLAUDNA_UNCLOSED_AFTER_H"
DEFAULT_AFTER_H = 24.0
SWEEP_INTERVAL_H = 6.0
SWEEP_LIMIT = 5  #: sessions closed per sweep run, oldest first
CLOSE_REASON = "abandoned"


def after_s(env: Mapping[str, str]) -> float:
    """The idle age past which a dead session counts as unclosed, in seconds."""
    try:
        hours = float(env.get(AFTER_ENV) or DEFAULT_AFTER_H)
    except ValueError:
        hours = DEFAULT_AFTER_H
    if not math.isfinite(hours):  # "nan" would pass every idle test; "inf" would never
        hours = DEFAULT_AFTER_H
    return max(hours, 1.0) * 3600  # never under an hour: a slow machine's live session isn't abandoned


def pid_alive(pid: int) -> bool:
    """Is ``pid`` a running process? Anything but "no such process" counts as alive."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:  # EPERM (someone else's process) and the rest: assume alive, never seal a live session
        pass
    return True


def idle_s(handle: SessionHandle, now: float) -> float | None:
    """Seconds since the session's last lifecycle event, from the log's mtime; ``None`` without a log."""
    try:
        return now - handle.paths.lifecycle.stat().st_mtime
    except OSError:
        return None


def unclosed_owner(handle: SessionHandle, env: Mapping[str, str], *, now: float | None = None,
                   alive: Callable[[int], bool] = pid_alive, idle: float | None = None) -> int | None:
    """The dead ``claude`` pid of an unclosed session, or ``None`` when it isn't one (see the module doc).

    Cheapest test first: the log's mtime (``idle``, when the caller already has
    it), then the small ``session.json`` projection's status, and only then the
    log itself. A projection behind a lost refresh can only make this say no.
    The pid is handed to :func:`abandon`, which re-checks it under the lock.
    """
    now = time.time() if now is None else now
    idle = idle_s(handle, now) if idle is None else idle
    if idle is None or idle < after_s(env):
        return None
    projection = read_json(handle.paths.session_json)
    if isinstance(projection, dict) and projection.get("status") != "open":
        return None
    lifecycle = load_lifecycle(handle.paths).events
    facts = session_facts(lifecycle)
    if facts.status != "open" or facts.claude_pid is None:
        return None
    # Only boundaries touch the lifecycle log; a working session writes its transcript every turn.
    transcript = transcript_path_of(lifecycle)
    try:
        if transcript and now - os.stat(transcript).st_mtime < after_s(env):
            return None
    except OSError:
        pass
    return None if alive(facts.claude_pid) else facts.claude_pid


def is_unclosed(handle: SessionHandle, env: Mapping[str, str], **kwargs) -> bool:
    return unclosed_owner(handle, env, **kwargs) is not None


def abandon(handle: SessionHandle, owner_pid: int | None = None) -> int | None:
    """Seal the current segment at its transcript's size and close the session as ``abandoned``.

    Returns the sealed segment's index (``None`` when none was left unsealed),
    for the caller to summarize. Given ``owner_pid`` (the sweep's), a session a
    resume took over since is left open. Raises ``ValueError`` when the session
    isn't open, or no longer belongs to ``owner_pid``.
    """
    try:
        return handle.close_abandoned(owner_pid=owner_pid)
    except StoreError as exc:
        raise ValueError(str(exc)) from exc


def _marker(root: Path) -> Path:
    return root / "hooks" / "unclosed-sweep.last"


def sweep_due(root: Path, *, now: float | None = None) -> bool:
    """Has :data:`SWEEP_INTERVAL_H` passed since the last sweep started? One ``stat``: safe on the hook path."""
    now = time.time() if now is None else now
    try:
        return now - _marker(root).stat().st_mtime >= SWEEP_INTERVAL_H * 3600
    except OSError:
        return True


def mark_swept(root: Path) -> None:
    """Record that a sweep started now, before it is spawned, so concurrent starts don't all spawn one."""
    marker = _marker(root)
    ensure_dir(marker.parent)
    marker.touch(mode=0o600)  # on an existing file, touch() updates the mtime


@dataclass
class SweepReport:
    closed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def sweep(store: SessionStore, env: Mapping[str, str], *,
          close: Callable[[SessionHandle, int], object] = abandon,
          now: float | None = None, alive: Callable[[int], bool] = pid_alive,
          limit: int = SWEEP_LIMIT, dry_run: bool = False) -> SweepReport:
    """Close up to ``limit`` unclosed sessions, oldest first, with ``close``; then drop stale clear links.

    ``close(handle, owner_pid)`` defaults to :func:`abandon`; the CLI passes the
    hook adapter's version, which also summarizes the sealed segment. Single-flight (a held
    lock skips the run). One session's failure is reported and the sweep moves on.
    """
    now = time.time() if now is None else now
    report = SweepReport()
    with exclusive_lock(ensure_dir(store.root / "hooks") / ".sweep.lock", blocking=False) as taken:
        if not taken:
            return report
        threshold = after_s(env)
        handles = (store.session(sid) for sid in store.session_ids())
        aged = sorted(((idle, h.sid, h) for h in handles
                       if (idle := idle_s(h, now)) is not None and idle >= threshold), reverse=True)
        for idle, sid, handle in aged:  # the longest idle first
            try:
                owner = unclosed_owner(handle, env, now=now, alive=alive, idle=idle)
                if owner is None:
                    continue
                if not dry_run:
                    close(handle, owner)
                report.closed.append(sid)  # only once it is closed: a failure is reported in errors alone
            except Exception as exc:  # noqa: BLE001 — one bad session never stops the sweep
                report.errors.append(f"{sid}: {type(exc).__name__}: {exc}")
            if len(report.closed) == limit:
                break
        if not dry_run:
            lineage.sweep_links(store.root)  # off the hook path; take_link enforces the TTL anyway
            try:
                telemetry.prune(env)  # the Claudosseum file's 30-day window, also off the hook path
            except OSError as exc:
                report.errors.append(f"telemetry prune: {exc}")
    return report
