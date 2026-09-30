"""R3 on clauDNA #369: after a parameter-only word, a single-label HOST/OWNER/REPO was
allowed for every verb, so a narrow `gh repo view *` grant reached a host named by one
label. Only a verb with a second positional (repo clone's directory, a skill name) needs
that leniency: for every other verb gh refuses a second positional before it sends
anything, so the word after an empty parameter is the repository. Fake values only."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "gh_guard_decide", _ROOT / "plugin-hooks" / "gh-guard-decide.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
HOOK = _ROOT / "plugin-hooks" / "pretooluse-permissions.sh"


def verdict(cmd):
    return mod.decide(cmd)[0]


def _hook(tmp_path, cmd, allow):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"allow": allow}}))
    p = subprocess.run(["bash", str(HOOK)], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
                       capture_output=True, text=True, cwd=tmp_path, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    if '"permissionDecision":"deny"' in p.stdout:
        return "deny"
    return "allow" if '"permissionDecision":"allow"' in p.stdout else "prompt"


@pytest.mark.parametrize("cmd", [
    "gh repo view $X intranet/o/r",
    'gh repo view "$R" intranet/o/r',
    "gh $X repo view intranet/o/r",
    "gh label clone $X intranet/o/r",
    "gh repo sync ${X} intranet/o/r",
])
def test_a_single_label_host_after_a_parameter_is_denied_for_a_one_positional_verb(cmd):
    assert verdict(cmd) == "deny", cmd


def test_the_hook_denies_it_under_the_narrow_grant(tmp_path):
    assert _hook(tmp_path, "gh repo view $X intranet/o/r", ["Bash(gh repo view *)"]) == "deny"


@pytest.mark.parametrize("cmd", [
    'gh repo clone "$R" src/o/r',          # a directory after the repository
    'gh repo view "$R"',
    "gh repo view $X o/r",                 # OWNER/REPO names no host
    "gh repo view $X github.com/o/r",
    'gh skills install "$R" my-skill',
])
def test_what_stays_allowed(cmd):
    assert verdict(cmd) == "allow", cmd
