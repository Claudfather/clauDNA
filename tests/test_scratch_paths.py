"""Scratch files and directories are private to the user who made them.

A skill, agent or hook makes its scratch directory with `mktemp -d` (created
new, readable by the user alone) and keeps hook state in the user's own state
directory. No file names a fixed or timestamped path in the shared temp
directory. Each failure names the file and line.
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
# A named path beneath /tmp or $TMPDIR: `/tmp/<skill>-<ts>/`, `${TMPDIR:-/tmp}/name`.
_NAMED_TEMP_PATH = re.compile(r"(?<![\w$}])/tmp/(?=[\w<{$.-])|\$\{?TMPDIR(?::-/tmp)?\}?/(?=[\w<{$.-])")
# `mktemp` makes the path new and private; an allowed-tools line is a permission pattern.
_EXEMPT = re.compile(r"\bmktemp\b|^\s*-\s*Bash\(")


def _flags(line: str) -> bool:
    return bool(_NAMED_TEMP_PATH.search(line)) and not _EXEMPT.search(line)


def test_files_are_found():
    # Positive control: an empty scan would pass the test below.
    assert len(FILES) > 40


def test_no_file_names_a_path_in_the_shared_temp_dir():
    hits = []
    for path in FILES:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if _flags(line):
                hits.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:120]}")
    assert not hits, "make it with mktemp -d, or keep it in the user's state directory:\n" + "\n".join(hits)


@pytest.mark.parametrize(
    "line",
    [
        "Scratch dir: `/tmp/audit-<YYYY-MM-DD_HHMMSS>/`",
        'OUT="${OUT:-/tmp/gh-activity-stats}"',
        'MARKER="${TMPDIR:-/tmp}/claudna-reflected-${SESSION_ID}"',
        "write it to `$TMPDIR/out.json`",
        'LOG="/tmp/claude-permissions.log"',
    ],
)
def test_the_lint_flags_each_form(line):
    assert _flags(line)


@pytest.mark.parametrize(
    "line",
    [
        'D=$(mktemp -d "${TMPDIR:-/tmp}/audit-x.XXXXXX")',
        "  - Bash(rm -rf /tmp/heist-*)",
        "writing research to `/tmp/`",
        "Scratch directory: `<scratch>/research/`",
    ],
)
def test_the_lint_passes_the_private_forms(line):
    assert not _flags(line)


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
