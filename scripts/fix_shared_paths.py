#!/usr/bin/env python3
"""Rewrite `_shared/` paths in skill markdown to the file-relative spelling.

SKILL_CONTRACT §1 (#336): a path in skill text resolves against the directory
of the file it is written in, so `_shared` material is `../_shared/<path>` from
a skill's top level and from `_shared/` itself, and `../../_shared/<path>` one
directory further down. `validate-skills.py` fails on any other spelling; this
script rewrites every such path that names something under `skills/_shared/`.

A path that names nothing there is reported, never guessed at, and the script
exits 1 so it cannot be mistaken for a clean run. A second run changes nothing.

Usage:
    python3 scripts/fix_shared_paths.py [--skills-dir DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skill_checks import rewrite_shared_paths, shared_path_findings

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skills-dir", type=Path, default=REPO_ROOT / "skills")
    args = parser.parse_args(argv)
    skills_dir = args.skills_dir.resolve()

    rewritten = files = 0
    unresolved: list[str] = []
    # Files directly in skills/ (its CLAUDE.md) belong to no skill and are
    # outside the rule, as they are outside the validator's walk.
    for md_file in sorted(p for p in skills_dir.rglob("*.md") if len(p.relative_to(skills_dir).parts) > 1):
        text = md_file.read_text()
        new_text, count = rewrite_shared_paths(text, md_file, skills_dir)
        if count:
            md_file.write_text(new_text)
            rewritten += count
            files += 1
        rel = md_file.relative_to(skills_dir)
        for lineno, written, _spelling in shared_path_findings(new_text, md_file, skills_dir):
            unresolved.append(f"{rel}:{lineno}: `{written}` names nothing under skills/_shared/")

    print(f"rewrote {rewritten} `_shared/` path(s) in {files} file(s)")
    for line in unresolved:
        print(f"UNRESOLVED {line}", file=sys.stderr)
    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
