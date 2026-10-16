"""Claude Code payload, actor and inherited-session policy."""

from __future__ import annotations

from typing import Mapping

from . import activity, lineage, transcript
from .host import Host, normalize
from .project import SessionFacts

INTERACTIVE_ENTRYPOINTS = ("cli", "claude-vscode", "claude-desktop")


def actor_from_env(env: Mapping[str, str]) -> dict:
    """Who is running this session, from the environment Claude Code and Claudlobby set.

    A Claudlobby bot exports ``BOT_ID`` (and ``BOT_NAME``, ``FLEET_NAME``) in
    its ``bot.conf``. Interactive means an entrypoint a person drives
    (:data:`INTERACTIVE_ENTRYPOINTS`); every other entrypoint — ``sdk-cli``
    for ``claude -p``, a CI action, a chat integration — is headless. No
    entrypoint at all (a direct call) counts as interactive.
    """
    entrypoint = env.get("CLAUDE_CODE_ENTRYPOINT") or None
    if env.get("BOT_ID"):
        kind = "bot"
    elif entrypoint is None or entrypoint in INTERACTIVE_ENTRYPOINTS:
        kind = "interactive"
    else:
        kind = "headless"
    return {
        "kind": kind,
        "fleet": env.get("FLEET_NAME") or env.get("CLAUDLOBBY_FLEET") or None,
        "bot_id": env.get("BOT_ID") or None,
        "bot_name": env.get("BOT_NAME") or None,
        "model": None,
        "entrypoint": entrypoint,
    }


def claude_pid_of(env: Mapping[str, str]) -> int | None:
    """The owning Claude Code process: ``$CLAUDE_PID``, which Claude Code exports to the commands it runs."""
    try:
        pid = int(env.get("CLAUDE_PID") or 0)
    except ValueError:
        return None
    return pid if pid > 0 else None


def inherited(event: str, payload: dict, facts: SessionFacts, env: Mapping[str, str]) -> bool:
    """Is this hook a nested ``claude`` reusing an existing session's id? (spec §11.5)

    A nested child inherits ``CLAUDE_CODE_SESSION_ID`` — and its entrypoint,
    except that a ``cli`` parent's child reports ``sdk-cli`` — so its hooks can
    look like the parent's. Three checks, any one enough, whether the parent is
    still open or already closed (a child can outlive its parent's SessionEnd):

    * **Another Claude Code process.** Claude Code exports ``CLAUDE_PID`` to
      what it runs; a hook whose ``CLAUDE_PID`` differs from the one the
      session recorded belongs to someone else.
    * **A fresh start of an existing session.** ``startup``, ``clear`` and
      ``fork`` each begin a new session id, so one naming a session the store
      already has can only be a child.
    * **Another entrypoint** (the phase 2 check; kept for sessions opened
      before ``claude_pid`` was recorded).

    A ``resume`` is always let through: ``claude --resume`` must reopen the
    session, from whatever process, whether a crash left it open or it closed.
    Claude Code's ``CLAUDE_CODE_CHILD_SESSION=1`` is on every hook and tool
    process, a top-level session's included (Claudlobby#2145 C11), so it is not read.
    """
    if facts.status == "unknown" or (event == "SessionStart" and payload.get("source") == "resume"):
        return False
    pid = claude_pid_of(env)
    if facts.claude_pid and pid and pid != facts.claude_pid:
        return True
    if event == "SessionStart" and payload.get("source") in ("startup", "clear", "fork"):
        return True
    return facts.actor is not None and facts.actor["entrypoint"] != (env.get("CLAUDE_CODE_ENTRYPOINT") or None)



def owner_pid(env: Mapping[str, str]) -> int | None:
    """The exported owner, with the bounded own-ancestry fallback."""
    return claude_pid_of(env) or lineage.claude_pid()


HOST = Host(
    name="claude",
    events={e: e for e in ("SessionStart", "PreCompact", "SessionEnd", *activity.EVENTS)},
    normalize=normalize, owner_pid=owner_pid, actor=actor_from_env, inherited=inherited,
    read_range=transcript.read_range,
)
