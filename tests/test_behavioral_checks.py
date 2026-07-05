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
    check_description_grammar,
    check_description_trigger_convention,
    check_no_raw_gh_commands,
    check_output_github_reference,
    check_skill_references,
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


# --- check_no_raw_gh_commands ---


class TestNoRawGhCommands:
    def test_clean_body(self):
        assert check_no_raw_gh_commands({}, "This skill analyzes things and writes a doc.") == []

    def test_raw_gh_issue_create_fails(self):
        body = "Then run: gh issue create --title 'foo' --body 'bar'"
        errors = check_no_raw_gh_commands({}, body)
        assert len(errors) == 1
        assert "gh issue create" in errors[0]
        assert "claudna:publish" in errors[0]

    def test_raw_gh_pr_create_fails(self):
        body = "Create the PR: gh pr create --base main --title 'x'"
        errors = check_no_raw_gh_commands({}, body)
        assert len(errors) == 1
        assert "gh pr create" in errors[0]

    def test_raw_gh_issue_comment_fails(self):
        body = "Post a summary: gh issue comment 123 --body 'done'"
        errors = check_no_raw_gh_commands({}, body)
        assert len(errors) == 1
        assert "gh issue comment" in errors[0]

    def test_raw_gh_pr_comment_fails(self):
        body = "Drop a note: gh pr comment 7 --body 'see review'"
        errors = check_no_raw_gh_commands({}, body)
        assert len(errors) == 1
        assert "gh pr comment" in errors[0]

    def test_delegation_prose_passes(self):
        # A line that names the command but points to publish is delegation guidance.
        body = "Never run `gh issue create` yourself -- delegate to /claudna:publish."
        assert check_no_raw_gh_commands({}, body) == []

    def test_issue_consumption_not_flagged(self):
        # Reading/editing issues (implement-plan) is not output publishing.
        body = "Fetch via gh issue view 5; gh issue list --state open; gh label create foo"
        assert check_no_raw_gh_commands({}, body) == []

    def test_allowlisted_skill_passes_via_validate(self):
        # publish/file-github-issue/commit-push-pr may use gh directly.
        body = "# Publish\n\nCreate it with gh issue create --repo o/r --title t.\n" + "x" * 200
        with tempfile.TemporaryDirectory() as d:
            skill = Path(d) / "SKILL.md"
            skill.write_text(
                '---\nname: publish\ndescription: "Output adapter that publishes docs '
                'to destinations."\n---\n' + body
            )
            errors = validate_skill_md(skill, dir_name="publish")
            assert not any("delegate GitHub output" in e for e in errors)

    def test_non_allowlisted_skill_fails_via_validate(self):
        body = "# Audit\n\nWhen done, gh issue create --repo o/r --title t.\n" + "x" * 200
        with tempfile.TemporaryDirectory() as d:
            skill = Path(d) / "SKILL.md"
            skill.write_text(
                '---\nname: my-audit\ndescription: "Audits the codebase for problems '
                'and reports them."\n---\n' + body
            )
            errors = validate_skill_md(skill, dir_name="my-audit")
            assert any("gh issue create" in e for e in errors)


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
        body = (
            "Run git commands. Read files. See output-guide.md for formatting. "
            "When --auto, emit the structured-result shape per orchestration-guide.md §10.C. "
            + "x" * 200
        )
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            assert errors == []
        finally:
            path.unlink()


# --- check_description_grammar ---


class TestDescriptionGrammar:
    def test_clean_trigger_description_passes(self):
        fm = {"description": "Use when tests have race conditions or timing dependencies."}
        assert check_description_grammar(fm, "body") == []

    def test_flag_token_fails(self):
        fm = {"description": "Audits the codebase. Supports --output github and --auto."}
        errors = check_description_grammar(fm, "body")
        assert len(errors) == 1
        assert "--output" in errors[0]
        assert "argument-hint" in errors[0]

    def test_single_flag_token_fails(self):
        fm = {"description": "Use at session end to write a handoff. --auto for headless callers."}
        errors = check_description_grammar(fm, "body")
        assert len(errors) == 1
        assert "--auto" in errors[0]

    def test_spaced_double_hyphen_em_dash_passes(self):
        # " -- " used as an em-dash is prose, not a flag token.
        fm = {"description": "Use when you need dbt commands -- build, test, compile -- against Snowflake."}
        assert check_description_grammar(fm, "body") == []

    def test_missing_description_ignored(self):
        assert check_description_grammar({}, "body") == []

    def test_non_string_description_ignored(self):
        assert check_description_grammar({"description": 42}, "body") == []


# --- check_description_trigger_convention (advisory) ---


class TestDescriptionTriggerConvention:
    def test_use_when_passes(self):
        fm = {"description": "Use when a frontend page has performance symptoms."}
        assert check_description_trigger_convention(fm, "body") == []

    def test_use_at_passes(self):
        fm = {"description": "Use at the end of a session to write a handoff file."}
        assert check_description_trigger_convention(fm, "body") == []

    def test_label_style_warns(self):
        fm = {"description": "Knowledge ingestion -- pull content from external sources."}
        warnings = check_description_trigger_convention(fm, "body")
        assert len(warnings) == 1
        assert "Use " in warnings[0]

    def test_missing_description_ignored(self):
        assert check_description_trigger_convention({}, "body") == []


# --- check_skill_references ---


class TestSkillReferences:
    VALID = {"publish", "implement-plan", "review-pr"}

    def test_known_reference_passes(self):
        text = "Route the doc via /claudna:publish, then /claudna:implement-plan builds it."
        assert check_skill_references(text, self.VALID) == []

    def test_unknown_reference_fails(self):
        text = "Hand off to /claudna:nonexistent-skill for the next step."
        errors = check_skill_references(text, self.VALID)
        assert len(errors) == 1
        assert "nonexistent-skill" in errors[0]

    def test_placeholder_not_matched(self):
        # Authoring docs use /claudna:<skill-name> placeholders; not a real reference.
        text = "Invoke it as /claudna:<skill-name> once created."
        assert check_skill_references(text, self.VALID) == []

    def test_repeated_unknown_reference_deduplicated(self):
        text = "See /claudna:ghost-skill. Then /claudna:ghost-skill again. And /claudna:ghost-skill."
        errors = check_skill_references(text, self.VALID)
        assert len(errors) == 1

    def test_bare_prefix_form_matched(self):
        # `claudna:review-pr` without the leading slash still counts as a reference.
        text = "The claudna:missing-thing skill handles that."
        errors = check_skill_references(text, {"review-pr"})
        assert len(errors) == 1
        assert "missing-thing" in errors[0]


# --- validate_skill_md picks up description grammar ---


class TestValidateSkillMdDescriptionGrammar:
    def test_flag_in_description_error_in_validate(self):
        body = "x" * 250
        with tempfile.TemporaryDirectory() as d:
            skill = Path(d) / "SKILL.md"
            skill.write_text(
                '---\nname: test-skill\ndescription: "Use when auditing. Supports '
                '--output github for issues."\n---\n' + body
            )
            errors = validate_skill_md(skill, dir_name="test-skill")
            assert any("--output" in e for e in errors)

    def test_clean_description_no_grammar_error(self):
        body = "x" * 250
        with tempfile.TemporaryDirectory() as d:
            skill = Path(d) / "SKILL.md"
            skill.write_text(
                '---\nname: test-skill\ndescription: "Use when you want a compliant '
                'description with no flag tokens."\n---\n' + body
            )
            errors = validate_skill_md(skill, dir_name="test-skill")
            assert not any("argument-hint" in e for e in errors)


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
