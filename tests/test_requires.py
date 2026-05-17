"""Unit tests for the requires field validation and dependency checking.

Tests boundary conditions for validate_requires() and check_dependencies().
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add scripts/ to path so skill_checks is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import (
    check_dependencies,
    parse_frontmatter,
    validate_requires,
    validate_skill_md,
)


# --- validate_requires: valid inputs ---


class TestValidateRequiresValid:
    def test_empty_list(self):
        assert validate_requires([]) == []

    def test_single_cli(self):
        assert validate_requires([{"cli": "gh"}]) == []

    def test_single_env(self):
        assert validate_requires([{"env": "VERCEL_TOKEN"}]) == []

    def test_cli_with_reason(self):
        assert validate_requires([{"cli": "gh", "reason": "GitHub API"}]) == []

    def test_env_with_reason(self):
        assert validate_requires([{"env": "API_KEY", "reason": "Auth"}]) == []

    def test_cli_with_version_constraint(self):
        assert validate_requires([{"cli": "gh>=2.0"}]) == []

    def test_cli_with_semver_constraint(self):
        assert validate_requires([{"cli": "python3>=3.10"}]) == []

    def test_cli_with_three_part_version(self):
        assert validate_requires([{"cli": "dbt>=1.7.0"}]) == []

    def test_multiple_entries(self):
        entries = [
            {"cli": "gh>=2.0", "reason": "GitHub"},
            {"cli": "vercel", "reason": "Deploy"},
            {"env": "VERCEL_TOKEN", "reason": "Auth"},
        ]
        assert validate_requires(entries) == []

    def test_cli_with_underscores_and_dots(self):
        assert validate_requires([{"cli": "docker-compose"}]) == []
        assert validate_requires([{"cli": "python3.11"}]) == []


# --- validate_requires: invalid inputs ---


class TestValidateRequiresInvalid:
    def test_not_a_list(self):
        errors = validate_requires("gh")
        assert len(errors) == 1
        assert "must be a list" in errors[0]

    def test_entry_not_a_dict(self):
        errors = validate_requires(["gh"])
        assert len(errors) == 1
        assert "must be a mapping" in errors[0]

    def test_missing_cli_and_env(self):
        errors = validate_requires([{"reason": "oops"}])
        assert len(errors) == 1
        assert "'cli' or 'env'" in errors[0]

    def test_both_cli_and_env(self):
        errors = validate_requires([{"cli": "gh", "env": "GH_TOKEN"}])
        assert len(errors) == 1
        assert "exactly one" in errors[0]

    def test_unknown_key(self):
        errors = validate_requires([{"cli": "gh", "version": "2.0"}])
        assert len(errors) == 1
        assert "unknown key" in errors[0]

    def test_empty_cli_string(self):
        errors = validate_requires([{"cli": ""}])
        assert len(errors) == 1
        assert "non-empty string" in errors[0]

    def test_cli_not_string(self):
        errors = validate_requires([{"cli": 123}])
        assert len(errors) == 1
        assert "non-empty string" in errors[0]

    def test_invalid_version_constraint(self):
        errors = validate_requires([{"cli": "gh>2.0"}])
        assert len(errors) == 1
        assert "invalid version constraint" in errors[0]

    def test_invalid_version_constraint_lte(self):
        errors = validate_requires([{"cli": "gh<=2.0"}])
        assert len(errors) == 1
        assert "invalid version constraint" in errors[0]

    def test_reason_not_string(self):
        errors = validate_requires([{"cli": "gh", "reason": 42}])
        assert len(errors) == 1
        assert "reason must be a string" in errors[0]

    def test_multiple_errors(self):
        entries = [
            {"cli": ""},  # empty cli
            "not-a-dict",  # not a mapping
            {"reason": "x"},  # missing cli/env
        ]
        errors = validate_requires(entries)
        assert len(errors) == 3


# --- validate_skill_md with requires ---


class TestValidateSkillMdRequires:
    def _write_skill(self, frontmatter: str, body: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, prefix="skill_"
        )
        tmp.write(f"---\n{frontmatter}---\n{body}")
        tmp.flush()
        return Path(tmp.name)

    def test_valid_requires_passes(self):
        fm = 'name: test-skill\ndescription: "Use when you need to test the requires field validation logic."\nrequires:\n  - cli: gh\n    reason: "GitHub"\n'
        body = "x" * 250
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            requires_errors = [e for e in errors if "requires" in e]
            assert requires_errors == []
        finally:
            path.unlink()

    def test_invalid_requires_caught(self):
        fm = 'name: test-skill\ndescription: "Use when you need to test the requires field with invalid data."\nrequires: "not a list"\n'
        body = "x" * 250
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            requires_errors = [e for e in errors if "requires" in e]
            assert len(requires_errors) == 1
            assert "must be a list" in requires_errors[0]
        finally:
            path.unlink()

    def test_requires_field_is_known(self):
        """requires should not trigger 'unknown field' error."""
        fm = 'name: test-skill\ndescription: "Use when you need to verify that requires is a recognized field."\nrequires:\n  - cli: gh\n'
        body = "x" * 250
        path = self._write_skill(fm, body)
        try:
            errors = validate_skill_md(path, dir_name="test-skill")
            unknown_errors = [e for e in errors if "unknown field" in e]
            assert unknown_errors == []
        finally:
            path.unlink()


# --- check_dependencies: runtime check ---


class TestCheckDependencies:
    def test_available_cli(self):
        # 'python3' should be on PATH in any test environment
        results = check_dependencies([{"cli": "python3"}])
        assert len(results) == 1
        assert results[0]["type"] == "cli"
        assert results[0]["name"] == "python3"
        assert results[0]["available"] is True

    def test_unavailable_cli(self):
        results = check_dependencies([{"cli": "nonexistent_tool_xyz_42"}])
        assert len(results) == 1
        assert results[0]["available"] is False

    def test_version_constraint_stripped_for_lookup(self):
        # The tool name 'python3' should be found even with a version spec
        results = check_dependencies([{"cli": "python3>=3.10"}])
        assert results[0]["name"] == "python3"
        assert results[0]["spec"] == "python3>=3.10"
        assert results[0]["available"] is True

    def test_env_available(self):
        with patch.dict(os.environ, {"TEST_DEP_VAR": "some_value"}):
            results = check_dependencies([{"env": "TEST_DEP_VAR"}])
            assert results[0]["available"] is True

    def test_env_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            # Ensure the var isn't set
            os.environ.pop("UNLIKELY_ENV_VAR_XYZ_999", None)
            results = check_dependencies([{"env": "UNLIKELY_ENV_VAR_XYZ_999"}])
            assert results[0]["available"] is False

    def test_reason_preserved(self):
        results = check_dependencies([{"cli": "python3", "reason": "Python runtime"}])
        assert results[0]["reason"] == "Python runtime"

    def test_empty_list(self):
        assert check_dependencies([]) == []

    def test_mixed_entries(self):
        with patch.dict(os.environ, {"MY_TOKEN": "x"}):
            results = check_dependencies(
                [
                    {"cli": "python3", "reason": "runtime"},
                    {"env": "MY_TOKEN", "reason": "auth"},
                    {"cli": "nonexistent_xyz_99"},
                ]
            )
            assert results[0]["available"] is True
            assert results[1]["available"] is True
            assert results[2]["available"] is False


# --- Integration: parse real skill frontmatter with requires ---


class TestParseFrontmatterWithRequires:
    def test_parse_dbt_skill(self):
        skill_path = REPO_ROOT / "skills" / "dbt" / "SKILL.md"
        if not skill_path.exists():
            return  # skip if running outside repo
        parsed = parse_frontmatter(skill_path)
        assert parsed is not None
        fm, _ = parsed
        assert "requires" in fm
        assert isinstance(fm["requires"], list)
        assert fm["requires"][0]["cli"] == "dbt"

    def test_parse_neon_branch_skill(self):
        skill_path = REPO_ROOT / "skills" / "neon-branch" / "SKILL.md"
        if not skill_path.exists():
            return
        parsed = parse_frontmatter(skill_path)
        assert parsed is not None
        fm, _ = parsed
        assert "requires" in fm
        cli_names = [e["cli"] for e in fm["requires"]]
        assert "neonctl" in cli_names
        assert "psql" in cli_names
