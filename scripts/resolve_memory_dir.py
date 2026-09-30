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
never the bot's. The nearest ancestor that sets the key wins.

Only the user's own settings choose the directory, by Claude Code's definitions
(code.claude.com/docs/en/memory, /docs/en/permissions):

- A project's shared `.claude/settings.json` is not read. It comes with the
  repository, and the walk reaches the settings of every checkout it passes.
- `.claude/settings.local.json` counts while it is the user's own file. Claude
  Code treats it as supplied by the repository when git tracks it or when
  `.claude` is a symlink, and then it does not count here either. A file outside
  any git repository is the user's own. When git cannot say whether it tracks
  the file, the file does not count.
- The user tier, `~/.claude/settings.json`, is the floor.
- A value must be an absolute path or start with `~/`, as Claude Code requires.
  Any other value does not count, and the search moves on.

    python3 scripts/resolve_memory_dir.py

Prints the resolved directory. Exit 0 when it holds a readable `MEMORY.md`,
1 when it does not (no harness memory for this project — the caller skips
silently). `resolve_memory_dir` can be imported directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SETTING_KEY = "autoMemoryDirectory"

# The one project settings file that may choose the directory, relative to the
# directory being searched. The shared `.claude/settings.json` is deliberately
# absent: see the module docstring.
LOCAL_SETTINGS = ".claude/settings.local.json"

GIT_TIMEOUT_S = 10


def project_slug(cwd: Path) -> str:
    """The harness's per-project directory name: the cwd with every `/` → `-`."""
    return str(cwd).replace("/", "-")


def default_memory_dir(cwd: Path, home: Path) -> Path:
    """Where the harness keeps auto-memory when nothing redirects it."""
    return home / ".claude" / "projects" / project_slug(cwd) / "memory"


def _candidate_dirs(cwd: Path, project_dir: Path | None) -> list[Path]:
    """Directories whose `.claude/` may set the key, nearest first.

    `CLAUDE_PROJECT_DIR` is the harness's own answer, so it stands alone when
    exported; otherwise walk up, because a bot's settings sit above the repo
    checkout its skills run in.
    """
    return [project_dir] if project_dir else [cwd, *cwd.parents]


def _read_setting(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None  # absent or malformed — that tier simply has no opinion
    if not isinstance(data, dict):
        return None
    value = data.get(SETTING_KEY)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _as_directory(value: str, home: Path) -> Path | None:
    """The directory a setting names, or None for a value Claude Code refuses.

    Claude Code takes an absolute path or one starting with `~/`. A relative
    value would resolve against whatever directory the command happens to run
    in, so it is not a directory at all.
    """
    if value.startswith("~/"):
        return Path(f"{home}/{value[2:]}")
    path = Path(value)
    return path if path.is_absolute() else None


def _inside_a_git_repository(directory: Path) -> bool:
    return any((d / ".git").exists() for d in (directory, *directory.parents))


def _git_tracks_local_settings(directory: Path) -> bool | None:
    """True when git tracks `directory/.claude/settings.local.json`, False when
    it does not, None when git cannot say (missing, failing or slow)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        result = subprocess.run(
            # `-c core.fsmonitor=`: a repository's own config runs no command
            # on this read (the session-start and statusline hooks do the same).
            [
                "git",
                "-C",
                str(directory),
                "-c",
                "core.fsmonitor=",
                "--no-optional-locks",
                "ls-files",
                "--error-unmatch",
                "--",
                LOCAL_SETTINGS,
            ],
            capture_output=True,
            env=env,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(result.returncode)


def _local_settings_are_the_users_own(directory: Path) -> bool:
    """Whether `directory/.claude/settings.local.json` is the user's own file."""
    if (directory / ".claude").is_symlink():
        return False
    if not _inside_a_git_repository(directory):
        return True
    return _git_tracks_local_settings(directory) is False


def _first_configured(cwd: Path, home: Path, project_dir: Path | None) -> Path | None:
    """The winning `autoMemoryDirectory`, or None if nothing sets one."""
    for base in _candidate_dirs(cwd, project_dir):
        value = _read_setting(base / LOCAL_SETTINGS)
        if value is None:
            continue
        directory = _as_directory(value, home)
        if directory is not None and _local_settings_are_the_users_own(base):
            return directory
    value = _read_setting(home / ".claude" / "settings.json")
    return _as_directory(value, home) if value else None


def resolve_memory_dir(cwd: Path, home: Path, project_dir: Path | None = None) -> Path:
    """The harness auto-memory dir for `cwd`, honouring any redirect.

    Falls back to the cwd-derived default only when nothing in the settings
    chain sets one. `~/` resolves against `home`, so the answer is always
    absolute.
    """
    configured = _first_configured(cwd, home, project_dir)
    return configured if configured is not None else default_memory_dir(cwd, home)


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
