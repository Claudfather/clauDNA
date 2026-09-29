"""Tests for the Cursor manifest scope gate (clauDNA #340).

.cursor-plugin/plugin.json's `skills` field is the set Cursor ships. This
gate cross-checks it against each skill's own hosts/requires-context frontmatter:
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


def _make_skill(skills_dir: Path, name: str, *, hosts=None, requires_context=None) -> None:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True)
    fm_lines = [
        f"name: {name}",
        f'description: "Use when testing {name}, a synthetic fixture skill '
        f'with a body long enough to pass the length floor."',
    ]
    if hosts is not None:
        fm_lines.append(f"hosts: {hosts}")
    if requires_context is not None:
        fm_lines.append(f"requires-context: {requires_context}")
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

    def test_list_entry_leading_dot_directory_not_mangled(self, tmp_path):
        # A real (if unusual) directory name starting with a literal dot.
        # .lstrip("./") strips characters, not a prefix -- ".agents" would
        # lose its leading dot and resolve to the wrong path.
        root = _make_skills_fixture(tmp_path)
        (root / "skills" / ".agents-skill").mkdir()
        (root / "skills" / ".agents-skill" / "SKILL.md").write_text(
            "---\nname: .agents-skill\ndescription: x\n---\n" + "x" * 250
        )
        _write_cursor_manifest(root, ["./skills/.agents-skill/"])
        names, is_explicit, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names == {".agents-skill"}

    def test_list_entry_folder_of_skills_is_expanded(self, tmp_path):
        # ravi's #343 repro: a bare folder entry inside the array (Cursor's
        # own docs show this shape -- "skills": "./my-skills/" -- and real
        # published plugins nest it inside an array).
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, ["./skills/"])
        names, is_explicit, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names == {"restricted-skill", "portable-skill-a", "portable-skill-b"}
        assert is_explicit is True

    def test_list_entry_nested_folder_of_skills_is_expanded(self, tmp_path):
        # The shape ArisGuimera/MobiAI-Core actually ships: a folder-of-skills
        # nested inside skills/, not skills/ itself.
        root = _make_skills_fixture(tmp_path)
        nested = root / "skills" / "core" / "skills"
        nested.mkdir(parents=True)
        _make_skill(nested, "nested-skill")
        _write_cursor_manifest(root, ["./skills/core/skills/"])
        names, is_explicit, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names == {"nested-skill"}

    def test_list_entry_file_path_is_an_error(self, tmp_path):
        # ravi's #343 repro: a file entry (a skill's SKILL.md itself) must
        # not silently resolve to that skill's basename via Path(...).name.
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, ["./skills/portable-skill-a/SKILL.md"])
        names, _, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names is None
        assert "does not resolve to a directory" in how

    def test_list_entry_outside_skills_dir_is_an_error(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        (root / "agents").mkdir()
        _write_cursor_manifest(root, ["./agents/"])
        names, _, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names is None
        assert "outside" in how

    def test_list_entry_nonexistent_path_is_an_error(self, tmp_path):
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, ["./skills/does-not-exist/"])
        names, _, how = ccs._declared_cursor_skills(root / ".cursor-plugin")
        assert names is None
        assert "does not resolve to a directory" in how


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

    def test_folder_entry_reopens_the_exclusion_check(self, tmp_path):
        # ravi's exact #343 repro: adding a bare folder entry alongside real
        # entries must not let a restricted skill back in silently. Before
        # the fix this passed at rc 0 with the gate seeing a skill named
        # "skills"; after the fix "./skills/" expands to every skill,
        # including the restricted one, and the exclusion check fires.
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(root, ["./skills/portable-skill-a/", "./skills/"])
        errors, _, _ = ccs.run_check(root)
        assert any("restricted-skill" in e for e in errors)

    def test_file_entry_reopens_the_exclusion_check(self, tmp_path):
        # ravi's other #343 repro: a SKILL.md file entry for a RESTRICTED
        # skill must not silently resolve to that skill's own basename and
        # pass. It must error instead of ever reaching a verdict.
        root = _make_skills_fixture(tmp_path)
        _write_cursor_manifest(
            root,
            ["./skills/portable-skill-a/", "./skills/restricted-skill/SKILL.md"],
        )
        errors, _, _ = ccs.run_check(root)
        assert len(errors) == 1
        assert "could not determine" in errors[0]

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
