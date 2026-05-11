#!/usr/bin/env python3
"""Validate every skill under skills/ against SKILL_CONTRACT.md.

Run: python scripts/validate-skills.py
Exits non-zero on any violation; prints a structured report.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

SKIP_DIRS = {"_shared"}
SKIP_SKILLS: set[str] = set()  # add skill names here to intentionally bypass validation

REQUIRED_FIELDS = {"name", "description"}
KNOWN_FIELDS = REQUIRED_FIELDS | {"allowed-tools", "argument-hint", "user-invocable"}

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
DESC_MIN = 20
DESC_MAX = 500
BODY_MIN = 200
STALE_PATH_RE = re.compile(r"~/\.claude/(skills|commands|agents)/")
STALE_PATH_SKIP_SKILLS = {"cleanup-legacy-install"}


def parse_frontmatter(path: Path) -> tuple[dict, str] | None:
    """Return (frontmatter_dict, body) or None if no frontmatter."""
    text = path.read_text()
    if not text.startswith("---"):
        return None
    lines = text.splitlines(keepends=True)
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return None
    frontmatter_text = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        data = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"frontmatter YAML parse error: {e}")
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a YAML mapping")
    return data, body


def validate_allowed_tools(value) -> list[str]:
    """Validate allowed-tools (string with comma-separated entries, or YAML list).

    Both forms are valid Claude Code frontmatter. Only the deprecated
    colon syntax (Bash(cmd:*) instead of Bash(cmd *)) is hard-failed,
    since CHANGELOG records that as a confirmed-broken pattern.
    Unknown tool names are not failed — the tool surface evolves.
    """
    errors: list[str] = []
    if isinstance(value, str):
        entries = [e.strip() for e in value.split(",") if e.strip()]
    elif isinstance(value, list):
        entries = []
        for i, entry in enumerate(value):
            if not isinstance(entry, str):
                errors.append(
                    f"allowed-tools[{i}] must be a string, got {type(entry).__name__}"
                )
                continue
            entries.append(entry.strip())
    else:
        errors.append(
            f"allowed-tools must be a string or list, got {type(value).__name__}"
        )
        return errors

    for entry in entries:
        m = re.match(r"^([A-Za-z]+)(\(.*\))?$", entry)
        if not m:
            errors.append(f"allowed-tools: unparseable entry {entry!r}")
            continue
        tool = m.group(1)
        pattern = m.group(2)
        if pattern and tool == "Bash":
            inner = pattern[1:-1]
            if ":" in inner and "*" in inner:
                errors.append(
                    f"allowed-tools: deprecated colon syntax in {entry!r} — use 'Bash(cmd *)' not 'Bash(cmd:*)'"
                )
    return errors


def validate_skill(skill_dir: Path) -> list[str]:
    name = skill_dir.name
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.is_file():
        return ["missing SKILL.md"]

    try:
        parsed = parse_frontmatter(skill_md)
    except ValueError as e:
        return [str(e)]
    if parsed is None:
        return ["SKILL.md has no YAML frontmatter (must start with --- ... ---)"]

    fm, body = parsed

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in fm:
            errors.append(f"frontmatter missing required field {field!r}")

    # Unknown fields
    for field in fm:
        if field not in KNOWN_FIELDS:
            errors.append(
                f"frontmatter has unknown field {field!r} (allowed: {sorted(KNOWN_FIELDS)})"
            )

    # name rules
    fm_name = fm.get("name")
    if fm_name is not None:
        if not isinstance(fm_name, str):
            errors.append(f"name must be a string, got {type(fm_name).__name__}")
        else:
            if not NAME_RE.match(fm_name):
                errors.append(f"name {fm_name!r} must match {NAME_RE.pattern}")
            if fm_name != name:
                errors.append(
                    f"name {fm_name!r} does not match directory name {name!r}"
                )

    # description rules
    desc = fm.get("description")
    if desc is not None:
        if not isinstance(desc, str):
            errors.append(f"description must be a string, got {type(desc).__name__}")
        else:
            length = len(desc)
            if length < DESC_MIN:
                errors.append(f"description too short ({length} chars, min {DESC_MIN})")
            if length > DESC_MAX:
                errors.append(f"description too long ({length} chars, max {DESC_MAX})")

    # allowed-tools rules
    if "allowed-tools" in fm:
        errors.extend(validate_allowed_tools(fm["allowed-tools"]))

    # argument-hint rules
    arg_hint = fm.get("argument-hint")
    if arg_hint is not None and not isinstance(arg_hint, str):
        errors.append(f"argument-hint must be a string, got {type(arg_hint).__name__}")

    # user-invocable rules
    user_invocable = fm.get("user-invocable")
    if user_invocable is not None and not isinstance(user_invocable, bool):
        errors.append(
            f"user-invocable must be a boolean, got {type(user_invocable).__name__}"
        )

    # body length
    body_chars = len(body.strip())
    if body_chars < BODY_MIN:
        errors.append(
            f"body too short ({body_chars} chars, min {BODY_MIN}) — looks like a stub"
        )

    # Stale hardcoded path check
    if name not in STALE_PATH_SKIP_SKILLS:
        for line in body.splitlines():
            if STALE_PATH_RE.search(line):
                errors.append(f"stale hardcoded path: {line.strip()}")

    return errors


def main() -> int:
    if not SKILLS_DIR.is_dir():
        print(f"FAIL: skills directory not found at {SKILLS_DIR}", file=sys.stderr)
        return 2

    skill_dirs = sorted(
        p for p in SKILLS_DIR.iterdir() if p.is_dir() and p.name not in SKIP_DIRS
    )

    all_errors: dict[str, list[str]] = {}
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
                        errors.append(
                            f"duplicate frontmatter name {fm_name!r} (also used by {seen_names[fm_name]})"
                        )
                    else:
                        seen_names[fm_name] = name

        if errors:
            all_errors[name] = errors

    # Lint _shared files for stale paths
    shared_dir = SKILLS_DIR / "_shared"
    if shared_dir.is_dir():
        for md_file in sorted(shared_dir.glob("*.md")):
            text = md_file.read_text()
            stale_lines = [
                line.strip() for line in text.splitlines() if STALE_PATH_RE.search(line)
            ]
            if stale_lines:
                all_errors[f"_shared/{md_file.name}"] = [
                    f"stale hardcoded path: {line}" for line in stale_lines
                ]

    total_skills = len(skill_dirs) - len(SKIP_SKILLS)

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
