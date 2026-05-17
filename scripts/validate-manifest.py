#!/usr/bin/env python3
"""Validate .claude-plugin/ manifest files.

Checks:
  1. All JSON files in .claude-plugin/ are valid JSON
  2. plugin.json has required fields (name, version, description, author)
  3. plugin.json version follows semver (X.Y.Z)
  4. Hooks path in plugin.json resolves to an existing file
  5. marketplace.json has required fields (name, plugins list)
  6. Each plugin listed in marketplace.json matches a known plugin name
  7. plugin.json version >= latest git tag (no version regression)

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
PLUGIN_DIR = REPO_ROOT / ".claude-plugin"

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
        error(f"{path.name}: malformed JSON — {e}")
        return None
    except FileNotFoundError:
        error(f"{path.name}: file not found")
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


def validate_plugin_json() -> None:
    """Validate .claude-plugin/plugin.json."""
    print("Validating plugin.json...")
    path = PLUGIN_DIR / "plugin.json"
    data = load_json(path)
    if data is None:
        return

    # Required top-level fields
    required = {"name", "version", "description", "author"}
    missing = required - set(data.keys())
    if missing:
        error(f"plugin.json: missing required fields: {sorted(missing)}")

    # Version follows semver
    version = data.get("version", "")
    if version and not SEMVER_RE.match(version):
        error(f"plugin.json: version '{version}' is not valid semver (expected X.Y.Z)")

    # Hooks path resolves to an existing file
    hooks_path = data.get("hooks")
    if hooks_path:
        resolved = (REPO_ROOT / hooks_path.lstrip("./")).resolve()
        if not resolved.exists():
            error(
                f"plugin.json: hooks path '{hooks_path}' does not exist (resolved: {resolved})"
            )
    else:
        error("plugin.json: no 'hooks' field — hooks file reference missing")

    # Version >= latest git tag (no regression)
    if version:
        current = parse_semver(version)
        latest_tag = get_latest_tag_version()
        if current and latest_tag and current < latest_tag:
            error(
                f"plugin.json: version {version} is less than latest tag "
                f"{'.'.join(str(x) for x in latest_tag)} — version regression"
            )


def validate_marketplace_json() -> None:
    """Validate .claude-plugin/marketplace.json."""
    print("Validating marketplace.json...")
    path = PLUGIN_DIR / "marketplace.json"
    data = load_json(path)
    if data is None:
        return

    # Required fields
    if "name" not in data:
        error("marketplace.json: missing required field 'name'")

    plugins = data.get("plugins")
    if plugins is None:
        error("marketplace.json: missing required field 'plugins'")
        return

    if not isinstance(plugins, list):
        error("marketplace.json: 'plugins' must be a list")
        return

    # Each listed plugin should reference a known plugin name from plugin.json
    plugin_json_path = PLUGIN_DIR / "plugin.json"
    plugin_data = load_json(plugin_json_path)
    known_plugin_name = plugin_data.get("name") if plugin_data else None

    for i, entry in enumerate(plugins):
        if not isinstance(entry, dict):
            error(f"marketplace.json: plugins[{i}] is not an object")
            continue
        entry_name = entry.get("name")
        if not entry_name:
            error(f"marketplace.json: plugins[{i}] missing 'name' field")
        elif known_plugin_name and entry_name != known_plugin_name:
            error(
                f"marketplace.json: plugins[{i}].name '{entry_name}' "
                f"does not match plugin.json name '{known_plugin_name}'"
            )


def validate_all_json_files() -> None:
    """Ensure every .json in .claude-plugin/ is parseable."""
    print("Checking all JSON files in .claude-plugin/...")
    if not PLUGIN_DIR.exists():
        error(".claude-plugin/ directory does not exist")
        return

    json_files = list(PLUGIN_DIR.glob("*.json"))
    if not json_files:
        error(".claude-plugin/ contains no JSON files")
        return

    for path in json_files:
        load_json(path)


def main() -> int:
    print(f"Manifest validation — repo root: {REPO_ROOT}\n")

    validate_all_json_files()
    validate_plugin_json()
    validate_marketplace_json()

    print()
    if errors:
        print(f"FAILED — {len(errors)} error(s) found.", file=sys.stderr)
        return 1

    print("PASSED — all manifest checks OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
