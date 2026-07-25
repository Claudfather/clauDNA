#!/usr/bin/env python3
"""Validate every skill under skills/ against SKILL_CONTRACT.md.

Run: python scripts/validate-skills.py
Exits non-zero on any violation; prints a structured report.

In CI (GITHUB_ACTIONS set), only errors from PR-touched skills block.
Untouched skill errors are reported as warnings for visibility.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from check_schema_drift import run_check as run_schema_drift_check
from check_vault_address import run_check as run_vault_address_check
from skill_checks import (
    GATE_EXTENSIONS,
    GATE_PRUNE_DIRS,
    STALE_PATH_RE,
    check_removed_name_mentions,
    collect_skill_reference_errors,
    find_resurrected_dirs,
    get_touched_skills,
    load_removed_skills,
    parse_frontmatter,
    validate_skill_md,
    warn_skill_md,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
REMOVED_SKILLS_FILE = REPO_ROOT / "scripts" / "removed-skills.txt"

SKIP_DIRS = {"_shared"}
SKIP_SKILLS: set[str] = set()  # add skill names here to intentionally bypass validation

# Removed-names gate scope: GATE_EXTENSIONS / GATE_PRUNE_DIRS (imported from
# skill_checks, shared with the vault-address gate) pick the repo-wide text
# surfaces; these exclusions carve out historical records and generated/managed
# paths. CHANGELOG and the archive legitimately narrate removed skills; the gate
# protects living surfaces.
GATE_EXCLUDE_FILES = {"CHANGELOG.md", "scripts/removed-skills.txt"}  # exact paths
# Point-in-time records legitimately narrate retired skills: the archive,
# plan/spec/decision documents (rewriting history would falsify them), and
# cleanup-legacy-install, which enumerates pre-plugin overlay files by their
# retired names by definition. The gate protects LIVING surfaces: README,
# guides, skills/, scripts/, tests/.
GATE_EXCLUDE_PREFIXES = (
    "documentation/archive/",
    "documentation/decisions/",
    "documentation/planning/",
    "documentation/specs/",
    "skills/cleanup-legacy-install/",
)


def scan_removed_names(removed_names: list[str]) -> list[tuple[str, str]]:
    """Walk the repo for mentions of removed skill names.

    Returns (rel_path, message) pairs. Callers must treat these as
    ALWAYS-BLOCKING — never demoted by CI touched-set scoping. Rationale:
    (a) a deleted skill directory can never be "touched" again, and git
    rename-detection can collapse even the deleting PR's removed paths into
    the successor's, so participant-keying silently demotes exactly the
    errors this gate exists to catch; (b) once a deletion release lands,
    main is clean of the removed names, so any hit was introduced by the
    change under test — there is no pre-existing-debt case to demote.

    Pruning matches directory names relative to REPO_ROOT (a checkout that
    itself lives under a directory named e.g. "worktrees" must not disable
    the gate); exclusions compare POSIX-separated relative paths.
    """
    hits: list[tuple[str, str]] = []
    if not removed_names:
        return hits

    candidates: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in GATE_PRUNE_DIRS]
        for fname in filenames:
            if Path(fname).suffix in GATE_EXTENSIONS:
                candidates.append(Path(dirpath) / fname)

    for path in sorted(candidates):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in GATE_EXCLUDE_FILES or rel.startswith(GATE_EXCLUDE_PREFIXES):
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError) as e:
            print(f"WARNING: removed-names gate could not read {rel}: {e}", file=sys.stderr)
            continue
        for _name, msg in check_removed_name_mentions(text, removed_names):
            hits.append((rel, msg))
    return hits


def validate_skill(skill_dir: Path) -> list[str]:
    return validate_skill_md(skill_dir / "SKILL.md", dir_name=skill_dir.name)


def main() -> int:
    if not SKILLS_DIR.is_dir():
        print(f"FAIL: skills directory not found at {SKILLS_DIR}", file=sys.stderr)
        return 2

    touched = get_touched_skills()
    ci_mode = touched is not None
    if ci_mode:
        if touched:
            print(f"CI mode: scoping errors to {len(touched)} touched skill(s): {', '.join(sorted(touched))}\n")
        else:
            print("CI mode: no skills touched in this PR — all errors reported as warnings\n")

    skill_dirs = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir() and p.name not in SKIP_DIRS)
    valid_names = {p.name for p in skill_dirs}

    all_errors: dict[str, list[str]] = {}
    all_warnings: dict[str, list[str]] = {}
    # Cross-skill errors: list of (involved_skills, error_msg) — block if ANY
    # participant is touched, preventing attribution bugs where alphabetical
    # ordering causes the error to land on the wrong (untouched) skill.
    cross_skill_errors: list[tuple[set[str], str, str]] = []  # (participants, target_skill, msg)
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
                        other = seen_names[fm_name]
                        msg = f"duplicate frontmatter name {fm_name!r}"
                        cross_skill_errors.append(({name, other}, name, f"{msg} (also used by {other})"))
                        cross_skill_errors.append(({name, other}, other, f"{msg} (also used by {name})"))
                    else:
                        seen_names[fm_name] = name

        # Cross-skill reference integrity: every claudna:<name> mention in this
        # skill's markdown (SKILL.md + support files) must resolve to a real skill.
        # Registered as cross-skill errors with the TARGET as a participant: a PR
        # that deletes skills/<target>/ marks only <target> as touched, so
        # referrer-keyed errors would demote to warnings in CI — exactly the
        # deletion scenario this check exists to block.
        for md_file in sorted(skill_dir.rglob("*.md")):
            rel = md_file.relative_to(skill_dir)
            for target, msg in collect_skill_reference_errors(md_file.read_text(), valid_names):
                cross_skill_errors.append(({name, target}, name, f"{rel}: {msg}"))

        if errors:
            all_errors[name] = errors

        # Collect warnings (advisory, non-blocking)
        warnings = warn_skill_md(skill_md)
        if warnings:
            all_warnings[name] = warnings

    # Lint _shared files for stale paths and dangling skill references.
    # _shared reference errors join cross_skill_errors keyed on the TARGET
    # alone ("_shared/<file>" is never in the touched set, so referrer-keyed
    # errors there would always demote in CI).
    shared_dir = SKILLS_DIR / "_shared"
    if shared_dir.is_dir():
        for md_file in sorted(shared_dir.rglob("*.md")):
            text = md_file.read_text()
            shared_key = f"_shared/{md_file.relative_to(shared_dir)}"
            stale_errors = [
                f"stale hardcoded path: {line.strip()}"
                for line in text.splitlines()
                if STALE_PATH_RE.search(line)
            ]
            if stale_errors:
                all_errors[shared_key] = stale_errors
            for target, msg in collect_skill_reference_errors(text, valid_names):
                cross_skill_errors.append(({target}, shared_key, msg))

    # Removed-names gate (epic #165 P2 step 0): no living surface may mention
    # a removed skill. Always-blocking — see scan_removed_names for why the
    # touched-set partition must not apply to this error class. A parallel
    # backstop lives in tests/test_removed_names.py (the unpartitioned
    # pytest CI job), so even a validator regression here cannot silently
    # re-open the hole.
    removed_names = load_removed_skills(REMOVED_SKILLS_FILE)
    removed_name_hits = scan_removed_names(removed_names)

    # Directory resurrection (#192): the text gate can't see a removed skill
    # re-created whole as skills/<name>/ with a valid body — catch it here.
    for name in find_resurrected_dirs(removed_names, SKILLS_DIR):
        removed_name_hits.append(
            (
                f"skills/{name}/",
                f"removed skill '{name}' has been re-created as a skill directory -- "
                "resurrections require removing the name from scripts/removed-skills.txt "
                "(a deliberate, reviewable act), not silently restoring the directory",
            )
        )

    # Schema-drift gate (#199, epic #197 P2): skills/_shared/output-guide.md §3
    # is a stamped rendered copy of Claudron SCHEMA.md and the repo's only
    # type/status enum table; publish/index must point at it, and (network
    # permitting) the copy must match the SSOT at the stamped ref. Errors are
    # ALWAYS-BLOCKING, like removed-name hits: vocabulary at an immutable
    # stamped ref cannot change on its own, so any failure was introduced by
    # the change under test. Network failures degrade to notes, never errors
    # -- CI must not flake when the SSOT host is unreachable.
    drift_errors, drift_warnings, drift_notes = run_schema_drift_check(REPO_ROOT)

    # Vault-address conformance (boundary phase D1). ALWAYS-BLOCKING for the
    # same reason as the removed-names gate: main is clean of the removed
    # variable, so any hit was introduced by the change under test. Offline
    # and textual by design -- §10 holds a pointer, not a rendered copy, so
    # there is no local copy to diff (see check_vault_address's docstring).
    vault_errors, vault_warnings, vault_notes = run_vault_address_check(REPO_ROOT)

    total_skills = len(skill_dirs) - len(SKIP_SKILLS)

    # In CI mode, partition errors into blocking (touched) vs warnings (untouched).
    # Cross-skill errors (e.g. duplicate names) block if ANY participant is touched,
    # preventing the bug where alphabetical ordering attributes the error to only
    # one skill — if that skill happens to be untouched, the error silently demotes.
    if ci_mode:
        blocking_errors: dict[str, list[str]] = {}
        demoted_warnings: dict[str, list[str]] = {}
        for name, errors in all_errors.items():
            if name in touched:
                blocking_errors[name] = errors
            else:
                demoted_warnings[name] = errors
        # Cross-skill errors: block if any participant is touched
        for participants, target_skill, msg in cross_skill_errors:
            if participants & touched:
                blocking_errors.setdefault(target_skill, []).append(msg)
            else:
                demoted_warnings.setdefault(target_skill, []).append(msg)
    else:
        blocking_errors = all_errors
        demoted_warnings = {}
        # In local mode, cross-skill errors are always blocking
        for _participants, target_skill, msg in cross_skill_errors:
            blocking_errors.setdefault(target_skill, []).append(msg)

    # Removed-name hits block in BOTH modes — the touched-set partition never
    # applies to this class (see scan_removed_names).
    for rel, msg in removed_name_hits:
        blocking_errors.setdefault(rel, []).append(msg)

    # Schema-drift errors likewise block in BOTH modes (rationale above).
    for msg in drift_errors:
        blocking_errors.setdefault("schema-drift", []).append(msg)

    # Vault-address conformance blocks in BOTH modes (rationale above).
    for msg in vault_errors:
        blocking_errors.setdefault("vault-address", []).append(msg)

    # Drift notes/warnings are advisory — always printed, never blocking.
    if drift_notes or drift_warnings:
        for n in drift_notes:
            print(f"NOTE(schema-drift): {n}")
        for w in drift_warnings:
            print(f"WARN(schema-drift): {w}")
        print()

    if vault_notes or vault_warnings:
        for n in vault_notes:
            print(f"NOTE(vault-address): {n}")
        for w in vault_warnings:
            print(f"WARN(vault-address): {w}")
        print()

    # Print advisory warnings (never blocking)
    if all_warnings:
        print(f"WARN: {len(all_warnings)} skill(s) have advisory warnings\n")
        for name in sorted(all_warnings):
            print(f"  {name}:")
            for w in all_warnings[name]:
                print(f"    - [WARN] {w}")
            print()

    # Print demoted warnings from untouched skills (CI only, non-blocking)
    if demoted_warnings:
        print(f"WARN: {len(demoted_warnings)} untouched skill(s) have pre-existing violations (not blocking)\n")
        for name in sorted(demoted_warnings):
            print(f"  {name}:")
            for err in demoted_warnings[name]:
                print(f"    - [WARN:untouched] {err}")
            print()

    if not blocking_errors:
        print(f"OK: {total_skills} skills validated, no blocking violations")
        return 0

    # Keys span skills, _shared/<file>, and repo-relative paths (gate hits) —
    # count "targets", not "skills", so the tally stays honest.
    print(f"FAIL: {len(blocking_errors)} target(s) have blocking violations ({total_skills} skills validated)\n")
    for name in sorted(blocking_errors):
        print(f"  {name}:")
        for err in blocking_errors[name]:
            print(f"    - {err}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
