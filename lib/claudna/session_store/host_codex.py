"""Codex boundary policy from the native 0.162 canary envelopes and own ancestry."""

from __future__ import annotations

from typing import Mapping

from . import lineage, transcript
from .host import Host, normalize
from .project import SessionFacts


def owner_pid(env: Mapping[str, str]) -> int | None:
    """Hooks lack a Codex PID variable: inspect only our bounded ancestor chain."""
    return lineage.claude_pid(matches=lambda name: name.lower() in ("codex", "codexcli"))


def actor_from_env(env: Mapping[str, str]) -> dict:
    """The measured interactive entrypoint; BOT_ID retains fleet actor policy."""
    return {"kind": "bot" if env.get("BOT_ID") else "interactive",
            "fleet": env.get("FLEET_NAME") or env.get("CLAUDLOBBY_FLEET") or None,
            "bot_id": env.get("BOT_ID") or None, "bot_name": env.get("BOT_NAME") or None,
            "model": None, "entrypoint": "codex"}


def inherited(event: str, payload: dict, facts: SessionFacts, env: Mapping[str, str]) -> bool:
    """Resume may take ownership; a different observed owner cannot mutate a parent."""
    if facts.status == "unknown" or (event == "SessionStart" and payload.get("source") == "resume"):
        return False
    pid = owner_pid(env)
    if facts.claude_pid and pid and pid != facts.claude_pid:
        return True
    return event == "SessionStart" and payload.get("source") in ("startup", "clear")


def read_range(path, start, end):
    return transcript.read_range(path, start, end, agent_cli="codex")


HOST = Host(
    name="codex",
    events={e: e for e in ("SessionStart", "PreCompact", "SessionEnd", "UserPromptSubmit", "PostToolUse")},
    normalize=normalize, owner_pid=owner_pid, actor=actor_from_env, inherited=inherited,
    read_range=read_range,
)
