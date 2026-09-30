"""Pins the checked-in settings grants so a future edit cannot silently restore
the broad pre-approvals.

A committed .claude/settings.json applies to every collaborator's agent,
including one working on an untrusted PR. `Bash(git:*)` pre-approves the
code-exec / config-rewrite subcommands (git -c, git config); `Bash(gh:*)`
pre-approves data egress (gh auth token, gh gist); `Bash(chmod:*)` is
unbounded. The template and the repo's own settings ship with narrow read-only
(template) or dev-subcommand (repo) allows plus explicit deny rules.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE = REPO_ROOT / "project-template" / ".claude" / "settings.json"
REPO_SETTINGS = REPO_ROOT / ".claude" / "settings.json"

BROAD_ALLOW_FORBIDDEN = {"Bash(git:*)", "Bash(gh:*)", "Bash(chmod:*)"}
DENY_REQUIRED = {
    "Bash(gh gist:*)",
    "Bash(gh extension:*)",
    "Bash(gh alias:*)",
    "Bash(gh auth token:*)",
    "Bash(git config:*)",
    "Bash(git -c:*)",
}


def _perms(path: Path) -> dict:
    data = json.loads(path.read_text())
    return data.get("permissions", {})


class TestTemplateSettings:
    def test_no_broad_family_allow(self):
        allow = set(_perms(TEMPLATE).get("allow", []))
        assert not (allow & BROAD_ALLOW_FORBIDDEN), allow & BROAD_ALLOW_FORBIDDEN

    def test_deny_list_covers_dangerous_verbs(self):
        deny = set(_perms(TEMPLATE).get("deny", []))
        missing = DENY_REQUIRED - deny
        assert not missing, f"template deny missing: {missing}"

    def test_still_grants_read_only_git(self):
        # narrowing must not leave the template with no git at all
        allow = set(_perms(TEMPLATE).get("allow", []))
        assert any(a.startswith("Bash(git ") for a in allow)


class TestRepoSettings:
    def test_no_broad_family_allow(self):
        allow = set(_perms(REPO_SETTINGS).get("allow", []))
        assert not (allow & BROAD_ALLOW_FORBIDDEN), allow & BROAD_ALLOW_FORBIDDEN

    def test_deny_list_covers_dangerous_verbs(self):
        deny = set(_perms(REPO_SETTINGS).get("deny", []))
        missing = DENY_REQUIRED - deny
        assert not missing, f"repo deny missing: {missing}"

    def test_valid_json(self):
        # both files parse (a malformed settings.json disables all permissions)
        json.loads(TEMPLATE.read_text())
        json.loads(REPO_SETTINGS.read_text())
