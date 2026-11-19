"""The session skill pre-approves reads only.

Its steps write through one door, the session-store CLI, which runs under the
host's own permission controls rather than a frontmatter grant. So the
frontmatter grants no write tool and no ``mv`` or ``mkdir``, and each
``git branch``, ``git log``, ``git stash``, ``git worktree``, ``grep`` and
``date`` grant is a command one of the steps runs, not a prefix that takes any
arguments.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "session"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import skill_checks  # noqa: E402
from skill_frontmatter import parse_frontmatter  # noqa: E402

# The whole list, in order: a change to the session skill's grants changes this
# list in the same commit.
GRANTS = [
    "Bash(git status *)",
    "Bash(git branch --list)",
    "Bash(git branch --show-current)",
    'Bash(git log --since="30 days ago" --oneline)',
    "Bash(git log --walk-reflogs --oneline -20 HEAD)",
    "Bash(git log --oneline -10 --all --source)",
    "Bash(git rev-parse *)",
    "Bash(git stash list)",
    "Bash(git worktree list)",
    "Bash(git check-ignore *)",
    "Bash(gh pr view *)",
    "Bash(gh pr list *)",
    "Bash(ls *)",
    "Bash(wc *)",
    "Bash(date -u +%Y-%m-%dT%H:%M:%SZ)",
    'Bash(grep -rE "IN PROGRESS|PENDING|✅ COMPLETE" documentation/planning/ --include="*.md")',
    'Bash(grep -rL "✅ COMPLETE" documentation/planning/ --include="[0-9][0-9]_*.md" --exclude="00_*")',
    'Bash(grep -rn "^type:" documentation/planning/ --include="[0-9][0-9]_*.md")',
    'Bash(grep -rnE "^(type|status):" documentation/archive/ --include="*.md")',
    'Bash(grep -rL "^status:" documentation/archive/ --include="*.md")',
    "Read",
    "Glob",
]

# Commands whose arguments the steps fix: each grant of one is a whole command.
FIXED = ("git branch", "git log", "git stash", "git worktree", "grep", "date")

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
WRITE_COMMANDS = {"mv", "mkdir", "cp", "rm", "rmdir", "touch", "tee", "ln", "install"}


def frontmatter() -> dict:
    parsed = parse_frontmatter(SKILL_DIR / "SKILL.md")
    assert parsed is not None, "skills/session/SKILL.md has no frontmatter"
    return parsed[0]


def grants() -> list[str]:
    return skill_checks._parse_allowed_tools_entries(frontmatter().get("allowed-tools"))


def bash_command(grant: str) -> str | None:
    if grant.startswith("Bash(") and grant.endswith(")"):
        return grant[len("Bash(") : -1]
    return None


def steps_text() -> str:
    """The depth files the verbs follow; SKILL.md is left out, since its frontmatter holds the grants."""
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(SKILL_DIR.glob("*.md")) if p.name != "SKILL.md"
    )


def test_the_session_skill_grants_exactly_this_list():
    assert grants() == GRANTS


def test_the_session_skill_grants_no_write_tool_and_no_write_command():
    for grant in grants():
        assert grant.split("(", 1)[0] not in WRITE_TOOLS, grant
        command = bash_command(grant)
        if command is not None:
            assert command.split()[0] not in WRITE_COMMANDS, grant


def test_each_fixed_command_grant_is_a_command_a_step_runs():
    text = steps_text()
    fixed = [c for c in map(bash_command, grants()) if c and c.startswith(FIXED)]
    assert len(fixed) == 13, fixed
    for command in fixed:
        assert not command.endswith("*"), f"Bash({command}) takes any arguments"
        assert command in text, f"Bash({command}) is not a command any step runs"


def test_the_session_skill_grants_pass_the_grant_scope_check():
    assert skill_checks.check_grant_scope(frontmatter()) == []


def test_the_colon_check_flags_only_a_colon_before_the_star():
    """The old ``Bash(cmd:*)`` prefix form fails; an exact command with a colon in its pattern passes."""
    assert skill_checks.validate_allowed_tools(["Bash(git log:*)"]) != []
    assert skill_checks.validate_allowed_tools(["Bash(git log: *)"]) != []
    assert skill_checks.validate_allowed_tools(GRANTS) == []
