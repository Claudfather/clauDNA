"""The gh read-guard reads ``$'...'`` and ``$"..."`` strings the way bash does.

bash drops the ``$`` of a ``$'...'`` or ``$"..."`` string, decodes a ``$'...'`` string's backslash
escapes, and joins the value to the text around it, so such a string can spell ``gh`` or one of its
flags. The decider also reads each command with every such string written as the value bash gives it,
and the hook sends a command that holds one to the decider. Each command below is first run by bash
with a stand-in ``gh`` and ``git`` that record their words, so each case is what the shell does. Fake
values only.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "gh_guard_decide", _ROOT / "plugin-hooks" / "gh-guard-decide.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
HOOK = _ROOT / "plugin-hooks" / "pretooluse-permissions.sh"

# bash runs a gh call that reads the environment, or a git call with --output, in each of these
RUNS_THE_CALL = [
    "$''gh pr list --jq env.X",
    "$'gh' pr list --jq env.X",
    '$"gh" pr list --jq env.X',
    '$""gh pr list --jq env.X',
    "g$''h pr list --jq env.X",
    "command $'gh' pr list --jq env.X",
    "echo x; $'gh' pr list --jq env.X",
    "gh pr list $'--jq' env.X",
    'gh pr list $"--jq" env.X',
    "gh pr list --$'jq' env.X",
    # moved from tests/test_gh_guard_v4_additions.py: the decider reads these strings too
    "gh pr list --json number $'--jq' env.X",
    'gh pr list --json number $"--jq" env.X',
    "env gh pr list --json number $'--jq' env.X",
    # escapes, decoded as bash decodes them
    "$'\\x67h' pr list --jq env.X",
    "$'\\147\\150' pr list --jq env.X",
    "gh pr list $'-\\u002dj\\x71' env.X",
    # a $'...' string that holds an escaped quote and a #, before the call or as an assignment's value
    "echo $'it\\'s #x'; gh pr list --jq env.X; echo \\'",
    "echo $'it\\'s #x'; gh pr list --jq env.X; echo a\\'b",
    "x=$'it\\'s #x' gh pr list --jq env.X",
    # \c before a character from U+0800 to U+0FFF ends the value; a \U of 0x80000000 or more gives nothing
    "$'gh\\c\u0801junk' pr list --jq env.X",
    "gh pr list $'--jq\\c\u0801x' env.X",
    "$'g\\UFFFFFFFFh' pr list --jq env.X",
    "g$'\\UFFFFFFFF'h pr list --jq env.X",
    "gh pr list $'--j\\U80000000q' env.X",
    # a continuation between the $ and the quote: bash joins the lines first, so the string still opens
    "$\\\n'gh' pr list --jq env.X",
    "gh pr list $\\\n'--jq' env.X",
    '$\\\n"gh" pr list --jq env.X',
    'gh pr list $\\\n"--jq" env.X',
    "$\\\n'\\x67h' pr list --jq env.X",
    "gh pr list $\\\n'--\\x6aq' env.X",
    # \x{...}: any number of hex digits, cut to one byte, the brace optional; no digit gives a NUL
    "$'\\x{67}h' pr list --jq env.X",
    "gh pr list $'--\\x{6a}q' env.X",
    "$'gh\\x{junk' pr list --jq env.X",
    "git log -1 $'\\x{2d}\\x{2d}output=out.txt'",
    # an apostrophe in a heredoc body opens no string
    "cat <<EOF\nit's\nEOF\n$'gh' pr list --jq env.X",
    # $$ is the shell's process id, so the quote after it opens a plain string, where a backslash is literal
    "echo $$'a\\'; $'gh' pr list --jq env.X; echo 'x'",
]

# bash runs no gh call that reads the environment in any of these
STAYS_ALLOWED = [
    "gh pr view 1 --json title --jq $'.title'",
    'gh pr view 1 --json title --jq $".title"',
    "echo $'gh pr list --jq env.X'",  # one word: echo's argument
    "printf $'%s\\n' ok",
    "echo $'it\\'s'; gh pr view 1 --json title",
]


def _shell_calls(tmp_path: Path, cmd: str) -> list[list[str]]:
    """The word lists bash hands a stand-in ``gh`` or ``git`` when it runs ``cmd``, each led by its name."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp_path / "gh-words"
    log.write_text("")
    for name in ("gh", "git"):
        stub = bindir / name
        stub.write_text(
            f'#!/bin/sh\nfor w in {name} "$@"; do printf "%s\\037" "$w"; done >> "$GH_WORDS"\n'
            'printf "\\036" >> "$GH_WORDS"\n'
        )
        stub.chmod(0o755)
    subprocess.run(
        ["bash", "-c", cmd],
        env={"PATH": f"{bindir}:/usr/bin:/bin", "GH_WORDS": str(log), "HOME": str(tmp_path)},
        cwd=tmp_path,
        capture_output=True,
        timeout=20,
    )
    return [call.split("\x1f")[:-1] for call in log.read_text().split("\x1e")[:-1]]


def _runs_the_call(words: list[str]) -> bool:
    """A gh call that reads the environment, or a git call with --output."""
    if words[:1] == ["git"]:
        return any(w.startswith("--output") for w in words[1:])
    return any(
        w in ("--jq", "-q") and i + 1 < len(words) and words[i + 1] == "env.X"
        for i, w in enumerate(words)
    )


@pytest.mark.parametrize("cmd", RUNS_THE_CALL)
def test_bash_runs_the_call_in_each_of_these(tmp_path, cmd):
    assert any(_runs_the_call(words) for words in _shell_calls(tmp_path, cmd)), repr(cmd)


@pytest.mark.parametrize("cmd", STAYS_ALLOWED)
def test_bash_runs_no_such_call_in_these(tmp_path, cmd):
    assert not any(_runs_the_call(words) for words in _shell_calls(tmp_path, cmd)), repr(cmd)


@pytest.mark.parametrize("cmd", RUNS_THE_CALL)
def test_the_decider_reads_the_strings_as_bash_does(cmd):
    assert mod.decide(cmd)[0] == "deny", repr(cmd)


@pytest.mark.parametrize("cmd", STAYS_ALLOWED)
def test_ordinary_strings_stay_allowed(cmd):
    assert mod.decide(cmd)[0] == "allow", repr(cmd)


def _hook(tmp_path: Path, cmd: str, allow: list[str]) -> str:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": allow}})
    )
    p = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        timeout=20,
    )
    return (
        "deny"
        if '"permissionDecision":"deny"' in p.stdout
        else "allow"
        if '"permissionDecision":"allow"' in p.stdout
        else "prompt"
    )


NARROW = ["Bash(gh *)", "Bash(echo *)", "Bash(command *)"]


@pytest.mark.parametrize("allow", [NARROW, ["Bash"]], ids=["narrow", "bare"])
@pytest.mark.parametrize("cmd", RUNS_THE_CALL)
def test_the_hook_denies_each_under_a_narrow_and_a_bare_grant(tmp_path, cmd, allow):
    assert _hook(tmp_path, cmd, allow) == "deny", (allow, repr(cmd))


@pytest.mark.parametrize("cmd", STAYS_ALLOWED)
def test_the_hook_still_approves_these_under_a_bare_grant(tmp_path, cmd):
    assert _hook(tmp_path, cmd, ["Bash"]) == "allow", repr(cmd)


# Bodies of $'...' strings whose value is ASCII, so bash's bytes compare one for one
DECODES = [
    "\\x67h", "\\147\\150", "\\u0068", "\\U00000067", "\\cA", "\\ca", "\\c?", "\\e", "\\E", "\\'", '\\"',
    "\\?", "\\q", "\\x", "\\xZ", "\\u", "\\c", "a\\0b", "\\1234", "\\x6g", "\\t\\n\\\\",
    "gh\\c\u0801junk", "g\\UFFFFFFFFh",
    "\\x{67}h", "gh\\x{junk", "\\x{41", "\\x{}",
]


@pytest.mark.parametrize("body", DECODES)
def test_the_decoder_gives_what_bash_gives(body):
    p = subprocess.run(
        ["bash", "-c", f"printf %s $'{body}'"],
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        timeout=20,
    )
    assert mod._ansi_c_value(body).encode() == p.stdout, repr(body)
