#!/usr/bin/env python3
"""Validate .claude-plugin/ and .cursor-plugin/ manifest files.

Checks:
  1. All JSON files in each plugin dir are valid JSON
  2. plugin.json has required fields (name, version, description, author)
  3. plugin.json version follows semver (X.Y.Z)
  4. Declared component paths resolve to existing files/directories
  5. marketplace.json has required fields (name, plugins list)
  6. Each plugin listed in marketplace.json matches a known plugin name
  7. plugin.json version >= latest git tag (no version regression)
  8. Claude and Cursor plugin.json versions stay in sync

Run: python scripts/validate-manifest.py
Exits non-zero on any violation.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_PLUGIN_DIR = REPO_ROOT / ".claude-plugin"
CURSOR_PLUGIN_DIR = REPO_ROOT / ".cursor-plugin"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

errors: list[str] = []


def error(msg: str) -> None:
    errors.append(msg)
    print(f"  ERROR: {msg}", file=sys.stderr)


def load_json(path: Path) -> dict | list | None:
    """Load and parse a JSON file. Returns None on failure."""
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        error(f"{path}: malformed JSON — {e}")
        return None
    except FileNotFoundError:
        error(f"{path}: file not found")
        return None


def parse_semver(version: str) -> tuple[int, ...] | None:
    """Parse X.Y.Z into a comparable tuple."""
    if not SEMVER_RE.match(version):
        return None
    return tuple(int(x) for x in version.split("."))


def get_latest_tag_version() -> tuple[int, ...] | None:
    """Get the latest semver git tag as a tuple."""
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-v:refname"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        for line in result.stdout.strip().splitlines():
            tag = line.strip().lstrip("v")
            parsed = parse_semver(tag)
            if parsed is not None:
                return parsed
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def resolve_component_path(raw_path: str) -> Path:
    return (REPO_ROOT / raw_path.lstrip("./")).resolve()


def validate_component_paths(label: str, data: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        raw_path = data.get(field)
        if not raw_path:
            continue
        resolved = resolve_component_path(raw_path)
        if not resolved.exists():
            error(
                f"{label}: {field} path '{raw_path}' does not exist "
                f"(resolved: {resolved})"
            )


def validate_plugin_json(plugin_dir: Path, *, require_hooks: bool) -> None:
    """Validate plugin.json under a plugin manifest directory."""
    label = f"{plugin_dir.name}/plugin.json"
    print(f"Validating {label}...")
    path = plugin_dir / "plugin.json"
    data = load_json(path)
    if data is None:
        return

    required = {"name", "version", "description", "author"}
    missing = required - set(data.keys())
    if missing:
        error(f"{label}: missing required fields: {sorted(missing)}")

    version = data.get("version", "")
    if version and not SEMVER_RE.match(version):
        error(f"{label}: version '{version}' is not valid semver (expected X.Y.Z)")

    hooks_path = data.get("hooks")
    if hooks_path:
        resolved = resolve_component_path(hooks_path)
        if not resolved.exists():
            error(
                f"{label}: hooks path '{hooks_path}' does not exist "
                f"(resolved: {resolved})"
            )
    elif require_hooks:
        error(f"{label}: no 'hooks' field — hooks file reference missing")

    validate_component_paths(label, data, ("skills", "agents", "rules", "commands"))

    if version:
        current = parse_semver(version)
        latest_tag = get_latest_tag_version()
        if current and latest_tag and current < latest_tag:
            error(
                f"{label}: version {version} is less than latest tag "
                f"{'.'.join(str(x) for x in latest_tag)} — version regression"
            )


def validate_marketplace_json(plugin_dir: Path) -> None:
    """Validate marketplace.json under a plugin manifest directory."""
    label = f"{plugin_dir.name}/marketplace.json"
    print(f"Validating {label}...")
    path = plugin_dir / "marketplace.json"
    data = load_json(path)
    if data is None:
        return

    if "name" not in data:
        error(f"{label}: missing required field 'name'")

    plugins = data.get("plugins")
    if plugins is None:
        error(f"{label}: missing required field 'plugins'")
        return

    if not isinstance(plugins, list):
        error(f"{label}: 'plugins' must be a list")
        return

    plugin_json_path = plugin_dir / "plugin.json"
    plugin_data = load_json(plugin_json_path)
    known_plugin_name = plugin_data.get("name") if plugin_data else None

    for i, entry in enumerate(plugins):
        if not isinstance(entry, dict):
            error(f"{label}: plugins[{i}] is not an object")
            continue
        entry_name = entry.get("name")
        if not entry_name:
            error(f"{label}: plugins[{i}] missing 'name' field")
        elif known_plugin_name and entry_name != known_plugin_name:
            error(
                f"{label}: plugins[{i}].name '{entry_name}' "
                f"does not match plugin.json name '{known_plugin_name}'"
            )


def validate_all_json_files(plugin_dir: Path) -> None:
    """Ensure every .json in a plugin dir is parseable."""
    print(f"Checking all JSON files in {plugin_dir.name}/...")
    if not plugin_dir.exists():
        error(f"{plugin_dir.name}/ directory does not exist")
        return

    json_files = list(plugin_dir.glob("*.json"))
    if not json_files:
        error(f"{plugin_dir.name}/ contains no JSON files")
        return

    for path in json_files:
        load_json(path)


def validate_version_sync() -> None:
    """Claude and Cursor plugin manifests must share the same version."""
    claude_path = CLAUDE_PLUGIN_DIR / "plugin.json"
    cursor_path = CURSOR_PLUGIN_DIR / "plugin.json"
    claude_data = load_json(claude_path)
    cursor_data = load_json(cursor_path)
    if not claude_data or not cursor_data:
        return

    claude_version = claude_data.get("version")
    cursor_version = cursor_data.get("version")
    if claude_version != cursor_version:
        error(
            "plugin.json version mismatch: "
            f".claude-plugin has {claude_version!r}, "
            f".cursor-plugin has {cursor_version!r}"
        )


def main() -> int:
    print(f"Manifest validation — repo root: {REPO_ROOT}\n")

    validate_all_json_files(CLAUDE_PLUGIN_DIR)
    validate_plugin_json(CLAUDE_PLUGIN_DIR, require_hooks=True)
    validate_marketplace_json(CLAUDE_PLUGIN_DIR)

    validate_all_json_files(CURSOR_PLUGIN_DIR)
    validate_plugin_json(CURSOR_PLUGIN_DIR, require_hooks=False)
    validate_marketplace_json(CURSOR_PLUGIN_DIR)
    validate_version_sync()

    print()
    if errors:
        print(f"FAILED — {len(errors)} error(s) found.", file=sys.stderr)
        return 1

    print("PASSED — all manifest checks OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
