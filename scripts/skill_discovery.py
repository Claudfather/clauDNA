"""Filesystem discovery shared by maintainer gates; standard library only."""

from __future__ import annotations

import os
from pathlib import Path

# One definition of "not a skill directory", shared by manifests and validators.
SKIP_DIRS = {"_shared"}

# Repo-wide text surfaces walked by the removed-names and vault-address gates.
GATE_EXTENSIONS = {".md", ".sh", ".py", ".json", ".yaml", ".yml", ".toml", ".txt"}
# Fixed VCS/build names are pruned directly. Virtual environments are identified
# by their marker below; .venv and venv are backstops for an unreadable/missing
# marker. Do not prune "env" by name: it can be a tracked config directory.
GATE_PRUNE_DIRS = {".git", "__pycache__", "worktrees", "node_modules", ".venv", "venv"}


def is_virtualenv(path: Path) -> bool:
    """True when *path* carries the PEP 405 virtual-environment root marker.

    Looking for pyvenv.cfg also catches arbitrarily named environments such as
    .venv313 or build-venv. Scanning their thousands of vendored files previously
    caused a 33x gate slowdown (#330). Environments without that marker rely on
    the name-level backstops in GATE_PRUNE_DIRS.
    """
    return (path / "pyvenv.cfg").is_file()


def walk_gate_files(root: Path) -> list[Path]:
    """Every gate-relevant file under *root*, vendored directories pruned.

    Prune os.walk's descent rather than filtering an already enumerated tree.
    Callers layer their own path exclusions on top of this common file set.
    """
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in GATE_PRUNE_DIRS and not is_virtualenv(here / d)]
        for fname in filenames:
            if Path(fname).suffix in GATE_EXTENSIONS:
                out.append(here / fname)
    return sorted(out)


def skill_dirs(skills_dir: Path) -> list[Path]:
    """Sorted skill directories containing SKILL.md, excluding SKIP_DIRS."""
    if not skills_dir.is_dir():
        return []
    return sorted(p for p in skills_dir.iterdir()
                  if p.is_dir() and p.name not in SKIP_DIRS and (p / "SKILL.md").is_file())
