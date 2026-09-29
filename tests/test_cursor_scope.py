"""Tests for the Cursor manifest scope gate (clauDNA #340).

.cursor-plugin/plugin.json's `skills` field is the set Cursor ships. This
gate cross-checks it against each skill's own hosts/context frontmatter:
a restricted skill must not be declared, and -- once the manifest is an
explicit list -- a portable skill must not be silently dropped either.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_cursor_scope as ccs


def _make_skill(skills_dir: Path, name: str, *, hosts=None, context=None) -> None:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True)
    fm_lines = [
        f"name: {name}",
        f'description: "Use when testing {name}, a synthetic fixture skill '
        f'with a body long enough to pass the length floor."',
    ]
    if hosts is not None:
        fm_lines.append(f"hosts: {hosts}")
    if context is not None:
        fm_lines.append(f"context: {context}")
    frontmatter = "\n".join(fm_lines)
    body = "x" * 250
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n{body}\n")


def _make_skills_fixture(tmp_path: Path) -> Path:
    """Three skills under tmp_path/skills/: one restricted, two portable,
    plus a _shared/ that must never be treated as a skill."""
    skills_dir = tmp_path / "skills"
    _make_skill(skills_dir, "restricted-skill", hosts=["claude-code"])
    _make_skill(skills_dir, "portable-skill-a")
    _make_skill(skills_dir, "portable-skill-b")
    (skills_dir / "_shared").mkdir()
    return tmp_path


def _write_cursor_manifest(root: Path, skills_value) -> None:
    cursor_dir = root / ".cursor-plugin"
    cursor_dir.mkdir(exist_ok=True)
    (cursor_dir / "plugin.json").write_text(json.dumps({"skills": skills_value}))


class TestDeclaredCursorSkills:
    def test_explicit_list_shape(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, ["./skills/portable-skill-a/"])
        names, is_explicit, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names == {"portable-skill-a"}
        assert is_explicit is True
        assert "explicit list" in how

    def test_directory_discovery_shape(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, "./skills/")
        names, is_explicit, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names == {"restricted-skill", "portable-skill-a", "portable-skill-b"}
        assert is_explicit is False
        assert "directory discovery" in how

    def test_missing_skills_field(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, ["./skills/portable-skill-a/"])
        (root / ".cursor-plugin" / "plugin.json").write_text(json.dumps({"name": "x"}))
        names, _, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names is None
        assert "no 'skills' field" in how

    def test_unreadable_json(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        (root / ".cursor-plugin").mkdir()
        (root / ".cursor-plugin" / "plugin.json").write_text("{not json")
        names, _, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names is None
        assert "not valid JSON" in how

    def test_non_string_list_entry(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, [123])
        names, _, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names is None
        assert "non-string entry" in how

    def test_skills_field_wrong_type(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, {"nested": "object"})
        names, _, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names is None
        assert "neither a string nor a list" in how


class TestRunCheck:
    def test_clean_explicit_list(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, ["./skills/portable-skill-a/", "./skills/portable-skill-b/"])
        errors, warnings, notes = ccs.run_check(root)
        assert errors == []
        assert any("explicit list" in n for n in notes)

    def test_restricted_skill_shipped_is_an_error(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(
            root,
            ["./skills/restricted-skill/", "./skills/portable-skill-a/", "./skills/portable-skill-b/"],
        )
        errors, _, _ = ccs.run_check(root)
        assert len(errors) == 1
        assert "restricted-skill" in errors[0]
        assert "#340" in errors[0]

    def test_portable_skill_missing_is_an_error(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, ["./skills/portable-skill-a/"])
        errors, _, _ = ccs.run_check(root)
        assert len(errors) == 1
        assert "portable-skill-b" in errors[0]
        assert "missing" in errors[0]

    def test_directory_discovery_never_reports_missing(self, tmp_path):
        # Directory discovery ships everything under it by construction --
        # the completeness direction is vacuous there, and must stay silent
        # even though nothing is explicitly named as shipped.
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, "./skills/")
        errors, _, _ = ccs.run_check(root)
        # restricted-skill IS shipped by directory discovery -- that half still fires.
        assert len(errors) == 1
        assert "restricted-skill" in errors[0]
        assert not any("missing" in e for e in errors)

    def test_unparseable_manifest_refuses_rather_than_passing(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        (root / ".cursor-plugin").mkdir()
        (root / ".cursor-plugin" / "plugin.json").write_text("{not json")
        errors, _, notes = ccs.run_check(root)
        assert len(errors) == 1
        assert "could not determine" in errors[0]
        assert notes == []  # a refusal, not a clean pass with nothing to say

    def test_both_directions_reported_together(self, tmp_path):
        # Declaring ONLY the restricted skill hits every rule at once: it
        # ships something excluded, AND both portable skills are missing.
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, ["./skills/restricted-skill/"])
        errors, _, _ = ccs.run_check(root)
        assert len(errors) == 3
        joined = " ".join(errors)
        assert "restricted-skill" in joined
        assert "portable-skill-a" in joined
        assert "portable-skill-b" in joined
        assert sum("missing" in e for e in errors) == 2
        assert sum("#340" in e for e in errors) == 3


class TestAgainstTheRealRepo:
    """The regression-anchoring case: the real repo's real manifest, post-#340 fix."""

    def test_real_repo_passes_clean(self):
        errors, warnings, notes = ccs.run_check(REPO_ROOT)
        assert errors == [], f"real repo should be clean: {errors}"

    def test_real_repo_uses_explicit_list(self):
        _, _, notes = ccs.run_check(REPO_ROOT)
        assert any("explicit list" in n for n in notes)
