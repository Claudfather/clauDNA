"""Shared skill validation logic used by validate-skills.py and validate-promotion-package.py.

Extracted so both the CI skill validator and the promotion pre-flight
can share the same rules without duplication.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REQUIRED_FIELDS = {"name", "description"}
KNOWN_FIELDS = REQUIRED_FIELDS | {
    "allowed-tools",
    "argument-hint",
    "requires",
    "user-invocable",
}

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
DESC_MIN = 20
DESC_MAX = 500
BODY_MIN = 200
STALE_PATH_RE = re.compile(r"~/\.claude/(skills|commands|agents)/")
STALE_PATH_SKIP_SKILLS = {"cleanup-legacy-install"}

# Skills must delegate GitHub output to /claudna:publish, never call `gh` directly.
# These three are the gh-endpoint skills where direct `gh` use is the whole point.
RAW_GH_ALLOWED_SKILLS = {"publish", "file-github-issue", "commit-push-pr"}
# Scope: issue/PR *creation* and *comment* verbs (output written to GitHub). We
# intentionally do NOT gate edit/view/list verbs (e.g. `gh issue edit --add-label`,
# `gh issue view`) — those are issue *consumption* / label management, used legitimately
# by consumer skills like implement-plan.
_RAW_GH_PATTERNS = [
    re.compile(r"\bgh\s+issue\s+create\b"),
    re.compile(r"\bgh\s+pr\s+create\b"),
    re.compile(r"\bgh\s+issue\s+comment\b"),
    re.compile(r"\bgh\s+pr\s+comment\b"),
]


def parse_frontmatter(path: Path) -> tuple[dict, str] | None:
    """Return (frontmatter_dict, body) or None if no frontmatter."""
    text = path.read_text()
    if not text.startswith("---"):
        return None
    lines = text.splitlines(keepends=True)
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return None
    frontmatter_text = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        data = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"frontmatter YAML parse error: {e}")
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a YAML mapping")
    return data, body


def validate_allowed_tools(value) -> list[str]:
    """Validate allowed-tools (string with comma-separated entries, or YAML list).

    Both forms are valid Claude Code frontmatter. Only the deprecated
    colon syntax (Bash(cmd:*) instead of Bash(cmd *)) is hard-failed,
    since CHANGELOG records that as a confirmed-broken pattern.
    Unknown tool names are not failed -- the tool surface evolves.
    """
    errors: list[str] = []
    if isinstance(value, str):
        entries = [e.strip() for e in value.split(",") if e.strip()]
    elif isinstance(value, list):
        entries = []
        for i, entry in enumerate(value):
            if not isinstance(entry, str):
                errors.append(f"allowed-tools[{i}] must be a string, got {type(entry).__name__}")
                continue
            entries.append(entry.strip())
    else:
        errors.append(f"allowed-tools must be a string or list, got {type(value).__name__}")
        return errors

    for entry in entries:
        m = re.match(r"^([A-Za-z]+)(\(.*\))?$", entry)
        if not m:
            errors.append(f"allowed-tools: unparseable entry {entry!r}")
            continue
        tool = m.group(1)
        pattern = m.group(2)
        if pattern and tool == "Bash":
            inner = pattern[1:-1]
            if ":" in inner and "*" in inner:
                errors.append(
                    f"allowed-tools: deprecated colon syntax in {entry!r} -- use 'Bash(cmd *)' not 'Bash(cmd:*)'"
                )
    return errors


REQUIRES_ENTRY_TYPES = {"cli", "env"}

# Regex for version constraints: >=1.0, >=3.10, >=2.0.0, etc.
VERSION_CONSTRAINT_RE = re.compile(r"^>=\d+(\.\d+){0,2}$")


def validate_requires(value) -> list[str]:
    """Validate the requires field (list of dependency objects).

    Each entry must be a dict with exactly one of 'cli' or 'env' (string),
    and an optional 'reason' (string). cli entries may include a version
    constraint suffix (e.g. 'gh>=2.0').
    """
    errors: list[str] = []
    if not isinstance(value, list):
        errors.append(f"requires must be a list, got {type(value).__name__}")
        return errors

    for i, entry in enumerate(value):
        prefix = f"requires[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be a mapping, got {type(entry).__name__}")
            continue

        # Exactly one of cli or env
        dep_keys = [k for k in entry if k in REQUIRES_ENTRY_TYPES]
        extra_keys = [k for k in entry if k not in REQUIRES_ENTRY_TYPES and k != "reason"]
        if len(dep_keys) == 0:
            errors.append(f"{prefix} must have 'cli' or 'env' key")
        elif len(dep_keys) > 1:
            errors.append(f"{prefix} must have exactly one of 'cli' or 'env', got both")

        for k in extra_keys:
            errors.append(f"{prefix} has unknown key {k!r} (allowed: cli, env, reason)")

        # Validate value types
        for k in dep_keys:
            v = entry[k]
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{prefix}.{k} must be a non-empty string")
            elif k == "cli":
                # Parse optional version constraint: name>=version
                m = re.match(r"^([A-Za-z0-9_][A-Za-z0-9_.+-]*)(.*)$", v)
                if not m:
                    errors.append(f"{prefix}.cli: invalid tool name {v!r}")
                elif m.group(2):
                    constraint = m.group(2)
                    if not VERSION_CONSTRAINT_RE.match(constraint):
                        errors.append(
                            f"{prefix}.cli: invalid version constraint {constraint!r} (expected >=X.Y or >=X.Y.Z)"
                        )

        reason = entry.get("reason")
        if reason is not None and not isinstance(reason, str):
            errors.append(f"{prefix}.reason must be a string, got {type(reason).__name__}")

    return errors


def check_dependencies(requires: list[dict]) -> list[dict]:
    """Check whether required dependencies are available on PATH.

    Returns a list of dicts with keys: type, name, available, reason.
    Entries with available=False are missing dependencies.

    This is a runtime check (not CI validation) -- call it when deciding
    whether a skill can run on the current system.
    """
    import shutil

    results = []
    for entry in requires:
        if "cli" in entry:
            raw = entry["cli"]
            # Strip version constraint for PATH lookup
            tool = re.match(r"^([A-Za-z0-9_][A-Za-z0-9_.+-]*)", raw)
            name = tool.group(1) if tool else raw
            results.append(
                {
                    "type": "cli",
                    "name": name,
                    "spec": raw,
                    "available": shutil.which(name) is not None,
                    "reason": entry.get("reason", ""),
                }
            )
        elif "env" in entry:
            import os

            var = entry["env"]
            results.append(
                {
                    "type": "env",
                    "name": var,
                    "spec": var,
                    "available": bool(os.environ.get(var)),
                    "reason": entry.get("reason", ""),
                }
            )
    return results


def _parse_allowed_tools_entries(value) -> list[str]:
    """Extract individual tool entries from an allowed-tools value."""
    if isinstance(value, str):
        return [e.strip() for e in value.split(",") if e.strip()]
    elif isinstance(value, list):
        return [e.strip() for e in value if isinstance(e, str)]
    return []


def check_output_github_reference(fm: dict, body: str) -> list[str]:
    """If argument-hint contains '--output github', body must reference output-guide.md."""
    errors: list[str] = []
    arg_hint = fm.get("argument-hint", "")
    if not isinstance(arg_hint, str):
        return errors
    if "--output github" in arg_hint:
        if "output-guide" not in body:
            errors.append(
                "argument-hint claims '--output github' but body does not reference "
                "output-guide.md (expected: skills/_shared/output-guide.md)"
            )
    return errors


def check_auto_no_ask_user(fm: dict, body: str) -> list[str]:
    """If argument-hint contains '--auto', body must not contain AskUserQuestion."""
    errors: list[str] = []
    arg_hint = fm.get("argument-hint", "")
    if not isinstance(arg_hint, str):
        return errors
    if "--auto" in arg_hint:
        if "AskUserQuestion" in body:
            errors.append(
                "argument-hint claims '--auto' (non-interactive) but body contains "
                "'AskUserQuestion' -- contradicts non-interactive contract"
            )
    return errors


_STRUCTURED_RESULT_PATTERNS = [
    re.compile(r"structured[\s\-]result", re.IGNORECASE),
    re.compile(r"§10\.C"),
    re.compile(r"orchestration-guide\.md.{0,30}10\.C"),
]


def check_structured_result_emission(fm: dict, body: str) -> list[str]:
    """If argument-hint contains '--auto', body must reference structured-result emission.

    Skills declaring --auto support must emit the §10.C structured-result JSON
    block as their final output. This check verifies the body documents that
    contract by mentioning 'structured result' / 'structured-result' / '§10.C' /
    a reference to orchestration-guide.md §10.C.
    """
    errors: list[str] = []
    arg_hint = fm.get("argument-hint", "")
    if not isinstance(arg_hint, str):
        return errors
    if "--auto" not in arg_hint:
        return errors
    if not any(p.search(body) for p in _STRUCTURED_RESULT_PATTERNS):
        errors.append(
            "argument-hint claims '--auto' but body does not reference structured-result "
            "emission (expected mention of 'structured result' / '§10.C' / "
            "orchestration-guide.md §10.C)"
        )
    return errors


# A whitespace-delimited token starting `--` followed by a letter is a CLI flag
# (--auto, --output). Both prose forms of the double hyphen are fine: the spaced
# em-dash (` -- `) and the glued compound (`plan--then-execute`) — hence the
# start-of-string/after-whitespace anchor.
_DESC_FLAG_RE = re.compile(r"(?:^|(?<=\s))--[A-Za-z][A-Za-z-]*")


def check_description_grammar(fm: dict, body: str) -> list[str]:
    """Descriptions state triggering conditions; CLI mechanics belong in argument-hint.

    The description is what the model reads when deciding whether to load a
    skill. Flag inventories ('Supports --output github ...') add selection
    noise without trigger value — the flags are already declared in
    argument-hint. Errors on any --flag token in the description.
    """
    errors: list[str] = []
    desc = fm.get("description")
    if not isinstance(desc, str):
        return errors
    flags = sorted(set(_DESC_FLAG_RE.findall(desc)))
    if flags:
        errors.append(
            f"description contains flag token(s) {', '.join(flags)} -- flag surfaces "
            "belong in argument-hint; the description should state triggering "
            "conditions only (see SKILL_CONTRACT.md description grammar)"
        )
    return errors


def check_description_trigger_convention(fm: dict, body: str) -> list[str]:
    """Warn when a description doesn't lead with a trigger clause.

    Descriptions should open with the situation that calls for the skill
    ('Use when ...', 'Use at ...', 'Use before ...'), not a label or a
    summary of what the skill does. Advisory, not CI-blocking.
    """
    warnings: list[str] = []
    desc = fm.get("description")
    if not isinstance(desc, str) or not desc:
        return warnings
    if not desc.startswith("Use "):
        preview = desc if len(desc) <= 60 else desc[:57] + "..."
        warnings.append(
            f'description does not lead with a trigger clause ("Use when ..."): {preview!r}'
        )
    return warnings


# Matches claudna:<skill-name> references (with or without leading slash).
# `claudna:<placeholder>` forms don't match: the char after the colon must be
# alphanumeric, so authoring-doc placeholders like /claudna:<skill-name> pass.
_SKILL_REF_RE = re.compile(r"\bclaudna:([A-Za-z0-9][A-Za-z0-9-]*)")


def collect_skill_reference_errors(text: str, valid_names: set[str]) -> list[tuple[str, str]]:
    """Every claudna:<name> mention must reference an existing skill.

    Cross-references are how skills route to each other (negative triggers,
    pipeline hand-offs); a dangling reference silently breaks that routing.
    Duplicate mentions of the same unknown target are reported once.

    Returns (target, message) pairs. The target name matters: the caller must
    register these as cross-skill errors with the TARGET as a participant, so
    that a PR deleting skills/<target>/ (which marks only <target> as touched
    in CI) still blocks on the dangling references left in untouched skills.
    Attributing the error to the referrer alone demotes it to a warning in
    exactly that scenario.

    Args:
        text: Markdown content to scan (a skill body or support file).
        valid_names: The set of existing skill directory names.
    """
    unknown = {m.group(1) for m in _SKILL_REF_RE.finditer(text)} - valid_names
    return [
        (
            target,
            f"reference to unknown skill 'claudna:{target}' -- no skills/{target}/ directory",
        )
        for target in sorted(unknown)
    ]


def check_skill_references(text: str, valid_names: set[str]) -> list[str]:
    """String-only projection of collect_skill_reference_errors."""
    return [msg for _target, msg in collect_skill_reference_errors(text, valid_names)]


def load_removed_skills(path: Path) -> list[str]:
    """Read scripts/removed-skills.txt: one removed skill name per line.

    `#` starts a comment (full-line or inline); blank lines are skipped;
    missing file → []. A remaining entry that isn't a valid skill name
    raises — a malformed entry would otherwise silently disable the gate
    for that name. Deletion PRs append the names they remove; the gate
    below keeps every later change from resurrecting references to them.
    """
    if not path.is_file():
        return []
    names: list[str] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not NAME_RE.match(line):
            raise ValueError(f"{path.name} line {lineno}: {line!r} is not a valid skill name")
        names.append(line)
    return names


def check_removed_name_mentions(text: str, removed_names: list[str]) -> list[tuple[str, str]]:
    """Flag any mention of a removed skill name, in any reference form.

    A single word-boundary match per name catches every form at once —
    `claudna:<name>`, `/<name>`, `skills/<name>/`, `Skill(<name>)`, and bare
    prose mentions — because the name itself is the invariant token.
    A mention positioned after a `Replaces` token on its line is exempt:
    SKILL_CONTRACT §2.1 rule 6 *requires* successor breadcrumbs to name the
    skills they replace. The exemption is positional — a real reference
    earlier on a line that merely also contains the word "Replaces" still
    flags.

    Returns (name, message) pairs. Callers must treat these as
    always-blocking (never demoted by CI touched-set scoping): once a
    deletion release lands, main is clean of the removed names, so any hit
    was introduced by the change under test.
    """
    if not removed_names:
        return []
    # One alternation for all names: a whole-text pre-pass skips clean files
    # (the common case), and per-line finditer replaces a per-name inner loop.
    # Measured ~5x over per-name patterns on this repo's scan set.
    alternation = "|".join(re.escape(name) for name in sorted(removed_names))
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_-])({alternation})(?![A-Za-z0-9_-])", re.IGNORECASE
    )
    if not pattern.search(text):
        return []
    replaces_re = re.compile(r"\bReplaces\b")
    errors: list[tuple[str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        m_replaces = replaces_re.search(line)
        breadcrumb_start = m_replaces.start() if m_replaces else None
        seen_on_line: set[str] = set()
        for m in pattern.finditer(line):
            if breadcrumb_start is not None and m.start() > breadcrumb_start:
                continue  # breadcrumb-sanctioned mention
            name = m.group(1).lower()
            if name in seen_on_line:
                continue
            seen_on_line.add(name)
            errors.append(
                (
                    name,
                    f"line {lineno}: mention of removed skill '{name}' -- update to its "
                    "successor engine or drop the reference (removed-names gate, "
                    "scripts/removed-skills.txt)",
                )
            )
    return errors


def check_allowed_tools_usage(fm: dict, body: str) -> list[str]:
    """Warn if allowed-tools declares a tool never mentioned in body.

    Returns a list of warning strings (advisory, not CI-blocking).
    """
    warnings: list[str] = []
    if "allowed-tools" not in fm:
        return warnings

    entries = _parse_allowed_tools_entries(fm["allowed-tools"])
    for entry in entries:
        # Extract the tool name (e.g. "Bash" from "Bash(git *)", "Read" from "Read")
        m = re.match(r"^([A-Za-z]+)(\(.*\))?$", entry)
        if not m:
            continue
        tool_name = m.group(1)
        pattern = m.group(2)  # e.g. "(git *)" or None

        # For Bash(cmd *) patterns, check for the command name in body
        if tool_name == "Bash" and pattern:
            inner = pattern[1:-1].strip()  # strip parens
            # Extract the command: first word before space or *
            cmd = inner.split()[0].rstrip("*") if inner else ""
            if cmd:
                # Check if command is referenced anywhere in body
                if cmd not in body:
                    warnings.append(f"allowed-tools declares 'Bash({inner})' but '{cmd}' is never mentioned in body")
        else:
            # Plain tool name (Read, Glob, Edit, etc.)
            if tool_name not in body:
                warnings.append(f"allowed-tools declares '{tool_name}' but it is never mentioned in body")

    return warnings


def check_no_raw_gh_commands(fm: dict, body: str) -> list[str]:
    """Skills must delegate GitHub output to /claudna:publish, not call `gh` directly.

    Flags executable 'gh issue create', 'gh pr create', or 'gh issue comment' in a
    skill body. Lines that reference /claudna:publish are treated as delegation prose
    and skipped (e.g. "don't run gh issue create -- use /claudna:publish"). Issue
    consumption (gh issue view/list/edit, gh label create) is not flagged.

    The allowlist of gh-endpoint skills (RAW_GH_ALLOWED_SKILLS) is applied by the
    caller, not here. Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        # Coarse heuristic: a line that names the publisher is treated as delegation
        # prose (e.g. "don't run gh issue create -- use /claudna:publish"). This means a
        # line that genuinely runs `gh` AND mentions publish would slip through; accepted
        # as a low-risk tradeoff for a prose check.
        if "claudna:publish" in line:
            continue
        for pat in _RAW_GH_PATTERNS:
            m = pat.search(line)
            if m:
                errors.append(
                    f"raw '{m.group(0)}' in body -- skills must delegate GitHub output to "
                    "/claudna:publish (--to github-issue), not invoke `gh` directly. "
                    "See skills/_shared/output-guide.md."
                )
                break
    return errors


def validate_skill_md(skill_md: Path, dir_name: str | None = None) -> list[str]:
    """Validate a SKILL.md file against the skill contract.

    Args:
        skill_md: Path to the SKILL.md file.
        dir_name: Expected directory name the skill should match.
                  If None, skips the name-vs-directory check.

    Returns:
        List of error strings (empty = valid).
    """
    errors: list[str] = []

    if not skill_md.is_file():
        return ["missing SKILL.md"]

    try:
        parsed = parse_frontmatter(skill_md)
    except ValueError as e:
        return [str(e)]
    if parsed is None:
        return ["SKILL.md has no YAML frontmatter (must start with --- ... ---)"]

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
            if dir_name is not None and fm_name != dir_name:
                errors.append(f"name {fm_name!r} does not match directory name {dir_name!r}")

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

    # allowed-tools rules
    if "allowed-tools" in fm:
        errors.extend(validate_allowed_tools(fm["allowed-tools"]))

    # requires rules
    if "requires" in fm:
        errors.extend(validate_requires(fm["requires"]))

    # argument-hint rules
    arg_hint = fm.get("argument-hint")
    if arg_hint is not None and not isinstance(arg_hint, str):
        errors.append(f"argument-hint must be a string, got {type(arg_hint).__name__}")

    # user-invocable rules
    user_invocable = fm.get("user-invocable")
    if user_invocable is not None and not isinstance(user_invocable, bool):
        errors.append(f"user-invocable must be a boolean, got {type(user_invocable).__name__}")

    # body length
    body_chars = len(body.strip())
    if body_chars < BODY_MIN:
        errors.append(f"body too short ({body_chars} chars, min {BODY_MIN}) -- looks like a stub")

    # Stale hardcoded path check
    name = fm_name if isinstance(fm_name, str) else dir_name
    if name not in STALE_PATH_SKIP_SKILLS:
        for line in body.splitlines():
            if STALE_PATH_RE.search(line):
                errors.append(f"stale hardcoded path: {line.strip()}")

    # Behavioral checks (hard errors)
    errors.extend(check_description_grammar(fm, body))
    errors.extend(check_output_github_reference(fm, body))
    errors.extend(check_auto_no_ask_user(fm, body))
    errors.extend(check_structured_result_emission(fm, body))
    if name not in RAW_GH_ALLOWED_SKILLS:
        errors.extend(check_no_raw_gh_commands(fm, body))

    return errors


def warn_skill_md(skill_md: Path) -> list[str]:
    """Return advisory warnings for a SKILL.md (not CI-blocking).

    Args:
        skill_md: Path to the SKILL.md file.

    Returns:
        List of warning strings (empty = clean).
    """
    if not skill_md.is_file():
        return []
    try:
        parsed = parse_frontmatter(skill_md)
    except ValueError:
        return []
    if parsed is None:
        return []

    fm, body = parsed
    warnings = check_allowed_tools_usage(fm, body)
    warnings.extend(check_description_trigger_convention(fm, body))
    return warnings


def get_touched_skills() -> set[str] | None:
    """Return skill dir names touched in this PR, or None if not in CI.

    In CI (GITHUB_ACTIONS set), diffs against origin/main to find which
    skill directories were modified. Returns None when running locally
    so callers can treat all errors as blocking.

    Escape hatches for full validation in CI:
    - Set env var FULL_VALIDATE=1
    - Add a [full-validate] label to the PR (detected via PR_LABELS env var)

    Note: setting GITHUB_ACTIONS=true locally activates CI scoping behavior.
    This is by design for local testing, but be aware it changes which errors
    block vs. warn.
    """
    import os
    import subprocess
    import sys

    if "GITHUB_ACTIONS" not in os.environ:
        return None

    # Escape hatch: force full blocking validation
    if os.environ.get("FULL_VALIDATE") == "1":
        print("FULL_VALIDATE=1: running full blocking validation", file=sys.stderr)
        return None
    pr_labels = os.environ.get("PR_LABELS", "")
    if "full-validate" in pr_labels:
        print("[full-validate] label detected: running full blocking validation", file=sys.stderr)
        return None

    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"WARNING: git diff failed (exit {result.returncode}), falling back to full "
            f"blocking validation. This typically means a shallow clone or missing "
            f"origin/main ref. stderr: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    touched: set[str] = set()
    for path in result.stdout.strip().splitlines():
        # Match skills/<name>/... but not skills/_shared/...
        if path.startswith("skills/") and "/" in path[len("skills/") :]:
            skill_name = path.split("/")[1]
            if skill_name != "_shared":
                touched.add(skill_name)
    # _shared/ files are referenced by many skills (orchestration guides, output
    # contracts, subagent prompts). A change there can break any skill's behavioral
    # checks (e.g. check_output_github_reference, check_structured_result_emission).
    # Full validation is the safe default — don't "optimize" this to only validate
    # skills that textually reference the changed _shared/ file, because the
    # dependency graph is implicit and hard to trace statically.
    for path in result.stdout.strip().splitlines():
        if path.startswith("skills/_shared/"):
            return None  # validate everything as blocking
    return touched
