"""Skill telemetry for Claudosseum: a projection of ``skill.invoked`` (phase 4).

On by default (``CLAUDNA_TELEMETRY=0`` opts out), every
``claudna:*`` Skill call appends one line to
``<effective clauDNA root>/telemetry/skill-events.jsonl``, in
Claudosseum's ingestion format::

    {"ts", "bot", "type": "skill_invocation", "source": "vitals",
     "data": {"skill_slug", "duration_ms", "success", "session_id"}}

The shape is the one ``telemetry-emit.sh`` always wrote; that hook now just
applies opt-outs and calls ``session_store telemetry``. Three values became
real (owner decision, 2026-09-30): ``success`` comes from the tool response,
not a grep of its output for "error"; ``duration_ms`` is the call's duration,
not ``null``; and ``session_id`` is Claude Code's session id, not the hook
shell's pid. ``ts`` keeps its second-resolution ``Z`` form.

It has its own entry point, apart from the session store's hook, so it works
with ``CLAUDNA_SESSION_STORE=0`` when ``CLAUDNA_TELEMETRY=1`` explicitly asks. The payload is decoded once, by
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
from .fsio import FILE_MODE, append_jsonl, cap_log, ensure_dir, exclusive_lock, read_jsonl, utc_seconds
from .paths import CHILD_ENV, SessionPaths, state_root, validate_sid

ENABLE_ENV = "CLAUDNA_TELEMETRY"
PATH_ENV = "CLAUDNA_TELEMETRY_PATH"
KEEP_DAYS = 30
PREFIX = "claudna:"
#: A real claudna skill slug. Anything else can't be one, and is dropped rather than written.
_SLUG = re.compile(r"^[A-Za-z0-9:_-]+$")


def telemetry_path(env: Mapping[str, str]) -> Path:
    """One writer/report policy: overrides must stay inside the effective root.

    Reject configured legacy destinations instead of silently redirecting their
    consumers. Explicit read-only report inputs are a separate CLI option.
    """
    root = state_root(dict(env))
    configured = env.get(PATH_ENV)
    if not configured:
        return root / "telemetry" / "skill-events.jsonl"
    path = Path(configured)
    resolved, boundary = path.resolve(), root.resolve()
    if not path.is_absolute() or resolved == boundary or not resolved.is_relative_to(boundary):
        raise ValueError("telemetry destination must be absolute and inside the effective clauDNA root")
    return path


def enabled(env: Mapping[str, str]) -> bool:
    """Default on, while preserving store/skill opt-outs and suppressing our own children."""
    if env.get(CHILD_ENV) == "1" or env.get(ENABLE_ENV) == "0" or env.get("CLAUDNA_SKILL_LOG") == "0":
        return False
    return env.get("CLAUDNA_SESSION_STORE") != "0" or env.get(ENABLE_ENV) == "1"


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


def _append_record(record: dict, env: Mapping[str, str]) -> bool:
    path = telemetry_path(env)
    ensure_dir(path.parent)
    append_jsonl(path, record, durable=False)
    return True


def emit(payload: dict, env: Mapping[str, str]) -> bool:
    """Append the line for ``payload`` when telemetry is on and it's a claudna skill; return whether it did."""
    if not enabled(env):
        return False
    record = record_for(payload, env)
    if record is None:
        return False
    sid = record["data"]["session_id"]
    if sid:
        # Read only the existing lifecycle; never create a session for this compatibility projection.
        paths = SessionPaths(state_root(dict(env)), validate_sid(sid))
        if paths.lifecycle.is_file():
            with exclusive_lock(paths.lock, blocking=False) as taken:
                if not taken:
                    return False
                private = False
                for event in read_jsonl(paths.lifecycle).records:
                    if event.get("kind") == "session.privacy_set":
                        private = event.get("data", {}).get("private") is True
                if private:
                    return False
                return _append_record(record, env)
    return _append_record(record, env)


def run_hook(raw: bytes | str, env: Mapping[str, str]) -> str:
    """The ``telemetry`` verb's hook body: never raises (a hook fails open); returns what happened.

    Failures retain fixed file-level codes beside an accepted feed. The shell
    wrapper discards arbitrary interpreter stderr and reports bootstrap codes.
    """
    try:
        if not enabled(env):
            return "ignored"
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if raw.strip() else None
        outcome = "emitted" if isinstance(payload, dict) and emit(payload, env) else "ignored"
        if prune_due(env):  # here, not in the store's sweep: telemetry runs with the store off too
            _marker(env).touch(mode=FILE_MODE)
            prune(env)
        return outcome
    except Exception as exc:  # noqa: BLE001 — telemetry must never break a Skill call
        # File-level diagnostics are global: never keep payload, path, arbitrary
        # exception text or interpreter stderr in the compatibility feed's owner.
        code = "decode" if isinstance(exc, (UnicodeError, json.JSONDecodeError)) else (
            "configuration" if isinstance(exc, ValueError) else
            "io" if isinstance(exc, OSError) else "runtime")
        outcome = f"error: {code}"
        try:
            path = telemetry_path(env)
            ensure_dir(path.parent)
            append_jsonl(cap_log(path.with_name(path.name + ".stderr")), {"code": code, "count": 1}, durable=False)
        except (OSError, ValueError):
            pass  # no valid writable destination: the bounded stderr notice remains
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
