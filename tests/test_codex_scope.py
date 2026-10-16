"""Codex publication is an explicit host/context scope, never default discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from skill_checks import validate_hosts  # noqa: E402


def fixture(tmp_path):
    root = tmp_path / "repo"
    (root / ".codex-plugin").mkdir(parents=True)
    for name, metadata in {"portable": "", "orientation": "hosts: [claude-code, codex]\n",
                           "claude-only": "hosts: [claude-code]\n",
                           "source-only": "requires-context: repo-clone\n"}.items():
        skill = root / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Use when testing host scope.\n{metadata}---\n")
    set_skills(root, ["./skills/portable", "./skills/orientation"])
    return root


def set_skills(root, skills):
    (root / ".codex-plugin/plugin.json").write_text(json.dumps({"skills": skills}))


def check(root):
    from check_codex_scope import run_check
    return run_check(root)[0]


def test_codex_is_a_recognized_host():
    assert validate_hosts(["claude-code", "codex"]) == []


def test_explicit_scope_includes_only_portable_existing_skills(tmp_path):
    assert check(fixture(tmp_path)) == []


@pytest.mark.parametrize("skills", [None, [], "./skills", ["./skills"], ["./skills/portable"]])
def test_missing_empty_default_or_incomplete_catalog_fails(tmp_path, skills):
    root = fixture(tmp_path)
    set_skills(root, skills)
    assert check(root)


@pytest.mark.parametrize("entry", ["./skills/claude-only", "./skills/source-only", "./skills/missing",
                                   "../elsewhere", "/tmp", "./skills/portable"])
def test_excluded_unknown_external_and_duplicate_entries_fail(tmp_path, entry):
    root = fixture(tmp_path)
    set_skills(root, ["./skills/portable", "./skills/orientation", entry])
    assert check(root)


def test_real_catalog_has_36_codex_35_cursor_39_canonical():
    from check_codex_scope import selected_names
    from check_cursor_scope import _declared_cursor_skills
    assert len(selected_names(ROOT)) == 36
    assert len(_declared_cursor_skills(ROOT / ".cursor-plugin")[0]) == 35
    assert len(list((ROOT / "skills").glob("*/SKILL.md"))) == 39
