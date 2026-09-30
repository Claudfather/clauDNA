"""Mechanical guards for the author-provenance wiring.

(a) No skill uses the field-list form `gh ... --json <...,authorAssociation,...>`:
    gh 2.92 rejects `authorAssociation` as a `--json` field, and one unknown field
    aborts the whole command, so this form fetches nothing. Provenance is read via
    scripts/check_provenance.py or `gh api ... --jq .author_association`.
    (`--json comments` is fine — each comment object carries authorAssociation.)

(b) Any skill that ingests a GitHub issue/PR body or comments references the trust
    rule (`trusted-input.md`), so an ingested body/comment is gated, not trusted
    blindly.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"

# authorAssociation packed into a --json field list (no spaces in a field list)
JSON_FIELDLIST_ASSOC = re.compile(r"--json\s+[\w,]*authorAssociation")
# a gh issue/pr view that pulls body or comments (content ingestion)
INGESTS_CONTENT = re.compile(r"gh\s+(?:issue|pr)\s+view[^\n`]*--json\s+[\w,]*(?:body|comments)")

# trusted-input.md documents the rejected form on purpose.
BAN_EXEMPT = {"_shared/trusted-input.md"}


def _md_files():
    return sorted(SKILLS.rglob("*.md"))


def test_no_skill_uses_the_rejected_json_field():
    offenders = []
    for f in _md_files():
        rel = f.relative_to(SKILLS).as_posix()
        if rel in BAN_EXEMPT:
            continue
        if JSON_FIELDLIST_ASSOC.search(f.read_text()):
            offenders.append(rel)
    assert offenders == [], f"broken --json authorAssociation field list in: {offenders}"


def test_content_ingesting_skills_reference_the_trust_rule():
    offenders = []
    for f in _md_files():
        rel = f.relative_to(SKILLS).as_posix()
        text = f.read_text()
        if INGESTS_CONTENT.search(text) and "trusted-input" not in text:
            offenders.append(rel)
    assert offenders == [], f"ingest GitHub content without referencing trusted-input.md: {offenders}"
