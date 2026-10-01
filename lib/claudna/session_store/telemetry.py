"""Skill telemetry for Claudosseum: a projection of ``skill.invoked`` (phase 4).

With ``CLAUDNA_TELEMETRY=1`` (Claudlobby sets it for fleet bots), every
``claudna:*`` Skill call appends one line to
``${CLAUDNA_TELEMETRY_PATH:-~/.claude/telemetry/skill-events.jsonl}``, in
Claudosseum's ingestion format::

    {"ts", "bot", "type": "skill_invocation", "source": "vitals",
     "data": {"skill_slug", "duration_ms", "success", "session_id"}}

The shape is the one ``telemetry-emit.sh`` always wrote; that hook now just
gates on the opt-in and calls ``session_store telemetry``. Three values became
real (owner decision, 2026-09-30): ``success`` comes from the tool response,
not a grep of its output for "error"; ``duration_ms`` is the call's duration,
not ``null``; and ``session_id`` is Claude Code's session id, not the hook
shell's pid. ``ts`` keeps its second-resolution ``Z`` form.

It has its own entry point, apart from the session store's hook, so it works
with ``CLAUDNA_SESSION_STORE=0``. The payload is decoded once, by
:func:`activity.skill_call`, the same decoder ``skill.invoked`` uses.
:func:`prune` (30 days) runs at most once a day, from this same async hook, so it works with the store off.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Mapping

from .activity import skill_call
from .fsio import FILE_MODE, append_jsonl, ensure_dir, exclusive_lock, utc_seconds

ENABLE_ENV = "CLAUDNA_TELEMETRY"
PATH_ENV = "CLAUDNA_TELEMETRY_PATH"
KEEP_DAYS = 30
PREFIX = "claudna:"
#: A real claudna skill slug. Anything else can't be one, and is dropped rather than written.
_SLUG = re.compile(r"^[A-Za-z0-9:_-]+$")


def telemetry_path(env: Mapping[str, str]) -> Path:
    return Path(env.get(PATH_ENV) or Path(env.get("HOME") or os.path.expanduser("~")) / ".claude" / "telemetry"
                / "skill-events.jsonl")


def record_for(payload: dict, env: Mapping[str, str], *, now: float | None = None) -> dict | None:
    """The Claudosseum line for one Skill payload, or ``None`` when it isn't a claudna skill.

    A failed Skill call fires PostToolUseFailure, not PostToolUse, and is
    recorded with ``success: false``; a call the user stopped (``is_interrupt``)
    isn't a skill outcome at all, so it writes nothing.
    """
    call = skill_call(payload)
    if call is None or not call["skill"].startswith(PREFIX):
        return None
    failed = payload.get("hook_event_name") == "PostToolUseFailure"
    if failed and payload.get("is_interrupt") is True:
        return None
    slug = call["skill"][len(PREFIX):]
    if not _SLUG.match(slug):
        return None
    session_id = payload.get("session_id")
    return {
        "ts": utc_seconds(now),
        "bot": env.get("BOT_NAME") or "interactive",
        "type": "skill_invocation",
        "source": "vitals",
        "data": {"skill_slug": slug, "duration_ms": call["duration_ms"], "success": False if failed else call["ok"],
                 "session_id": session_id if isinstance(session_id, str) else None},
    }


def emit(payload: dict, env: Mapping[str, str]) -> bool:
    """Append the line for ``payload`` when telemetry is on and it's a claudna skill; return whether it did."""
    if env.get(ENABLE_ENV) != "1":
        return False
    record = record_for(payload, env)
    if record is None:
        return False
    path = telemetry_path(env)
    ensure_dir(path.parent)
    append_jsonl(path, record, durable=False)
    return True


def run_hook(raw: bytes | str, env: Mapping[str, str]) -> str:
    """The ``telemetry`` verb's hook body: never raises (a hook fails open); returns what happened.

    A failure is also printed to stderr, which ``telemetry-emit.sh`` keeps in
    ``<telemetry file>.stderr``: failing open never means failing silently.
    """
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if raw.strip() else None
        outcome = "emitted" if isinstance(payload, dict) and emit(payload, env) else "ignored"
        if prune_due(env):  # here, not in the store's sweep: telemetry runs with the store off too
            _marker(env).touch(mode=FILE_MODE)
            prune(env)
        return outcome
    except Exception as exc:  # noqa: BLE001 — telemetry must never break a Skill call
        outcome = f"error: {type(exc).__name__}: {exc}"
        print(f"session_store telemetry: {outcome}", file=sys.stderr)
        return outcome


PRUNE_EVERY_S = 24 * 3600


def _marker(env: Mapping[str, str]) -> Path:
    path = telemetry_path(env)
    return path.with_name(path.name + ".pruned")


def prune_due(env: Mapping[str, str], *, now: float | None = None) -> bool:
    """A day since the last prune started, and there's a file to prune? Two ``stat`` calls."""
    now = time.time() if now is None else now
    if not telemetry_path(env).is_file():
        return False
    try:
        return now - _marker(env).stat().st_mtime >= PRUNE_EVERY_S
    except OSError:
        return True


def _expired(line: bytes, cutoff: str) -> bool:
    """Is ``line`` a record whose ``ts`` is before ``cutoff``? A line that isn't one is kept."""
    try:
        ts = json.loads(line).get("ts")
    except (ValueError, AttributeError, RecursionError):
        return False
    return isinstance(ts, str) and ts < cutoff


def _append_bytes(path: Path, data: bytes) -> None:
    """Append ``data`` to ``path`` (created ``0600``, even when ``data`` is empty)."""
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, FILE_MODE)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


def prune(env: Mapping[str, str], *, now: float | None = None, keep_days: int = KEEP_DAYS) -> int:
    """Drop lines older than ``keep_days``; return how many. Single-flight.

    Nothing is rewritten unless a line is due. Then the live file is rotated
    aside (``rename`` is atomic: a writer holding it keeps appending to the
    rotated inode) and survivors are appended back, followed by whatever such a
    writer added while they were filtered. Residual window: a writer that opened
    the old file and writes only after that last read loses its one line. A
    prune killed mid-way leaves the rotated file; the next one puts its lines
    back before rotating again, so they are never overwritten. Lines are kept
    byte for byte; one that isn't JSON is kept.
    """
    path = telemetry_path(env)
    rotated = path.with_name(path.name + ".pruning")
    if not path.is_file() and not rotated.is_file():
        return 0
    cutoff = utc_seconds((time.time() if now is None else now) - keep_days * 86400)
    with exclusive_lock(path.with_name(path.name + ".prune.lock"), blocking=False) as taken:
        if not taken:
            return 0
        if rotated.is_file():  # a killed prune stranded its lines there: back first, never overwritten
            stranded = rotated.read_bytes()
            _append_bytes(path, stranded if stranded.endswith(b"\n") or not stranded else stranded + b"\n")
            rotated.unlink()
        if not path.is_file() or not any(_expired(line, cutoff) for line in path.read_bytes().splitlines()):
            return 0
        os.replace(path, rotated)
        raw = rotated.read_bytes()
        whole = raw[: raw.rfind(b"\n") + 1]  # a line still being written is carried over below, untouched
        lines = whole.splitlines()
        kept = [line for line in lines if not _expired(line, cutoff)]
        _append_bytes(path, b"".join(line + b"\n" for line in kept))
        _append_bytes(path, rotated.read_bytes()[len(whole):])  # appended to the rotated inode since
        rotated.unlink()
    return len(lines) - len(kept)
