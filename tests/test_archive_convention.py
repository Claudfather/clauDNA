"""documentation-standard §6 owns the archive procedure (#441).

Archiving a plan session was a bare `git mv` in five places, and none of them
touched frontmatter, so archived plans kept saying `draft` or `active`
(Claudron#232). §6 now moves the docs and gives each a terminal `status:`.
Every other place that archives points there instead of restating the move,
and `/claudna:session` handoff flags what slipped through.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS = REPO_ROOT / "skills"
STANDARD = SKILLS / "_shared" / "documentation-standard.md"


def section(text: str, number: int) -> str:
    """`## <number>.` up to the next `## ` heading."""
    m = re.search(rf"^## {number}\..*?(?=^## )", text, re.M | re.S)
    assert m, f"§{number} not found"
    return m.group(0)


def test_every_archive_move_points_at_section_6() -> None:
    seen, offenders = [], []
    for md in sorted(SKILLS.rglob("*.md")):
        if md == STANDARD:
            continue
        for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if "git mv" in line and "archive" in line.lower():
                seen.append(f"{md.relative_to(REPO_ROOT)}:{n}")
                if not ("documentation-standard" in line and "§6" in line):
                    offenders.append(seen[-1])
    assert seen, "no archive instruction found under skills/"
    assert offenders == [], offenders


def test_section_6_closes_the_frontmatter() -> None:
    six = section(STANDARD.read_text(encoding="utf-8"), 6)
    assert "git mv" in six
    for token in ("terminal", "`status:`", "`updated:`", "`superseded_by:`"):
        assert token in six, token
    # audit, review and person have no `superseded`: the rule must check the type first.
    assert "its type has `superseded`" in six


def test_handoff_flags_both_kinds_of_drift() -> None:
    handoff = (SKILLS / "session" / "handoff.md").read_text(encoding="utf-8")
    assert "documentation/archive/" in handoff
    assert "Archive (documentation-standard §6)" in handoff
    assert "Set terminal statuses (documentation-standard §6)" in handoff
    # A phase that was never started has no marker, so the scan lists the phases themselves.
    assert '--include="[0-9][0-9]_*.md"' in handoff


def test_a_session_without_phases_is_never_due() -> None:
    """'Every phase complete' alone is vacuously true of a retro or a decision session."""
    six = section(STANDARD.read_text(encoding="utf-8"), 6)
    handoff = (SKILLS / "session" / "handoff.md").read_text(encoding="utf-8")
    assert "at least one phase" in six
    assert "at least one phase" in handoff


def test_the_reaper_leaves_the_flags_to_handoff() -> None:
    """Resume reaps before it briefs: the `✅ COMPLETE` drop must not eat the archive flag."""
    reaper = (SKILLS / "_shared" / "reaper-rules.md").read_text(encoding="utf-8")
    assert "Archive (documentation-standard §6):" in reaper
    assert "Set terminal statuses (documentation-standard §6):" in reaper
