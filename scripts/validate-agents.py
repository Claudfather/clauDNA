#!/usr/bin/env python3
"""Validate every agent under agents/ against AGENT_CONTRACT.md.

Run: python scripts/validate-agents.py
Exits non-zero on any violation; prints a structured report.
Runs in CI via `make check` (target `check-agents`; see the repo Makefile).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from skill_checks import STALE_PATH_RE, parse_frontmatter

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"

REQUIRED_FIELDS = {"name", "description"}
KNOWN_FIELDS = REQUIRED_FIELDS | {
    "model",
    "memory",
    "tools",
    "background",
    "isolation",
}

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
DESC_MIN = 20
DESC_MAX = 500
BODY_MIN = 200

MEMORY_VALUES = {"none", "user", "project"}


def validate_agent(agent_file: Path) -> list[str]:
    """Validate a single agent .md file against the agent contract."""
    errors: list[str] = []
    expected_name = agent_file.stem  # filename without .md

    if not agent_file.is_file():
        return [f"missing agent file {agent_file.name}"]

    try:
        parsed = parse_frontmatter(agent_file)
    except ValueError as e:
        return [str(e)]
    if parsed is None:
        return ["agent file has no YAML frontmatter (must start with --- ... ---)"]

    fm, body = parsed

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in fm:
            errors.append(f"frontmatter missing required field {field!r}")

    # Unknown fields
    for field in fm:
        if field not in KNOWN_FIELDS:
            errors.append(f"frontmatter has unknown field {field!r} (allowed: {sorted(KNOWN_FIELDS)})")

    # name rules
    fm_name = fm.get("name")
    if fm_name is not None:
        if not isinstance(fm_name, str):
            errors.append(f"name must be a string, got {type(fm_name).__name__}")
        else:
            if not NAME_RE.match(fm_name):
                errors.append(f"name {fm_name!r} must match {NAME_RE.pattern}")
            if fm_name != expected_name:
                errors.append(f"name {fm_name!r} does not match filename {expected_name!r}")

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

    # model rules
    model = fm.get("model")
    if model is not None and not isinstance(model, str):
        errors.append(f"model must be a string, got {type(model).__name__}")

    # memory rules
    memory = fm.get("memory")
    if memory is not None:
        if not isinstance(memory, str):
            errors.append(f"memory must be a string, got {type(memory).__name__}")
        elif memory not in MEMORY_VALUES:
            errors.append(f"memory {memory!r} is not a known value (allowed: {sorted(MEMORY_VALUES)})")

    # tools rules
    tools = fm.get("tools")
    if tools is not None:
        if not isinstance(tools, list):
            errors.append(f"tools must be a list, got {type(tools).__name__}")
        else:
            for i, tool in enumerate(tools):
                if not isinstance(tool, str):
                    errors.append(f"tools[{i}] must be a string, got {type(tool).__name__}")

    # background rules
    background = fm.get("background")
    if background is not None and not isinstance(background, bool):
        errors.append(f"background must be a boolean, got {type(background).__name__}")

    # isolation rules
    isolation = fm.get("isolation")
    if isolation is not None and not isinstance(isolation, str):
        errors.append(f"isolation must be a string, got {type(isolation).__name__}")

    # body length
    body_chars = len(body.strip())
    if body_chars < BODY_MIN:
        errors.append(f"body too short ({body_chars} chars, min {BODY_MIN}) -- looks like a stub")

    # Stale hardcoded path check
    for line in body.splitlines():
        if STALE_PATH_RE.search(line):
            errors.append(f"stale hardcoded path: {line.strip()}")

    return errors


def main() -> int:
    if not AGENTS_DIR.is_dir():
        print(f"FAIL: agents directory not found at {AGENTS_DIR}", file=sys.stderr)
        return 2

    agent_files = sorted(p for p in AGENTS_DIR.iterdir() if p.suffix == ".md")

    if not agent_files:
        print("FAIL: no agent files found in agents/", file=sys.stderr)
        return 2

    all_errors: dict[str, list[str]] = {}
    seen_names: dict[str, str] = {}  # name -> filename

    for agent_file in agent_files:
        errors = validate_agent(agent_file)

        # Track duplicates by frontmatter name
        try:
            parsed = parse_frontmatter(agent_file)
        except ValueError:
            parsed = None
        if parsed:
            fm_name = parsed[0].get("name")
            if isinstance(fm_name, str):
                if fm_name in seen_names:
                    errors.append(f"duplicate frontmatter name {fm_name!r} (also used by {seen_names[fm_name]})")
                else:
                    seen_names[fm_name] = agent_file.name

        if errors:
            all_errors[agent_file.name] = errors

    total = len(agent_files)

    if not all_errors:
        print(f"OK: {total} agents validated, no violations")
        return 0

    print(f"FAIL: {len(all_errors)} of {total} agents have violations\n")
    for name in sorted(all_errors):
        print(f"  {name}:")
        for err in all_errors[name]:
            print(f"    - {err}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
