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
:func:`prune` (30 days) runs in the detached sweep worker, never on the hook path.
"""

from __future__ import annotations

import json
import os
import re
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
    """The Claudosseum line for one PostToolUse(Skill) payload, or ``None`` when it isn't a claudna skill."""
    call = skill_call(payload)
    if call is None or not call["skill"].startswith(PREFIX):
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
        "data": {"skill_slug": slug, "duration_ms": call["duration_ms"], "success": call["ok"],
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
    """The ``telemetry`` verb's hook body: never raises (a hook fails open); returns what happened."""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if raw.strip() else None
        return "emitted" if isinstance(payload, dict) and emit(payload, env) else "ignored"
    except Exception as exc:  # noqa: BLE001 — telemetry must never break a Skill call
        return f"error: {type(exc).__name__}: {exc}"


def prune(env: Mapping[str, str], *, now: float | None = None, keep_days: int = KEEP_DAYS) -> int:
    """Drop lines older than ``keep_days``; return how many. Single-flight; never loses a concurrent append.

    The live file is rotated aside (``rename`` is atomic: a writer holding it
    keeps appending to the rotated inode, which is read after), and survivors
    are appended back. A line that isn't JSON is kept.
    """
    path = telemetry_path(env)
    if not path.is_file():
        return 0
    cutoff = utc_seconds((time.time() if now is None else now) - keep_days * 86400)
    rotated = path.with_name(path.name + ".pruning")
    with exclusive_lock(path.with_name(path.name + ".prune.lock"), blocking=False) as taken:
        if not taken:
            return 0
        os.replace(path, rotated)
        kept, dropped = [], 0
        for line in rotated.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ts = json.loads(line).get("ts")
            except (ValueError, AttributeError):
                ts = None
            if isinstance(ts, str) and ts < cutoff:
                dropped += 1
            else:
                kept.append(line)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, FILE_MODE)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.writelines(line + "\n" for line in kept)
        rotated.unlink()
    return dropped
