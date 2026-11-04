"""Codex boundary policy from the native 0.162 canary envelopes and own ancestry."""

from __future__ import annotations

from typing import Mapping

from . import lineage, transcript
from .host import Host, normalize
from .project import SessionFacts


def record_skill_start(skill: str, env: Mapping[str, str], root=None) -> str:
    """Record an agent's explicit entry into a selected skill, not a native Skill callback.

    Codex's read-and-execute workflow has no measured Skill tool callback. This
    entry is called by the shared installed procedure, never inferred from a
    mention or file read. Arguments, prompts and outcomes are not collected.
    """
    import json
    import uuid
    from pathlib import Path

    from .store import SessionStore
    from .paths import state_root

    if (env.get("CLAUDNA_SESSION_STORE") == "0" or env.get("CLAUDNA_SKILL_LOG") == "0"
            or env.get("CLAUDNA_SESSION_CHILD") == "1"):
        return "ignored: disabled"
    sid = env.get("CODEX_THREAD_ID") or env.get("CODEX_SESSION_ID")
    if not sid or (env.get("CODEX_SESSION_ID") and env.get("CODEX_SESSION_ID") != sid):
        return "ignored: missing or conflicting native session identity"
    plugin = Path(__file__).resolve().parents[3]
    manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
    selected = {Path(p).name for p in manifest["skills"]}
    slug = skill.removeprefix("claudna:")
    if slug not in selected:
        return "ignored: skill not selected for codex"
    return SessionStore(root if root is not None else state_root(env)).session(sid).record_skill_start({
        "skill": "claudna:" + slug, "args_chars": None, "ok": None,
        "duration_ms": None, "prompt_id": None, "tool_use_id": None,
        "observation": "agent_procedure_start", "plugin_version": manifest.get("version"),
        "invocation_id": str(uuid.uuid4()),
    })


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
