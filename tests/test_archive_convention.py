"""documentation-standard §6 owns the archive procedure (#441).

Archiving a plan session was a bare `git mv` in five places, and none of them
touched frontmatter, so archived plans kept saying `draft` or `active`
(Claudron#232). §6 now moves the docs and gives each a terminal `status:`.
Every other place that archives points there instead of restating the move,
and `/claudna:session` handoff flags what slipped through.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS = REPO_ROOT / "skills"
STANDARD = SKILLS / "_shared" / "documentation-standard.md"
DOCUMENTATION = REPO_ROOT / "documentation"
ARCHIVE = DOCUMENTATION / "archive"
CONTRACT = REPO_ROOT / "contracts" / "claudron.json"


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


def frontmatter(md: Path) -> dict:
    """A doc's YAML frontmatter, or {} when it has none."""
    text = md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    data = yaml.safe_load(text.split("---\n", 2)[1])
    return data if isinstance(data, dict) else {}


def test_every_archived_doc_carries_a_terminal_status() -> None:
    """The repo's own archive follows §6 (#444). The terminal sets are Claudron's, from the vendored contract."""
    statuses = json.loads(CONTRACT.read_text(encoding="utf-8"))["statuses"]
    terminal = {kind: set(vocab["terminal"]) for kind, vocab in statuses.items()}
    docs = sorted(ARCHIVE.rglob("*.md"))
    assert docs, "no doc under documentation/archive/"
    live, unlinked = [], []
    for md in docs:
        fm, name = frontmatter(md), str(md.relative_to(REPO_ROOT))
        if str(fm.get("status")) not in terminal.get(str(fm.get("type")), set()):
            live.append(f"{name}: type {fm.get('type')!r}, status {fm.get('status')!r}")
        # §6 rule 2: a quoted wikilink, since YAML reads a bare [[…]] as a list.
        link = fm.get("superseded_by")
        if (link is not None or fm.get("status") == "superseded") and not (
            isinstance(link, str) and re.fullmatch(r"\[\[[^\[\]]+\]\]", link)
        ):
            unlinked.append(f"{name}: superseded_by {link!r}")
    assert live == [], live
    assert unlinked == [], unlinked


def test_every_doc_carries_the_vocabulary() -> None:
    """Every doc under documentation/ has a type and a canonical status for it (#451).

    A plan lives in planning/ or archive/, where the standard's scans read it: `documentation/plans/` held
    eight that handoff never saw.
    """
    statuses = json.loads(CONTRACT.read_text(encoding="utf-8"))["statuses"]
    canonical = {kind: set(vocab["canonical"]) for kind, vocab in statuses.items()}
    off, stray = [], []
    for md in sorted(DOCUMENTATION.rglob("*.md")):
        fm, name = frontmatter(md), md.relative_to(DOCUMENTATION)
        if str(fm.get("status")) not in canonical.get(str(fm.get("type")), set()):
            off.append(f"{name}: type {fm.get('type')!r}, status {fm.get('status')!r}")
        if fm.get("type") == "plan" and name.parts[0] not in ("planning", "archive"):
            stray.append(str(name))
    assert off == [], off
    assert stray == [], stray


def test_handoff_flags_both_kinds_of_drift() -> None:
    handoff = (SKILLS / "session" / "handoff.md").read_text(encoding="utf-8")
    assert "documentation/archive/" in handoff
    assert "Archive (documentation-standard §6)" in handoff
    assert "Set terminal statuses (documentation-standard §6)" in handoff
    # A phase that was never started has no marker, so the scan lists the phases themselves.
    assert '--include="[0-9][0-9]_*.md"' in handoff


def test_a_session_without_phases_is_never_due() -> None:
    """'Every phase complete' alone is vacuously true of a retro or a decision session."""
    text = STANDARD.read_text(encoding="utf-8")
    handoff = (SKILLS / "session" / "handoff.md").read_text(encoding="utf-8")
    assert "at least one phase" in section(text, 6)
    assert "at least one phase" in section(text, 8)  # the scan's comment states it too (#448)
    assert "at least one phase" in handoff


def test_a_standalone_plan_doc_has_an_archive_trigger() -> None:
    """§6 named a trigger for sessions only, though handoff flags a finished standalone doc (#448).

    Both say it must carry `✅ COMPLETE`: "every marker is complete" alone is
    vacuously true of a doc with no markers, the hole "at least one phase" closes.
    """
    six = section(STANDARD.read_text(encoding="utf-8"), 6)
    handoff = (SKILLS / "session" / "handoff.md").read_text(encoding="utf-8")
    assert "a standalone plan doc when it carries `✅ COMPLETE` and no other marker" in six
    assert "carries `✅ COMPLETE` and neither of the others" in handoff
    build = (SKILLS / "build" / "SKILL.md").read_text(encoding="utf-8")
    assert "makes a standalone plan doc due for archiving" in step(build, 7)


def test_the_reaper_leaves_the_flags_to_handoff() -> None:
    """Resume reaps before it briefs: the `✅ COMPLETE` drop must not eat the archive flag."""
    reaper = (SKILLS / "_shared" / "reaper-rules.md").read_text(encoding="utf-8")
    assert "Archive (documentation-standard §6):" in reaper
    assert "Set terminal statuses (documentation-standard §6):" in reaper


def step(text: str, number: int) -> str:
    """`### Step <number>:` up to the next `### ` heading."""
    m = re.search(rf"^### Step {number}:.*?(?=^### )", text, re.M | re.S)
    assert m, f"Step {number} not found"
    return m.group(0)


def test_the_archive_lands_through_a_pull_request() -> None:
    """A protected main rejects a direct push (#447), so finished work carries its archive in its final PR."""
    six = section(STANDARD.read_text(encoding="utf-8"), 6)
    assert "through a pull request, never a direct push" in six
    assert "`/claudna:build` archives in Step 7" in six
    build = (SKILLS / "build" / "SKILL.md").read_text(encoding="utf-8")
    # Step 7 archives on the PR branch; Step 8 runs after the switch to main, so it never moves docs itself.
    assert "git mv" in step(build, 7)
    eight = step(build, 8)
    assert "git mv" not in eight
    assert "its own branch and PR" in eight
    assert "merge the archive PR" in eight
