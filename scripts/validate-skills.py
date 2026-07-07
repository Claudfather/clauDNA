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

from skill_checks import (
    STALE_PATH_RE,
    check_removed_name_mentions,
    collect_skill_reference_errors,
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

# Removed-names gate scope: repo-wide over these text extensions, minus
# historical records and generated/managed paths. CHANGELOG and the archive
# legitimately narrate removed skills; the gate protects living surfaces.
GATE_EXTENSIONS = {".md", ".sh", ".py", ".json", ".yaml", ".yml", ".toml", ".txt"}
GATE_PRUNE_DIRS = {".git", "__pycache__", "worktrees", "node_modules"}
GATE_EXCLUDE_FILES = {"CHANGELOG.md", "scripts/removed-skills.txt"}  # exact paths
GATE_EXCLUDE_PREFIXES = ("documentation/archive/",)


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
    removed_name_hits = scan_removed_names(load_removed_skills(REMOVED_SKILLS_FILE))

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
