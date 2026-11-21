"""The permissions hook prints its decision as JSON that parses, whatever its reason holds.

approve() and deny() in plugin-hooks/pretooluse-permissions.sh escape the reason they print for JSON:
each backslash, double quote and control character. The ``$'...'`` refusal's reason holds a backslash,
so each command that refusal denies in tests/test_gh_guard_dollar_quotes.py runs through the hook here,
under a narrow grant and a bare one, and the hook's output is parsed as JSON. So does the guard's
reason for a git command that writes its output to a file when the command's verb is spelled with a
``$'...'`` escape, and two such commands run through the hook the same way. A stand-in guard, and
approve() and deny() themselves, print stand-in reasons that hold a double quote, a backslash and
control characters. Each test of such a reason fails without the escape; the last one checks that the
hook's own reasons print as before.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
HOOK = _ROOT / "plugin-hooks" / "pretooluse-permissions.sh"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load("gh_guard_decide", _ROOT / "plugin-hooks" / "gh-guard-decide.py")
_cases = _load("gh_guard_dollar_quotes_cases", _ROOT / "tests" / "test_gh_guard_dollar_quotes.py")

# each command the $'...' refusal denies in tests/test_gh_guard_dollar_quotes.py
REFUSED = [_cases.JQ_CALL, "echo $'\\c\\\\'"] + [
    f"gh pr list --json title --jq $'.title{body}'" for body in _cases.UNREADABLE
]
# git writing its output to a file, its verb spelled with a $'...' escape: the guard's reason holds the
# verb as the guard reads it, with its backslash
GIT_OUTPUT = ["git $'l\\x6fg' --output=FILE", "git $'form\\x61t-patch' -o DIR"]
GRANTS = pytest.mark.parametrize("allow", [_cases.NARROW, ["Bash"]], ids=["narrow", "bare"])
# a double quote, a backslash and a control character between words; then every control character
# JSON escapes (0x01 to 0x1f: a NUL cannot reach the hook's text), a double quote and a backslash
STAND_INS = pytest.mark.parametrize(
    "reason",
    [
        'a "quoted" word, a \\ backslash and a \x01 control character',
        "".join(chr(code) for code in range(1, 32)) + '"\\',
    ],
    ids=["words", "controls"],
)


def _output(tmp_path: Path, cmd: str, allow: list[str], hook: Path = HOOK) -> dict:
    """The hook's output for a Bash call of ``cmd`` under the ``allow`` grant, parsed as JSON."""
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"allow": allow}}))
    p = subprocess.run(
        ["bash", str(hook)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        timeout=60,
    )
    assert p.returncode == 0, p.stderr[-500:]
    return json.loads(p.stdout)


def _denied(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


@GRANTS
@pytest.mark.parametrize("cmd", REFUSED)
def test_the_hook_prints_json_for_each_command_the_dollar_quote_refusal_denies(tmp_path, cmd, allow):
    verdict, reason = mod.decide(cmd)
    assert verdict == "deny" and "\\c" in reason
    assert _output(tmp_path, cmd, allow) == _denied(reason)


@GRANTS
@pytest.mark.parametrize("cmd", GIT_OUTPUT, ids=["output", "dash-o"])
def test_the_hook_prints_json_for_the_git_output_deny_of_a_dollar_quoted_verb(tmp_path, cmd, allow):
    verdict, reason = mod.decide(cmd)
    assert verdict == "deny" and "writes its output to a file" in reason and "\\" in reason
    assert _output(tmp_path, cmd, allow) == _denied(reason)


@GRANTS
@STAND_INS
def test_the_hook_prints_json_for_a_stand_in_guard_reason(tmp_path, allow, reason):
    hooks = tmp_path / "plugin-hooks"
    shutil.copytree(HOOK.parent, hooks)
    # a stand-in guard that denies every command it reads, with ``reason``
    (hooks / "gh-guard-decide.py").write_text(f"import sys\nsys.stdout.write({reason!r})\nsys.exit(10)\n")
    assert _output(tmp_path, "gh pr list --json title --jq .title", allow, hooks / HOOK.name) == _denied(reason)


# the hook's helpers, log() through deny() and any helper between them, as the hook defines them
_HELPERS = re.search(r"^log\(\) \{$.*?(?=^HOOK_DIR=)", HOOK.read_text(), re.M | re.S).group(0)


@STAND_INS
@pytest.mark.parametrize(
    "name,decision,key", [("approve", "allow", "reason"), ("deny", "deny", "permissionDecisionReason")]
)
def test_approve_and_deny_print_json_for_a_stand_in_reason(name, decision, key, reason):
    p = subprocess.run(
        ["bash", "-c", 'set -eo pipefail\nLOG_DIR=""\nCOMMAND=x\n' + _HELPERS + f'\n{name} "$R"\n'],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "R": reason},
        timeout=20,
    )
    assert p.returncode == 0, p.stderr[-500:]
    assert json.loads(p.stdout) == {
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, key: reason}
    }


@pytest.mark.parametrize(
    "cmd,allow,decision,key,reason",
    [
        ("ls", ["Bash"], "allow", "reason", "bare Bash in allow list"),
        (
            "gh pr list --json title --jq env.X",
            ["Bash"],
            "deny",
            "permissionDecisionReason",
            "gh --jq/--template reads the process environment",
        ),
    ],
    ids=["allow", "deny"],
)
def test_the_hook_prints_its_own_reasons_as_before(tmp_path, cmd, allow, decision, key, reason):
    assert _output(tmp_path, cmd, allow) == {
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, key: reason}
    }
