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

Cursor-only checks, mirroring the submission checklist at
https://cursor.com/docs/reference/plugins and the validator in
cursor/plugin-template (scripts/validate-template.mjs):

  9. Plugin `name` is lowercase kebab-case (alphanumerics, hyphens, periods;
     starts and ends alphanumeric)
 10. Marketplace `name` is lowercase kebab-case. Cursor only — Claude Code's
     marketplace is named `Claudfather` and the documented install command
     (`/plugin install claudna@Claudfather`) depends on that casing.
 11. A `logo` is declared, relative, and committed
 12. Every declared path is relative with no `..` and no absolute prefix,
     checked against the raw manifest string
 13. The Cursor manifest stays hook-free: no `hooks` field, and no
     `hooks/hooks.json` for Cursor's folder discovery to find

Run: python scripts/validate-manifest.py
Exits non-zero on any violation.
"""

from __future__ import annotations

import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_PLUGIN_DIR = REPO_ROOT / ".claude-plugin"
CURSOR_PLUGIN_DIR = REPO_ROOT / ".cursor-plugin"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# Cursor's identifier grammar (cursor/plugin-template validate-template.mjs).
# Plugin names additionally allow periods (e.g. `prompts.chat`).
PLUGIN_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
MARKETPLACE_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

COMPONENT_FIELDS = ("skills", "agents", "rules", "commands")

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


def is_safe_relative(raw_path: str) -> bool:
    """Reject absolute paths and any escape above the plugin root.

    Judged on the raw manifest string, because resolve_component_path()'s
    lstrip("./") would quietly turn '../secrets' into 'secrets' and hide the
    traversal it is supposed to catch.
    """
    if not raw_path:
        return False
    if PurePosixPath(raw_path).is_absolute():
        return False
    normalized = posixpath.normpath(raw_path.replace("\\", "/"))
    return normalized != ".." and not normalized.startswith("../")


def validate_declared_path(label: str, field: str, raw_path: str) -> None:
    """A declared path must be relative, escape-free, and present on disk."""
    if not is_safe_relative(raw_path):
        error(
            f"{label}: {field} path '{raw_path}' must be relative with no '..' "
            "and no absolute prefix"
        )
        return
    resolved = resolve_component_path(raw_path)
    if not resolved.exists():
        error(
            f"{label}: {field} path '{raw_path}' does not exist "
            f"(resolved: {resolved})"
        )


def validate_component_paths(label: str, data: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        raw = data.get(field)
        if not raw:
            continue
        # Cursor accepts a single path or a list of them for every component.
        values = [raw] if isinstance(raw, str) else raw
        if not isinstance(values, list):
            error(f"{label}: {field} must be a string or a list of strings")
            continue
        for value in values:
            if not isinstance(value, str):
                error(f"{label}: {field} entry {value!r} is not a string")
                continue
            validate_declared_path(label, field, value)


def validate_plugin_json(
    plugin_dir: Path,
    *,
    require_hooks: bool,
    forbid_hooks: bool = False,
    require_logo: bool = False,
) -> None:
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

    name = data.get("name", "")
    if name and not PLUGIN_NAME_RE.match(name):
        error(
            f"{label}: name '{name}' is not lowercase kebab-case "
            "(alphanumerics, hyphens, periods; must start and end alphanumeric)"
        )

    version = data.get("version", "")
    if version and not SEMVER_RE.match(version):
        error(f"{label}: version '{version}' is not valid semver (expected X.Y.Z)")

    hooks_path = data.get("hooks")
    if hooks_path:
        if forbid_hooks:
            error(
                f"{label}: declares hooks '{hooks_path}' — this manifest is "
                "deliberately hook-free so Cursor-based environments never fire "
                "the Claude Code shell hooks"
            )
        else:
            validate_declared_path(label, "hooks", hooks_path)
    elif require_hooks:
        error(f"{label}: no 'hooks' field — hooks file reference missing")

    logo = data.get("logo")
    if logo:
        if logo.startswith(("http://", "https://")):
            # Cursor accepts an absolute URL, but the checklist prefers a
            # committed file, and only a committed file is versioned with the
            # manifest that points at it.
            error(
                f"{label}: logo '{logo}' is a URL — commit the logo and "
                "reference it by relative path so it is versioned with the plugin"
            )
        else:
            validate_declared_path(label, "logo", logo)
    elif require_logo:
        error(
            f"{label}: no 'logo' field — the marketplace submission checklist "
            "wants a logo committed to the repo and referenced by relative path"
        )

    validate_component_paths(label, data, COMPONENT_FIELDS)

    if version:
        current = parse_semver(version)
        latest_tag = get_latest_tag_version()
        if current and latest_tag and current < latest_tag:
            error(
                f"{label}: version {version} is less than latest tag "
                f"{'.'.join(str(x) for x in latest_tag)} — version regression"
            )


def validate_marketplace_json(plugin_dir: Path, *, cursor: bool = False) -> None:
    """Validate marketplace.json under a plugin manifest directory."""
    label = f"{plugin_dir.name}/marketplace.json"
    print(f"Validating {label}...")
    path = plugin_dir / "marketplace.json"
    data = load_json(path)
    if data is None:
        return

    name = data.get("name")
    if name is None:
        error(f"{label}: missing required field 'name'")
    elif cursor and not MARKETPLACE_NAME_RE.match(name):
        error(
            f"{label}: name '{name}' is not lowercase kebab-case — Cursor's "
            "marketplace identifier grammar allows only lowercase "
            "alphanumerics and hyphens"
        )

    owner = data.get("owner")
    if not isinstance(owner, dict) or not owner.get("name"):
        error(f"{label}: missing required field 'owner.name'")

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

    seen_names: set[str] = set()
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
        if entry_name:
            if entry_name in seen_names:
                error(f"{label}: duplicate plugin name '{entry_name}'")
            seen_names.add(entry_name)

        if not cursor:
            continue

        # A Cursor marketplace entry's `source` is a path relative to the repo
        # root, and resolution looks for <source>/.cursor-plugin/plugin.json.
        source = entry.get("source")
        if not isinstance(source, str):
            error(f"{label}: plugins[{i}].source must be a relative path string")
            continue
        if not is_safe_relative(source):
            error(
                f"{label}: plugins[{i}].source '{source}' must be relative "
                "with no '..' and no absolute prefix"
            )
            continue
        source_manifest = (
            (REPO_ROOT / source).resolve() / ".cursor-plugin" / "plugin.json"
        )
        if not source_manifest.exists():
            error(
                f"{label}: plugins[{i}].source '{source}' has no "
                f".cursor-plugin/plugin.json (looked for {source_manifest})"
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


def validate_cursor_hook_free() -> None:
    """Cursor must not discover hooks by folder convention.

    The Claude Code hooks live in plugin-hooks/ — renamed away from hooks/ to
    dodge a Claude Code bug, and load-bearing here for a second reason: hooks/
    is exactly where Cursor's folder discovery looks. A hooks/ directory at the
    repo root would wire the Claude shell hooks into Cursor sessions with no
    manifest change to notice.
    """
    print("Checking Cursor stays hook-free...")
    stray = REPO_ROOT / "hooks" / "hooks.json"
    if stray.exists():
        error(
            f"{stray.relative_to(REPO_ROOT)} exists — Cursor discovers hooks at "
            "hooks/hooks.json by convention. Plugin hooks belong in "
            "plugin-hooks/, wired only from .claude-plugin/plugin.json"
        )


def main() -> int:
    print(f"Manifest validation — repo root: {REPO_ROOT}\n")

    validate_all_json_files(CLAUDE_PLUGIN_DIR)
    validate_plugin_json(CLAUDE_PLUGIN_DIR, require_hooks=True)
    validate_marketplace_json(CLAUDE_PLUGIN_DIR)

    validate_all_json_files(CURSOR_PLUGIN_DIR)
    validate_plugin_json(
        CURSOR_PLUGIN_DIR,
        require_hooks=False,
        forbid_hooks=True,
        require_logo=True,
    )
    validate_marketplace_json(CURSOR_PLUGIN_DIR, cursor=True)
    validate_cursor_hook_free()
    validate_version_sync()

    print()
    if errors:
        print(f"FAILED — {len(errors)} error(s) found.", file=sys.stderr)
        return 1

    print("PASSED — all manifest checks OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
