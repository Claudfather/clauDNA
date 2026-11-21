"""The gh read-guard reads ``$'...'`` and ``$"..."`` strings the way bash does.

bash drops the ``$`` of a ``$'...'`` or ``$"..."`` string, decodes a ``$'...'`` string's backslash
escapes, and joins the value to the text around it, so such a string can spell ``gh`` or one of its
flags. The decider also reads each command with every such string written as the value bash gives it,
and the hook sends a command that holds one to the decider. A ``$'...'`` string whose value the
decider does not give the way bash does (a ``\\c`` before a backslash pair, a DEL byte or a 0x01
byte) is not read, and the command is denied. Each command below is first run by bash
with stand-in ``gh`` and ``git`` executables that record their words. A few spellings have explicit
observed argv variants because Bash 3.2 and newer Bash decode Unicode escapes differently. Fake
values only.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
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

# The guard denies every spelling below; four Unicode forms have different native
# argv on Bash 3.2, checked explicitly by the shell-observation test.
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
    "printf %s $'\\c\\x'",  # \c before one backslash: read
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
def test_native_bash_observes_expected_argv_for_each_spelling(tmp_path, cmd):
    calls = _shell_calls(tmp_path, cmd)
    native_variants = {
        "gh pr list $'-\\u002dj\\x71' env.X": [
            [["gh", "pr", "list", "-\\u002djq", "env.X"]],
            [["gh", "pr", "list", "--jq", "env.X"]],
        ],
        "$'g\\UFFFFFFFFh' pr list --jq env.X": [[], [["gh", "pr", "list", "--jq", "env.X"]]],
        "g$'\\UFFFFFFFF'h pr list --jq env.X": [[], [["gh", "pr", "list", "--jq", "env.X"]]],
        "gh pr list $'--j\\U80000000q' env.X": [
            [["gh", "pr", "list", "--j\\U80000000q", "env.X"]],
            [["gh", "pr", "list", "--jq", "env.X"]],
        ],
    }
    if cmd in native_variants:
        assert calls in native_variants[cmd], (repr(cmd), calls)
    else:
        assert any(_runs_the_call(words) for words in calls), repr(cmd)


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
DECODER_VALUES = [
    ("\\x67h", "6768", {"6768"}), ("\\147\\150", "6768", {"6768"}),
    ("\\u0068", "68", {"5c7530303638", "68"}),
    ("\\U00000067", "67", {"5c553030303030303637", "67"}),
    ("\\cA", "01", {"01"}), ("\\ca", "01", {"01"}),
    ("\\c?", "7f", {"1f", "7f"}), ("\\e", "1b", {"1b"}),
    ("\\E", "1b", {"1b"}), ("\\'", "27", {"27"}), ('\\"', "22", {"22"}),
    ("\\?", "3f", {"3f"}), ("\\q", "5c71", {"5c71"}),
    ("\\x", "5c78", {"5c78"}), ("\\xZ", "5c785a", {"5c785a"}),
    ("\\u", "5c75", {"5c75"}), ("\\c", "5c63", {"5c", "5c63"}),
    ("a\\0b", "61", {"61"}), ("\\1234", "5334", {"5334"}),
    ("\\x6g", "0667", {"0667"}), ("\\t\\n\\\\", "090a5c", {"090a5c"}),
    ("gh\\c\u0801junk", "6768", {"6768"}),
    ("g\\UFFFFFFFFh", "6768", {"675c55464646464646464668", "6768"}),
    ("\\x{67}h", "6768", {"6768"}), ("gh\\x{junk", "6768", {"6768"}),
    ("\\x{41", "41", {"41"}), ("\\x{}", "", {""}),
    ("\\c\\x", "1c78", {"1c78"}),
]


@pytest.mark.parametrize(
    ("body", "expected_hex"), [(body, expected_hex) for body, expected_hex, _ in DECODER_VALUES]
)
def test_the_decoder_matches_its_explicit_bash_value(body, expected_hex):
    assert mod._ansi_c_value(body).encode() == bytes.fromhex(expected_hex), repr(body)


@pytest.mark.parametrize(("body", "_expected_hex", "native_hex"), DECODER_VALUES)
def test_native_bash_matches_a_known_ansi_c_value(body, _expected_hex, native_hex):
    p = subprocess.run(
        ["bash", "-c", f"printf %s $'{body}'"],
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        timeout=20,
    )
    assert p.returncode == 0, (repr(body), p.returncode, p.stderr)
    assert p.stdout.hex() in native_hex, (repr(body), p.stdout.hex())


# Bodies with a \c before a backslash pair, a DEL byte or a 0x01 byte: bash 5.2 takes the pair whole, and
# its reader keeps a DEL or 0x01 byte behind a 0x01 byte of its own, which the \c then takes
UNREADABLE = ["\\c\\\\", "\\c\\\\x", "\\c\\\\n", "\\c\\\\\\\\", "\\c\x7f", "a\\c\x7fb", "\\c\x01", "\\c\x01x"]


@pytest.mark.parametrize("body", UNREADABLE)
def test_the_decider_decodes_such_a_string_as_bash_does_or_denies_it(body):
    p = subprocess.run(
        ["bash", "-c", f"printf %s $'{body}'"],
        capture_output=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        timeout=20,
    )
    denied = mod.decide(f"gh pr list --json title --jq $'.title{body}'")[0] == "deny"
    assert denied or mod._ansi_c_value(body).encode() == p.stdout, repr(body)


def test_a_command_that_holds_such_a_string_is_denied_gh_or_not():
    verdict, reason = mod.decide("echo $'\\c\\\\'")
    assert verdict == "deny" and "\\c" in reason


# bash takes the backslash pair after each \c whole, so the jq strings in this value end where jq ends
# them and env.X is read between them; a reading that took one backslash would end them elsewhere
JQ_CALL = "gh pr list --jq $'" + '"\\c\\\\\\" + env.X + "\\c\\\\\\\\\\""' + "'"
JQ_VALUE = '"\x1c" + env.X + "\x1c\\""'


def test_bash_passes_that_jq_value_to_gh(tmp_path):
    assert _shell_calls(tmp_path, JQ_CALL) == [["gh", "pr", "list", "--jq", JQ_VALUE]]


@pytest.mark.skipif(shutil.which("jq") is None, reason="no jq here to read the value")
def test_jq_reads_the_environment_in_that_value():
    p = subprocess.run(
        ["jq", "-n", "-r", JQ_VALUE], env={"X": "fake-value"}, capture_output=True, text=True, timeout=20
    )
    assert "fake-value" in p.stdout


def test_the_decider_denies_that_call():
    assert mod.decide(JQ_CALL)[0] == "deny"


@pytest.mark.parametrize("allow", [NARROW, ["Bash"]], ids=["narrow", "bare"])
def test_the_hook_denies_that_call_under_a_narrow_and_a_bare_grant(tmp_path, allow):
    assert _hook(tmp_path, JQ_CALL, allow) == "deny", allow
