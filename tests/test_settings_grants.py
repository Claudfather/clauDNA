"""Pins the checked-in settings grants against the grant-scope allowlist.

A committed ``.claude/settings.json`` pre-approves commands for every agent that
runs in the repo, so its ``permissions.allow`` list must stay within the same
allowlist the skills use. The test drives the shared predicate
(``skill_checks.check_settings_grants``) rather than pinning individual strings,
so a future broad grant fails however it is spelled, and it checks the deny list
is present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import skill_checks  # noqa: E402

TEMPLATE = REPO_ROOT / "project-template" / ".claude" / "settings.json"
REPO_SETTINGS = REPO_ROOT / ".claude" / "settings.json"

DENY_REQUIRED = {
    "Bash(gh gist:*)",
    "Bash(gh extension:*)",
    "Bash(gh alias:*)",
    "Bash(gh auth token:*)",
    "Bash(git config:*)",
    "Bash(git -c:*)",
}

# One row per form that must be rejected if it appears in a shipped allow list.
REJECTED_SETTINGS_GRANTS = [
    "Bash(git:*)",
    "Bash(gh:*)",
    "Bash(chmod:*)",
    "Bash(*)",
    "Bash(curl:*)",
    "Bash(wget:*)",
    "Bash(python3:*)",
    "Bash(node:*)",
    "Bash(npm:*)",
    "Bash(pip:*)",
    "Bash(rm:*)",
    "Bash(find:*)",
    "Bash(env:*)",
    "Bash(sudo:*)",
    "Bash(gh api:*)",
    "Bash(gh auth:*)",
    "Bash(git clone:*)",
    "Bash(git -c:*)",
    "Bash(pytest:*)",
    "Bash(make:*)",
]


def _perms(path: Path) -> dict:
    return json.loads(path.read_text()).get("permissions", {})


class TestShippedSettingsWithinAllowlist:
    def test_template_allow_clean(self):
        errs = skill_checks.check_settings_grants(_perms(TEMPLATE).get("allow", []))
        assert errs == [], errs

    def test_repo_allow_clean(self):
        errs = skill_checks.check_settings_grants(_perms(REPO_SETTINGS).get("allow", []))
        assert errs == [], errs


class TestPredicateRejectsTheClass:
    def test_every_rejected_form_is_rejected(self):
        missed = [g for g in REJECTED_SETTINGS_GRANTS if not skill_checks.check_settings_grants([g])]
        assert missed == [], f"settings allowlist accepted: {missed}"


class TestDenyAndJson:
    def test_template_deny_covers_required(self):
        deny = set(_perms(TEMPLATE).get("deny", []))
        assert not (DENY_REQUIRED - deny), DENY_REQUIRED - deny

    def test_repo_deny_covers_required(self):
        deny = set(_perms(REPO_SETTINGS).get("deny", []))
        assert not (DENY_REQUIRED - deny), DENY_REQUIRED - deny

    def test_both_parse(self):
        json.loads(TEMPLATE.read_text())
        json.loads(REPO_SETTINGS.read_text())

    def test_still_grants_read_only_git(self):
        allow = set(_perms(TEMPLATE).get("allow", []))
        assert any(a.startswith("Bash(git ") for a in allow)
