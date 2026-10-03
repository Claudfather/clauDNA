"""clauDNA's mirrors of Claudron's contract, checked against the vendored copy.

``contracts/claudron.json`` is ``claudron contract --json`` from the release
``contracts/claudron.ref`` names (``scripts/sync_claudron_contract.py``). These
tests read only that copy, so they run everywhere, with no engine installed.
Whether the copy still matches a real engine is ``tests/contract/``'s job: it
runs in this repo's contract CI leg against the pinned release, and in
Claudron's CI against every Claudron change.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from claudna.session_store import filing

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = json.loads((REPO_ROOT / "contracts" / "claudron.json").read_text(encoding="utf-8"))
SUMMARY_SCHEMA = REPO_ROOT / "lib" / "claudna" / "session_store" / "schemas" / "segment-summary.schema.json"

#: Sections harvest never files a fact under: Claudron keeps superseded facts in History and refuses a
#: write there; a decision's Supersedes is its relation, not a fact.
UNFILED_SECTIONS = ("History", "Supersedes")
#: Homes harvest never files under: a person note needs the user's own assertion (Claudron#200 §2).
UNFILED_HOMES = ("person",)


def test_the_copy_is_the_shape_this_side_reads():
    assert CONTRACT["contract_version"] == 1
    assert re.fullmatch(r"v\d+\.\d+\.\d+", (REPO_ROOT / "contracts" / "claudron.ref").read_text().strip())


class TestHomes:
    def test_each_homes_sections_are_claudrons_minus_the_unfiled_ones(self):
        engine = {home: tuple(s for s in sections if s not in UNFILED_SECTIONS)
                  for home, sections in CONTRACT["homes"].items() if home not in UNFILED_HOMES}
        assert filing.HOME_SECTIONS == engine

    @pytest.mark.parametrize("home", sorted(filing.HOME_DEFAULT_SECTION))
    def test_a_homes_default_section_is_one_of_its_sections(self, home):
        assert filing.HOME_DEFAULT_SECTION[home] in CONTRACT["homes"][home]
        assert filing.HOME_DEFAULT_SECTION[home] not in UNFILED_SECTIONS

    def test_every_filed_home_has_a_default_section(self):
        assert set(filing.HOME_DEFAULT_SECTION) == set(filing.HOME_SECTIONS)

    def test_the_summary_schemas_home_enum_is_claudrons_homes(self):
        """The summarizer may only name a home Claudron has: every ``home`` enum in the schema."""
        def enums(node):
            if isinstance(node, dict):
                if "home" in node.get("properties", {}):
                    yield node["properties"]["home"]["enum"]
                for child in node.values():
                    yield from enums(child)
            elif isinstance(node, list):
                for child in node:
                    yield from enums(child)

        found = list(enums(json.loads(SUMMARY_SCHEMA.read_text(encoding="utf-8"))))
        assert found, "the summary schema names no home enum: this test reads the wrong place"
        for enum in found:
            assert enum == list(CONTRACT["homes"])


class TestVocabulary:
    def test_every_capability_harvest_gates_on_is_one_claudron_declares(self):
        used = {*filing.FILING_CAPS, filing.HOMES_CAP, filing.RUN_CAP, filing.TRUST_CAP}
        assert used <= set(CONTRACT["capabilities"])

    def test_every_type_harvest_writes_is_a_claudron_type(self):
        """``knowledge`` on an engine without homes; the block's home with them."""
        assert {"knowledge", *filing.HOME_SECTIONS} <= set(CONTRACT["types"])

    def test_the_provenance_harvest_writes_and_reads_is_claudrons(self):
        assert {"session", "inline"} <= set(CONTRACT["source_types"])
        assert "draft" in CONTRACT["maturity"]
        assert "external" in CONTRACT["trust_classes"]  # filing._is_subject_draft reads it
