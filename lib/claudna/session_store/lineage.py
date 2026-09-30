"""Clear lineage (spec §4.3): which session a ``/clear`` came from.

Claude Code gives a ``/clear`` a new session id and names neither side in the
hook payloads. The one thing both sides share is the ``claude`` process
(canary, 2026-09-30: its pid is the same before and after ``/clear``). So
SessionEnd(``clear``) leaves a **link** under ``<root>/links/<claude-pid>.json``,
and the SessionStart(``clear``) that follows from the same process consumes it.

A link is used once, only within :data:`LINK_TTL_S`, and never for the session
that wrote it. No link means no lineage: it is never guessed.

The pid is ``$CLAUDE_PID``, which Claude Code exports to its hooks (the same
value ``session.opened`` records for the nested-child guard). :func:`claude_pid`,
the ancestor walk, is only the fallback for a Claude Code that doesn't export it.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from .fsio import atomic_write_json, ensure_dir, read_json

LINK_SCHEMA = "claudna.clear-link/1"
LINK_TTL_S = 60
_MAX_HOPS = 6


def _parent(pid: int) -> tuple[int, str] | None:
    """``(ppid, name)`` of ``pid``: ``/proc`` on Linux, one ``ps`` call elsewhere."""
    try:
        with open(f"/proc/{pid}/stat") as fh:
            stat = fh.read()
        name = stat[stat.index("(") + 1:stat.rindex(")")]
        return int(stat[stat.rindex(")") + 2:].split()[1]), name
    except (OSError, ValueError):
        pass
    if sys.platform.startswith("linux"):
        return None
    import subprocess

    try:
        out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=1).stdout.split(None, 1)
        return int(out[0]), os.path.basename(out[1].strip())
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def claude_pid(start: int | None = None) -> int | None:
    """The pid of the ``claude`` process this hook runs under, or ``None``.

    Walks up from ``start`` (default: this process's parent) through at most a
    few ancestors — the hook wrapper, then Claude Code's per-hook shell — to
    the first one whose name contains ``claude``.
    """
    pid = os.getppid() if start is None else start
    for _ in range(_MAX_HOPS):
        found = _parent(pid)
        if found is None:
            return None
        ppid, name = found
        if "claude" in name:
            return pid
        if ppid <= 1:
            return None
        pid = ppid
    return None


def _link_path(root: Path, pid: int) -> Path:
    return root / "links" / f"{pid}.json"


def write_link(root: Path, pid: int, *, sid: str, chain_id: str) -> None:
    """Leave the link a following SessionStart(``clear``) from the same process consumes."""
    ensure_dir(root / "links")
    atomic_write_json(_link_path(root, pid),
                      {"schema": LINK_SCHEMA, "pid": pid, "sid": sid, "chain_id": chain_id, "ts": time.time()})


def take_link(root: Path, pid: int, *, sid: str, now: float | None = None) -> dict | None:
    """Consume the link for ``pid``: its ``{sid, chain_id}`` if fresh and another session's, else ``None``."""
    path = _link_path(root, pid)
    link = read_json(path)
    try:
        path.unlink()
    except OSError:
        pass
    now = time.time() if now is None else now
    if not isinstance(link, dict) or link.get("schema") != LINK_SCHEMA or link.get("sid") == sid:
        return None
    if not isinstance(link.get("ts"), (int, float)) or now - link["ts"] > LINK_TTL_S:
        return None
    return {"sid": link["sid"], "chain_id": link.get("chain_id") or link["sid"]}


def sweep_links(root: Path, now: float | None = None) -> int:
    """Delete links past their TTL (a crashed or never-restarted ``claude``); return how many."""
    now = time.time() if now is None else now
    removed = 0
    links = root / "links"
    for path in links.glob("*.json") if links.is_dir() else []:
        try:
            if now - path.stat().st_mtime > LINK_TTL_S:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
