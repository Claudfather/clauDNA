#!/usr/bin/env python3
"""Resolve the harness auto-memory directory for the current project (#245).

`/claudna:recall` re-reads the harness `MEMORY.md` live on every recall. To do
that it has to know where the harness actually keeps it — and that is a setting,
not a formula.

The default location is derived from the cwd (`~/.claude/projects/<cwd-slug>/
memory`), but the `autoMemoryDirectory` setting redirects it anywhere. Claudlobby
sets it on every composed bot, pointing at the bot's own `memory/` dir outside
`~/.claude/` entirely. A skill that reconstructs the default path instead of
reading the setting therefore looks in a directory that does not exist on any
fleet bot, finds nothing, and skips silently — the feature no-ops in the exact
environment it ships into, while passing any test run on an un-redirected box.

So resolution is mechanical here rather than prose in a skill body: the path is
read from the settings chain, with the derived path as the fallback it always
was for un-redirected setups.

Settings are searched from `CLAUDE_PROJECT_DIR` when the harness exports it
(hooks get it; an interactive session does not), otherwise by walking up from
the cwd. The walk matters: a bot's session starts in its own directory and its
settings live there, but skills run with the cwd inside a repo checkout several
levels below — so reading only `./.claude/` finds the *repo's* settings and
never the bot's. The nearest ancestor that actually sets the key wins.

    python3 scripts/resolve_memory_dir.py

Prints the resolved directory. Exit 0 when it holds a readable `MEMORY.md`,
1 when it does not (no harness memory for this project — the caller skips
silently). `resolve_memory_dir` can be imported directly.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SETTING_KEY = "autoMemoryDirectory"

# Within one directory, `.local` overrides the shared file.
PROJECT_SETTINGS = (".claude/settings.json", ".claude/settings.local.json")


def project_slug(cwd: Path) -> str:
    """The harness's per-project directory name: the cwd with every `/` → `-`."""
    return str(cwd).replace("/", "-")


def default_memory_dir(cwd: Path, home: Path) -> Path:
    """Where the harness keeps auto-memory when nothing redirects it."""
    return home / ".claude" / "projects" / project_slug(cwd) / "memory"


def _settings_files(cwd: Path, home: Path, project_dir: Path | None) -> list[Path]:
    """The settings files to consult, in ascending precedence order."""
    files = [home / ".claude" / "settings.json"]
    # Furthest ancestor first so the nearest directory's setting lands last.
    bases = [project_dir] if project_dir else [cwd, *cwd.parents]
    for base in reversed(bases):
        files.extend(base / rel for rel in PROJECT_SETTINGS)
    # Preserve order while dropping the duplicate when home is itself an ancestor.
    return list(dict.fromkeys(files))


def _read_setting(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None  # absent or malformed — that tier simply has no opinion
    if not isinstance(data, dict):
        return None
    value = data.get(SETTING_KEY)
    return value.strip() if isinstance(value, str) and value.strip() else None


def resolve_memory_dir(cwd: Path, home: Path, project_dir: Path | None = None) -> Path:
    """The harness auto-memory dir for `cwd`, honouring any redirect.

    Falls back to the cwd-derived default only when nothing in the settings
    chain sets one. A relative setting resolves against `cwd`, and `~` against
    `home`, so the answer is always absolute.
    """
    configured: str | None = None
    for path in _settings_files(cwd, home, project_dir):
        configured = _read_setting(path) or configured
    if configured is None:
        return default_memory_dir(cwd, home)
    expanded = Path(configured).expanduser() if configured.startswith("~") else Path(configured)
    return expanded if expanded.is_absolute() else (cwd / expanded).resolve()


def main() -> int:
    env_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    memory_dir = resolve_memory_dir(
        Path.cwd(),
        Path.home(),
        Path(env_project_dir) if env_project_dir else None,
    )
    print(memory_dir)
    return 0 if (memory_dir / "MEMORY.md").is_file() else 1


if __name__ == "__main__":
    sys.exit(main())
