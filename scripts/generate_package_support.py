#!/usr/bin/env python3
"""Derive the shipped support projection and public table from existing owners.

Development only: YAML parsing and distribution checks stay in their existing
modules. Runtime consumers read JSON and verify source hashes, never import this
generator. Hashes cover full SKILL.md bytes (including their frontmatter).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

from check_codex_scope import run_check as check_codex_scope
from check_cursor_scope import run_check as check_cursor_scope
from plugin_scope import declared_skills
from skill_checks import KNOWN_HOSTS, parse_frontmatter, skill_dirs, validate_requires, validate_skill_md

ROOT = Path(__file__).resolve().parent.parent
POLICY = "lib/claudna/package_support/host-policy.json"
CATALOG = "lib/claudna/package_support/catalog.json"
GUIDE = "documentation/guides/PACKAGE_SUPPORT.md"
START = "<!-- BEGIN GENERATED PACKAGE SUPPORT -->"
END = "<!-- END GENERATED PACKAGE SUPPORT -->"


def source_path(root: Path, relative: str) -> Path:
    """Require portable, root-contained source paths, including symlink targets."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"invalid source-relative path: {relative!r}")
    pure = PurePosixPath(relative)
    path = root / relative
    if pure.is_absolute() or ".." in pure.parts or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"source path escapes package root: {relative!r}")
    return path


def build_catalog(root: Path) -> dict:
    sources = {}

    def record(relative: str) -> Path:
        path = source_path(root, relative)
        sources[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    def read_json(relative: str) -> dict:
        data = json.loads(record(relative).read_text())
        if not isinstance(data, dict):
            raise ValueError(f"{relative}: expected a JSON object")
        return data

    policy = read_json(POLICY)
    if policy.get("schema") != "claudna.host-policy/1" or set(policy.get("hosts", {})) != KNOWN_HOSTS:
        raise ValueError("host policy must declare exactly the existing hosts and schema")

    skills = {}
    for directory in skill_dirs(root / "skills"):
        relative = f"skills/{directory.name}/SKILL.md"
        path = record(relative)
        errors = validate_skill_md(path, directory.name)
        if errors:
            raise ValueError(f"{relative}: {'; '.join(errors)}")
        metadata, _ = parse_frontmatter(path)
        skills[directory.name] = {
            "path": relative,
            "description": metadata["description"],
            "hosts": sorted(metadata.get("hosts", KNOWN_HOSTS)),
            "requires_context": metadata.get("requires-context"),
            "requires": metadata.get("requires", []),
        }
    if not skills:
        raise ValueError("no canonical skills found")

    for check in (check_cursor_scope, check_codex_scope):
        errors, _, _ = check(root)
        if errors:
            raise ValueError("; ".join(errors))

    hosts = {}
    versions = set()
    for host, settings in sorted(policy["hosts"].items()):
        required = {"manifest", "marketplace", "agents", "hook_capability", "runtime_platforms",
                    "runtime_prerequisites", "evidence_limits"}
        if not isinstance(settings, dict) or set(settings) != required:
            raise ValueError(f"{host}: invalid host policy fields")
        for key in required - {"runtime_platforms", "runtime_prerequisites"}:
            if not isinstance(settings[key], str) or not settings[key].strip():
                raise ValueError(f"{host}: {key} must be a nonempty string")
        platforms = settings["runtime_platforms"]
        if not isinstance(platforms, list) or any(p not in ("macOS", "Linux") for p in platforms):
            raise ValueError(f"{host}: invalid runtime platforms")
        errors = validate_requires(settings["runtime_prerequisites"])
        if errors:
            raise ValueError(f"{host}: {'; '.join(errors)}")
        manifest = read_json(settings["manifest"])
        read_json(settings["marketplace"])
        version = manifest.get("version")
        if not isinstance(version, str) or not version:
            raise ValueError(f"{host}: missing package version")
        versions.add(version)
        if host == "claude-code" and "skills" not in manifest:
            names = set(skills)  # Native default directory discovery, not an empty catalog.
        else:
            names, _, detail = declared_skills(source_path(root, settings["manifest"]).parent)
            if names is None:
                raise ValueError(f"{host}: {detail}")
        if names - skills.keys():
            raise ValueError(f"{host}: selected unknown skill(s): {sorted(names - skills.keys())}")
        hooks = {"path": None, "events": {}, "handler_count": 0}
        if "hooks" in manifest:
            if host == "cursor":
                raise ValueError("Cursor must remain hook-free")
            hook_path = manifest["hooks"]
            config = read_json(hook_path)
            events = config.get("hooks")
            if not isinstance(events, dict):
                raise ValueError(f"{hook_path}: missing hook event map")
            counts = {}
            for event, groups in sorted(events.items()):
                if not isinstance(groups, list) or any(
                    not isinstance(group, dict) or not isinstance(group.get("hooks"), list) for group in groups
                ):
                    raise ValueError(f"{hook_path}: invalid handlers for {event}")
                counts[event] = sum(len(group["hooks"]) for group in groups)
            hooks = {"path": source_path(root, hook_path).relative_to(root).as_posix(),
                     "events": counts, "handler_count": sum(counts.values())}
        if host == "cursor" and (root / "hooks/hooks.json").exists():
            raise ValueError("Cursor must remain hook-free: hooks/hooks.json exists")
        hosts[host] = {**settings, "skills": sorted(names), "skill_count": len(names), "hooks": hooks}

    if len(versions) != 1:
        raise ValueError("host manifest versions disagree")
    return {"schema": "claudna.package-support/1", "package_version": versions.pop(),
            "sources": dict(sorted(sources.items())), "skills": skills, "hosts": hosts}


def render_table(catalog: dict) -> str:
    lines = [START, "", f"Source package version: **{catalog['package_version']}**. "
             "Generated declarations; native certification is **unknown**.", "",
             "| Host | Selected skills | Agent policy | Declared hook handlers | Baseline checks |",
             "|---|---:|---|---|---|"]
    for host, entry in catalog["hosts"].items():
        dependencies = ", ".join(f"`{dep.get('cli', dep.get('env'))}`" for dep in entry["runtime_prerequisites"])
        hooks = entry["hooks"]
        lines.append(f"| {host} | {entry['skill_count']} | {entry['agents']} | "
                     f"{hooks['handler_count']} — {entry['hook_capability']} | "
                     f"{dependencies or 'Workflow-specific only'} |")
    lines.extend(["", "| Skill | Claude Code | Cursor | Codex | Context restriction |",
                  "|---|:---:|:---:|:---:|---|"])
    for name, entry in catalog["skills"].items():
        selected = ["Selected" if name in catalog["hosts"][host]["skills"] else "Excluded"
                    for host in ("claude-code", "cursor", "codex")]
        lines.append(f"| [{name}](../../{entry['path']}) | {' | '.join(selected)} | "
                     f"{entry['requires_context'] or 'None declared'} |")
    lines.extend(["", "Baseline checks have different consequences; they are not a universal execution gate. "
                  "Per-tool reasons and skill-specific prerequisites are in the "
                  "[generated catalog](../../lib/claudna/package_support/catalog.json).", ""])
    for host, entry in catalog["hosts"].items():
        lines.append(f"- **{host}:** {entry['evidence_limits']}")
    lines.extend(["", END])
    return "\n".join(lines)


def generate(root: Path, *, check: bool = False) -> list[str]:
    catalog = build_catalog(root)
    guide = source_path(root, GUIDE).read_text()
    if guide.count(START) != 1 or guide.count(END) != 1 or guide.index(START) >= guide.index(END):
        raise ValueError(f"{GUIDE}: expected one ordered pair of generated markers")
    before, rest = guide.split(START)
    _, after = rest.split(END)
    outputs = {CATALOG: json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
               GUIDE: before + render_table(catalog) + after}
    changed = []
    for relative, content in outputs.items():
        path = source_path(root, relative)
        if not path.is_file() or path.read_text() != content:
            changed.append(relative)
            if not check:
                path.write_text(content)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report drift without writing")
    parser.add_argument("--root", type=Path, default=ROOT, help="Source package root")
    args = parser.parse_args(argv)
    try:
        changed = generate(args.root.resolve(), check=args.check)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"package support: {exc}", file=sys.stderr)
        return 1
    if args.check and changed:
        print("package support drift: " + ", ".join(changed), file=sys.stderr)
        print("Run python3 scripts/generate_package_support.py", file=sys.stderr)
        return 1
    print("package support: " + (", ".join(changed) if changed else "current"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
