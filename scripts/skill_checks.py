"""Shared skill validation logic used by validate-skills.py and validate-promotion-package.py.

Extracted so both the CI skill validator and the promotion pre-flight
can share the same rules without duplication.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

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
    Unknown tool names are not failed -- the tool surface evolves.
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
                    f"allowed-tools: deprecated colon syntax in {entry!r} -- use 'Bash(cmd *)' not 'Bash(cmd:*)'"
                )
    return errors


def validate_skill_md(skill_md: Path, dir_name: str | None = None) -> list[str]:
    """Validate a SKILL.md file against the skill contract.

    Args:
        skill_md: Path to the SKILL.md file.
        dir_name: Expected directory name the skill should match.
                  If None, skips the name-vs-directory check.

    Returns:
        List of error strings (empty = valid).
    """
    errors: list[str] = []

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
            if dir_name is not None and fm_name != dir_name:
                errors.append(
                    f"name {fm_name!r} does not match directory name {dir_name!r}"
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
            f"body too short ({body_chars} chars, min {BODY_MIN}) -- looks like a stub"
        )

    # Stale hardcoded path check
    name = fm_name if isinstance(fm_name, str) else dir_name
    if name not in STALE_PATH_SKIP_SKILLS:
        for line in body.splitlines():
            if STALE_PATH_RE.search(line):
                errors.append(f"stale hardcoded path: {line.strip()}")

    return errors
