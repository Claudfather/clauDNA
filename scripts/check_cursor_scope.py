#!/usr/bin/env python3
"""Cursor manifest scope gate (clauDNA #340).

`.cursor-plugin/plugin.json`'s `skills` field is the set of skills Cursor
ships. This gate keeps that set honest against each skill's own `hosts` /
`requires-context` frontmatter (`skill_checks.cursor_should_exclude`):

  - A skill marked host- or context-restricted must NOT appear in the
    declared set -- it would ship to Cursor despite being unusable there
    (the bug #340 files: `hosts`/`requires-context` didn't exist, so nothing
    could be marked, and the directory-discovery manifest shipped
    everything).
  - A skill NOT so marked MUST appear in the declared set. This direction
    exists because the fix for the first bug creates a new failure mode:
    an explicit list, unlike directory discovery, can silently omit a
    skill nobody meant to exclude, the day it is added and nobody
    remembers to add it here too.

Run via validate-manifest.py (`make check-manifest`), not validate-skills.py:
this is a property of the MANIFEST's declared list, not of any one skill's
own frontmatter shape (that half is skill_checks.validate_hosts /
validate_requires_context, enforced by `make check-skills`).
"""

from __future__ import annotations

import json
from pathlib import Path

from skill_checks import SKIP_DIRS, cursor_should_exclude, parse_frontmatter


def _declared_cursor_skills(cursor_plugin_dir: Path) -> tuple[set[str] | None, bool, str]:
    """Parse plugin.json's `skills` field into a set of skill names.

    Returns (names, is_explicit_list, description). `names` is None when the
    field is absent or unparseable in either supported shape -- the caller
    then refuses the check rather than fabricate a verdict from nothing.
    `is_explicit_list` distinguishes the two supported shapes because only
    one of them makes "missing from the list" a meaningful question: a bare
    directory path ships everything under it by construction, so nothing can
    go missing from it.
    """
    path = cursor_plugin_dir / "plugin.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return None, False, f"{path} unreadable or not valid JSON ({e})"

    raw = data.get("skills")
    if raw is None:
        return None, False, "plugin.json has no 'skills' field"

    plugin_root = cursor_plugin_dir.parent
    skills_dir = plugin_root / "skills"

    if isinstance(raw, str):
        # Path(...) already normalizes a "./" prefix on join; lstrip("./")
        # strips *characters*, not a prefix, so a real dot-leading name
        # (".agents") would lose its dot too (#343).
        resolved = (plugin_root / raw).resolve()
        if not resolved.is_dir():
            return None, False, f"plugin.json's skills path {raw!r} is not a directory"
        names = {p.name for p in resolved.iterdir() if p.is_dir() and p.name not in SKIP_DIRS}
        return names, False, f"directory discovery ({raw!r})"

    if isinstance(raw, list):
        names: set[str] = set()
        for entry in raw:
            if not isinstance(entry, str):
                return None, False, f"plugin.json's skills[] has a non-string entry: {entry!r}"
            # #343: a naive basename of the raw string passes ANY entry --
            # a folder ("./skills/") basenames to "skills", a file
            # (".../SKILL.md") basenames to "SKILL.md" -- neither matches a
            # real skill name, so the exclusion check silently finds nothing
            # wrong while Cursor itself would ship every restricted skill.
            # Resolve against the plugin root and classify what is actually
            # there instead of trusting the entry's own text.
            resolved = (plugin_root / entry).resolve()
            if not resolved.is_dir():
                return (
                    None,
                    False,
                    f"plugin.json's skills[] entry {entry!r} does not resolve to a "
                    f"directory ({resolved}) -- each entry must be a skill "
                    f"directory (one SKILL.md) or a directory of skills",
                )
            if resolved != skills_dir and skills_dir not in resolved.parents:
                return (
                    None,
                    False,
                    f"plugin.json's skills[] entry {entry!r} resolves to {resolved}, "
                    f"which is outside {skills_dir} -- refusing rather than guessing "
                    f"what it means",
                )
            if (resolved / "SKILL.md").is_file():
                names.add(resolved.name)  # one skill directory
            else:
                # A folder of skills (Cursor's own directory-discovery shape,
                # nested inside the array) -- expand it the same way the
                # string branch above expands a bare directory-discovery path.
                names.update(p.name for p in resolved.iterdir() if p.is_dir() and p.name not in SKIP_DIRS)
        return names, True, "explicit list"

    return (
        None,
        False,
        f"plugin.json's skills field is neither a string nor a list (got {type(raw).__name__})",
    )


def run_check(repo_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (errors, warnings, notes) -- the shape validate-manifest.py expects."""
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    skills_dir = repo_root / "skills"
    cursor_plugin_dir = repo_root / ".cursor-plugin"

    declared, is_explicit, how = _declared_cursor_skills(cursor_plugin_dir)
    if declared is None:
        errors.append(f"cursor-scope gate could not determine the declared skill set: {how}")
        return errors, warnings, notes
    notes.append(f"cursor-plugin/plugin.json declares its skill set via {how}")

    expected_shipped: set[str] = set()
    expected_excluded: set[str] = set()
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir() and p.name not in SKIP_DIRS):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue  # validate-skills.py's check-skills already reports this
        try:
            parsed = parse_frontmatter(skill_md)
        except ValueError:
            continue  # ditto -- malformed frontmatter is check-skills's finding
        if parsed is None:
            continue
        fm, _ = parsed
        if cursor_should_exclude(fm):
            expected_excluded.add(skill_dir.name)
        else:
            expected_shipped.add(skill_dir.name)

    for name in sorted(declared & expected_excluded):
        errors.append(
            f"cursor-plugin/plugin.json ships '{name}', which is marked "
            f"host/context-restricted in its own frontmatter (#340) -- remove it "
            f"from the skills list, or drop the restriction if it no longer applies"
        )

    if is_explicit:
        for name in sorted(expected_shipped - declared):
            errors.append(
                f"cursor-plugin/plugin.json's skills list is missing '{name}', "
                f"which carries no host/context restriction (#340) -- add it to "
                f"the list, or mark it restricted if it needs one"
            )

    return errors, warnings, notes
