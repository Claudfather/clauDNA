"""The gh read-guard reads a command's lines the way bash ends them.

bash pairs backslashes from the left, so a backslash continues its line only when no backslash in
front of it escapes it, and a backslash in front of a carriage return escapes that character. A
comment runs to the newline that ends it, a backslash at its end or not. A quoted string that runs
across lines is text up to its closing quote, ``#`` and all, and so is a ``$'...'`` string that
holds an escaped quote on one line. The decider reads each line that way, and the hook's trigger
pairs backslashes the same way before it joins lines. Each command below is
first run by bash with a stand-in ``gh`` that records its words, so each case is what the shell
does. Fake values only.
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

G = "gh pr view 1 --jq env.X"

# bash runs a gh call that reads the environment in each of these
RUNS_THE_CALL = [
    f"echo \\\\\n{G}",  # a line that ends in an escaped backslash ends its command
    f"echo \\\\\\\\\n{G}",  # two escaped backslashes
    f"true \\\\\n{G}",
    f"echo ok \\\\\n{G}",
    "echo \\\\\ngh pr view 1 \\\n--jq env.X",  # the call after it continues onto its next line
    f"# a note \\\n{G}",  # a comment ends at its newline
    f"echo ok # a note \\\n{G}",
    "# a note \\\ngh pr view 1 \\\n--jq env.X",
    f"echo a\\\r\n{G}",  # a backslash before a carriage return escapes it
    'gh pr view 1 --json body --template "line one\n#two" --jq env.X',  # a quoted string over lines
    "gh pr view 1 --json body --template 'line one\n#two' --jq env.X",
    "gh pr view 1 --json body --template $'line one\n#two' --jq env.X",
    'gh pr view 1 --json body --template "one\nsee #2" -q env.X',
    f"echo $'it\\'s #x'; {G}",  # one line too: a $'...' string runs past an escaped quote
]

# bash runs no gh call that reads the environment in any of these
STAYS_ALLOWED = [
    f"echo \\\n{G}",  # a backslash-newline joins the line: the gh words are echo's
    "gh pr view 1 \\\n  --json title \\\n  --jq '.title'",
    "echo \\\\\ngh pr view 1 --json title --jq '.title'",
    "# a note \\\ngh pr view 1 --json title",
    'gh pr view 1 --json body --template "line one\n#two"',
    "gh pr view 1 --json title \\\r\n  --jq '.title'",
    "echo 'a \\\n# b'; gh pr view 1 --json title",
]


def _shell_calls(tmp_path: Path, cmd: str) -> list[list[str]]:
    """The word lists bash hands a stand-in ``gh`` when it runs ``cmd``."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp_path / "gh-words"
    log.write_text("")
    stub = bindir / "gh"
    stub.write_text(
        '#!/bin/sh\nfor w in "$@"; do printf "%s\\037" "$w"; done >> "$GH_WORDS"\n'
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


def _reads_env(words: list[str]) -> bool:
    return any(
        w in ("--jq", "-q") and i + 1 < len(words) and words[i + 1] == "env.X"
        for i, w in enumerate(words)
    )


@pytest.mark.parametrize("cmd", RUNS_THE_CALL)
def test_bash_runs_the_call_in_each_of_these(tmp_path, cmd):
    assert any(_reads_env(words) for words in _shell_calls(tmp_path, cmd)), repr(cmd)


@pytest.mark.parametrize("cmd", STAYS_ALLOWED)
def test_bash_runs_no_such_call_in_these(tmp_path, cmd):
    assert not any(_reads_env(words) for words in _shell_calls(tmp_path, cmd)), repr(cmd)


@pytest.mark.parametrize("cmd", RUNS_THE_CALL)
def test_the_decider_reads_each_line_as_bash_ends_it(cmd):
    assert mod.decide(cmd)[0] == "deny", repr(cmd)


@pytest.mark.parametrize("cmd", STAYS_ALLOWED)
def test_ordinary_lines_stay_allowed(cmd):
    assert mod.decide(cmd)[0] == "allow", repr(cmd)


def test_the_decider_denies_a_git_output_flag_after_such_a_string():
    # the one-line case's string, then a git call that writes the file its --output names
    assert mod.decide("echo $'it\\'s #x'; git log -1 --output=out.txt")[0] == "deny"


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


NARROW = ["Bash(gh *)", "Bash(echo *)", "Bash(true *)"]


@pytest.mark.parametrize("cmd", RUNS_THE_CALL)
def test_the_hook_denies_each_under_a_narrow_and_a_bare_grant(tmp_path, cmd):
    for allow in (NARROW, ["Bash"]):
        assert _hook(tmp_path, cmd, allow) == "deny", (allow, repr(cmd))


def _trigger_text(command: str) -> str:
    """The text the hook's gh trigger reads: the hook's own ``NL=`` and ``NOQ=`` lines, run on
    ``command``."""
    lines = [
        ln
        for ln in HOOK.read_text().splitlines()
        if ln.startswith(("NL=", "NOQ="))
    ]
    assert len(lines) >= 2, "the hook's trigger text lines are not where this test reads them"
    p = subprocess.run(
        ["bash", "-c", "\n".join(lines) + '\nprintf "%s" "$NOQ"'],
        env={"PATH": "/usr/bin:/bin", "COMMAND": command},
        capture_output=True,
        text=True,
        timeout=20,
    )
    return p.stdout


@pytest.mark.parametrize(
    ("command", "text"),
    [
        ("echo \\\\\nx", "echo \nx"),  # an escaped backslash: the newline stays
        ("echo \\\\\\\\\nx", "echo \nx"),
        ("echo \\\nx", "echo x"),  # a backslash-newline joins the line
        ("echo \\\\\\\nx", "echo x"),  # an escaped backslash, then a backslash-newline
        ("--j\\\nq x", "--jq x"),
        ("-\\q 'a' \"b\"", "-q a b"),
    ],
)
def test_the_hook_trigger_pairs_backslashes_before_it_joins_lines(command, text):
    assert _trigger_text(command) == text
