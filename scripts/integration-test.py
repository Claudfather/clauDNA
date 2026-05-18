#!/usr/bin/env python3
"""Integration tests for clauDNA skills — validates beyond frontmatter.

Checks reference file resolution, tool name validity, body structure
conventions, cross-skill uniqueness, and agent/shared references.

Run: python scripts/integration-test.py
Exits non-zero on errors. Warnings are printed but don't block.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
AGENTS_DIR = REPO_ROOT / "agents"
SHARED_DIR = SKILLS_DIR / "_shared"

SKIP_DIRS = {"_shared"}

# Skills where reference resolution is not meaningful — e.g., skills that list
# external filesystem paths to search/delete rather than local supporting files.
SKIP_REFERENCE_CHECK = {"cleanup-legacy-install"}

# Known Claude Code tool names (base names, not including Bash sub-patterns).
# This is an allowlist for the tool name prefix in allowed-tools declarations.
# Warn on unknowns rather than fail — the tool surface evolves.
KNOWN_TOOLS = {
    "Agent",
    "Bash",
    "Edit",
    "EnterPlanMode",
    "EnterWorktree",
    "ExitPlanMode",
    "ExitWorktree",
    "Glob",
    "Grep",
    "NotebookEdit",
    "Read",
    "Skill",
    "Task",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskUpdate",
    "WebFetch",
    "WebSearch",
    "Write",
}


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
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data, body


def get_agent_names() -> set[str]:
    """Return set of agent stem names from agents/ directory."""
    if not AGENTS_DIR.is_dir():
        return set()
    return {p.stem for p in AGENTS_DIR.glob("*.md")}


def get_shared_files() -> set[str]:
    """Return set of filenames in skills/_shared/, recursing into subdirectories.

    Top-level files are returned as bare names (e.g., "output-guide.md"); files
    inside subdirectories are returned as relative paths (e.g.,
    "subagent-prompts/adversarial-chain.md") so references can match either form.
    """
    if not SHARED_DIR.is_dir():
        return set()
    files: set[str] = set()
    for p in SHARED_DIR.rglob("*"):
        if p.is_file():
            files.add(str(p.relative_to(SHARED_DIR)))
    return files


def get_skill_files(skill_dir: Path) -> set[str]:
    """Return set of supporting filenames in a skill directory (excluding SKILL.md)."""
    files = set()
    for p in skill_dir.iterdir():
        if p.is_file() and p.name != "SKILL.md":
            files.add(p.name)
        elif p.is_dir():
            for child in p.rglob("*"):
                if child.is_file():
                    # Store as relative path from skill dir
                    files.add(str(child.relative_to(skill_dir)))
    return files


# References that are template placeholders, external project files, or runtime
# output paths — not actual files that should exist in the skill directory.
_SKIP_REF_PATTERNS = re.compile(
    r"<[^>]+>"  # template placeholders: <name>, <timestamp>, <scratch>
    r"|[{}]"  # curly-brace placeholders: {project}, {topic}
    r"|^~"  # home-relative paths: ~/.claude/...
    r"|^/"  # absolute paths: /tmp/...
    r"|^rm "  # shell commands mistakenly captured
    r"|^00_"  # output naming conventions: 00_OVERVIEW.md, 00_TECH_DEBT.md
    r"|^\."  # dotfile-relative paths: .claude/lessons.md
)

# Common project files that skills reference but don't ship — they exist in
# the user's target project, not in the skill directory.
_EXTERNAL_PROJECT_FILES = {
    "CLAUDE.md",
    "README.md",
    "CHANGELOG.md",
    "INDEX.md",
    "PROJECT_MISSION.md",
    "MEMORY.md",
    ".claude/lessons.md",
}


def _is_local_skill_reference(ref: str) -> bool:
    """Return True if ref looks like it should resolve to a file in the skill dir or _shared/."""
    if _SKIP_REF_PATTERNS.search(ref):
        return False
    # Strip leading path noise
    basename = Path(ref).name
    if basename in _EXTERNAL_PROJECT_FILES:
        return False
    # Paths with multiple segments that look like output dirs (research/, scratch/)
    if "/" in ref and ref.split("/")[0] in (
        "research",
        "scratch",
        "docs",
        "documentation",
        "shared",
    ):
        return False
    # Bare .md without a real filename (e.g., just ".md" from regex overmatch)
    if basename == ".md":
        return False
    return True


def extract_file_references(body: str) -> list[str]:
    """Extract markdown file references from skill body text.

    Returns only references that should resolve to files in the skill directory
    or skills/_shared/. Filters out template placeholders, external project files,
    and runtime output paths.
    """
    refs = []

    # Backtick-quoted .md files: `something.md`
    for m in re.finditer(r"`([^`]*\.md)`", body):
        refs.append(m.group(1))

    # Bare "See/Read <filename>.md" patterns (not in backticks)
    for m in re.finditer(r"(?:See|Read)\s+(\S+\.md)", body):
        ref = m.group(1).strip("()`")
        if ref not in refs:
            refs.append(ref)

    # Filter to local skill references only
    return [r for r in refs if _is_local_skill_reference(r)]


def resolve_reference(ref: str, skill_dir: Path) -> Path | None:
    """Resolve a file reference to an actual path. Returns None if not found."""
    # Clean up markdown link artifacts: [text](path or (path)
    ref = ref.lstrip("[").split("](")[-1].rstrip(")")

    # Absolute-style: skills/_shared/filename.md
    if ref.startswith("skills/_shared/"):
        candidate = REPO_ROOT / ref
        return candidate if candidate.is_file() else None

    # Also handle _shared/ without skills/ prefix
    if ref.startswith("_shared/"):
        candidate = SKILLS_DIR / ref
        return candidate if candidate.is_file() else None

    # Cross-skill reference: skills/<other-skill>/<file>.md
    if ref.startswith("skills/"):
        candidate = REPO_ROOT / ref
        if candidate.is_file():
            return candidate

    # Relative with subdirectory: references/filename.md
    candidate = skill_dir / ref
    if candidate.is_file():
        return candidate

    # Bare filename: look in skill directory
    candidate = skill_dir / Path(ref).name
    if candidate.is_file():
        return candidate

    return None


def extract_tool_names(allowed_tools) -> list[str]:
    """Extract base tool names from allowed-tools value."""
    if isinstance(allowed_tools, str):
        entries = [e.strip() for e in allowed_tools.split(",") if e.strip()]
    elif isinstance(allowed_tools, list):
        entries = [e.strip() for e in allowed_tools if isinstance(e, str)]
    else:
        return []

    names = []
    for entry in entries:
        m = re.match(r"^([A-Za-z]+)", entry)
        if m:
            names.append(m.group(1))
    return names


def check_reference_resolution(
    skill_name: str, skill_dir: Path, body: str
) -> tuple[list[str], list[str]]:
    """Check that file references in the body resolve to actual files.

    Returns (errors, warnings).
    """
    errors = []
    warnings = []
    refs = extract_file_references(body)
    referenced_files = set()

    for ref in refs:
        # Skip glob-style patterns like 00_*.md
        if "*" in ref:
            continue
        path = resolve_reference(ref, skill_dir)
        if path is not None:
            referenced_files.add(path.name)
        else:
            errors.append(f"broken reference: `{ref}` not found")

    # Check for orphaned supporting files (exist but never referenced in SKILL.md)
    actual_files = get_skill_files(skill_dir)
    for fname in sorted(actual_files):
        # Flatten paths for comparison
        basename = Path(fname).name
        if basename not in referenced_files:
            warnings.append(
                f"orphaned file: `{fname}` exists but is not referenced in SKILL.md"
            )

    return errors, warnings


def check_tool_names(skill_name: str, fm: dict) -> tuple[list[str], list[str]]:
    """Validate tool names in allowed-tools against known set."""
    errors = []
    warnings = []
    allowed = fm.get("allowed-tools")
    if not allowed:
        return errors, warnings

    for tool in extract_tool_names(allowed):
        if tool not in KNOWN_TOOLS:
            warnings.append(
                f"unknown tool `{tool}` in allowed-tools (may be valid if newly added)"
            )

    return errors, warnings


def check_body_structure(
    skill_name: str, fm: dict, body: str
) -> tuple[list[str], list[str]]:
    """Check body conventions for user-invocable skills."""
    errors = []
    warnings = []
    user_invocable = fm.get("user-invocable", True)

    if user_invocable:
        # User-invocable skills should have a Procedure heading
        if not re.search(r"^##\s+Procedure", body, re.MULTILINE):
            warnings.append("user-invocable skill missing `## Procedure` heading")

    return errors, warnings


def check_agent_references(
    skill_name: str, body: str, agent_names: set[str]
) -> tuple[list[str], list[str]]:
    """Check that agent type references in skill bodies are valid."""
    errors = []
    warnings = []

    # Match subagent_type declarations: subagent_type: "name" or subagent_type="name"
    for m in re.finditer(r'subagent_type[=:]\s*["\']([^"\']+)["\']', body):
        agent_type = m.group(1)
        # These are built-in agent types, not file-based agents
        if agent_type in ("general-purpose", "Explore", "Plan"):
            continue
        # Check if it matches an agent file
        if agent_type not in agent_names:
            warnings.append(
                f"subagent_type `{agent_type}` does not match any agent in agents/"
            )

    return errors, warnings


def check_shared_references(
    skill_name: str, body: str, shared_files: set[str]
) -> tuple[list[str], list[str]]:
    """Check that _shared/ references resolve to actual files."""
    errors = []
    warnings = []

    for m in re.finditer(r"skills/_shared/(\S+\.md)", body):
        fname = m.group(1).rstrip(")`")
        if fname not in shared_files:
            errors.append(
                f"broken shared reference: `skills/_shared/{fname}` not found"
            )

    return errors, warnings


def check_argument_hint_output(
    skill_name: str, fm: dict, body: str
) -> tuple[list[str], list[str]]:
    """If argument-hint mentions --output, verify the body handles it."""
    errors = []
    warnings = []
    hint = fm.get("argument-hint", "")
    if not isinstance(hint, str):
        return errors, warnings

    if "--output" in hint:
        # Body should mention --output handling or reference the output guide
        if (
            "--output" not in body
            and "output-guide" not in body
            and "output guide" not in body.lower()
        ):
            warnings.append(
                "argument-hint declares `--output` but body doesn't reference output handling or output-guide.md"
            )

    return errors, warnings


def check_description_uniqueness(
    skills_data: dict[str, dict],
) -> list[tuple[str, str, str]]:
    """Find skills with identical descriptions. Returns list of (skill_a, skill_b, desc)."""
    dupes = []
    seen: dict[str, str] = {}  # normalized desc -> skill name
    for name, fm in sorted(skills_data.items()):
        desc = fm.get("description", "")
        if not isinstance(desc, str):
            continue
        normalized = desc.strip().lower()
        if normalized in seen:
            dupes.append((seen[normalized], name, desc[:80]))
        else:
            seen[normalized] = name
    return dupes


def check_requires_consistency(
    skill_name: str, fm: dict, body: str
) -> tuple[list[str], list[str]]:
    """Cross-check requires entries against allowed-tools and body content.

    Warns when a skill uses Bash(tool *) in allowed-tools but doesn't declare
    the tool in requires, since that's a likely missing dependency.
    """
    errors = []
    warnings = []
    requires = fm.get("requires")
    if requires is None:
        # No requires field -- check if the skill references external CLIs
        # in allowed-tools that suggest it should have one
        allowed = fm.get("allowed-tools")
        if allowed:
            bash_tools = set()
            if isinstance(allowed, str):
                entries = [e.strip() for e in allowed.split(",") if e.strip()]
            elif isinstance(allowed, list):
                entries = [e.strip() for e in allowed if isinstance(e, str)]
            else:
                entries = []
            for entry in entries:
                m = re.match(r"^Bash\((\w+)\s", entry)
                if m:
                    tool = m.group(1)
                    # universally-available commands per SKILL_CONTRACT
                    if tool not in ("git", "curl", "jq"):
                        bash_tools.add(tool)
            if bash_tools:
                warnings.append(
                    f"allowed-tools references external CLI(s) {sorted(bash_tools)} "
                    f"but no `requires` field declared"
                )
        return errors, warnings

    if not isinstance(requires, list):
        return errors, warnings  # schema error caught by validate_requires

    # Check for duplicate entries
    seen = set()
    for entry in requires:
        if not isinstance(entry, dict):
            continue
        key = entry.get("cli") or entry.get("env")
        if key and key in seen:
            errors.append(f"duplicate requires entry: {key!r}")
        elif key:
            seen.add(key)

    return errors, warnings


def check_code_blocks(skill_name: str, body: str) -> tuple[list[str], list[str]]:
    """Validate syntax of fenced code blocks in skill body."""
    errors = []
    warnings = []

    # Extract fenced code blocks with language
    for m in re.finditer(r"```(\w+)\n(.*?)```", body, re.DOTALL):
        lang = m.group(1)
        code = m.group(2).strip()
        if not code:
            continue

        if lang == "json":
            try:
                json.loads(code)
            except json.JSONDecodeError as e:
                warnings.append(
                    f"invalid JSON in ```json block: {e.msg} (line {e.lineno})"
                )

        elif lang in ("bash", "sh"):
            # Check for common bash syntax issues: unmatched quotes
            single_quotes = code.count("'") - code.count("\\'")
            double_quotes = code.count('"') - code.count('\\"')
            # Very basic check — odd quote count suggests unmatched
            if single_quotes % 2 != 0:
                warnings.append("possible unmatched single quotes in ```bash block")
            if double_quotes % 2 != 0:
                warnings.append("possible unmatched double quotes in ```bash block")

    return errors, warnings


def main() -> int:
    if not SKILLS_DIR.is_dir():
        print(f"FAIL: skills directory not found at {SKILLS_DIR}", file=sys.stderr)
        return 2

    agent_names = get_agent_names()
    shared_files = get_shared_files()

    skill_dirs = sorted(
        p for p in SKILLS_DIR.iterdir() if p.is_dir() and p.name not in SKIP_DIRS
    )

    all_errors: dict[str, list[str]] = {}
    all_warnings: dict[str, list[str]] = {}
    skills_data: dict[str, dict] = {}

    for skill_dir in skill_dirs:
        name = skill_dir.name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue

        parsed = parse_frontmatter(skill_md)
        if parsed is None:
            all_errors.setdefault(name, []).append(
                "SKILL.md has no valid YAML frontmatter (must start with --- ... ---)"
            )
            continue

        fm, body = parsed
        skills_data[name] = fm
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Reference file resolution
        if name not in SKIP_REFERENCE_CHECK:
            e, w = check_reference_resolution(name, skill_dir, body)
            errors.extend(e)
            warnings.extend(w)

        # 2. Tool name validation
        e, w = check_tool_names(name, fm)
        errors.extend(e)
        warnings.extend(w)

        # 3. Body structure conventions
        e, w = check_body_structure(name, fm, body)
        errors.extend(e)
        warnings.extend(w)

        # 4. Agent references
        e, w = check_agent_references(name, body, agent_names)
        errors.extend(e)
        warnings.extend(w)

        # 5. Shared file references
        e, w = check_shared_references(name, body, shared_files)
        errors.extend(e)
        warnings.extend(w)

        # 6. Argument-hint / --output consistency
        e, w = check_argument_hint_output(name, fm, body)
        errors.extend(e)
        warnings.extend(w)

        # 7. Code block syntax
        e, w = check_code_blocks(name, body)
        errors.extend(e)
        warnings.extend(w)

        # 8. Requires consistency
        e, w = check_requires_consistency(name, fm, body)
        errors.extend(e)
        warnings.extend(w)

        if errors:
            all_errors[name] = errors
        if warnings:
            all_warnings[name] = warnings

    # Cross-skill: duplicate descriptions
    dupes = check_description_uniqueness(skills_data)
    for skill_a, skill_b, desc in dupes:
        all_errors.setdefault(skill_b, []).append(
            f'duplicate description with `{skill_a}`: "{desc}..."'
        )

    total = len(skill_dirs)
    error_count = sum(len(v) for v in all_errors.values())
    warning_count = sum(len(v) for v in all_warnings.values())

    # Print warnings (non-blocking)
    if all_warnings:
        print(f"WARN: {warning_count} warnings across {len(all_warnings)} skills\n")
        for name in sorted(all_warnings):
            print(f"  {name}:")
            for w in all_warnings[name]:
                print(f"    ⚠ {w}")
            print()

    # Print errors (blocking)
    if all_errors:
        print(f"FAIL: {error_count} errors across {len(all_errors)} skills\n")
        for name in sorted(all_errors):
            print(f"  {name}:")
            for e in all_errors[name]:
                print(f"    ✗ {e}")
            print()
        return 1

    print(f"OK: {total} skills passed integration checks ({warning_count} warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
