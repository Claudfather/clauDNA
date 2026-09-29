"""Unit tests for the hosts/context frontmatter fields (clauDNA #340).

Tests validate_hosts(), validate_context(), and cursor_should_exclude() --
the field-shape validation enforced by `make check-skills`, and the
Cursor-exclusion predicate `make check-manifest` reads (the manifest-level
cross-check itself is tested separately, against a synthetic repo, in
test_cursor_scope.py).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import (
    cursor_should_exclude,
    parse_frontmatter,
    validate_context,
    validate_hosts,
    validate_skill_md,
)


# --- validate_hosts: valid inputs ---


class TestValidateHostsValid:
    def test_single_known_host(self):
        assert validate_hosts(["claude-code"]) == []

    def test_multiple_known_hosts(self):
        assert validate_hosts(["claude-code", "cursor"]) == []


# --- validate_hosts: invalid inputs ---


class TestValidateHostsInvalid:
    def test_not_a_list(self):
        errors = validate_hosts("claude-code")
        assert len(errors) == 1
        assert "must be a list" in errors[0]

    def test_empty_list(self):
        errors = validate_hosts([])
        assert len(errors) == 1
        assert "must not be empty" in errors[0]

    def test_entry_not_a_string(self):
        errors = validate_hosts([123])
        assert len(errors) == 1
        assert "must be a string" in errors[0]

    def test_unknown_host(self):
        errors = validate_hosts(["vscode"])
        assert len(errors) == 1
        assert "not a known host" in errors[0]

    def test_multiple_errors_all_reported(self):
        errors = validate_hosts(["claude-code", "vscode", 123])
        assert len(errors) == 2


# --- validate_context: valid inputs ---


class TestValidateContextValid:
    def test_known_context(self):
        assert validate_context("repo-clone") == []


# --- validate_context: invalid inputs ---


class TestValidateContextInvalid:
    def test_not_a_string(self):
        errors = validate_context(["repo-clone"])
        assert len(errors) == 1
        assert "must be a string" in errors[0]

    def test_unknown_context(self):
        errors = validate_context("docker-container")
        assert len(errors) == 1
        assert "not a known context" in errors[0]


# --- cursor_should_exclude: the exclusion predicate ---


class TestCursorShouldExclude:
    def test_no_fields_is_portable(self):
        assert cursor_should_exclude({}) is False

    def test_hosts_including_cursor_is_portable(self):
        assert cursor_should_exclude({"hosts": ["claude-code", "cursor"]}) is False

    def test_hosts_excluding_cursor_is_excluded(self):
        assert cursor_should_exclude({"hosts": ["claude-code"]}) is True

    def test_context_alone_is_excluded(self):
        assert cursor_should_exclude({"context": "repo-clone"}) is True

    def test_hosts_with_cursor_but_context_set_is_still_excluded(self):
        # Either reason is independently sufficient -- a skill can be
        # host-portable and still need a repo clone.
        fm = {"hosts": ["claude-code", "cursor"], "context": "repo-clone"}
        assert cursor_should_exclude(fm) is True

    def test_unrelated_fields_dont_trigger_it(self):
        assert cursor_should_exclude({"argument-hint": "[x]", "allowed-tools": "Read"}) is False


# --- validate_skill_md integration ---


class TestValidateSkillMdHostsContext:
    def _write_skill(self, frontmatter: str, body: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, prefix="skill_")
        tmp.write(f"---\n{frontmatter}---\n{body}")
        tmp.flush()
        return Path(tmp.name)

    def test_valid_hosts_passes(self):
        fm = (
            'name: test-skill\ndescription: "Use when you need to test the '
            'hosts field validation logic."\nhosts: [claude-code]\n'
        )
        body = "x" * 250
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            hosts_errors = [e for e in errors if "hosts" in e]
            assert hosts_errors == []
        finally:
            path.unlink()

    def test_invalid_hosts_caught(self):
        fm = (
            'name: test-skill\ndescription: "Use when you need to test the '
            'hosts field with an invalid value."\nhosts: not-a-list\n'
        )
        body = "x" * 250
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            hosts_errors = [e for e in errors if "hosts" in e]
            assert len(hosts_errors) == 1
            assert "must be a list" in hosts_errors[0]
        finally:
            path.unlink()

    def test_valid_context_passes(self):
        fm = (
            'name: test-skill\ndescription: "Use when you need to test the '
            'context field validation logic."\ncontext: repo-clone\n'
        )
        body = "x" * 250
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            context_errors = [e for e in errors if "context" in e]
            assert context_errors == []
        finally:
            path.unlink()

    def test_invalid_context_caught(self):
        fm = (
            'name: test-skill\ndescription: "Use when you need to test the '
            'context field with an invalid value."\ncontext: docker\n'
        )
        body = "x" * 250
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            context_errors = [e for e in errors if "context" in e]
            assert len(context_errors) == 1
            assert "not a known context" in context_errors[0]
        finally:
            path.unlink()

    def test_hosts_and_context_are_known_fields(self):
        """hosts/context should not trigger 'unknown field' errors."""
        fm = (
            'name: test-skill\ndescription: "Use when you need to verify hosts '
            'and context are recognized fields."\nhosts: [claude-code]\ncontext: repo-clone\n'
        )
        body = "x" * 250
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            unknown_errors = [e for e in errors if "unknown field" in e]
            assert unknown_errors == []
        finally:
            path.unlink()


# --- Integration: the real four skills #340 marks, plus a portable control ---


class TestRealMarkedSkills:
    @staticmethod
    def _fm(name: str) -> dict:
        skill_path = REPO_ROOT / "skills" / name / "SKILL.md"
        parsed = parse_frontmatter(skill_path)
        assert parsed is not None
        fm, _ = parsed
        return fm

    def test_using_claudna_is_claude_code_only(self):
        fm = self._fm("using-claudna")
        assert fm.get("hosts") == ["claude-code"]
        assert cursor_should_exclude(fm) is True

    def test_cleanup_legacy_install_is_claude_code_only(self):
        fm = self._fm("cleanup-legacy-install")
        assert fm.get("hosts") == ["claude-code"]
        assert cursor_should_exclude(fm) is True

    def test_promotion_intake_needs_repo_clone(self):
        fm = self._fm("promotion-intake")
        assert fm.get("context") == "repo-clone"
        assert cursor_should_exclude(fm) is True

    def test_skill_scaffold_needs_repo_clone(self):
        fm = self._fm("skill-scaffold")
        assert fm.get("context") == "repo-clone"
        assert cursor_should_exclude(fm) is True

    def test_an_arbitrary_unmarked_skill_stays_portable(self):
        # Positive control: a skill with neither field ships to Cursor.
        fm = self._fm("recall")
        assert "hosts" not in fm
        assert "context" not in fm
        assert cursor_should_exclude(fm) is False
