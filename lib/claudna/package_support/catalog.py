"""Validate the generated JSON projection and its local sources, without YAML.

Hashes establish consistency with source bytes, not publisher authenticity. The
development generator owns frontmatter parsing; this consumer checks its schema,
source coverage and manifest membership without reconstructing frontmatter.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path, PurePosixPath

CATALOG = "lib/claudna/package_support/catalog.json"
POLICY = "lib/claudna/package_support/host-policy.json"
HOSTS = {"claude-code", "cursor", "codex"}
CLI = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_.+-]*)(?:>=(\d+(?:\.\d+){0,2}))?")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
POLICY_FIELDS = {"manifest", "marketplace", "agents", "hook_capability", "runtime_platforms",
                 "runtime_prerequisites", "evidence_limits"}


class InvalidPackage(ValueError):
    """A fixed diagnostic code; never includes raw input, paths or parser errors."""


def require(condition: bool, code: str = "metadata_schema") -> None:
    if not condition:
        raise InvalidPackage(code)


def bundled(root: Path, relative: str, *, directory: bool = False) -> Path:
    """Only regular root-contained paths; reject symlinks even within the root."""
    require(isinstance(relative, str) and bool(relative) and "\\" not in relative
            and "\0" not in relative, "bundled_path")
    pure = PurePosixPath(relative)
    require(not pure.is_absolute() and ".." not in pure.parts and bool(pure.parts), "bundled_path")
    path = root
    for part in pure.parts:
        path = path / part
        require(not path.is_symlink(), "bundled_symlink")
    require(path.resolve().is_relative_to(root), "bundled_path")
    require(path.is_dir() if directory else path.is_file(), "bundled_missing")
    return path


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def read_json(root: Path, relative: str) -> dict:
    data = json.loads(bundled(root, relative).read_text(encoding="utf-8"), object_pairs_hook=_unique)
    require(isinstance(data, dict))
    return data


def _strings(value, *, choices=None, nonempty=False):
    require(isinstance(value, list) and (not nonempty or bool(value)))
    require(all(isinstance(item, str) for item in value))
    require(len(value) == len(set(value)))
    if choices is not None:
        require(set(value) <= choices)


def _requires(value):
    require(isinstance(value, list))
    for entry in value:
        require(isinstance(entry, dict))
        keys = set(entry)
        require(keys <= {"cli", "env", "reason"} and len(keys & {"cli", "env"}) == 1)
        require("reason" not in entry or isinstance(entry["reason"], str))
        key = "cli" if "cli" in entry else "env"
        pattern = CLI if key == "cli" else re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
        require(isinstance(entry[key], str) and pattern.fullmatch(entry[key]) is not None)


def _skill_names(root: Path) -> set[str]:
    names = set()
    for path in bundled(root, "skills", directory=True).iterdir():
        require(not path.is_symlink(), "bundled_symlink")
        if path.is_dir() and path.name != "_shared" and (path / "SKILL.md").exists():
            require(NAME.fullmatch(path.name) is not None, "skill_membership")
            bundled(root, f"skills/{path.name}/SKILL.md")
            names.add(path.name)
    require(bool(names), "skill_membership")
    return names


def _selected(root: Path, manifest: dict, host: str, names: set[str]) -> set[str]:
    if host == "claude-code" and "skills" not in manifest:
        return names
    raw = manifest.get("skills")
    entries = [raw] if isinstance(raw, str) else raw
    require(isinstance(entries, list) and bool(entries), "manifest_membership")
    selected = set()
    for entry in entries:
        path = bundled(root, entry, directory=True)
        if path == root / "skills":
            selected.update(names)
        else:
            require(path.parent == root / "skills" and path.name in names, "manifest_membership")
            selected.add(path.name)
    return selected


def _hooks(root: Path, manifest: dict, host: str) -> dict:
    if "hooks" not in manifest:
        return {"path": None, "events": {}, "handler_count": 0}
    require(host != "cursor", "hook_membership")
    relative = manifest["hooks"]
    config = read_json(root, relative)
    events = config.get("hooks")
    require(isinstance(events, dict), "hook_membership")
    counts = {}
    for event, groups in events.items():
        require(isinstance(event, str) and isinstance(groups, list), "hook_membership")
        counts[event] = 0
        for group in groups:
            require(isinstance(group, dict) and isinstance(group.get("hooks"), list), "hook_membership")
            for handler in group["hooks"]:
                require(isinstance(handler, dict) and handler.get("type") == "command"
                        and isinstance(handler.get("command"), str), "hook_membership")
                words = shlex.split(handler["command"])
                require(bool(words), "hook_membership")
                prefix = "${PLUGIN_ROOT}/" if host == "codex" else "${CLAUDE_PLUGIN_ROOT}/"
                require(words[0].startswith(prefix), "bundled_path")
                bundled(root, words[0][len(prefix):])
                counts[event] += 1
    return {"path": bundled(root, relative).relative_to(root).as_posix(),
            "events": counts, "handler_count": sum(counts.values())}


def load(root: Path) -> dict:
    """Return a validated projection or fail closed with a non-sensitive code."""
    require(root.is_absolute() and root.is_dir(), "package_root")
    catalog = read_json(root, CATALOG)
    require(set(catalog) == {"schema", "package_version", "sources", "skills", "hosts"})
    require(catalog["schema"] == "claudna.package-support/1")
    require(isinstance(catalog["package_version"], str)
            and re.fullmatch(r"\d+\.\d+\.\d+", catalog["package_version"]) is not None)
    sources, skills, hosts = catalog["sources"], catalog["skills"], catalog["hosts"]
    require(isinstance(sources, dict) and isinstance(skills, dict) and isinstance(hosts, dict))
    require(set(hosts) == HOSTS)
    policy = read_json(root, POLICY)
    require(set(policy) == {"schema", "hosts"} and policy["schema"] == "claudna.host-policy/1"
            and isinstance(policy["hosts"], dict) and set(policy["hosts"]) == HOSTS)
    names = _skill_names(root)
    require(set(skills) == names, "skill_membership")
    expected_sources = {POLICY}
    for name, entry in skills.items():
        require(isinstance(entry, dict) and set(entry) == {
            "path", "description", "hosts", "requires_context", "requires"})
        require(entry["path"] == f"skills/{name}/SKILL.md", "skill_membership")
        require(isinstance(entry["description"], str) and bool(entry["description"].strip()))
        _strings(entry["hosts"], choices=HOSTS, nonempty=True)
        require(entry["requires_context"] is None or entry["requires_context"] == "repo-clone")
        _requires(entry["requires"])
        expected_sources.add(entry["path"])
    for host, entry in hosts.items():
        require(isinstance(entry, dict) and set(entry) == POLICY_FIELDS | {"skills", "skill_count", "hooks"})
        settings = policy["hosts"][host]
        require(isinstance(settings, dict) and set(settings) == POLICY_FIELDS)
        require(all(entry[key] == settings[key] for key in POLICY_FIELDS), "policy_mismatch")
        for key in POLICY_FIELDS - {"runtime_platforms", "runtime_prerequisites"}:
            require(isinstance(entry[key], str) and bool(entry[key].strip()))
        _strings(entry["runtime_platforms"], choices={"macOS", "Linux"})
        _requires(entry["runtime_prerequisites"])
        _strings(entry["skills"], choices=names, nonempty=True)
        require(type(entry["skill_count"]) is int and entry["skill_count"] == len(entry["skills"]))
        manifest = read_json(root, entry["manifest"])
        read_json(root, entry["marketplace"])
        require(manifest.get("name") == "claudna" and manifest.get("version") == catalog["package_version"],
                "manifest_version")
        require(set(entry["skills"]) == _selected(root, manifest, host, names), "manifest_membership")
        if host != "claude-code":
            require(all(host in skills[name]["hosts"] for name in entry["skills"]), "manifest_membership")
            require(all(skills[name]["requires_context"] is None for name in entry["skills"]),
                    "manifest_membership")
        hooks = entry["hooks"]
        require(isinstance(hooks, dict) and set(hooks) == {"path", "events", "handler_count"})
        require(type(hooks["handler_count"]) is int and isinstance(hooks["events"], dict)
                and all(type(count) is int for count in hooks["events"].values()))
        require(hooks == _hooks(root, manifest, host), "hook_membership")
        expected_sources.update({entry["manifest"], entry["marketplace"]})
        if entry["hooks"]["path"]:
            expected_sources.add(entry["hooks"]["path"])
        bundled(root, manifest.get("agents", "agents"), directory=True)
        if "logo" in manifest:
            bundled(root, manifest["logo"])
    require(not (root / "hooks/hooks.json").exists() and not (root / "hooks/hooks.json").is_symlink(),
            "hook_membership")
    require(set(sources) == expected_sources, "source_membership")
    for relative, digest in sources.items():
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None)
        require(hashlib.sha256(bundled(root, relative).read_bytes()).hexdigest() == digest, "source_hash")
    for relative in ("lib/claudna/session_store/__main__.py", "lib/claudna/package_support/__main__.py",
                     "lib/claudna/package_support/catalog.py", "lib/claudna/package_support/doctor.py",
                     "skills/_shared/claudna-root.md", "skills/_shared/codex-tools.md"):
        bundled(root, relative)
    return catalog
