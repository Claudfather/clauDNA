"""The gh read-guard inspects a gh call behind a wrapper's options and their values, and
the permission hook refuses a triggering gh command the guard could not check.

Two findings held from the clauDNA tech-debt audit:

1. `plugin-hooks/gh-guard-decide.py` skipped a leading wrapper's words only while each was a
   dash-option or a bare number, so the value word of a value-taking option ended the skip and
   the gh call behind it was read as a different command and never inspected: `env -u X`,
   `timeout -s KILL 5`, `xargs -I {}`. `env` alone and `nice -n 5` (a bare number) already
   reached the decider; the guard now finds the gh command word past any wrapper's options.
2. `plugin-hooks/pretooluse-permissions.sh` sent a guard exit other than 0 or 10, and a missing
   python3, to the allow patterns, which could approve the unchecked command — against the
   comment that a failed spawn must not read as allow. A hook deny is the only decision that
   overrides an allow grant, so the hook now refuses a command that matched the gh trigger and
   could not be checked.

Each deny case is red on e0ef4b4 (main before this change) and green with it. Fake values only."""

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


def verdict(cmd: str) -> str:
    return mod.decide(cmd)[0]


# -- 1. A gh call behind a wrapper's options and their values is inspected -----------------
# env=the environment read, host=a foreign -R/positional: both shapes, each wrapper form.
ENV = "gh pr list --json number --jq env.X"
HOST = "gh pr list -R evil.example/o/r --search x"


@pytest.mark.parametrize(
    "cmd",
    [
        f"env -u FOO {ENV}",  # -u takes the next word; its value ended the old skip
        f"env -u FOO {HOST}",
        f"timeout -s KILL 5 {ENV}",  # -s takes a signal word, then the duration
        f"timeout -s KILL 5 {HOST}",
        f"timeout --signal=KILL 5 {ENV}",  # the glued long form
        f"xargs -I {{}} {ENV}",  # -I takes a replace-string word
        f"xargs -I {{}} {HOST}",
        f"nice -n 5 {ENV}",  # control: a bare number already reached the decider
        f"env {ENV}",  # control: plain env already reached the decider
        f"env {HOST}",
        f"timeout 5 env -u X {ENV}",  # chained wrappers, the inner one value-taking
        f"nice -n 5 timeout -s KILL 5 {HOST}",  # chained, both value-taking
        f"stdbuf -oL timeout -k 5 5 {ENV}",  # stdbuf -oL, timeout -k 5
        "env -u X gh repo view evil.example/o/r",  # the repository positional too
    ],
)
def test_a_gh_call_behind_a_wrappers_options_is_inspected(cmd):
    assert verdict(cmd) == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "env -u FOO gh pr list --json number --jq .[].number",  # clean read behind each wrapper
        "timeout -s KILL 5 gh pr list --json title --jq .title",
        "timeout --signal=KILL 5 gh pr list --json number",
        "xargs -I {} gh pr list --json number",
        "nice -n 5 gh pr view 5 --json title",
        "env gh pr list --json number --jq '.[] | .title'",
        "timeout 5 env -u X gh pr list --json number",
        "stdbuf -oL gh api user --jq .login",
        "env -u X ls -la",  # a wrapper in front of a non-gh command is not a gh call
        "env FOO=bar gh pr list --json number",  # an env NAME=value argument, then a clean gh
        "env -u X gh repo view github.com/o/r",  # a github.com repository positional
    ],
)
def test_an_ordinary_call_behind_a_wrapper_stays_allowed(cmd):
    assert verdict(cmd) == "allow", cmd


def _hook(tmp_path: Path, cmd: str, allow: list[str], *, path: str = "/usr/bin:/bin",
          env_extra: dict | None = None) -> str:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": allow}})
    )
    env = {"HOME": str(tmp_path), "PATH": path, **(env_extra or {})}
    p = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True, text=True, cwd=tmp_path, env=env, timeout=20,
    )
    return (
        "deny" if '"permissionDecision":"deny"' in p.stdout
        else "allow" if '"permissionDecision":"allow"' in p.stdout
        else "prompt"
    )


@pytest.mark.parametrize(
    "cmd",
    [
        "env -u FOO gh pr list --json number --jq env.X",
        "timeout -s KILL 5 gh pr list --json number --jq env.X",
        "xargs -I {} gh pr list --json number --jq env.X",
        "nice -n 5 gh pr list -R evil.example/o/r --search x",
        "timeout 5 env -u X gh pr list --json number --jq env.X",
    ],
)
def test_the_hook_denies_a_wrapped_leak_under_a_narrow_and_a_bare_grant(tmp_path, cmd):
    for allow in (["Bash(gh pr list *)"], ["Bash"]):
        assert _hook(tmp_path, cmd, allow) == "deny", (allow, cmd)


# -- 2. The hook refuses a triggering gh command the guard could not check -----------------
def _bin_without_python3(tmp_path: Path) -> str:
    """A PATH with the tools the hook needs but no python3, so `command -v python3` fails."""
    bin_dir = tmp_path / "nopy"
    bin_dir.mkdir(exist_ok=True)
    for tool in ("bash", "jq", "cat", "mkdir", "mv", "wc", "date", "sed", "dirname", "env"):
        src = shutil.which(tool)
        if src:
            (bin_dir / tool).symlink_to(src)
    assert shutil.which("python3", path=str(bin_dir)) is None
    return str(bin_dir)


def _python3_shim(tmp_path: Path, exit_code: int) -> str:
    shim = tmp_path / f"shim{exit_code}"
    shim.mkdir(exist_ok=True)
    (shim / "python3").write_text(f"#!/bin/sh\nexit {exit_code}\n")
    (shim / "python3").chmod(0o755)
    return f"{shim}:/usr/bin:/bin"


LEAK = "gh pr list --json number --jq env.X"
CLEAN_TRIGGER = "gh pr list --json number --jq .title"  # a field read, but it matched the trigger


def test_no_python3_refuses_a_triggering_gh_command(tmp_path):
    # Both a leaking and a clean-but-triggering command are refused: with the guard unable to
    # run, the hook cannot tell them apart and will not approve either.
    path = _bin_without_python3(tmp_path)
    for cmd in (LEAK, CLEAN_TRIGGER):
        for allow in (["Bash(gh pr list *)"], ["Bash"]):
            assert _hook(tmp_path, cmd, allow, path=path) == "deny", (cmd, allow)


def test_no_python3_still_approves_a_gh_command_that_never_triggers_the_guard(tmp_path):
    # The guard is never invoked without a trigger flag, so normal matching still approves.
    path = _bin_without_python3(tmp_path)
    assert _hook(tmp_path, "gh pr list --json number,title", ["Bash(gh pr list *)"], path=path) == "allow"


@pytest.mark.parametrize("exit_code", [7, 3, 1, 2, 11, 255])
def test_a_guard_error_or_unknown_exit_refuses_a_triggering_gh_command(tmp_path, exit_code):
    # A python3 that neither allows (0) nor denies (10): the guard did not answer, so the hook
    # refuses rather than fall through to the allow patterns.
    path = _python3_shim(tmp_path, exit_code)
    for allow in (["Bash(gh pr list *)"], ["Bash"]):
        assert _hook(tmp_path, LEAK, allow, path=path) == "deny", (exit_code, allow)


def test_a_guard_that_allows_still_lets_normal_matching_run(tmp_path):
    # exit 0 = this shape is clear; the command then matches its allow pattern and is approved.
    shim = tmp_path / "shim0"
    shim.mkdir()
    (shim / "python3").write_text("#!/bin/sh\nexit 0\n")
    (shim / "python3").chmod(0o755)
    assert _hook(tmp_path, LEAK, ["Bash(gh pr list *)"], path=f"{shim}:/usr/bin:/bin") == "allow"
