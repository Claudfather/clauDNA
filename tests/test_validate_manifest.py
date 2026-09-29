"""Tests for the manifest gate (scripts/validate-manifest.py).

The gate guards two manifests that are *not* interchangeable. Claude Code
reads .claude-plugin/ and wires the shell hooks; Cursor reads .cursor-plugin/
and deliberately wires none. Several rules therefore apply to one host and
must not apply to the other — most visibly the marketplace name, which stays
`Claudfather` for Claude Code (the documented install command depends on that
casing) and must be `claudfather` for Cursor (whose identifier grammar admits
only lowercase alphanumerics and hyphens).

Every check is driven through the real script as a subprocess, against a
synthetic repo root seeded with the *shipped* manifests. Two consequences,
both deliberate: the baseline case fails if the real manifests stop passing,
and the module-level `errors` list cannot leak between cases the way it would
if the functions were imported and called in-process.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate-manifest.py"


def build_repo(tmp_path: Path) -> Path:
    """Seed a synthetic repo root that mirrors the shipped layout.

    Only what the manifests declare needs to exist, so the component
    directories are empty — skill and agent *content* is the business of
    validate-skills.py and validate-agents.py, not this gate.
    """
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, root / "scripts" / "validate-manifest.py")
    # validate-manifest.py imports check_cursor_scope, which imports
    # skill_checks (#340) -- both travel with it so the subprocess's
    # top-level import resolves.
    for module in ("check_cursor_scope.py", "skill_checks.py"):
        shutil.copy2(REPO_ROOT / "scripts" / module, root / "scripts" / module)

    for manifest_dir in (".claude-plugin", ".cursor-plugin"):
        (root / manifest_dir).mkdir()
        for name in ("plugin.json", "marketplace.json"):
            shutil.copy2(REPO_ROOT / manifest_dir / name, root / manifest_dir / name)

    (root / "skills").mkdir()
    # A cursor manifest may declare skills as an explicit list of individual
    # directories rather than one directory string (#340); each entry then
    # needs to exist for validate_declared_path()'s existence check. Mirror
    # whatever the REAL manifest currently declares, rather than hardcoding
    # a list that goes stale the next time a skill is added or removed.
    real_cursor_skills = json.loads((REPO_ROOT / CURSOR).read_text()).get("skills")
    if isinstance(real_cursor_skills, list):
        for entry in real_cursor_skills:
            # Path(...) already normalizes a leading "./" on join -- lstrip("./")
            # strips characters, not a prefix, and repeats the #344 fix this
            # fixture exists to guard (harmless today, since every real entry
            # starts with "./skills/", but the fixture should match the fix).
            (root / entry).mkdir(parents=True, exist_ok=True)
    (root / "agents").mkdir()
    (root / "assets").mkdir()
    (root / "assets" / "logo.svg").write_text("<svg />\n")
    (root / "plugin-hooks").mkdir()
    (root / "plugin-hooks" / "hooks.json").write_text("{}\n")
    return root


def run_gate(root: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "scripts/validate-manifest.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def patch(root: Path, manifest: str, key: str, value: object) -> None:
    """Set (or, with value=None, delete) one top-level manifest field."""
    path = root / manifest
    data = json.loads(path.read_text())
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    path.write_text(json.dumps(data, indent=2) + "\n")


CURSOR = ".cursor-plugin/plugin.json"
CURSOR_MARKET = ".cursor-plugin/marketplace.json"
CLAUDE = ".claude-plugin/plugin.json"
CLAUDE_MARKET = ".claude-plugin/marketplace.json"


# --- baseline ---


def test_shipped_manifests_pass(tmp_path):
    """The positive control. Every negative case below depends on it."""
    root = build_repo(tmp_path)
    code, output = run_gate(root)
    assert code == 0, output
    assert "PASSED" in output


# --- name grammar ---


def test_cursor_marketplace_name_must_be_lowercase(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CURSOR_MARKET, "name", "Claudfather")
    code, output = run_gate(root)
    assert code != 0
    assert "not lowercase kebab-case" in output


def test_claude_marketplace_name_may_stay_capitalized(tmp_path):
    """Scoping guard: /plugin install claudna@Claudfather depends on the case.

    The shipped Claude manifest is already named `Claudfather`, so the
    baseline covers this — but only by accident of the current value. Setting
    it explicitly keeps the guard honest if that value ever changes.
    """
    root = build_repo(tmp_path)
    patch(root, CLAUDE_MARKET, "name", "Claudfather")
    code, output = run_gate(root)
    assert code == 0, output


def test_plugin_name_must_be_kebab_case(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CURSOR, "name", "clauDNA")
    code, output = run_gate(root)
    assert code != 0
    assert "is not lowercase kebab-case" in output


def test_duplicate_plugin_names_rejected(tmp_path):
    root = build_repo(tmp_path)
    entry = {"name": "claudna", "source": "."}
    patch(root, CURSOR_MARKET, "plugins", [entry, dict(entry)])
    code, output = run_gate(root)
    assert code != 0
    assert "duplicate plugin name" in output


def test_marketplace_owner_name_required(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CURSOR_MARKET, "owner", {})
    code, output = run_gate(root)
    assert code != 0
    assert "owner.name" in output


# --- logo ---


def test_cursor_logo_required(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CURSOR, "logo", None)
    code, output = run_gate(root)
    assert code != 0
    assert "no 'logo' field" in output


def test_cursor_logo_must_be_committed_not_a_url(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CURSOR, "logo", "https://example.com/logo.svg")
    code, output = run_gate(root)
    assert code != 0
    assert "is a URL" in output


def test_cursor_logo_must_exist(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CURSOR, "logo", "assets/missing.svg")
    code, output = run_gate(root)
    assert code != 0
    assert "does not exist" in output


# --- path safety ---


def test_declared_path_may_not_escape_the_plugin_root(tmp_path):
    """resolve_component_path()'s lstrip("./") turns '../x' into 'x'.

    That is str.lstrip over a character set, so a traversal check applied to
    the resolved path would see an ordinary relative path. This fails only if
    the check runs on the raw manifest string.
    """
    root = build_repo(tmp_path)
    (tmp_path / "skills").mkdir()  # make the escaped target real
    patch(root, CURSOR, "skills", "../skills")
    code, output = run_gate(root)
    assert code != 0
    assert "must be relative with no '..'" in output


def test_declared_path_may_not_be_absolute(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CURSOR, "skills", "/etc")
    code, output = run_gate(root)
    assert code != 0
    assert "must be relative with no '..'" in output


def test_component_path_accepts_a_list(tmp_path):
    """Cursor allows a list of paths per component; each entry is checked.

    Nested under skills/, not a repo-root sibling: the cursor-scope gate
    (#340/#343) refuses a skills[] entry outside skills/ by design, so a
    fixture testing this UNRELATED generic path-existence check must not
    also trip that one.
    """
    root = build_repo(tmp_path)
    (root / "skills" / "extra-skills").mkdir()
    patch(root, CURSOR, "skills", ["./skills/", "./skills/extra-skills/"])
    code, output = run_gate(root)
    assert code == 0, output

    patch(root, CURSOR, "skills", ["./skills/", "./ghost/"])
    code, output = run_gate(root)
    assert code != 0
    assert "./ghost/" in output


def test_marketplace_source_must_resolve_to_a_manifest(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CURSOR_MARKET, "plugins", [{"name": "claudna", "source": "nowhere"}])
    code, output = run_gate(root)
    assert code != 0
    assert "no .cursor-plugin/plugin.json" in output


# --- hooks stay out of Cursor ---


def test_cursor_manifest_may_not_declare_hooks(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CURSOR, "hooks", "./plugin-hooks/hooks.json")
    code, output = run_gate(root)
    assert code != 0
    assert "deliberately hook-free" in output


def test_stray_hooks_directory_is_rejected(tmp_path):
    """Cursor discovers hooks at hooks/hooks.json by folder convention.

    This is the invisible half: the directory alone wires the Claude Code
    shell hooks into Cursor sessions, with no manifest diff to review.
    """
    root = build_repo(tmp_path)
    (root / "hooks").mkdir()
    (root / "hooks" / "hooks.json").write_text("{}\n")
    code, output = run_gate(root)
    assert code != 0
    assert "Cursor discovers hooks" in output


def test_claude_manifest_still_requires_hooks(tmp_path):
    """The mirror of the rule above — Claude Code is where the hooks belong."""
    root = build_repo(tmp_path)
    patch(root, CLAUDE, "hooks", None)
    code, output = run_gate(root)
    assert code != 0
    assert "no 'hooks' field" in output


# --- version sync (the release.sh failure mode) ---


def test_version_mismatch_between_manifests_is_rejected(tmp_path):
    """release.sh bumped only .claude-plugin/ and would have tripped this."""
    root = build_repo(tmp_path)
    patch(root, CLAUDE, "version", "0.99.0")
    code, output = run_gate(root)
    assert code != 0
    assert "version mismatch" in output


def test_non_semver_version_is_rejected(tmp_path):
    root = build_repo(tmp_path)
    patch(root, CLAUDE, "version", "0.19")
    patch(root, CURSOR, "version", "0.19")
    code, output = run_gate(root)
    assert code != 0
    assert "not valid semver" in output


# --- cursor-scope gate wiring (#344 -- #343 shipped the gate; nothing pinned
# that validate-manifest.py actually calls it) ---


def build_repo_with_restricted_skill(tmp_path: Path) -> tuple[Path, str]:
    """build_repo(), plus a real SKILL.md on one already-listed Cursor skill,
    marking it host-restricted -- reproducing #340's exact failure mode: a
    skill that cannot run on Cursor, shipped to Cursor anyway.

    build_repo()'s skill directories are deliberately empty (skill *content*
    is validate-skills.py's business, not this gate's -- see its docstring).
    This writes just enough frontmatter for check_cursor_scope.run_check() to
    read, without needing to satisfy validate-skills.py's own contract (a
    different script, not exercised by validate-manifest.py or this test).
    """
    root = build_repo(tmp_path)
    real_cursor_skills = json.loads((REPO_ROOT / CURSOR).read_text()).get("skills")
    assert isinstance(real_cursor_skills, list) and real_cursor_skills, (
        "the real Cursor manifest must be a non-empty explicit list for this "
        "fixture to mark one entry -- if it ever reverts to directory "
        "discovery, this fixture needs a different way to pick a skill"
    )
    marked = Path(real_cursor_skills[0]).name
    skill_md = root / "skills" / marked / "SKILL.md"
    skill_md.write_text(f"---\nname: {marked}\ndescription: fixture\nhosts: [claude-code]\n---\nfixture body\n")
    return root, marked


def test_cursor_manifest_shipping_a_restricted_skill_is_rejected(tmp_path):
    """Pins the wiring #343 left unpinned (#344, ravi's review of #343,
    issuecomment-5883111726). If validate-manifest.py's call to
    run_cursor_scope_check were removed, or its errors were printed instead
    of passed to error(), this is the only test in the suite that would
    notice: make check still catches manifest drift through
    test_cursor_scope.py's test_real_repo_passes_clean, which calls run_check
    directly, but the standalone `validate-manifest.yml` workflow runs only
    this script as a subprocess, with no such backstop -- and that gap is
    exactly what let a restricted skill ship to Cursor in the first place.
    """
    root, marked = build_repo_with_restricted_skill(tmp_path)
    code, output = run_gate(root)
    assert code != 0
    assert marked in output
    assert "#340" in output
