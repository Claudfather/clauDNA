"""Unit tests for behavioral validation checks.

Tests the three behavioral validators added for issue #25:
1. --output github must reference output-guide.md
2. --auto must not contain AskUserQuestion
3. allowed-tools entries should be referenced in body (warnings)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Add scripts/ to path so skill_checks is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import (
    check_allowed_tools_usage,
    check_auto_no_ask_user,
    check_output_github_reference,
    validate_skill_md,
    warn_skill_md,
)


# --- check_output_github_reference ---


class TestOutputGithubReference:
    def test_no_argument_hint(self):
        fm = {"name": "test-skill", "description": "Use when testing."}
        assert check_output_github_reference(fm, "some body text") == []

    def test_no_output_github_in_hint(self):
        fm = {"argument-hint": "[--auto] [focus-area]"}
        assert check_output_github_reference(fm, "some body text") == []

    def test_output_github_with_reference(self):
        fm = {"argument-hint": "[--output github|session]"}
        body = "See output guide (`skills/_shared/output-guide.md`)."
        assert check_output_github_reference(fm, body) == []

    def test_output_github_without_reference(self):
        fm = {"argument-hint": "[--output github|session]"}
        body = "This skill does stuff but never mentions the guide."
        errors = check_output_github_reference(fm, body)
        assert len(errors) == 1
        assert "output-guide" in errors[0]

    def test_output_github_partial_reference(self):
        fm = {"argument-hint": "[--auto] [--output github|session]"}
        body = "Follow the output-guide for formatting."
        assert check_output_github_reference(fm, body) == []

    def test_argument_hint_not_string(self):
        fm = {"argument-hint": 123}
        assert check_output_github_reference(fm, "body") == []


# --- check_auto_no_ask_user ---


class TestAutoNoAskUser:
    def test_no_argument_hint(self):
        fm = {"name": "test-skill"}
        assert check_auto_no_ask_user(fm, "AskUserQuestion is here") == []

    def test_no_auto_in_hint(self):
        fm = {"argument-hint": "[--output github]"}
        body = "Step 1: AskUserQuestion to confirm."
        assert check_auto_no_ask_user(fm, body) == []

    def test_auto_without_ask_user(self):
        fm = {"argument-hint": "[--auto] [--output github|session]"}
        body = "This skill runs non-interactively. No questions asked."
        assert check_auto_no_ask_user(fm, body) == []

    def test_auto_with_ask_user(self):
        fm = {"argument-hint": "[--auto] [focus-area]"}
        body = "Step 3: Use AskUserQuestion to confirm scope."
        errors = check_auto_no_ask_user(fm, body)
        assert len(errors) == 1
        assert "AskUserQuestion" in errors[0]
        assert "--auto" in errors[0]

    def test_argument_hint_not_string(self):
        fm = {"argument-hint": 42}
        assert check_auto_no_ask_user(fm, "AskUserQuestion") == []


# --- check_allowed_tools_usage ---


class TestAllowedToolsUsage:
    def test_no_allowed_tools(self):
        fm = {"name": "test-skill"}
        assert check_allowed_tools_usage(fm, "body") == []

    def test_all_tools_referenced(self):
        fm = {"allowed-tools": "Bash(git *), Read, Grep"}
        body = "Use git to commit. Read files. Grep for patterns."
        assert check_allowed_tools_usage(fm, body) == []

    def test_unreferenced_plain_tool(self):
        fm = {"allowed-tools": "Read, Write, Glob"}
        body = "Read the file. Write the result."
        warnings = check_allowed_tools_usage(fm, body)
        assert len(warnings) == 1
        assert "Glob" in warnings[0]

    def test_unreferenced_bash_command(self):
        fm = {"allowed-tools": "Bash(git *), Bash(gh *), Bash(curl *)"}
        body = "Run git log and gh pr create."
        warnings = check_allowed_tools_usage(fm, body)
        assert len(warnings) == 1
        assert "curl" in warnings[0]

    def test_list_format(self):
        fm = {"allowed-tools": ["Bash(git *)", "Read", "Agent"]}
        body = "Use git to check status. Read the file."
        warnings = check_allowed_tools_usage(fm, body)
        assert len(warnings) == 1
        assert "Agent" in warnings[0]

    def test_empty_allowed_tools(self):
        fm = {"allowed-tools": ""}
        assert check_allowed_tools_usage(fm, "body") == []

    def test_bash_pattern_with_path(self):
        fm = {"allowed-tools": 'Bash("/Applications/Google*)'}
        body = "Launch Google Chrome at /Applications/Google Chrome."
        # The command extracted is "/Applications/Google" -- tricky path pattern
        # Should not crash
        check_allowed_tools_usage(fm, body)


# --- Integration: validate_skill_md with behavioral checks ---


class TestValidateSkillMdBehavioral:
    def _write_skill(self, frontmatter: str, body: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, prefix="skill_")
        tmp.write(f"---\n{frontmatter}---\n{body}")
        tmp.flush()
        return Path(tmp.name)

    def test_output_github_error_in_validate(self):
        fm = (
            "name: test-skill\n"
            'description: "Use when you want to test output github validation checks."\n'
            'argument-hint: "[--output github|session]"\n'
        )
        body = "x" * 250  # meets body length, no output-guide reference
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            output_errors = [e for e in errors if "output-guide" in e]
            assert len(output_errors) == 1
        finally:
            path.unlink()

    def test_auto_ask_user_error_in_validate(self):
        fm = (
            "name: test-skill\n"
            'description: "Use when you want to test auto mode constraint validation."\n'
            'argument-hint: "[--auto]"\n'
        )
        body = "x" * 200 + "\nUse AskUserQuestion to confirm.\n"
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            auto_errors = [e for e in errors if "AskUserQuestion" in e]
            assert len(auto_errors) == 1
        finally:
            path.unlink()

    def test_clean_skill_passes(self):
        fm = (
            "name: test-skill\n"
            'description: "Use when you want to verify a fully compliant skill passes validation."\n'
            'argument-hint: "[--auto] [--output github|session]"\n'
            "allowed-tools: Bash(git *), Read\n"
        )
        body = "Run git commands. Read files. See output-guide.md for formatting. " + "x" * 200
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            assert errors == []
        finally:
            path.unlink()


# --- warn_skill_md integration ---


class TestWarnSkillMd:
    def _write_skill(self, frontmatter: str, body: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, prefix="skill_")
        tmp.write(f"---\n{frontmatter}---\n{body}")
        tmp.flush()
        return Path(tmp.name)

    def test_warns_on_unreferenced_tool(self):
        fm = 'name: test-skill\ndescription: "Use when testing."\nallowed-tools: Bash(git *), Agent\n'
        body = "Use git to commit." + "x" * 200
        path = self._write_skill(fm, body)
        try:
            warnings = warn_skill_md(path)
            assert len(warnings) == 1
            assert "Agent" in warnings[0]
        finally:
            path.unlink()

    def test_no_warnings_when_all_referenced(self):
        fm = 'name: test-skill\ndescription: "Use when testing."\nallowed-tools: Bash(git *), Read\n'
        body = "Use git and Read." + "x" * 200
        path = self._write_skill(fm, body)
        try:
            warnings = warn_skill_md(path)
            assert warnings == []
        finally:
            path.unlink()

    def test_missing_file_returns_empty(self):
        path = Path("/tmp/nonexistent_skill_xyz.md")
        assert warn_skill_md(path) == []
