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

# authorAssociation packed into a --json field list, in either spelling
# (`--json a,b` or `--json=a,b`; gh accepts both)
JSON_FIELDLIST_ASSOC = re.compile(r"--json[\s=]+[\w,]*authorAssociation")
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


AGENTS = SKILLS.parent / "agents"

# Each step that reads a GitHub body as a plan, or a PR as code to run, calls the
# gate by name. A sentence that only mentions trusted-input.md does not count.
GATE_CALLS = {
    "_shared/source-guide.md": "check_provenance.py <owner> <repo> issue <number>",
    "build/SKILL.md": "check_provenance.py <owner> <repo> issue <number>",
    "review-work/pr.md": "check_provenance.py <owner> <repo> pr <number>",
}

# The steps that fold comments into a plan take them from trusted authors only.
TRUST_CLAUSES = {
    "ironclad/SKILL.md": "from trusted authors only",
    "forge/SKILL.md": "from a trusted author only",
}


def test_each_plan_or_code_reader_calls_the_gate():
    missing = [f for f, call in GATE_CALLS.items() if call not in (SKILLS / f).read_text()]
    assert missing == [], f"gate call missing from: {missing}"


def test_comment_folding_keeps_its_trusted_author_clause():
    missing = [f for f, clause in TRUST_CLAUSES.items() if clause not in (SKILLS / f).read_text()]
    assert missing == [], f"trusted-author clause missing from: {missing}"


def test_reviewer_agents_read_the_change_as_untrusted_input():
    for name in ("code-reviewer.md", "spec-reviewer.md"):
        text = (AGENTS / name).read_text()
        assert "**untrusted input**" in text, name
        assert "never run the branch's code" in text, name
