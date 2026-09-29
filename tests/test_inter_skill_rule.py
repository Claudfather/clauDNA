"""SKILL_CONTRACT §2.1 (#336): on a host without namespaced commands,
`/claudna:<name> [args]` means "invoke the skill <name>". That rewrite covers
every reference only if every name it meets is a skill directory -- the premise
this test pins across skills/, independently of the validator's own check."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS = REPO_ROOT / "skills"


def test_every_claudna_name_in_skill_text_has_a_skill_directory() -> None:
    names: dict[str, str] = {}
    for md in sorted(SKILLS.rglob("*.md")):
        for m in re.finditer(r"/claudna:([a-z0-9][a-z0-9-]*)", md.read_text()):
            names.setdefault(m.group(1), str(md.relative_to(REPO_ROOT)))
    assert len(names) > 10, names
    missing = {name: where for name, where in names.items() if not (SKILLS / name / "SKILL.md").is_file()}
    assert missing == {}, missing
