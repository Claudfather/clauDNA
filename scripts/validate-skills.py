#!/usr/bin/env python3
"""Validate every skill under skills/ against SKILL_CONTRACT.md.

Run: python scripts/validate-skills.py
Exits non-zero on any violation; prints a structured report.
"""

from __future__ import annotations

import sys
from pathlib import Path

from skill_checks import (
    STALE_PATH_RE,
    parse_frontmatter,
    validate_skill_md,
    warn_skill_md,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

SKIP_DIRS = {"_shared"}
SKIP_SKILLS: set[str] = set()  # add skill names here to intentionally bypass validation


def validate_skill(skill_dir: Path) -> list[str]:
    return validate_skill_md(skill_dir / "SKILL.md", dir_name=skill_dir.name)


def main() -> int:
    if not SKILLS_DIR.is_dir():
        print(f"FAIL: skills directory not found at {SKILLS_DIR}", file=sys.stderr)
        return 2

    skill_dirs = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir() and p.name not in SKIP_DIRS)

    all_errors: dict[str, list[str]] = {}
    all_warnings: dict[str, list[str]] = {}
    seen_names: dict[str, str] = {}  # name -> dir

    for skill_dir in skill_dirs:
        name = skill_dir.name
        if name in SKIP_SKILLS:
            print(f"SKIP {name}")
            continue
        errors = validate_skill(skill_dir)

        # Track duplicates by frontmatter name (separate from dir mismatch)
        skill_md = skill_dir / "SKILL.md"
        if skill_md.is_file():
            try:
                parsed = parse_frontmatter(skill_md)
            except ValueError:
                parsed = None
            if parsed:
                fm_name = parsed[0].get("name")
                if isinstance(fm_name, str):
                    if fm_name in seen_names:
                        errors.append(f"duplicate frontmatter name {fm_name!r} (also used by {seen_names[fm_name]})")
                    else:
                        seen_names[fm_name] = name

        if errors:
            all_errors[name] = errors

        # Collect warnings (advisory, non-blocking)
        warnings = warn_skill_md(skill_md)
        if warnings:
            all_warnings[name] = warnings

    # Lint _shared files for stale paths
    shared_dir = SKILLS_DIR / "_shared"
    if shared_dir.is_dir():
        for md_file in sorted(shared_dir.glob("*.md")):
            text = md_file.read_text()
            stale_lines = [line.strip() for line in text.splitlines() if STALE_PATH_RE.search(line)]
            if stale_lines:
                all_errors[f"_shared/{md_file.name}"] = [f"stale hardcoded path: {line}" for line in stale_lines]

    total_skills = len(skill_dirs) - len(SKIP_SKILLS)

    # Print warnings (non-blocking)
    if all_warnings:
        print(f"WARN: {len(all_warnings)} skill(s) have advisory warnings\n")
        for name in sorted(all_warnings):
            print(f"  {name}:")
            for w in all_warnings[name]:
                print(f"    - [WARN] {w}")
            print()

    if not all_errors:
        print(f"OK: {total_skills} skills validated, no violations")
        return 0

    print(f"FAIL: {len(all_errors)} of {total_skills} skills have violations\n")
    for name in sorted(all_errors):
        print(f"  {name}:")
        for err in all_errors[name]:
            print(f"    - {err}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
