"""The gh read-guard inspects a gh call behind a wrapper's options and their values, and
the permission hook refuses a triggering gh command the guard could not check.

Four behaviors are covered here:

1. `plugin-hooks/gh-guard-decide.py` skipped a leading wrapper's words only while each was a
   dash-option or a bare number, so the value word of a value-taking option ended the skip and
   the gh call behind it was read as a different command and never inspected: `env -u X`,
   `timeout -s KILL 5`, `xargs -I {}`. `env` alone and `nice -n 5` (a bare number) already
   reached the decider; the guard now reads every word past a wrapper up to the gh word.
2. `plugin-hooks/pretooluse-permissions.sh` sent a guard exit other than 0 or 10, and a missing
   python3, to the allow patterns, which could approve the unchecked command — against the
   comment that a failed spawn must not read as allow. A hook deny is the only decision that
   overrides an allow grant, so the hook now refuses a command that matched the gh trigger and
   could not be checked.
3. Each word past a wrapper still goes through the decider's assignment handling, so a GH_HOST=
   or GH_REPO= prefix after a wrapper's options (`env -i GH_HOST=... gh ...`) names the host as
   one in front of them does. After a dash-option or a number e0ef4b4 already denies it, and
   fea265d (this branch before the fix) allowed it; after a value-taking option both allowed it.
4. `sudo` and `doas` are in the hook's `is_gh_command` wrapper list but were not in the
   decider's, so a gh call behind them was never inspected. The decider's list now holds every
   wrapper the hook names, and a test reads the hook's list to keep the two in step.

Each deny case is red on e0ef4b4 (main before this change), at fea265d, or on both, and green
with this change; the allow cases are green on all three. Fake values only."""

from __future__ import annotations

import importlib.util
import json
import re
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
def test_the_hook_denies_a_wrapped_environment_read_under_a_narrow_and_a_bare_grant(tmp_path, cmd):
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


ENV_READ = "gh pr list --json number --jq env.X"  # a --jq expression that reads the process environment
CLEAN_TRIGGER = "gh pr list --json number --jq .title"  # a field read, but it matched the trigger


def test_no_python3_refuses_a_triggering_gh_command(tmp_path):
    # Both an environment-reading and a clean-but-triggering command are refused: with the guard unable to
    # run, the hook cannot tell them apart and will not approve either.
    path = _bin_without_python3(tmp_path)
    for cmd in (ENV_READ, CLEAN_TRIGGER):
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
        assert _hook(tmp_path, ENV_READ, allow, path=path) == "deny", (exit_code, allow)


def test_a_guard_that_allows_still_lets_normal_matching_run(tmp_path):
    # exit 0 = this shape is clear; the command then matches its allow pattern and is approved.
    shim = tmp_path / "shim0"
    shim.mkdir()
    (shim / "python3").write_text("#!/bin/sh\nexit 0\n")
    (shim / "python3").chmod(0o755)
    assert _hook(tmp_path, ENV_READ, ["Bash(gh pr list *)"], path=f"{shim}:/usr/bin:/bin") == "allow"


# -- 3. A GH_HOST= or GH_REPO= prefix after a wrapper's options names the host -------------
# The decider reads every word between a wrapper and the gh word, so a prefix after the
# wrapper's options goes through the same assignment handling as one in front of them. Each
# form puts one kind of option in front of the prefix ({P}): a dash-option, a number, or a
# value-taking option. The gh tail is a clean read, so only the prefix can deny.
PREFIX_FORMS = [
    "env -i {P}",  # a dash-option
    "env -i 2>&1 {P}",  # a dash-option, then a redirection
    "time -p env {P}",  # another wrapper's dash-option, then env
    "timeout 5 env {P}",  # a number
    "nice -n 5 env {P}",  # an option and its number
    "env -u X {P}",  # a value-taking option
    "timeout -s KILL 5 env {P}",  # a value-taking option, then a number
    "xargs -I {{}} env {P}",  # a value-taking option
]
CLEAN = "gh pr list --json number"


@pytest.mark.parametrize("prefix", ["GH_HOST=other.example", "GH_REPO=other.example/o/r", "GH_HOST+=x"])
@pytest.mark.parametrize("form", PREFIX_FORMS)
def test_a_host_prefix_after_a_wrappers_options_is_read(form, prefix):
    cmd = f"{form.format(P=prefix)} {CLEAN}"
    assert verdict(cmd) == "deny", cmd


@pytest.mark.parametrize("prefix", ["GH_HOST=github.com", "GH_REPO=o/r"])
@pytest.mark.parametrize("form", PREFIX_FORMS)
def test_a_github_com_prefix_after_a_wrappers_options_stays_allowed(form, prefix):
    cmd = f"{form.format(P=prefix)} {CLEAN}"
    assert verdict(cmd) == "allow", cmd


@pytest.mark.parametrize("prefix", ["GH_HOST=other.example", "GH_REPO=other.example/o/r"])
@pytest.mark.parametrize("form", ["env -i {P}", "timeout 5 env {P}", "env -u X {P}"])
def test_the_hook_denies_a_host_prefix_after_a_wrappers_options(tmp_path, form, prefix):
    cmd = f"{form.format(P=prefix)} {CLEAN}"
    for allow in ([f"Bash({cmd.split()[0]} *)"], ["Bash"]):
        assert _hook(tmp_path, cmd, allow) == "deny", (allow, cmd)


@pytest.mark.parametrize("form", ["env -i {P}", "timeout 5 env {P}", "env -u X {P}"])
def test_the_hook_allows_a_github_com_prefix_after_a_wrappers_options(tmp_path, form):
    cmd = f"{form.format(P='GH_HOST=github.com')} {CLEAN}"
    for allow in ([f"Bash({cmd.split()[0]} *)"], ["Bash"]):
        assert _hook(tmp_path, cmd, allow) == "allow", (allow, cmd)


# -- 4. sudo and doas are wrappers to the decider, as they are to the hook ------------------
def _hook_wrappers() -> set[str]:
    """The wrapper words of the hook's `is_gh_command`: its one `word|word...) ;;` case arm."""
    body = HOOK.read_text().split("is_gh_command() {", 1)[1].split("\n}\n", 1)[0]
    arms = re.findall(r"^\s*([A-Za-z|]+)\) ;;$", body, re.M)
    assert len(arms) == 1, arms
    return set(arms[0].split("|"))


def test_the_deciders_wrapper_list_holds_every_wrapper_the_hook_names():
    hook = _hook_wrappers()
    assert {"env", "timeout", "sudo", "doas"} <= hook  # the arm was found and read
    assert hook <= mod._WRAPPERS, sorted(hook - mod._WRAPPERS)


@pytest.mark.parametrize(
    "cmd",
    [
        f"sudo {ENV}",
        f"sudo -u x {ENV}",  # -u takes the user name
        f"sudo -u x {HOST}",
        f"sudo -E -u x {ENV}",
        "sudo -u x GH_HOST=other.example gh pr list --json number",  # sudo's own NAME=value
        f"doas {ENV}",
        f"doas -u x {ENV}",
        f"doas -u x {HOST}",
    ],
)
def test_a_gh_call_behind_sudo_or_doas_is_inspected(cmd):
    assert verdict(cmd) == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "sudo gh pr list --json number",
        "sudo -u x gh pr list --json title --jq .title",
        "sudo -u x GH_HOST=github.com gh pr list --json number",
        "doas -u x gh pr view 5 --json title",
        "sudo -u x ls -la",  # a non-gh command behind sudo is not a gh call
    ],
)
def test_an_ordinary_call_behind_sudo_or_doas_stays_allowed(cmd):
    assert verdict(cmd) == "allow", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "sudo -u x gh pr list --json number --jq env.X",
        "doas -u x gh pr list --json number --jq env.X",
        "sudo gh pr list -R evil.example/o/r --search x",
    ],
)
def test_the_hook_denies_a_gh_call_behind_sudo_or_doas_under_a_narrow_and_a_bare_grant(tmp_path, cmd):
    for allow in ([f"Bash({cmd.split()[0]} *)"], ["Bash"]):
        assert _hook(tmp_path, cmd, allow) == "deny", (allow, cmd)


def test_the_hook_allows_a_clean_gh_read_behind_sudo(tmp_path):
    cmd = "sudo -u x gh pr list --json number --jq .title"
    for allow in (["Bash(sudo *)"], ["Bash"]):
        assert _hook(tmp_path, cmd, allow) == "allow", (allow, cmd)
