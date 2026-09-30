"""Scratch files and directories are private to the user who made them.

A skill, agent or hook makes its scratch directory with `mktemp -d` (created
new, readable by the user alone) and keeps hook state in the user's own state
directory. No file names a fixed or timestamped path in the shared temp
directory, and every file a skill writes for its own use goes in that private
directory (orchestration guide §1). Each failure names the file and line.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FILES = sorted(
    p for d in ("skills", "agents", "plugin-hooks") for p in (REPO / d).rglob("*") if p.suffix in (".md", ".sh")
)
PROSE = [p for p in FILES if p.suffix == ".md"]

# A path in the shared temp directory: anything beneath /tmp/ or $TMPDIR/ (`/tmp/<skill>-<ts>/`,
# `${TMPDIR:-/tmp}/name`, `/tmp/` itself as a place to write), or /tmp or $TMPDIR as a working
# directory (`cd /tmp && ...`). A mention of the directory, such as "never under `/tmp`", is not one.
_TEMP_PATH = re.compile(
    r"(?<![\w$}.~])/tmp(?:/|(?=[\s&;|)]|$))"
    r"|\$\{?TMPDIR\b(?:\}|:?[-=?+][^}\s]*\})?(?=[/\s&;|)]|$)"
)
# Removed before matching, and only that span of the line: the template `mktemp` makes new and
# private (up to its run of X), and a `Bash(...)` permission pattern.
_PRIVATE = re.compile(r"\bmktemp\b[^`\n]*?X{3,}[\"']?|\bBash\([^)]*\)")


def _flags(line: str) -> bool:
    return bool(_TEMP_PATH.search(_PRIVATE.sub("", line)))


# Orchestration guide §1 (never §10), where the private directory is made and this rule is stated.
_SECTION_1 = r"orchestration[- ]guide(?:\.md`?\)?)? §\s?1(?!\d)"
# A line that has the model write a file it names only by a placeholder, or not at all.
_WRITES_A_FILE = re.compile(r"\b(?:with|by|via) the Write tool\b")
_UNNAMED_FILE = re.compile(r"<[a-z0-9-]*file>|\b(?:a|two|three|its own|those three) files?\b|\btemp(?:orary)? file\b")
_SAYS_WHERE = re.compile(r"<scratch>|\bmktemp\b|" + _SECTION_1)
# Output written "to a scratch directory" or "in scratch": the file must make one or point at §1.
_WRITES_TO_SCRATCH = re.compile(
    r"\b(?:to|in|into) (?:a |the )?scratch\b|\ba scratch (?:file|directory|dir)\b|\btemporary or ignored directory\b",
    re.I,
)
_MAKES_OR_POINTS = re.compile(r"<scratch>|\bmktemp -d\b|" + _SECTION_1)


def _leaves_the_file_unplaced(line: str) -> bool:
    return bool(_WRITES_A_FILE.search(line) and _UNNAMED_FILE.search(line) and not _SAYS_WHERE.search(line))


def _leaves_scratch_unmade(text: str) -> bool:
    return bool(_WRITES_TO_SCRATCH.search(text) and not _MAKES_OR_POINTS.search(text))


def test_files_are_found():
    # Positive control: an empty scan would pass the tests below.
    assert len(FILES) > 40
    assert sum(1 for p in PROSE for line in p.read_text().splitlines() if _WRITES_A_FILE.search(line)) > 20


def test_no_file_names_a_path_in_the_shared_temp_dir():
    hits = []
    for path in FILES:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if _flags(line):
                hits.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:120]}")
    assert not hits, "make it with mktemp -d, or keep it in the user's state directory:\n" + "\n".join(hits)


def test_each_file_a_skill_writes_says_where():
    # A command's text file, a finding, a message: the line that writes it places it in <scratch>.
    hits = [
        f"{p.relative_to(REPO)}:{n}: {line.strip()[:120]}"
        for p in PROSE
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if _leaves_the_file_unplaced(line)
    ]
    assert not hits, "write it in <scratch> (orchestration guide §1):\n" + "\n".join(hits)


def test_a_file_that_writes_to_scratch_makes_it_or_points_at_section_1():
    hits = [str(p.relative_to(REPO)) for p in PROSE if _leaves_scratch_unmade(p.read_text())]
    assert not hits, "make <scratch> with mktemp -d, or point at orchestration guide §1:\n" + "\n".join(hits)


def test_section_1_states_the_rule_and_the_refusal():
    guide = (REPO / "skills" / "_shared" / "orchestration-guide.md").read_text()
    section_1 = guide.split("\n## 1.", 1)[1].split("\n## 2.", 1)[0]
    assert "Every file a skill writes for its own use goes in `<scratch>`" in section_1
    assert "If `mktemp -d` is refused, stop and say so" in section_1


@pytest.mark.parametrize(
    "line",
    [
        "Scratch dir: `/tmp/audit-<YYYY-MM-DD_HHMMSS>/`",
        'OUT="${OUT:-/tmp/gh-activity-stats}"',
        'MARKER="${TMPDIR:-/tmp}/claudna-reflected-${SESSION_ID}"',
        "write it to `$TMPDIR/out.json`",
        'LOG="/tmp/claude-permissions.log"',
        # A mktemp call on the line does not excuse the rest of it.
        'made once with `mktemp -d "${TMPDIR:-/tmp}/audit.XXXXXX"`, so the maps are `/tmp/audit-<TS>/system/map.md`',
        "cd /tmp && git clone <url>",
        'OUT="/tmp/"',
        "rm -rf /tmp/*",
        "write it to ${TMPDIR-/tmp}/out.json",
        "writing research to `/tmp/`",
    ],
)
def test_the_lint_flags_each_form(line):
    assert _flags(line)


@pytest.mark.parametrize(
    "line",
    [
        'D=$(mktemp -d "${TMPDIR:-/tmp}/audit-x.XXXXXX")',
        "  - Bash(rm -rf /tmp/heist-*)",
        "Scratch directory: `<scratch>/research/`",
        "Never name a scratch path yourself under `/tmp` or `$TMPDIR`: make it with `mktemp -d`.",
        'if path in ("/", "/tmp", os.path.expanduser("~")):',
        "state lives in the Issue's comments, not `/tmp`, which stays ephemeral.",
    ],
)
def test_the_lint_passes_the_private_forms(line):
    assert not _flags(line)


@pytest.mark.parametrize(
    "line",
    [
        "Write the keywords to `<keywords-file>` with the Write tool, then:",
        "Write the title and the description to two files with the Write tool, then run `gh pr create`.",
        "write the markdown body to a temp file (with the Write tool) and post it with `-F body=@<file>`",
        "Write it to `<out-file>` with the Write tool (orchestration guide §10).",
    ],
)
def test_an_unplaced_file_is_flagged(line):
    assert _leaves_the_file_unplaced(line)


@pytest.mark.parametrize(
    "line",
    [
        "Write the keywords to `<keywords-file>` in `<scratch>` (`../_shared/orchestration-guide.md` §1) with the Write tool",
        "write the title and the body to two files with the Write tool, inside a directory you make with mktemp -d",
        "Create `CLAUDE.md` in the project root with the Write tool.",
    ],
)
def test_a_placed_or_named_file_passes(line):
    assert not _leaves_the_file_unplaced(line)


def test_a_doc_written_in_scratch_needs_scratch_made_or_pointed_at():
    line = "author the retro as a publishable doc in scratch named `00_RETRO.md`, then publish it"
    assert _leaves_scratch_unmade(line)
    assert _leaves_scratch_unmade(line + " (see `../_shared/orchestration-guide.md` §10)")
    assert not _leaves_scratch_unmade(line.replace("in scratch", "in `<scratch>`"))
    assert not _leaves_scratch_unmade(line + " (`../_shared/orchestration-guide.md` §1)")


def test_the_activity_crawl_needs_its_output_dir_named(tmp_path):
    crawl = REPO / "skills" / "github-activity-report" / "crawl.sh"
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "SCOPE": "fake-org",
        "SINCE_DATE": "2026-01-01",
        "UNTIL_DATE": "2026-01-31",
    }
    run = subprocess.run(["bash", str(crawl)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode != 0 and "OUT" in run.stderr, run.stdout + run.stderr
