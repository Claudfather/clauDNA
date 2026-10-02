"""Tests for the catalog budget gate (``scripts/check_catalog_budget.py``).

The live-repo case is the backstop; the fixture cases are the point. Each is a
repo state the gate must reject or flag (over the ceiling, far under it, a
broken budget file, an empty walk), so the gate is shown to catch the
regression it exists for, not only to pass on today's tree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_catalog_budget as budget  # noqa: E402


def _write(path: Path, name: str, description: str, extra: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: \"{description}\"\n{extra}---\n\nBody.\n")


def _set_budget(root: Path, **ceilings) -> None:
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "catalog-budget.json").write_text(json.dumps(ceilings))


def _totals(root: Path) -> dict[str, int]:
    return {kind: sum(sizes.values()) for kind, sizes in budget.catalogs(root).items()}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Two skills, a `_shared/` that looks like one but isn't, and one agent; no budget file yet."""
    _write(tmp_path / "skills" / "alpha" / "SKILL.md", "alpha", "Use when alpha.")
    _write(tmp_path / "skills" / "beta" / "SKILL.md", "beta", "Use when beta.")
    _write(tmp_path / "skills" / "_shared" / "SKILL.md", "shared", "Not a skill, though it looks like one.")
    _write(tmp_path / "agents" / "helper.md", "helper", "Use for help.")
    return tmp_path


def test_the_live_repo_is_within_its_budget():
    errors, _, notes = budget.run_check(REPO_ROOT)
    assert errors == []
    assert {n.split(":")[0] for n in notes} == {"skills", "agents"}


def test_entry_size_is_the_listing_entry():
    assert budget.entry_size("alpha", "Use when alpha.") == len("claudna:alpha: Use when alpha.")
    assert budget.entry_size("helper", "Use for help.", "Read, Grep") == len(
        "claudna:helper: Use for help. (Tools: Read, Grep)")


def test_an_agent_counts_its_tool_list_and_all_tools_when_it_declares_none(repo):
    _write(repo / "agents" / "reader.md", "reader", "Use to read.", "tools:\n  - Read\n  - Grep\n")
    sizes = budget.catalogs(repo)["agents"]
    assert sizes["reader"] == budget.entry_size("reader", "Use to read.", "Read, Grep")
    assert sizes["helper"] == budget.entry_size("helper", "Use for help.", "*")


def test_catalogs_skip_shared_and_count_agents(repo):
    cats = budget.catalogs(repo)
    assert set(cats["skills"]) == {"alpha", "beta"}
    assert set(cats["agents"]) == {"helper"}


def test_a_skill_hidden_from_the_model_is_not_counted(repo):
    _write(repo / "skills" / "manual" / "SKILL.md", "manual", "Use when asked.", "disable-model-invocation: true\n")
    assert "manual" not in budget.catalogs(repo)["skills"]


def test_disable_model_invocation_is_a_skill_field_an_agent_is_still_counted(repo):
    _write(repo / "agents" / "sneaky.md", "sneaky", "Use for tricks.", "disable-model-invocation: true\n")
    assert "sneaky" in budget.catalogs(repo)["agents"]


def test_at_the_ceiling_passes_quietly(repo):
    _set_budget(repo, **_totals(repo))
    errors, warnings, _ = budget.run_check(repo)
    assert errors == [] and warnings == []


def test_over_the_ceiling_fails_and_names_the_number_and_the_largest(repo):
    totals = _totals(repo)
    _set_budget(repo, skills=totals["skills"] - 1, agents=totals["agents"])
    errors = budget.run_check(repo)[0]
    assert len(errors) == 1
    assert "over its" in errors[0] and f"to {totals['skills']}" in errors[0]
    assert "alpha (" in errors[0]


def test_a_new_skill_needs_the_ceiling_raised(repo):
    _set_budget(repo, **_totals(repo))
    _write(repo / "skills" / "gamma" / "SKILL.md", "gamma", "Use when gamma.")
    assert any("over its" in e for e in budget.run_check(repo)[0])


def test_under_the_ceiling_at_all_warns_with_the_new_number_but_never_fails(repo):
    totals = _totals(repo)
    _set_budget(repo, skills=totals["skills"] + 1, agents=totals["agents"])
    errors, warnings, _ = budget.run_check(repo)
    assert errors == []
    assert len(warnings) == 1 and f"to {totals['skills']}" in warnings[0]


@pytest.mark.parametrize("value", [None, 0, -5, "100", True])
def test_a_bad_ceiling_is_an_error(repo, value):
    _set_budget(repo, skills=value, agents=_totals(repo)["agents"])
    assert any("positive integer" in e for e in budget.run_check(repo)[0])


@pytest.mark.parametrize("doc", [[11806, 926], 12, "skills"])
def test_a_budget_that_is_not_an_object_is_an_error_not_a_crash(repo, doc):
    (repo / "scripts").mkdir()
    (repo / "scripts" / "catalog-budget.json").write_text(json.dumps(doc))
    errors = budget.run_check(repo)[0]
    assert len(errors) == 1 and "JSON object" in errors[0]


def test_a_missing_skills_directory_is_an_error_not_a_crash(tmp_path):
    _set_budget(tmp_path, skills=1, agents=1)
    assert any("found no skills" in e for e in budget.run_check(tmp_path)[0])


def test_a_missing_budget_file_is_an_error(repo):
    errors = budget.run_check(repo)[0]
    assert len(errors) == 1 and "unreadable" in errors[0]


def test_an_empty_catalog_is_an_error_not_a_pass(repo):
    _set_budget(repo, **_totals(repo))
    for skill in (repo / "skills").glob("*/SKILL.md"):
        skill.unlink()
    assert any("found no skills" in e for e in budget.run_check(repo)[0])


def test_main_prints_the_bill_and_exits_nonzero_only_on_an_error(monkeypatch, repo, capsys):
    monkeypatch.setattr(budget, "REPO_ROOT", repo)
    _set_budget(repo, **_totals(repo))
    assert budget.main() == 0
    assert "skills/alpha" in capsys.readouterr().out
    _set_budget(repo, skills=1, agents=1)
    assert budget.main() == 1
    assert "ERROR: skills catalog" in capsys.readouterr().out
