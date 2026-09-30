"""Activity (phase 4): what happens inside a segment, from three hook payloads.

One pure function, :func:`event_for`, maps a hook payload to at most one
activity event ``(kind, data)``. The hook adapter (``boundaries.py``) applies
it after the usual guards (a child, a nested ``claude``, no open session).

| Hook | Kind |
|---|---|
| UserPromptSubmit | ``prompt.submitted``: ``prompt_id``, ``chars``; text only with ``CLAUDNA_CAPTURE_PROMPTS=1`` |
| PostToolUse (``Skill``) | ``skill.invoked``: the skill as called, its real ``ok`` and ``duration_ms`` |
| PostToolUseFailure | ``tool.failed``, or ``tool.interrupted`` when the user stopped the call (Esc) |

Tool events point into the transcript (``tool_use_id``) instead of copying
the command or its stderr: the transcript already holds both, and a second
copy would be a second place for a secret to sit. What the store keeps is
what groups and counts them: the tool, the exit code and a **signature**, the
first real error line normalized (paths, numbers, ids and quoted strings
replaced) and redacted, so the same failure groups across sessions.

Canaries (Claude Code 2.1.286, the phase 4 plan): the payload fields used here
are ``prompt``/``prompt_id``; ``tool_name``, ``tool_input``, ``tool_response``,
``tool_use_id``, ``duration_ms``; and ``error`` (first line ``Exit code N`` for
Bash) with ``is_interrupt``.
"""

from __future__ import annotations

import re
from typing import Mapping

CAPTURE_PROMPTS_ENV = "CLAUDNA_CAPTURE_PROMPTS"
EVENTS = ("UserPromptSubmit", "PostToolUse", "PostToolUseFailure")

_EXIT = re.compile(r"^Exit code (-?\d+)\s*$")
#: Normalization, in order: the most specific shapes first, so a UUID isn't read as numbers.
_NORMALIZE = (
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<id>"),
    (re.compile(r"(['\"`])[^'\"`]*\1"), "<str>"),
    (re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I), "<url>"),
    (re.compile(r"[\w.~@+-]*(?:/[\w.~@+-]+)+/?"), "<path>"),  # absolute or relative: any token with a /segment
    (re.compile(r"\b(?:0x)?[0-9a-f]{12,}\b", re.I), "<id>"),
    (re.compile(r"\d+(?:\.\d+)?"), "<n>"),
    (re.compile(r"\s+"), " "),
)


def exit_code(error: str) -> int | None:
    """The exit code a Bash failure's first line reports (``Exit code N``), else ``None``."""
    first = error.split("\n", 1)[0]
    match = _EXIT.match(first)
    return int(match.group(1)) if match else None


def signature(tool: str, error: str) -> str:
    """``tool: <first real error line, normalized and redacted>``: a key that groups one failure.

    The ``Exit code N`` line is skipped (the code is its own field). An empty or
    missing error gives just ``tool``. The registry caps the result at 200.
    """
    from claudna.redact import redact_text

    lines = (line.strip() for line in error.splitlines())
    first = next((line for line in lines if line and not _EXIT.match(line)), "")
    first = redact_text(first)  # before normalizing: a pattern needs the secret's real shape
    for pattern, placeholder in _NORMALIZE:
        first = pattern.sub(placeholder, first)
    first = first.strip()
    return f"{tool}: {first}" if first else tool


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _ms(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _pointers(payload: dict) -> dict:
    """What ties a tool event back to its prompt and its transcript entry."""
    return {"duration_ms": _ms(payload.get("duration_ms")), "prompt_id": _str(payload.get("prompt_id")),
            "tool_use_id": _str(payload.get("tool_use_id"))}


def event_for(hook: str, payload: dict, env: Mapping[str, str]) -> tuple[str, dict] | None:
    """The activity event for one hook payload, or ``None`` when there is nothing to record."""
    if hook == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            return None
        data = {"prompt_id": _str(payload.get("prompt_id")), "chars": len(prompt)}
        if env.get(CAPTURE_PROMPTS_ENV) == "1":
            data["text"] = prompt  # redacted and capped by make_event
        return "prompt.submitted", data
    tool = _str(payload.get("tool_name"))
    if tool is None:
        return None
    if hook == "PostToolUse":
        tool_input = payload.get("tool_input")
        skill = _str(tool_input.get("skill")) if tool == "Skill" and isinstance(tool_input, dict) else None
        if skill is None:
            return None
        args = tool_input.get("args")
        response = payload.get("tool_response")
        ok = response.get("success") if isinstance(response, dict) else None
        return "skill.invoked", {"skill": skill, "args_chars": len(args) if isinstance(args, str) else 0,
                                 "ok": ok if isinstance(ok, bool) else None, **_pointers(payload)}
    if hook == "PostToolUseFailure":
        if payload.get("is_interrupt") is True:
            return "tool.interrupted", {"tool": tool, **_pointers(payload)}
        error = payload.get("error") if isinstance(payload.get("error"), str) else ""
        return "tool.failed", {"tool": tool, "signature": signature(tool, error), "exit_code": exit_code(error),
                               **_pointers(payload)}
    return None
