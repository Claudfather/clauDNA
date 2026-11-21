"""The gh read-guard reads at most 128 KiB of one command, for at most 60 s.

A command over 128 KiB that reaches the guard is denied before any reading, and a command is denied once
its readings pass 60 s, checked between readings; the reason says to put long text in a file and pass it
with --body-file. A command of 128 KiB or less is read as before. Each test that such a command is
denied fails without these limits. A stand-in clock times the readings, so no test waits 60 s.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
DECIDER = _ROOT / "plugin-hooks" / "gh-guard-decide.py"
_spec = importlib.util.spec_from_file_location("gh_guard_decide", DECIDER)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
HOOK = _ROOT / "plugin-hooks" / "pretooluse-permissions.sh"

CAP = 128 * 1024
# a PR body in one double-quoted string; --repo takes it to the guard
HEAD = 'gh pr create --repo o/r --title t --body "'
# prose that holds an apostrophe, a double quote, a $' and a backtick: the slowest text known to read
PROSE = "It's a line of prose with a \"quote\", a $'x and a `tick` in it, sixty-four chars.\n"


def command_of(size: int, fill: str = "a word ") -> str:
    """A harmless command of ``size`` bytes: ``HEAD``, ``fill`` repeated, and the closing quote."""
    room = size - len(HEAD) - 1
    cmd = HEAD + (fill * (room // len(fill) + 1))[:room] + '"'
    assert len(cmd.encode()) == size
    return cmd


def test_a_command_at_the_cap_is_read():
    assert mod.decide(command_of(CAP)) == ("allow", "")
    assert mod.decide(command_of(CAP, "a line\n")) == ("allow", "")
    env = command_of(CAP - len(" --jq env.X")) + " --jq env.X"
    assert len(env.encode()) == CAP
    assert mod.decide(env) == ("deny", "gh --jq/--template reads the process environment")


def test_a_command_over_the_cap_is_denied_before_any_reading(monkeypatch):
    calls = []
    for name in ("_texts", "_readings", "_dollar_quotes", "_heredoc_restarts"):
        real = getattr(mod, name)
        monkeypatch.setattr(mod, name, lambda *a, _real=real, _name=name, **k: calls.append(_name) or _real(*a, **k))
    verdict, reason = mod.decide(command_of(CAP + 1))
    assert verdict == "deny"
    assert reason == (
        "the gh read-guard reads at most 128 KiB in one command;"
        " put long text in a file and pass it with --body-file"
    )
    assert calls == []


def test_the_cap_counts_bytes_not_characters():
    # a two-byte character: under the cap in characters and over it in bytes, or at it in bytes
    wide = "\u00e9"
    over = HEAD + wide * ((CAP - len(HEAD) - 1) // 2 + 1) + '"'
    assert len(over) <= CAP < len(over.encode())
    assert mod.decide(over)[0] == "deny"
    at = HEAD + wide * ((CAP - len(HEAD) - 1) // 2) + "x" * ((CAP - len(HEAD) - 1) % 2) + '"'
    assert len(at.encode()) == CAP
    assert mod.decide(at) == ("allow", "")


@pytest.mark.parametrize("size,code", [(CAP, 0), (CAP + 1, 10)])
def test_the_decider_counts_a_byte_it_cannot_decode_as_one(size, code):
    head = HEAD.encode()
    data = head + b"\xff" * (size - len(head) - 1) + b'"'
    assert len(data) == size
    p = subprocess.run(
        [sys.executable, "-I", "-B", str(DECIDER)], input=data, capture_output=True, timeout=120
    )
    assert p.returncode == code, p.stdout[-300:]


def test_a_command_over_the_cap_is_denied_at_once():
    cmd = command_of(CAP + 1, PROSE)
    start = time.perf_counter()
    assert mod.decide(cmd)[0] == "deny"
    assert time.perf_counter() - start < 1


class _Clock:
    """A stand-in for the ``time`` module: ``monotonic()`` gives each of ``readings`` in turn, and the
    last one from then on."""

    def __init__(self, *readings: float):
        self.readings = list(readings)

    def monotonic(self) -> float:
        return self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]


def test_a_command_whose_readings_pass_60_s_is_denied(monkeypatch):
    monkeypatch.setattr(mod, "time", _Clock(0.0, 60.5), raising=False)
    assert mod.decide("gh pr list --json number --jq .x") == (
        "deny",
        "the gh read-guard reads one command for at most 60 s;"
        " put long text in a file and pass it with --body-file",
    )


def test_readings_under_60_s_are_read_to_the_end(monkeypatch):
    monkeypatch.setattr(mod, "time", _Clock(0.0, 59.5), raising=False)
    assert mod.decide("gh pr list --json number --jq .x") == ("allow", "")
    monkeypatch.setattr(mod, "time", _Clock(0.0, 59.5), raising=False)
    assert mod.decide("gh pr list --json number --jq env.X") == (
        "deny",
        "gh --jq/--template reads the process environment",
    )


def test_the_clock_is_read_between_readings(monkeypatch):
    seen = []
    real = mod._gh_command_words
    monkeypatch.setattr(mod, "_gh_command_words", lambda tokens: seen.append(tokens) or real(tokens))
    # the deadline, then before the first reading, then before the next
    monkeypatch.setattr(mod, "time", _Clock(0.0, 0.0, 60.5), raising=False)
    verdict, reason = mod.decide("gh pr list --json number --jq .x\necho ok")
    assert verdict == "deny" and "60 s" in reason
    assert len(seen) == 1


def test_the_time_limit_covers_the_readings_after_a_here_document(monkeypatch):
    cmd = "cat <<EOF\nit's\nEOF\necho done"
    real = mod._heredoc_restarts
    assert real(cmd)
    clock = _Clock(0.0)

    def restarts(command):
        clock.readings = [60.5]
        return real(command)

    monkeypatch.setattr(mod, "_heredoc_restarts", restarts)
    monkeypatch.setattr(mod, "time", clock, raising=False)
    verdict, reason = mod.decide(cmd)
    assert verdict == "deny" and "60 s" in reason


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
        timeout=60,
    )
    return (
        "deny"
        if '"permissionDecision":"deny"' in p.stdout
        else "allow"
        if '"permissionDecision":"allow"' in p.stdout
        else "prompt"
    )


@pytest.mark.parametrize("allow", [["Bash(gh *)"], ["Bash"]], ids=["narrow", "bare"])
def test_the_hook_denies_a_command_over_the_cap_under_a_narrow_and_a_bare_grant(tmp_path, allow):
    assert _hook(tmp_path, command_of(CAP + 1), allow) == "deny"


def test_the_hook_reads_a_command_at_the_cap_as_before_under_a_bare_grant(tmp_path):
    assert _hook(tmp_path, command_of(CAP), ["Bash"]) == "allow"
