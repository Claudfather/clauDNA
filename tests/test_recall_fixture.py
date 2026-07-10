"""Retrieval-delta fixture check (#202, epic #197 Track B).

`/claudna:recall` renders `claudron recall --json` as a two-tier orientation
briefing (skills/recall/SKILL.md Step 2). It is a prose (LLM-run) skill, so
there is no unit to execute — instead this fixture pins the CONTRACT the skill
renders against:

  1. The committed vault (fixtures/recall-vault/) is well-formed: a project
     tier (knowledge/demo-service/) and a fleet tier (shared/), each note
     carrying the frontmatter fields the briefing line shows.
  2. SCENARIO.md documents the retrieval delta — a bare recall leads with the
     project (recency); a --query recall leads with the fleet (relevance).
  3. skills/recall/SKILL.md stays aligned with the recall envelope documented
     in claudron-engine.md §2 (the four data keys, the score-null tier signal,
     the adaptive lead). If Claudron's envelope drifts and the engine contract
     is updated, this flags a recall skill that wasn't.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "recall-vault"
RECALL = REPO_ROOT / "skills" / "recall" / "SKILL.md"
ENGINE = REPO_ROOT / "skills" / "_shared" / "claudron-engine.md"


def _frontmatter(path: Path) -> dict:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path.name}: no frontmatter"
    _, fm, _body = text.split("---\n", 2)
    data = yaml.safe_load(fm)
    assert isinstance(data, dict), f"{path.name}: frontmatter is not a mapping"
    return data


def test_fixture_vault_has_both_tiers():
    project = sorted((FIXTURE / "knowledge" / "demo-service").glob("*.md"))
    fleet = sorted((FIXTURE / "shared").glob("*.md"))
    assert len(project) == 2, "expected 2 project-tier notes"
    assert len(fleet) == 2, "expected 2 fleet-tier notes"
    assert (FIXTURE / "CONVENTIONS.md").is_file()


def test_fixture_notes_carry_briefing_fields():
    # The briefing line renders: **title** (type[, maturity]) — summary `path`.
    shown = {"title", "type", "status", "maturity"}
    for note in FIXTURE.rglob("*.md"):
        if note.name in ("SCENARIO.md", "CONVENTIONS.md"):
            continue
        fm = _frontmatter(note)
        missing = shown - fm.keys()
        assert not missing, f"{note.name}: missing {missing}"


def test_scenario_documents_the_delta():
    text = (FIXTURE / "SCENARIO.md").read_text()
    assert "Bare recall" in text, "scenario must document the bare-recall lead"
    assert "Queried recall" in text, "scenario must document the queried lead"
    # opposite leads, one per case
    assert "This project — most recent" in text
    assert "Fleet — most relevant" in text


def test_recall_skill_matches_engine_envelope():
    engine = ENGINE.read_text()
    # The §2 recall row is the only line naming recall + conventions + notes.
    row = next(
        line
        for line in engine.splitlines()
        if "`recall`" in line and "conventions" in line and "notes" in line
    )
    keys = set(re.findall(r"`([a-z_]+)`", row.split("|")[2]))
    assert keys == {"project", "query", "conventions", "notes"}, keys
    recall = RECALL.read_text()
    for key in keys:
        assert key in recall, f"recall skill omits envelope key '{key}'"


def test_recall_skill_documents_tier_split_and_adaptive_lead():
    recall = RECALL.read_text().lower()
    assert "score" in recall and "null" in recall, "tier signal (score null) undocumented"
    assert "adaptive" in recall, "adaptive lead undocumented"
    assert "project" in recall and "fleet" in recall
