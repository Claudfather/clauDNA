"""Routing-fixture matrix check (epic #165, P2 step 0.5).

The skill picker routes on frontmatter descriptions. For every fixture
utterance, its anchor keywords must appear in the expected skill's
description — the deterministic CI proxy for routing quality across the
consolidation epic. The richer manual protocol (fresh-session picker runs,
2-of-3 pass rule) is documented in the fixture file header and runs at
phase boundaries, not in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import parse_frontmatter

FIXTURES = Path(__file__).parent / "fixtures" / "routing-matrix.yaml"


def load_rows() -> list[dict]:
    data = yaml.safe_load(FIXTURES.read_text())
    assert isinstance(data, dict) and isinstance(data.get("rows"), list)
    return data["rows"]


def test_fixture_schema():
    for row in load_rows():
        assert isinstance(row.get("utterance"), str) and row["utterance"]
        assert isinstance(row.get("keywords"), list) and row["keywords"]
        assert isinstance(row.get("expect"), str) and row["expect"]
        assert isinstance(row.get("phase"), str) and row["phase"]


def test_expected_skills_exist():
    missing = [
        row["expect"]
        for row in load_rows()
        if not (REPO_ROOT / "skills" / row["expect"] / "SKILL.md").is_file()
    ]
    assert not missing, (
        f"fixture rows expect nonexistent skills: {sorted(set(missing))} — "
        "a consolidation phase deleted a skill without updating its fixture rows"
    )


def test_modes_appear_in_expected_argument_hint():
    # A row's `mode` drives the manual phase-boundary protocol; a typo'd mode
    # would silently mislead it. Engines carry their verbs in argument-hint.
    failures = []
    for row in load_rows():
        mode = row.get("mode")
        if not mode:
            continue
        skill_md = REPO_ROOT / "skills" / row["expect"] / "SKILL.md"
        if not skill_md.is_file():
            continue  # covered by test_expected_skills_exist
        parsed = parse_frontmatter(skill_md)
        hint = str(parsed[0].get("argument-hint", "")) if parsed else ""
        if mode not in hint:
            failures.append(f"{row['expect']}: mode {mode!r} not in argument-hint {hint!r}")
    assert not failures, "\n".join(failures)


def test_keywords_anchor_in_expected_description():
    failures = []
    for row in load_rows():
        skill_md = REPO_ROOT / "skills" / row["expect"] / "SKILL.md"
        if not skill_md.is_file():
            continue  # covered by test_expected_skills_exist
        parsed = parse_frontmatter(skill_md)
        assert parsed is not None, f"{row['expect']}: unparseable frontmatter"
        desc = str(parsed[0].get("description", "")).lower()
        for kw in row["keywords"]:
            if str(kw).lower() not in desc:
                failures.append(
                    f"{row['expect']}: keyword {kw!r} (utterance: {row['utterance']!r}) "
                    "not in description — routing anchor lost"
                )
    assert not failures, "\n".join(failures)
