"""Explicit Codex catalog scope; host/context restrictions are distribution policy."""

from __future__ import annotations

import json
from pathlib import Path

from plugin_scope import declared_skills
from skill_checks import parse_frontmatter, skill_dirs, validate_hosts, validate_requires_context


def eligible_names(root: Path) -> set[str]:
    names = set()
    for directory in skill_dirs(root / "skills"):
        parsed = parse_frontmatter(directory / "SKILL.md")
        if parsed is None:
            raise ValueError(f"missing skill frontmatter: {directory.name}")
        metadata, _ = parsed
        if "hosts" in metadata and validate_hosts(metadata["hosts"]):
            raise ValueError(f"invalid hosts metadata: {directory.name}")
        if "requires-context" in metadata and validate_requires_context(metadata["requires-context"]):
            raise ValueError(f"invalid context metadata: {directory.name}")
        if "requires-context" in metadata or ("hosts" in metadata and "codex" not in metadata["hosts"]):
            continue
        names.add(directory.name)
    return names


def run_check(root: Path) -> tuple[list[str], list[str], list[str]]:
    errors = []
    try:
        data = json.loads((root / ".codex-plugin/plugin.json").read_text())
        raw = data.get("skills")
        if not isinstance(raw, list) or not raw:
            return ["Codex requires an explicit nonempty skill-directory list; default discovery is forbidden"], [], []
        if any(not isinstance(value, str) for value in raw):
            return ["Codex skills entries must be relative skill-directory strings"], [], []
        if len(raw) != len(set(raw)):
            errors.append("Codex skills list contains duplicate entries")
        skills_root = (root / "skills").resolve()
        for value in raw:
            path = (root / value).resolve()
            if not value.startswith("./skills/") or path.parent != skills_root or not (path / "SKILL.md").is_file():
                errors.append(f"Codex entry {value!r} must select one existing skill directory inside skills/")
        declared, explicit, detail = declared_skills(root / ".codex-plugin")
        if declared is None or not explicit:
            errors.append(f"Codex catalog cannot be classified: {detail}")
            return errors, [], []
        expected = eligible_names(root)
        for name in sorted(declared - expected):
            errors.append(f"Codex catalog ships excluded or unknown skill {name!r}")
        for name in sorted(expected - declared):
            errors.append(f"Codex catalog is missing eligible skill {name!r}")
        return errors, [], [f"Codex explicit catalog: {len(declared)} skills"]
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return [f"Codex scope cannot be determined: {exc}"], [], []


def selected_names(root: Path) -> frozenset[str]:
    errors, _, _ = run_check(root)
    if errors:
        raise ValueError("; ".join(errors))
    names, _, _ = declared_skills(root / ".codex-plugin")
    return frozenset(names)
