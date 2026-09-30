"""Resolving <claudna-root> (#336): the candidate list's order, its refusal,
and its version compare, pinned in the text the model follows; and every
bundled-script call resolved by that procedure and run with CLAUDE_PLUGIN_ROOT
unset from an unrelated directory (acceptance criterion 3).

The model, not `_resolve` below, resolves <claudna-root> at run time. What
this file pins is the text it follows, and it shows that the procedure the text
describes lands on a runnable script in every case the text names. The order is
read from the definition itself, so reordering the list fails the order cases.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFINITION = REPO_ROOT / "skills" / "_shared" / "claudna-root.md"
REFUSAL = (
    "If none of them contains the file, stop and say so.",
    "Never fall back to a path in the working directory, which is the user's project, not this plugin.",
)
FIXTURE = "DATABASE_URL=postgres://app:hunter2-not-real@db.example.com:5432/app\n"


def _candidate_kinds() -> list[str]:
    text = DEFINITION.read_text()
    block = text[text.index("<!-- claudna-root:begin -->") : text.index("<!-- claudna-root:end -->")]
    kinds = []
    for item in re.findall(r"^\d+\. (.+)$", block, re.M):
        if "${CLAUDE_PLUGIN_ROOT}" in item:
            kinds.append("filled-in")
        elif "$CLAUDNA_ROOT" in item:
            kinds.append("env")
        elif "<skill-dir>/../.." in item:
            kinds.append("skill-dir")
        elif "plugins/cache/Claudfather/claudna" in item:
            kinds.append("cache")
        else:
            kinds.append(f"unrecognised: {item[:40]}")
    return kinds


def test_the_candidates_are_listed_in_order_with_the_refusal_and_a_version_compare() -> None:
    text = DEFINITION.read_text()
    assert _candidate_kinds() == ["filled-in", "env", "skill-dir", "cache"]
    for sentence in REFUSAL:
        assert sentence in text
    assert "as version numbers, not as text: `0.19.0` is above `0.9.0`" in text


def _version_key(path: Path) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"[.+-]", path.name))


def _resolve(script: str, *, filled_in: Path | None, env: Path | None, skill_dir: Path, cache: Path) -> Path | None:
    """The procedure the definition describes, taken in the order it lists."""
    for kind in _candidate_kinds():
        if kind == "filled-in":
            roots = [filled_in] if filled_in else []
        elif kind == "env":
            roots = [env] if env else []
        elif kind == "skill-dir":
            roots = [skill_dir / ".." / ".."]
        else:
            versions = sorted((p for p in cache.iterdir() if p.is_dir()), key=_version_key) if cache.is_dir() else []
            roots = versions[-1:]
        for root in roots:
            if (root / "scripts" / script).is_file():
                return root.resolve()
    return None


def _bundled_scripts() -> set[str]:
    names = set()
    for md in (REPO_ROOT / "skills").rglob("*.md"):
        names |= set(re.findall(r"(?:<claudna-root>|\$\{CLAUDE_PLUGIN_ROOT\})/scripts/([\w.-]+\.py)", md.read_text()))
    return names


def _plugin(root: Path) -> Path:
    shutil.copytree(REPO_ROOT / "scripts", root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "skills" / "recall").mkdir(parents=True)
    return root


@pytest.fixture
def layout(tmp_path: Path) -> dict[str, Path]:
    cache = tmp_path / "home" / ".claude" / "plugins" / "cache" / "Claudfather" / "claudna"
    for version in ("0.9.0", "0.19.0"):
        _plugin(cache / version)
    skills_only = tmp_path / "skills-only"
    (skills_only / "skills" / "recall").mkdir(parents=True)
    empty_root = tmp_path / "empty-root"
    empty_root.mkdir()
    return {
        "plugin": _plugin(tmp_path / "plugin"),
        "env": _plugin(tmp_path / "env-root"),
        "empty": empty_root,
        "cache": cache,
        "no-cache": tmp_path / "nowhere",
        "skills-only": skills_only,
        "work": tmp_path / "work",
    }


CASES = {
    # name: (filled_in, env, skill_dir owner, cache, expected winner)
    "filled-in wins": ("plugin", "env", "plugin", "cache", "plugin"),
    "$CLAUDNA_ROOT beats the skill directory": (None, "env", "plugin", "cache", "env"),
    "a candidate without the file is skipped": (None, "empty", "plugin", "cache", "plugin"),
    "the skill directory beats the cache": (None, None, "plugin", "cache", "plugin"),
    "the cache's highest version, compared as numbers": (None, None, "skills-only", "cache", "0.19.0"),
    "nothing found refuses": (None, None, "skills-only", "no-cache", None),
}


@pytest.mark.parametrize("case", CASES)
def test_every_bundled_script_resolves_and_runs_without_claude_plugin_root(
    layout: dict[str, Path], tmp_path: Path, case: str
) -> None:
    filled_in, env, owner, cache, expected = CASES[case]
    scripts = _bundled_scripts()
    assert scripts == {"check_provenance.py", "crawl_page.py", "env_from_file.py", "redact.py", "resolve_memory_dir.py"}
    run_env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_ROOT", "CLAUDNA_ROOT")}
    run_env["HOME"] = str(tmp_path / "home")
    layout["work"].mkdir(exist_ok=True)
    for script in sorted(scripts):
        root = _resolve(
            script,
            filled_in=layout[filled_in] if filled_in else None,
            env=layout[env] if env else None,
            skill_dir=layout[owner] / "skills" / "recall",
            cache=layout[cache],
        )
        if expected is None:
            assert root is None
            continue
        want = layout["cache"] / expected if expected == "0.19.0" else layout[expected]
        assert root == want.resolve()
        if script == "redact.py":
            target = layout["work"] / "cli-output.txt"
            target.write_text(FIXTURE)
            run = subprocess.run(
                [sys.executable, str(root / "scripts" / script), str(target)],
                cwd=layout["work"],
                env=run_env,
                capture_output=True,
                text=True,
            )
            assert run.returncode == 0, run.stderr
            assert "hunter2" not in target.read_text() and "[REDACTED]" in target.read_text()
        elif script in ("crawl_page.py", "env_from_file.py"):
            # Run bare, it says how it is run and exits 2; it must get that far.
            run = subprocess.run(
                [sys.executable, str(root / "scripts" / script)],
                cwd=layout["work"],
                env=run_env,
                capture_output=True,
                text=True,
            )
            assert run.returncode == 2 and "usage:" in run.stderr and "Traceback" not in run.stderr, run.stderr
        else:
            run = subprocess.run(
                [sys.executable, str(root / "scripts" / script)],
                cwd=layout["work"],
                env=run_env,
                capture_output=True,
                text=True,
            )
            assert run.returncode in (0, 1) and "Traceback" not in run.stderr, run.stderr
