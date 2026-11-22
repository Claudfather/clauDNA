"""The gh read-guard reads the text after a here-document body the way bash reads it.

bash reads a here-document body as text, up to the line that is its delimiter, and then reads commands
again with no quote open, so a quote in the body (an apostrophe, a double quote, a ``$'``) opens no
string. The decider's readings of the whole text pair such a quote with one on a later line, and a
line read on its own can start inside a string that runs across lines, so a call spelled with quotes
after the body was read in none of them. The decider now also reads the text after each line that may
end a body, as it stands and as the rest of a double-quoted string (a body inside ``"$(...)"`` ends
inside one). Each command below is first run by bash with a stand-in ``gh`` and ``git`` that record
their words, so each case is what the shell does. Fake values only.
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

# after the body: a string over two lines, then the call
T = "echo $'a\nb'; $'gh' pr list --jq env.X"
A = "cat <<EOF\nit's\nEOF\n"

# bash runs a gh call that reads the environment in each of these
RUNS_THE_CALL = [
    "cat <<EOF\nit's\nEOF\necho $'a\nb'; $'gh' pr list --jq env.X",
    # what the body holds: a double quote, a $'
    'cat <<EOF\nsay "hi\nEOF\n' + T,
    "cat <<EOF\ncost $'5\nEOF\n" + T,
    # the delimiter: <<-, quoted, partly quoted, a $'...' or $"..." string, empty, a CR, a parameter
    "cat <<-EOF\n\tit's\n\tEOF\n" + T,
    "cat <<-EOF\n\t it's\n\t\tEOF\n" + T,
    "cat <<'EOF'\nit's\nEOF\n" + T,
    "cat <<-'EOF'\n\tit's\n\tEOF\n" + T,
    'cat <<"EOF"\nit\'s\nEOF\n' + T,
    "cat <<\\EOF\nit's\nEOF\n" + T,
    'cat <<E"O"F\nit\'s\nEOF\n' + T,
    "cat <<$'EOF'\nit's\nEOF\n" + T,
    "cat <<$'E\\x4fF'\nit's\nEOF\n" + T,
    'cat <<$"EOF"\nit\'s\nEOF\n' + T,
    "cat <<''\nit's\n\n" + T,
    "cat <<EOF\r\nit's\r\nEOF\r\n" + T,
    "cat <<$X\nit's\n$X\n" + T,
    # a delimiter line that a backslash-newline joins
    "cat <<EOF\nit's\nE\\\nOF\n" + T,
    # two bodies, on one line and one after the other
    'cat <<A <<B\nit\'s\nA\nsay "x\nB\n' + T,
    'cat <<A\nit\'s\nA\ncat <<B\nsay "x\nB\n' + T,
    # where the operator stands: a pipeline, a command substitution, one inside a double-quoted string
    "cat <<EOF |\nit's\nEOF\nwc -l\n" + T,
    "x=$(cat <<EOF\nit's\nEOF\n)\n" + T,
    "x=$(cat <<'EOF'\nit's\nEOF)\n" + T,
    'gh pr create --title t --body "$(cat <<\'EOF\'\nsay "hi\nEOF\n)"; ' + T,
    'x="$(echo "$(cat <<\'EOF\'\nit\'s\nEOF\n)")"; ' + T,
    # a shift's << and a here-string's <<< before the operator
    "echo $((1<<X))\ncat <<EOF\nX\nit's\nEOF\n" + T,
    "cat <<<x; cat <<EOF\nit's\nEOF\n" + T,
    # the string after the body, and the call's spelling
    A + "echo 'a\nb'; $'gh' pr list --jq env.X",
    A + 'echo "a\nb"; $\'gh\' pr list --jq env.X',
    A + "echo $'a\nb'; gh pr list $'--jq' env.X",
    A + 'echo $\'a\nb\'; $"gh" pr list --jq env.X',
    A + "echo $'a\nb'; g$''h pr list --jq env.X",
    A + "echo $'a\nb'; $'gh' pr list \\\n--jq env.X",
    A + "echo 'a\nb'; g\\h pr list --jq env.X",
    A + 'echo "a\nb"; "g"h pr list --jq env.X',
    A + "echo 'a\nb'; gh pr list --j\\q env.X",
]

# bash runs no gh call that reads the environment in any of these
STAYS_ALLOWED = [
    "gh pr create --title t --body \"$(cat <<'EOF'\nIt's done: \"quoted\n\nEOF\n)\"",
    "cat <<'EOF' > notes.md\nit's\nEOF\necho $'a\nb'; gh pr view 1 --json title --jq '.title'",
    "echo $((1<<2)); gh pr view 1 --json title --jq '.title'",
    "cat <<-EOF\n\tit's\n\tEOF\nprintf '%s\\n' $'a\\tb'",
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
    """A gh call that reads the environment."""
    return words[:1] == ["gh"] and any(
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
def test_the_decider_reads_the_text_after_each_body(cmd):
    assert mod.decide(cmd)[0] == "deny", repr(cmd)


@pytest.mark.parametrize("cmd", STAYS_ALLOWED)
def test_ordinary_heredocs_stay_allowed(cmd):
    assert mod.decide(cmd)[0] == "allow", repr(cmd)


def test_more_heredocs_than_the_guard_reads_deny():
    sixteen = "".join(f"cat <<E{i}\nx\nE{i}\n" for i in range(16)) + "echo $'ok'"
    seventeen = "".join(f"cat <<E{i}\nx\nE{i}\n" for i in range(17)) + "echo $'ok'"
    assert mod.decide(sixteen) == ("allow", "")
    verdict, reason = mod.decide(seventeen)
    assert verdict == "deny" and "here-documents" in reason


def test_more_text_after_the_bodies_than_the_guard_reads_denies():
    head = "cat <<EOF\nx\nEOF\n"
    assert mod._heredoc_restarts(head + "y" * (mod._MAX_HEREDOC_TEXT - 1)) == [len(head)]
    assert mod._heredoc_restarts(head + "y" * (mod._MAX_HEREDOC_TEXT + 1)) is None


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


NARROW = ["Bash(gh *)", "Bash(cat *)", "Bash(echo *)", "Bash(x=*)"]


@pytest.mark.parametrize("allow", [NARROW, ["Bash"]], ids=["narrow", "bare"])
@pytest.mark.parametrize("cmd", RUNS_THE_CALL)
def test_the_hook_denies_each_under_a_narrow_and_a_bare_grant(tmp_path, cmd, allow):
    assert _hook(tmp_path, cmd, allow) == "deny", (allow, repr(cmd))
