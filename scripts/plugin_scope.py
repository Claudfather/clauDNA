"""Shared manifest component-path classification; host exclusion policy stays local."""

from __future__ import annotations

import json
from pathlib import Path

from skill_checks import SKIP_DIRS


def declared_skills(plugin_dir: Path) -> tuple[set[str] | None, bool, str]:
    """Parse plugin.json's `skills` field into a set of skill names.

    Returns (names, is_explicit_list, description). `names` is None when the
    field is absent or unparseable in either supported shape -- the caller
    then refuses the check rather than fabricate a verdict from nothing.
    `is_explicit_list` distinguishes the two supported shapes because only
    one of them makes "missing from the list" a meaningful question: a bare
    directory path ships everything under it by construction, so nothing can
    go missing from it.
    """
    path = plugin_dir / "plugin.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return None, False, f"{path} unreadable or not valid JSON ({e})"

    raw = data.get("skills")
    if raw is None:
        return None, False, "plugin.json has no 'skills' field"

    plugin_root = plugin_dir.parent
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
