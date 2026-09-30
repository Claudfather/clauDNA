"""Shared skill validation logic used by validate-skills.py and validate-promotion-package.py.

Extracted so both the CI skill validator and the promotion pre-flight
can share the same rules without duplication.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

REQUIRED_FIELDS = {"name", "description"}
KNOWN_FIELDS = REQUIRED_FIELDS | {
    "allowed-tools",
    "argument-hint",
    "requires",
    "user-invocable",
    "hosts",
    "requires-context",
    "disable-model-invocation",
}

# clauDNA #340: hosts a skill is known to function on, and a special
# execution context it needs beyond "any project directory". Both are
# optional and additive -- their absence means "no restriction", which is
# why most skills never need either. See cursor_should_exclude() below for
# the one place today that reads them.
#
# #343: the field is `requires-context`, not `context` -- Claude Code's own
# skills reference already defines `context` (set to `fork` to run in a
# forked subagent context, paired with `agent:`). A same-named field here
# collides with that: this repo's validator rejected Claude Code's own
# `fork` value as an unknown context, and the exclusion predicate below
# would have treated any skill that later adopts `context: fork` for its
# native meaning as needing a repo clone. `requires-context` is a key
# Claude Code does not define.
KNOWN_HOSTS = {"claude-code", "cursor"}
KNOWN_CONTEXTS = {"repo-clone"}

# clauDNA #344: the one definition of "not a skill directory" -- was three
# independent copies (here, validate-skills.py, integration-test.py,
# check_cursor_scope.py), which is exactly how a gate and a validator end up
# disagreeing about what counts as a skill without either one changing.
SKIP_DIRS = {"_shared"}

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
DESC_MIN = 20
DESC_MAX = 500
BODY_MIN = 200
STALE_PATH_RE = re.compile(r"~/\.claude/(skills|commands|agents)/")
STALE_PATH_SKIP_SKILLS = {"cleanup-legacy-install"}

# Repo-wide text surfaces the gates walk, minus VCS/build directories. Owned
# here because two gates reason over the same living-surface file set:
# validate-skills.py's removed-names scan and check_vault_address.py's
# vault-address conformance gate.
GATE_EXTENSIONS = {".md", ".sh", ".py", ".json", ".yaml", ".yml", ".toml", ".txt"}
# Names with no structural marker to key on: git, CPython and npm each mandate
# their own directory name, so the name IS the invariant here. A virtualenv is
# the opposite case and is handled by is_virtualenv() below -- .venv and venv
# are listed only as a name-level backstop for a venv whose marker is missing
# or unreadable. "env" is deliberately NOT listed: it is a plausible name for a
# tracked config directory, and a literal entry would silently drop real files
# from a gate whose whole job is to find them. A venv named env is caught by
# the marker instead, which keys on contents rather than on the name.
GATE_PRUNE_DIRS = {".git", "__pycache__", "worktrees", "node_modules", ".venv", "venv"}


def is_virtualenv(path: Path) -> bool:
    """True when *path* is the root of a Python virtual environment.

    PEP 405 defines ``pyvenv.cfg`` at the environment root as the marker, and
    ``python -m venv`` writes it (verified). Keying on the marker rather than on
    the directory name is what stops this recurring the moment a contributor
    picks ``.venv313``, ``env`` or ``build-venv``: the set of names a person
    might choose is unbounded, the marker is not.

    Why it matters that the gates skip one: an environment holds thousands of
    gate-matching files whose lines are long, and the gates run a per-line regex
    over every file they walk. One in the repo root measured a 33x slowdown --
    slow enough to read as a hang, which is how it cost hours (#330).

    Layouts that do not write the marker (conda prefix environments, older
    virtualenv) were not measured; the name-level entries in GATE_PRUNE_DIRS are
    the backstop for those.
    """
    return (path / "pyvenv.cfg").is_file()


def walk_gate_files(root: Path) -> list[Path]:
    """Every gate-relevant file under *root*, vendored directories pruned.

    The single walk behind both gates. os.walk rather than rglob because the
    prune has to stop the DESCENT: a filter applied to an already-enumerated
    list still pays to enumerate the environment, and a bare venv is ~1,500
    files before a single package is installed.

    Callers layer their own path exclusions on top -- the two gates deliberately
    differ there (see each one's GATE_EXCLUDE_* constants).
    """
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in GATE_PRUNE_DIRS and not is_virtualenv(here / d)]
        for fname in filenames:
            if Path(fname).suffix in GATE_EXTENSIONS:
                out.append(here / fname)
    return sorted(out)


# Skills must delegate GitHub output to /claudna:publish, never call `gh` directly.
# These three are the gh-endpoint skills where direct `gh` use is the whole point.
RAW_GH_ALLOWED_SKILLS = {"publish", "file-github-issue", "ship"}
# Scope: issue/PR *creation* and *comment* verbs (output written to GitHub). We
# intentionally do NOT gate edit/view/list verbs (e.g. `gh issue edit --add-label`,
# `gh issue view`) — those are issue *consumption* / label management, used legitimately
# by consumer skills like build.
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


def validate_hosts(value) -> list[str]:
    """Validate the `hosts` field (list of known host identifiers, #340).

    Absence means "no host restriction" (ships everywhere this skill's
    other fields don't otherwise exclude it from). An empty list is a
    likely mistake -- a skill declaring it runs NOWHERE -- so it is
    rejected rather than silently treated as "no restriction"; the way to
    say "no restriction" is to omit the field entirely.
    """
    errors: list[str] = []
    if not isinstance(value, list):
        errors.append(f"hosts must be a list, got {type(value).__name__}")
        return errors
    if not value:
        errors.append("hosts must not be empty (omit the field entirely for 'all hosts')")
        return errors
    for i, entry in enumerate(value):
        if not isinstance(entry, str):
            errors.append(f"hosts[{i}] must be a string, got {type(entry).__name__}")
        elif entry not in KNOWN_HOSTS:
            errors.append(f"hosts[{i}] {entry!r} is not a known host (known: {sorted(KNOWN_HOSTS)})")
    return errors


def validate_requires_context(value) -> list[str]:
    """Validate the `requires-context` field (a single known execution-context id, #340)."""
    errors: list[str] = []
    if not isinstance(value, str):
        errors.append(f"requires-context must be a string, got {type(value).__name__}")
    elif value not in KNOWN_CONTEXTS:
        errors.append(f"requires-context {value!r} is not a known context (known: {sorted(KNOWN_CONTEXTS)})")
    return errors


def cursor_should_exclude(fm: dict) -> bool:
    """Whether a skill's frontmatter marks it out of scope for the Cursor
    distribution (clauDNA #340).

    Two independent reasons exclude a skill; either is sufficient:
      - `hosts` is declared and does not include "cursor" (the skill uses
        host-specific features -- e.g. Claude Code plugin/hook internals --
        that Cursor does not have).
      - `requires-context` is declared at all (the skill needs to run from
        inside a clone of this repo; Cursor's marketplace install gives no
        such guarantee).

    Scope: this predicate is Cursor-specific, not a general host resolver.
    Per #340's acceptance criteria, Claude Code's manifest is UNCHANGED by
    these fields -- it ships every skill regardless, as it always has; that
    is a deliberate, conservative scoping choice for this issue, not a claim
    that Claude Code is somehow exempt from what the fields describe.
    """
    hosts = fm.get("hosts")
    if hosts is not None and "cursor" not in hosts:
        return True
    if fm.get("requires-context") is not None:
        return True
    return False


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
                "output-guide.md (expected a reference to ../_shared/output-guide.md)"
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
        warnings.append(f'description does not lead with a trigger clause ("Use when ..."): {preview!r}')
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


# clauDNA #336: a path in skill text resolves against the directory of the file
# it is written in -- plain markdown semantics, and what every reference between
# a skill's own files already does -- so a host that knows where it loaded a
# file can follow the path without this repo's layout or working directory.
# `_shared/` material is therefore spelled one of two ways (SKILL_CONTRACT §1):
# one "../" per directory between the file and skills/, then "_shared/<path>";
# or, in text that leaves its file before anyone reads it (a prompt forwarded to
# another agent, a shell command), the resolver form below.
CLAUDNA_ROOT = "<claudna-root>"
_RESOLVER_PREFIX = CLAUDNA_ROOT + "/skills/"
# The candidate list for <claudna-root> is defined between these markers, in
# SKILL_CONTRACT.md §1.1 and in its run-time copy, skills/_shared/claudna-root.md.
# Text inside them names ${CLAUDE_PLUGIN_ROOT} and the plugin cache on purpose.
CLAUDNA_ROOT_BEGIN = "<!-- claudna-root:begin -->"
CLAUDNA_ROOT_END = "<!-- claudna-root:end -->"
_SHARED_SEGMENT_RE = re.compile(r"(?<![\w-])_shared/")
# Whatever path text runs up to the segment is part of how the path is written
# (`skills/`, `../`, `${CLAUDE_PLUGIN_ROOT}/skills/`, `~/.claude/skills/`).
_SHARED_PREFIX_RE = re.compile(r"[\w.~${}/-]*$")
_SHARED_TAIL_RE = re.compile(r"[\w./-]*")
# A prefix of path segments only: the one kind the file-relative rule governs.
_PLAIN_PREFIX_RE = re.compile(r"(?:[\w.-]+/)*")


def _shared_path_spans(line: str) -> list[tuple[int, int, str, str]]:
    """(start, end, tail, kind) of every `_shared/` path in line, prefix included.

    kind is "plain" (path segments only), "resolver" (`<claudna-root>/skills/`),
    "url" (inside a `scheme://` URL, which is not a path and is left alone), or
    "other" (a `${...}`, `~` or absolute prefix).
    """
    spans: list[tuple[int, int, str, str]] = []
    for m in _SHARED_SEGMENT_RE.finditer(line):
        start = _SHARED_PREFIX_RE.search(line, 0, m.start()).start()
        if spans and start < spans[-1][1]:
            continue  # a second segment inside a path already taken
        tail = _SHARED_TAIL_RE.match(line, m.end()).group(0).rstrip(".")
        prefix = line[start : m.start()]
        if start > 0 and line[start - 1] == ":" and prefix.startswith("//"):
            kind = "url"
        elif prefix == "/skills/" and line[:start].endswith(CLAUDNA_ROOT):
            start -= len(CLAUDNA_ROOT)
            kind = "resolver"
        elif _PLAIN_PREFIX_RE.fullmatch(prefix):
            kind = "plain"
        else:
            kind = "other"
        spans.append((start, m.end() + len(tail), tail, kind))
    return spans


def _shared_target_exists(skills_dir: Path, tail: str) -> bool:
    """Whether `_shared/<tail>` names a file or directory inside skills/_shared/."""
    shared_root = (skills_dir / "_shared").resolve()
    target = (shared_root / tail).resolve()
    return target.exists() and (target == shared_root or shared_root in target.parents)


def _shared_spelling(md_file: Path, skills_dir: Path, tail: str, kind: str) -> str | None:
    """The accepted spelling of `_shared/<tail>` for a path of this kind in
    md_file, or None when <tail> names nothing under skills/_shared/.

    A plain prefix is a relative path, so its spelling is the file-relative
    one. A resolver path keeps its form. Any other prefix was meant to anchor
    the path somewhere absolute (a command, a forwarded prompt), so its
    spelling is the resolver form: rewriting it to a relative path would hand
    a shell or another agent a path relative to its own working directory.
    """
    if not _shared_target_exists(skills_dir, tail):
        return None
    if kind == "plain":
        depth = len(md_file.relative_to(skills_dir).parts) - 1
        return "../" * depth + "_shared/" + tail
    return _RESOLVER_PREFIX + "_shared/" + tail


def shared_path_findings(text: str, md_file: Path, skills_dir: Path) -> list[tuple[int, str, str | None]]:
    """Every `_shared/` path in md_file's text that is not spelled as §1 requires.

    Returns (line number, path as written, accepted spelling) triples. The
    spelling is None when the path names nothing under skills/_shared/: there
    is then nothing to rewrite it to, and a human has to decide.
    """
    findings: list[tuple[int, str, str | None]] = []
    for lineno, line in enumerate(text.split("\n"), 1):
        for start, end, tail, kind in _shared_path_spans(line):
            if kind == "url":
                continue
            written = line[start:end]
            spelling = _shared_spelling(md_file, skills_dir, tail, kind)
            if written != spelling:
                findings.append((lineno, written, spelling))
    return findings


def check_shared_paths(text: str, md_file: Path, skills_dir: Path) -> list[str]:
    """Check (a): string projection of shared_path_findings, for the validator."""
    rel = md_file.relative_to(skills_dir)
    errors: list[str] = []
    for lineno, written, spelling in shared_path_findings(text, md_file, skills_dir):
        if spelling is None:
            errors.append(f"{rel}:{lineno}: `{written}` names nothing under skills/_shared/")
        elif spelling.startswith(CLAUDNA_ROOT):
            errors.append(
                f"{rel}:{lineno}: `{written}` is anchored to a root no other host sets -- write `{spelling}` "
                "(SKILL_CONTRACT §1; `python3 scripts/fix_shared_paths.py` rewrites these)"
            )
        else:
            errors.append(
                f"{rel}:{lineno}: `{written}` is not relative to this file -- write `{spelling}` "
                "(SKILL_CONTRACT §1; `python3 scripts/fix_shared_paths.py` rewrites these)"
            )
    return errors


def rewrite_shared_paths(text: str, md_file: Path, skills_dir: Path) -> tuple[str, int]:
    """Rewrite every `_shared/` path that has an accepted spelling to it.

    Returns (new text, paths rewritten). URLs are left alone, and so are paths
    naming nothing under skills/_shared/, for shared_path_findings to report.
    """
    lines = text.split("\n")
    count = 0
    for i, line in enumerate(lines):
        pieces: list[str] = []
        pos = 0
        for start, end, tail, kind in _shared_path_spans(line):
            if kind == "url":
                continue
            spelling = _shared_spelling(md_file, skills_dir, tail, kind)
            if spelling is not None and line[start:end] != spelling:
                pieces += [line[pos:start], spelling]
                pos = end
                count += 1
        lines[i] = "".join(pieces) + line[pos:]
    return "\n".join(lines), count


_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
# Claude Code fills these in only in an expanded SKILL.md body, fenced blocks
# included (measured on 2.1.281 and 2.1.284); in a file opened with Read they
# stay literal, and neither is set in the shell.
_PLUGIN_VAR_RE = re.compile(r"\$\{CLAUDE_(?:PLUGIN_ROOT|SKILL_DIR)\}")
_PLUGIN_CACHE = "plugins/cache/Claudfather/claudna"
# A bundled script run from the working directory, which is the user's project.
_CWD_SCRIPT_RE = re.compile(r"(?<![\w/.-])(?:python3?|bash|sh)\s+[\"']?(?:\./)?scripts/[\w.-]+")


def _definition_lines(lines: list[str]) -> set[int]:
    """Indices of the lines between the <claudna-root> definition markers."""
    inside: set[int] = set()
    on = False
    for i, line in enumerate(lines):
        if CLAUDNA_ROOT_BEGIN in line:
            on = True
        elif CLAUDNA_ROOT_END in line:
            on = False
        elif on:
            inside.add(i)
    return inside


def _fence_closers(lines: list[str]) -> dict[int, int]:
    """For each line inside a fenced block, the index of the line closing it."""
    closer: dict[int, int] = {}
    opened: int | None = None
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            if opened is None:
                opened = i
            else:
                closer.update({j: i for j in range(opened + 1, i)})
                opened = None
    return closer


def _has_resolver_fallback(lines: list[str], i: int, closer: dict[int, int]) -> bool:
    """Whether <claudna-root> sits on line i or, for a line in a fenced block,
    in the first paragraph after that block closes."""
    if CLAUDNA_ROOT in lines[i]:
        return True
    if i not in closer:
        return False
    j = closer[i] + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    while j < len(lines) and lines[j].strip() and not _FENCE_RE.match(lines[j]):
        if CLAUDNA_ROOT in lines[j]:
            return True
        j += 1
    return False


def check_plugin_variables(text: str, md_file: Path, skills_dir: Path) -> list[str]:
    """Check (b): ${CLAUDE_PLUGIN_ROOT} / ${CLAUDE_SKILL_DIR} only where Claude
    Code fills them in, a SKILL.md body, and only beside the <claudna-root>
    fallback that every other host needs."""
    rel = md_file.relative_to(skills_dir)
    lines = text.split("\n")
    definition = _definition_lines(lines)
    closer = _fence_closers(lines)
    errors: list[str] = []
    for i, line in enumerate(lines):
        m = _PLUGIN_VAR_RE.search(line)
        if not m or i in definition:
            continue
        if md_file.name != "SKILL.md":
            errors.append(
                f"{rel}:{i + 1}: `{m.group(0)}` is filled in only in a SKILL.md body; here it stays literal "
                f"and the shell has it unset -- write `{CLAUDNA_ROOT}` (SKILL_CONTRACT §1.1)"
            )
        elif not _has_resolver_fallback(lines, i, closer):
            errors.append(
                f"{rel}:{i + 1}: `{m.group(0)}` has no `{CLAUDNA_ROOT}` fallback on its line or in the paragraph "
                "after its code block -- no host but Claude Code fills it in (SKILL_CONTRACT §1.1)"
            )
    return errors


def check_plugin_cache_paths(text: str, md_file: Path, skills_dir: Path, fm: dict | None) -> list[str]:
    """Check (c): the plugin cache is the last <claudna-root> candidate, named
    only in its definition and in skills that run on Claude Code alone."""
    hosts = (fm or {}).get("hosts")
    if isinstance(hosts, list) and hosts and set(hosts) <= {"claude-code"}:
        return []
    rel = md_file.relative_to(skills_dir)
    lines = text.split("\n")
    definition = _definition_lines(lines)
    return [
        f"{rel}:{i + 1}: a Claude Code plugin-cache path -- write `{CLAUDNA_ROOT}`, whose last candidate is that "
        "cache; only a `hosts: [claude-code]` skill names the cache itself (SKILL_CONTRACT §1.1)"
        for i, line in enumerate(lines)
        if _PLUGIN_CACHE in line and i not in definition
    ]


def check_cwd_script_calls(text: str, md_file: Path, skills_dir: Path, fm: dict | None) -> list[str]:
    """Check (d): a bundled script run from the working directory, outside a
    skill that declares it runs from a clone of this repo."""
    if (fm or {}).get("requires-context") == "repo-clone":
        return []
    rel = md_file.relative_to(skills_dir)
    return [
        f"{rel}:{i + 1}: `{m.group(0)}` runs from the working directory, which is the user's project, not "
        f'this plugin -- write `python3 "{CLAUDNA_ROOT}/scripts/<name>"` (SKILL_CONTRACT §1.1)'
        for i, line in enumerate(text.split("\n"))
        for m in _CWD_SCRIPT_RE.finditer(line)
    ]


def check_resolver_pointer(text: str, md_file: Path, skills_dir: Path) -> list[str]:
    """Check (e): a file that writes <claudna-root> also names the file that
    says how to resolve it, so the reader -- or the orchestrator filling it
    into a prompt it forwards -- is not left to find the definition."""
    if CLAUDNA_ROOT not in text or "claudna-root.md" in text:
        return []
    rel = md_file.relative_to(skills_dir)
    first = next(i for i, line in enumerate(text.split("\n"), 1) if CLAUDNA_ROOT in line)
    return [
        f"{rel}:{first}: uses `{CLAUDNA_ROOT}` but never points at `claudna-root.md` -- add the pointer beside it "
        "(SKILL_CONTRACT §1.1)"
    ]


def check_host_portability(text: str, md_file: Path, skills_dir: Path, fm: dict | None) -> list[str]:
    """Checks (a)-(e) of SKILL_CONTRACT §5.1 (#336) for one markdown file under
    skills/. fm is the owning skill's frontmatter, or None for skills/_shared/."""
    return (
        check_shared_paths(text, md_file, skills_dir)
        + check_plugin_variables(text, md_file, skills_dir)
        + check_plugin_cache_paths(text, md_file, skills_dir, fm)
        + check_cwd_script_calls(text, md_file, skills_dir, fm)
        + check_resolver_pointer(text, md_file, skills_dir)
    )


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


def find_resurrected_dirs(removed_names: list[str], skills_dir: Path) -> list[str]:
    """Removed skill names that exist again as skills/<name>/ directories.

    The text gate matches references; a removed skill restored whole as a
    directory needs this check (#192). Resurrection is legitimate only via
    deliberately deleting the name from removed-skills.txt — a reviewable
    diff — never by silently recreating the directory. Used by both the
    validator (always-blocking) and the pytest backstop.
    """
    return [name for name in removed_names if (skills_dir / name).is_dir()]


def check_removed_name_mentions(text: str, removed_names: list[str]) -> list[tuple[str, str]]:
    """Flag reference-form mentions of a removed skill name.

    Four reference forms are matched: `claudna:<name>`, `/<name>`,
    `skills/<name>/`-style paths, and `Skill(<name>)` permission rules —
    each is the name preceded by a reference sigil. Bare prose mentions are
    deliberately NOT flagged: a retired skill's name may legitimately
    persist as ordinary vocabulary (e.g. the `tech-debt` GitHub label and
    concern taxonomy outlive the tech-debt skill).
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
    # A reference sigil must immediately precede the name: `claudna:`,
    # `Skill(`, a slash-command `/` (slash NOT continuing a path — a removed
    # name may be reborn as a lens/verb token, so `audit/tech-debt/…` inner
    # segments are legitimate), or the old top-level `skills/<name>` path.
    pattern = re.compile(
        rf"(?:claudna:|Skill\(|(?<![A-Za-z0-9_./-])/|(?<![A-Za-z0-9_-])skills/)"
        rf"({alternation})(?![A-Za-z0-9_-])",
        re.IGNORECASE,
    )
    if not pattern.search(text):
        return []
    # Deliberately canonical-case: only the §2.1 rule-6 breadcrumb form
    # ("Replaces /old-name") is sanctioned; lowercase prose like "this engine
    # replaces /old-name" is a real reference and must flag (the safe,
    # false-positive direction).
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



# --- grant-scope rule (allowlist) -------------------------------------------
# A skill's allowed-tools pre-approves commands with no prompt backstop, so this
# is an ALLOWLIST: a Bash grant is rejected unless it matches a small set of safe
# shapes. A denylist of command names cannot do the job -- it accepts every
# spelling it does not enumerate (a bare Bash, an absolute-path or version-
# suffixed interpreter, a package runner, a global-flag-first git/gh call).
#
# Accepted Bash shapes:
#   * an exact command with no wildcard (author-fixed; cannot be extended by
#     extended at call time), excluding commands that run project-defined code
#     even when exact (npm ci, pytest, make, ...);
#   * an interpreter running a FIXED script path, optionally with a trailing arg
#     wildcard (the repo's own script, not a free-form command);
#   * a safe git/gh/claudron SUBCOMMAND (git diff *, gh pr view *);
#   * a curated set of read-only shell utilities (ls *, cat *, grep *).
# Non-Bash tools (Read, Write, Edit, WebFetch, Agent, ...) are out of scope here.
# disable-model-invocation: true exempts a skill, since only an explicit user
# invokes it -- but that flag stops MODEL invocation of the skill, not content
# read during a run the user themselves started.

# Interpreters: allowed only to run a fixed script path, never bare / inline / glob.
_GRANT_INTERPRETERS = {
    "python", "python2", "python3", "node", "nodejs", "ruby", "perl",
    "bash", "sh", "zsh", "deno", "bun", "rscript",
}
_INTERP_INLINE_FLAGS = {"-c", "-e", "--eval", "-"}

# Rejected even as an exact grant: these run project-defined or free-form code,
# reach the network, or read the environment in a single command. Test runners
# and build tools run project-defined code (config, recipes), so no command that
# runs code the working tree controls is pre-approved -- it prompts instead, and
# the setup guide covers pre-approving these in the user's own settings.
_GRANT_REJECT_ALWAYS = {
    "npm", "pnpm", "yarn", "npx", "pip", "pip3", "uv", "uvx", "pipx",
    "poetry", "bundle", "gem",
    "make", "cmake", "ninja", "cargo", "go", "gradle", "mvn", "gcc", "cc",
    "clang", "rustc", "javac",
    "pytest", "tox", "nox", "jest", "vitest", "mocha", "ava", "cypress",
    "playwright", "eslint", "prettier", "tsc", "black", "flake8", "isort",
    "mypy", "ruff", "pylint", "bandit",
    "curl", "wget", "nc", "ncat", "socat", "ssh", "scp", "sftp", "rsync",
    "telnet", "ftp",
    "env", "eval", "exec", "source", "xargs", "sudo", "doas", "nice",
    "nohup", "timeout", "watch", "script",
    "docker", "podman", "kubectl", "terraform", "ansible", "aws", "gcloud", "az",
    "sed", "awk", "find",
    "printenv", "chmod", "chown", "dd", "rm", "tar", "unzip", "zip", "chattr",
    "php", "java", "pwsh", "powershell", "osascript", "groovy", "scala",
    "elixir", "lua", "tclsh", "expect",
}

# Read-only / non-code-running utilities: safe to pre-approve with arguments.
_GRANT_SAFE_UTILS = {
    "ls", "cat", "head", "tail", "wc", "stat", "file", "du", "df", "tree",
    "diff", "cmp", "grep", "egrep", "fgrep", "rg", "sort", "uniq", "cut",
    "tr", "comm", "join", "paste", "column", "nl", "fold", "rev", "tac",
    "mkdir", "rmdir", "mv", "cp", "touch", "date", "echo", "printf",
    "basename", "dirname", "realpath", "readlink", "pwd", "whoami", "id",
    "hostname", "uname", "which", "type", "command", "test", "true", "false",
    "seq", "tee", "jq", "lsof",
}

# Safe git subcommands: history and worktree only; not config, clone, or a global flag.
_GRANT_SAFE_GIT_SUB = {
    "status", "diff", "log", "show", "add", "commit", "branch", "checkout",
    "switch", "restore", "fetch", "rev-parse", "tag", "mv", "reset", "stash",
    "worktree", "check-ignore", "describe", "blame", "shortlog", "rev-list",
    "ls-files", "cat-file", "symbolic-ref", "name-rev", "merge-base",
    "for-each-ref", "diff-tree",
}
_GRANT_GIT_FORCE_FLAGS = {"--force", "-f", "--force-with-lease"}

# Safe gh subcommands: issues and pull requests only; not the api/auth/repo subcommands.
_GRANT_SAFE_GH_SUB = {"pr", "issue", "label", "search", "browse"}

# Safe claudron subcommands (read-only).
_GRANT_SAFE_CLAUDRON_SUB = {"status", "doctor", "lookup", "recall"}


def _reject_grant(entry: str, why: str) -> str:
    return (
        f"allowed-tools: {entry!r} pre-approves {why}; grant an exact command, a "
        "fixed script path, a read-only git/gh subcommand, or a read-only "
        "utility instead"
    )


def _grant_interpreter(entry: str, cmd: str, rest: list[str]) -> str | None:
    if not rest:
        return _reject_grant(entry, f"a bare '{cmd}' interpreter")
    first = rest[0]
    if first in _INTERP_INLINE_FLAGS or first.startswith("-"):
        return _reject_grant(entry, f"an inline-code flag on '{cmd}'")
    if "*" in first:
        return _reject_grant(entry, f"'{cmd}' with a wildcard script path")
    return None


def _grant_git(entry: str, rest: list[str]) -> str | None:
    if not rest:
        return _reject_grant(entry, "the whole 'git' command family")
    sub = rest[0]
    if sub.startswith("-"):
        return _reject_grant(entry, f"a git global flag {sub!r}")
    if sub == "push":
        if any(f in rest for f in _GRANT_GIT_FORCE_FLAGS):
            return _reject_grant(entry, "a forced 'git push'")
        return None
    if sub in _GRANT_SAFE_GIT_SUB:
        return None
    return _reject_grant(entry, f"'git {sub}'")


def _grant_sub(entry: str, cmd: str, rest: list[str], safe: set) -> str | None:
    if not rest:
        return _reject_grant(entry, f"the whole '{cmd}' command family")
    sub = rest[0]
    if sub.startswith("-"):
        return _reject_grant(entry, f"a {cmd} global flag {sub!r}")
    if sub in safe:
        return None
    return _reject_grant(entry, f"'{cmd} {sub}'")


def _grant_scope_error(entry: str) -> str | None:
    """Return an error string if this allowed-tools entry is an over-broad Bash
    grant, else None. Only Bash(...) entries are examined; other tools are out of
    scope for this rule."""
    stripped = entry.strip()
    if stripped == "Bash":
        return _reject_grant(entry, "the whole shell")
    m = re.match(r"^Bash\((.*)\)$", stripped)
    if not m:
        return None
    inner = m.group(1).strip()
    if not inner or inner.startswith("*"):
        return _reject_grant(entry, "the whole shell")
    toks = inner.split()
    cmd = toks[0]
    rest = toks[1:]
    has_star = "*" in inner

    if cmd == "git":
        return _grant_git(entry, rest)
    if cmd == "gh":
        return _grant_sub(entry, "gh", rest, _GRANT_SAFE_GH_SUB)
    if cmd == "claudron":
        return _grant_sub(entry, "claudron", rest, _GRANT_SAFE_CLAUDRON_SUB)
    if cmd in _GRANT_INTERPRETERS:
        return _grant_interpreter(entry, cmd, rest)
    if cmd in _GRANT_REJECT_ALWAYS:
        return _reject_grant(entry, f"'{cmd}', which is not an allowed command")
    if cmd in _GRANT_SAFE_UTILS:
        return None
    if has_star:
        return _reject_grant(entry, f"an unbounded wildcard grant of '{cmd}'")
    return None


def check_grant_scope(fm: dict) -> list[str]:
    """Reject over-broad pre-approved command grants in allowed-tools.

    An allowlist: a Bash grant is rejected unless it is an exact command, an
    interpreter running a fixed script, a safe git/gh/claudron subcommand, or a
    read-only utility. A skill that sets disable-model-invocation: true is exempt.
    """
    if "allowed-tools" not in fm:
        return []
    if fm.get("disable-model-invocation") is True:
        return []
    errors: list[str] = []
    for entry in _parse_allowed_tools_entries(fm["allowed-tools"]):
        err = _grant_scope_error(entry)
        if err:
            errors.append(err)
    return errors


def normalize_settings_grant(entry: str) -> str:
    """Convert a settings.json permission entry to skill allowed-tools form so the
    SAME allowlist predicate governs both surfaces (DRY).

    Settings.json writes ``Bash(cmd:*)`` where ``:*`` means "any arguments";
    skill allowed-tools writes ``Bash(cmd *)``. Everything else (a bare command,
    ``Bash(*)``) is already common to both forms.
    """
    m = re.match(r"^Bash\((.*)\)$", entry.strip())
    if not m:
        return entry.strip()
    inner = m.group(1)
    if inner.endswith(":*"):
        inner = inner[:-2].rstrip() + " *"
    return f"Bash({inner})"


def check_settings_grants(allow_entries: list) -> list[str]:
    """Apply the grant-scope allowlist to a settings.json ``permissions.allow``
    list. Returns error strings for any entry outside the allowlist, so a shipped
    settings file cannot restore a broad pre-approval the skills just dropped."""
    errors: list[str] = []
    for entry in allow_entries:
        if not isinstance(entry, str):
            continue
        err = _grant_scope_error(normalize_settings_grant(entry))
        if err:
            errors.append(err)
    return errors


#: Claudron CLI verbs, per skills/_shared/claudron-engine.md §2 and Claudron's
#: own docs/CLI_CONTRACT.md. Used only to recognize an *invocation*; this list
#: being incomplete makes the check miss a call, never invent one.
CLAUDRON_CLI_VERBS = (
    "capture",
    "doctor",
    "hooks",
    "index",
    "init",
    "lookup",
    "migrate",
    "recall",
    "status",
    "sync",
    "validate",
)

#: An invocation is `claudron <verb>` or the PATH probe. The lookbehind is the
#: load-bearing part: it drops `/claudron lookup` and `/claudna:claudron status`,
#: which are *skill* invocations. A skill that merely routes to the engine skill
#: takes on no dependency of its own, so requiring a declaration there would be
#: wrong — and would make the rule unsatisfiable for orientation skills that
#: enumerate the catalog.
_CLAUDRON_INVOCATION_RE = re.compile(
    r"(?<![/\w:.-])claudron[ \t]+(?:" + "|".join(CLAUDRON_CLI_VERBS) + r")\b"
    r"|command[ \t]+-v[ \t]+claudron\b"
)


def invokes_claudron(text: str) -> bool:
    """True when *text* shells out to the `claudron` CLI (not the engine skill)."""
    return _CLAUDRON_INVOCATION_RE.search(text) is not None


def declares_claudron(fm: dict) -> bool:
    """True when frontmatter declares the Claudron CLI in `requires:`."""
    requires = fm.get("requires")
    if not isinstance(requires, list):
        return False
    for entry in requires:
        if not isinstance(entry, dict):
            continue
        cli = entry.get("cli")
        if isinstance(cli, str) and re.match(r"^claudron\b", cli.strip()):
            return True
    return False


def check_claudron_requires(fm: dict, body: str) -> list[str]:
    """A skill that invokes the Claudron CLI must declare it in `requires:`.

    Claudron is an optional external CLI and every consumer degrades when it is
    absent (skills/_shared/claudron-engine.md §3). An undeclared dependency is
    how that degradation becomes invisible: nothing in the skill's frontmatter
    says the skill has a soft edge, so a reader — or a host installing skills
    without Claudron — has no way to know a fallback path exists before hitting
    it. Declaring it does not gate execution (the §1 detection ladder is the
    only runtime gate); it makes the dependency reviewable.
    """
    if not invokes_claudron(body) or declares_claudron(fm):
        return []
    return [
        "body invokes the `claudron` CLI but `requires:` does not declare it -- add "
        "`- cli: claudron` with a reason naming whether the dependency is hard or "
        "soft and which path needs it (see skills/_shared/claudron-engine.md §1)"
    ]


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

    # grant-scope allowlist
    errors.extend(check_grant_scope(fm))

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

    # disable-model-invocation rules
    dmi = fm.get("disable-model-invocation")
    if dmi is not None and not isinstance(dmi, bool):
        errors.append(f"disable-model-invocation must be a boolean, got {type(dmi).__name__}")

    # hosts rules (#340)
    if "hosts" in fm:
        errors.extend(validate_hosts(fm["hosts"]))

    # requires-context rules (#340, renamed from `context` in #343 -- see
    # KNOWN_FIELDS above for why)
    if "requires-context" in fm:
        errors.extend(validate_requires_context(fm["requires-context"]))

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
    errors.extend(check_claudron_requires(fm, body))
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
