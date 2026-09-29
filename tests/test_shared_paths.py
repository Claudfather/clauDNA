"""`_shared/` paths are relative to the file they are written in (#336).

SKILL_CONTRACT §1 and §5.1. The positive controls pin that the accepted
spelling passes at every depth; each violation case is one mutant of that
spelling, and each must be reported exactly once, on its own line.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import (  # noqa: E402
    _shared_path_spans,
    check_shared_paths,
    rewrite_shared_paths,
    shared_path_findings,
)


@pytest.fixture
def skills(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    (root / "_shared" / "contracts").mkdir(parents=True)
    (root / "_shared" / "guide.md").write_text("# guide\n")
    (root / "_shared" / "contracts" / "c.md").write_text("# c\n")
    (root / "demo" / "sub").mkdir(parents=True)
    (root / "demo" / "SKILL.md").write_text("# demo\n")
    return root


def _findings(skills: Path, rel: str, body: str) -> list:
    md_file = skills / rel
    md_file.write_text(body)
    return shared_path_findings(body, md_file, skills)


@pytest.mark.parametrize(
    ("rel", "body"),
    [
        ("demo/SKILL.md", "Read `../_shared/guide.md` §3.\n"),
        ("demo/sub/deep.md", "Read `../../_shared/guide.md` and ../../_shared/contracts/c.md.\n"),
        ("_shared/other.md", "See `../_shared/contracts/c.md`.\n"),
        ("_shared/contracts/d.md", "See [the guide](../../_shared/guide.md#rules).\n"),
        ("demo/SKILL.md", "The `../_shared/` directory and `../_shared/contracts/`.\n"),
        ("demo/SKILL.md", "Not paths: foo_shared/x.md, my-_shared/x.md, the _shared dir.\n"),
        ("demo/sub/deep.md", "Forwarded: Read <claudna-root>/skills/_shared/contracts/c.md first.\n"),
        ("demo/SKILL.md", "Not a path: https://github.com/o/r/blob/main/skills/_shared/guide.md\n"),
    ],
)
def test_the_file_relative_spelling_passes(skills: Path, rel: str, body: str) -> None:
    assert _findings(skills, rel, body) == []


@pytest.mark.parametrize(
    ("rel", "written", "spelling"),
    [
        ("demo/SKILL.md", "skills/_shared/guide.md", "../_shared/guide.md"),
        ("demo/SKILL.md", "_shared/guide.md", "../_shared/guide.md"),
        ("demo/sub/deep.md", "../_shared/guide.md", "../../_shared/guide.md"),
        ("demo/sub/deep.md", "skills/_shared/contracts/c.md", "../../_shared/contracts/c.md"),
        ("_shared/contracts/d.md", "../_shared/guide.md", "../../_shared/guide.md"),
        ("demo/SKILL.md", "../../skills/_shared/guide.md", "../_shared/guide.md"),
        ("demo/SKILL.md", "${CLAUDE_PLUGIN_ROOT}/skills/_shared/guide.md", "<claudna-root>/skills/_shared/guide.md"),
        ("demo/SKILL.md", "${CLAUDE_SKILL_DIR}/../_shared/guide.md", "<claudna-root>/skills/_shared/guide.md"),
        ("demo/SKILL.md", "~/.claude/skills/_shared/guide.md", "<claudna-root>/skills/_shared/guide.md"),
        ("demo/SKILL.md", "<claudna-root>/skills/_shared/missing.md", None),
        ("demo/SKILL.md", "../_shared/missing.md", None),
        ("demo/SKILL.md", "../_shared/../demo/SKILL.md", None),
    ],
)
def test_each_violation_is_reported_once_on_its_line(
    skills: Path, rel: str, written: str, spelling: str | None
) -> None:
    body = f"intro\n\nuse `{written}` here\n"
    assert _findings(skills, rel, body) == [(3, written, spelling)]


def test_the_validator_message_names_the_file_line_and_the_fix(skills: Path) -> None:
    md_file = skills / "demo" / "sub" / "deep.md"
    body = "x\n`skills/_shared/guide.md`\n"
    md_file.write_text(body)
    [message] = check_shared_paths(body, md_file, skills)
    assert message.startswith("demo/sub/deep.md:2: `skills/_shared/guide.md` is not relative to this file")
    assert "write `../../_shared/guide.md`" in message


def test_rewrite_fixes_what_it_can_and_leaves_the_rest_reported(skills: Path) -> None:
    md_file = skills / "demo" / "sub" / "deep.md"
    body = "a `skills/_shared/guide.md` b\nc _shared/contracts/c.md, `../_shared/missing.md`\n"
    new, count = rewrite_shared_paths(body, md_file, skills)
    assert count == 2
    assert new == "a `../../_shared/guide.md` b\nc ../../_shared/contracts/c.md, `../_shared/missing.md`\n"
    assert rewrite_shared_paths(new, md_file, skills) == (new, 0)
    assert shared_path_findings(new, md_file, skills) == [(2, "../_shared/missing.md", None)]


def test_rewrite_never_makes_a_command_or_url_relative(skills: Path) -> None:
    # A shell resolves a relative path against its working directory, so a
    # root-anchored path in a command becomes the resolver form, never
    # `../_shared/`; and a URL is not a path at all.
    md_file = skills / "demo" / "SKILL.md"
    body = (
        "python3 ${CLAUDE_PLUGIN_ROOT}/skills/_shared/guide.md\n"
        "See https://github.com/o/r/blob/main/skills/_shared/guide.md\n"
    )
    new, count = rewrite_shared_paths(body, md_file, skills)
    assert count == 1
    assert new == (
        "python3 <claudna-root>/skills/_shared/guide.md\nSee https://github.com/o/r/blob/main/skills/_shared/guide.md\n"
    )
    assert shared_path_findings(new, md_file, skills) == []


def test_the_script_rewrites_in_place_and_exits_1_on_what_it_cannot_fix(skills: Path) -> None:
    (skills / "demo" / "SKILL.md").write_text("Read `skills/_shared/guide.md`.\n")
    (skills / "demo" / "sub" / "deep.md").write_text("Read `../_shared/missing.md`.\n")
    script = REPO_ROOT / "scripts" / "fix_shared_paths.py"
    run = subprocess.run([sys.executable, str(script), "--skills-dir", str(skills)], capture_output=True, text=True)
    assert run.returncode == 1, run.stdout + run.stderr
    assert "rewrote 1 `_shared/` path(s) in 1 file(s)" in run.stdout
    assert "demo/sub/deep.md:1: `../_shared/missing.md` names nothing" in run.stderr
    assert (skills / "demo" / "SKILL.md").read_text() == "Read `../_shared/guide.md`.\n"

    (skills / "demo" / "sub" / "deep.md").write_text("Read `../../_shared/guide.md`.\n")
    again = subprocess.run([sys.executable, str(script), "--skills-dir", str(skills)], capture_output=True, text=True)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "rewrote 0 `_shared/` path(s) in 0 file(s)" in again.stdout


def test_every_shared_path_in_this_repo_is_file_relative() -> None:
    skills = REPO_ROOT / "skills"
    files = [p for p in sorted(skills.rglob("*.md")) if len(p.relative_to(skills).parts) > 1]
    # Counted independently of the checker and compared with what the
    # checker examined, so a checker that silently skipped paths cannot pass.
    seen = sum(len(re.findall(r"(?<![\w-])_shared/", p.read_text())) for p in files)
    examined = sum(len(_shared_path_spans(line)) for p in files for line in p.read_text().split("\n"))
    assert seen > 0
    assert examined == seen
    errors = [e for p in files for e in check_shared_paths(p.read_text(), p, skills)]
    assert errors == []
