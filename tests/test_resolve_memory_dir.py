"""Tests for scripts/resolve_memory_dir.py — harness auto-memory resolution (#245).

`/claudna:recall` re-reads the harness `MEMORY.md` live. The first cut of that
feature reconstructed the path (`~/.claude/projects/<cwd-slug>/memory`) instead
of reading the `autoMemoryDirectory` setting that redirects it. On an
un-redirected box the reconstruction is correct, so it passed review and sixteen
days of green CI — while no-opping silently on every Claudlobby fleet bot, where
memory is redirected out of `~/.claude/` entirely.

That is the trap these tests exist to close: **a test that only exercises the
default path cannot tell the two implementations apart.** So the centrepiece
below builds the redirected topology a real bot has — settings at the bot dir,
cwd several levels below it in a repo checkout — and asserts resolution follows
the redirect. Each such test also asserts the answer differs from the
cwd-derived default, which is the exact assertion the old implementation fails.

Which settings choose the directory is tested both ways. A project's shared
`.claude/settings.json`, a `.claude/settings.local.json` that git tracks or that
sits in a symlinked `.claude`, and a value that is neither absolute nor
`~/`-prefixed leave the answer unchanged; the user's own local and user settings
keep choosing it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from resolve_memory_dir import default_memory_dir, project_slug, resolve_memory_dir  # noqa: E402

RESOLVER_PY = REPO_ROOT / "scripts" / "resolve_memory_dir.py"
RECALL_SKILL = REPO_ROOT / "skills" / "recall" / "SKILL.md"


def _write_settings(directory: Path, name: str, payload: dict) -> Path:
    settings = directory / ".claude" / name
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(payload))
    return settings


def _memory_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "MEMORY.md").write_text("- [A note](note.md) — a line\n")
    return path


def _fleet_bot_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    """The topology a Claudlobby bot actually runs in.

    Settings and memory live at the bot dir; skills run with the cwd inside a
    repo checkout below it. Returns (home, cwd, redirected_memory_dir).
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)

    bot_dir = tmp_path / "fleet" / "bots" / "alex"
    memory = bot_dir / "memory"
    memory.mkdir(parents=True)
    (memory / "MEMORY.md").write_text("- [Telegram outbound](tg.md) — plain text only\n")
    _write_settings(bot_dir, "settings.local.json", {"autoMemoryDirectory": str(memory)})

    cwd = bot_dir / "projects" / "some-repo"
    cwd.mkdir(parents=True)
    return home, cwd, memory


def _git(repo: Path, *args: str) -> None:
    """Run git in `repo` with no user or system configuration."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(repo),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


# --- the regression: a redirected directory ---------------------------------


def test_follows_redirect_from_a_repo_cwd_below_the_bot_dir(tmp_path):
    """The fleet-bot case the original implementation silently no-opped on."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)

    resolved = resolve_memory_dir(cwd, home)

    assert resolved == memory
    # The assertion that fails against a reconstructed path.
    assert resolved != default_memory_dir(cwd, home)
    assert (resolved / "MEMORY.md").is_file()


def test_redirect_wins_even_when_the_repo_has_its_own_settings(tmp_path):
    """A repo's committed .claude/settings.json must not mask the bot's redirect.

    clauDNA itself ships one, so this is the real arrangement, not a hypothetical.
    """
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    _write_settings(cwd, "settings.json", {"permissions": {"allow": ["Bash"]}})

    assert resolve_memory_dir(cwd, home) == memory


def test_nearest_setting_wins(tmp_path):
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    nearer = tmp_path / "override-memory"
    nearer.mkdir()
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": str(nearer)})

    assert resolve_memory_dir(cwd, home) == nearer
    assert resolve_memory_dir(cwd, home) != memory


def test_user_tier_redirect_is_honoured(tmp_path):
    home = tmp_path / "home"
    memory = tmp_path / "user-memory"
    memory.mkdir()
    (home / ".claude").mkdir(parents=True)
    _write_settings(home, "settings.json", {"autoMemoryDirectory": str(memory)})
    cwd = tmp_path / "work"
    cwd.mkdir()

    assert resolve_memory_dir(cwd, home) == memory


def test_explicit_project_dir_overrides_the_ancestor_walk(tmp_path):
    """CLAUDE_PROJECT_DIR, when the harness exports it, is authoritative."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    elsewhere = tmp_path / "explicit"
    elsewhere.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    _write_settings(project, "settings.local.json", {"autoMemoryDirectory": str(elsewhere)})

    assert resolve_memory_dir(cwd, home, project_dir=project) == elsewhere
    assert resolve_memory_dir(cwd, home, project_dir=project) != memory


# --- the un-redirected default still works ----------------------------------


def test_falls_back_to_the_derived_default_when_nothing_redirects(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    cwd = tmp_path / "plain-project"
    cwd.mkdir()

    resolved = resolve_memory_dir(cwd, home)

    assert resolved == home / ".claude" / "projects" / project_slug(cwd) / "memory"


def test_project_slug_replaces_every_separator(tmp_path):
    assert project_slug(Path("/home/crog/work")) == "-home-crog-work"


# --- which settings choose the directory ------------------------------------


def test_a_projects_shared_settings_file_does_not_choose_the_directory(tmp_path):
    """The shared `.claude/settings.json` comes with the checkout; it is not read."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    chosen = _memory_dir(tmp_path / "chosen-by-the-checkout")
    _write_settings(cwd, "settings.json", {"autoMemoryDirectory": str(chosen)})

    assert resolve_memory_dir(cwd, home) == memory


def test_a_shared_settings_file_is_not_read_even_when_nothing_else_sets_one(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    cwd = tmp_path / "checkout"
    chosen = _memory_dir(tmp_path / "chosen-by-the-checkout")
    _write_settings(cwd, "settings.json", {"autoMemoryDirectory": str(chosen)})

    assert resolve_memory_dir(cwd, home) == default_memory_dir(cwd, home)


def test_an_explicit_project_dirs_shared_settings_file_is_not_read(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    cwd = tmp_path / "work"
    cwd.mkdir()
    project = tmp_path / "project"
    chosen = _memory_dir(tmp_path / "chosen-by-the-project")
    _write_settings(project, "settings.json", {"autoMemoryDirectory": str(chosen)})

    assert resolve_memory_dir(cwd, home, project_dir=project) == default_memory_dir(cwd, home)


def test_a_local_settings_file_tracked_in_git_does_not_choose_the_directory(tmp_path):
    """A tracked `settings.local.json` came with the repository, not from the user."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    _git(cwd, "init", "-q")
    chosen = _memory_dir(tmp_path / "chosen-by-the-checkout")
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": str(chosen)})
    _git(cwd, "add", ".claude/settings.local.json")

    assert resolve_memory_dir(cwd, home) == memory


def test_a_tracked_local_settings_file_in_a_repository_subdirectory_does_not_count(tmp_path):
    """The file sits below the repository root: the `.git` that says it is tracked is above it."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    _git(cwd, "init", "-q")
    package = cwd / "packages" / "app"
    chosen = _memory_dir(tmp_path / "chosen-by-a-subdirectory")
    _write_settings(package, "settings.local.json", {"autoMemoryDirectory": str(chosen)})
    _git(cwd, "add", "packages/app/.claude/settings.local.json")
    (package / "src").mkdir()

    assert resolve_memory_dir(package / "src", home) == memory


def test_an_untracked_local_settings_file_in_a_git_checkout_still_counts(tmp_path):
    """The user's own `settings.local.json` in a checkout keeps choosing the directory."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    _git(cwd, "init", "-q")
    (cwd / "README.md").write_text("a tracked file\n")
    _git(cwd, "add", "README.md")
    own = _memory_dir(tmp_path / "users-own-choice")
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": str(own)})

    assert resolve_memory_dir(cwd, home) == own
    assert resolve_memory_dir(cwd, home) != memory


def test_a_local_settings_file_in_a_symlinked_claude_dir_does_not_count(tmp_path):
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    chosen = _memory_dir(tmp_path / "chosen-through-a-link")
    target = tmp_path / "elsewhere"
    _write_settings(target, "settings.local.json", {"autoMemoryDirectory": str(chosen)})
    (cwd / ".claude").symlink_to(target / ".claude", target_is_directory=True)

    assert resolve_memory_dir(cwd, home) == memory


def test_a_local_settings_file_git_cannot_classify_does_not_count(tmp_path):
    """Inside something that looks like a repository but git cannot read: fail closed."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    (cwd / ".git").mkdir()  # not a repository git can open
    chosen = _memory_dir(tmp_path / "chosen-by-the-checkout")
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": str(chosen)})

    assert resolve_memory_dir(cwd, home) == memory


def test_asking_git_runs_no_command_the_repositorys_config_names(tmp_path):
    """The one git read runs with `core.fsmonitor` cleared, as the hooks' reads do."""
    home, cwd, _memory = _fleet_bot_layout(tmp_path)
    _git(cwd, "init", "-q")
    own = _memory_dir(tmp_path / "users-own-choice")
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": str(own)})
    marker = tmp_path / "ran"
    hook = tmp_path / "fsmonitor-hook"
    hook.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    hook.chmod(0o755)
    _git(cwd, "config", "core.fsmonitor", str(hook))

    assert resolve_memory_dir(cwd, home) == own  # git was asked: the file is untracked
    assert not marker.exists()


def test_git_variables_in_the_environment_do_not_change_the_answer(tmp_path, monkeypatch):
    """git is asked about the checkout itself, never a repository named by `GIT_DIR`."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    _git(cwd, "init", "-q")
    chosen = _memory_dir(tmp_path / "chosen-by-the-checkout")
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": str(chosen)})
    _git(cwd, "add", ".claude/settings.local.json")
    other = tmp_path / "other-repo"
    other.mkdir()
    _git(other, "init", "-q")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))

    assert resolve_memory_dir(cwd, home) == memory


# --- setting-value handling --------------------------------------------------


def test_a_tilde_value_expands_against_home(tmp_path, monkeypatch):
    home, cwd, _memory = _fleet_bot_layout(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": "~/tilde-memory"})

    assert resolve_memory_dir(cwd, home) == home / "tilde-memory"


@pytest.mark.parametrize("value", ["notes", "./notes", "../elsewhere", "memory/sub", "~"])
def test_a_value_that_is_neither_absolute_nor_home_relative_is_refused(tmp_path, value):
    """Claude Code takes an absolute path or one starting with `~/`, nothing else."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": value})

    resolved = resolve_memory_dir(cwd, home)

    assert resolved == memory
    assert resolved != (cwd / value).resolve()


def test_a_relative_value_in_the_user_settings_is_refused(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    _write_settings(home, "settings.json", {"autoMemoryDirectory": "notes"})
    cwd = tmp_path / "work"
    cwd.mkdir()

    assert resolve_memory_dir(cwd, home) == default_memory_dir(cwd, home)


def test_malformed_or_empty_settings_do_not_break_resolution(tmp_path):
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    broken = cwd / ".claude"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "settings.local.json").write_text("{not json")

    # The malformed tier is ignored; the bot's redirect still applies.
    assert resolve_memory_dir(cwd, home) == memory

    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": "   "})
    assert resolve_memory_dir(cwd, home) == memory


# --- CLI contract ------------------------------------------------------------


def _run(cwd: Path, home: Path, path: str = "/usr/bin:/bin") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RESOLVER_PY)],
        cwd=cwd,
        env={"HOME": str(home), "PATH": path},
        capture_output=True,
        text=True,
    )


def test_cli_prints_the_redirected_dir_and_exits_zero_when_memory_exists(tmp_path):
    home, cwd, memory = _fleet_bot_layout(tmp_path)

    result = _run(cwd, home)

    assert result.stdout.strip() == str(memory)
    assert result.returncode == 0


def test_cli_exits_one_when_there_is_no_memory_file(tmp_path):
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    (memory / "MEMORY.md").unlink()

    result = _run(cwd, home)

    assert result.stdout.strip() == str(memory)  # still reports where it looked
    assert result.returncode == 1


def test_cli_without_git_does_not_count_a_local_settings_file_inside_a_repository(tmp_path):
    """With no git to ask, a local settings file inside a checkout does not count."""
    home, cwd, memory = _fleet_bot_layout(tmp_path)
    _git(cwd, "init", "-q")
    own = _memory_dir(tmp_path / "unverifiable-choice")
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": str(own)})

    result = _run(cwd, home, path=str(tmp_path / "no-tools-here"))

    assert result.stdout.strip() == str(memory)
    assert result.returncode == 0


# --- the skill must delegate, not reconstruct --------------------------------


def test_recall_skill_invokes_the_resolver(tmp_path):
    """Pins the fix at the skill surface — the prose is what actually ships."""
    body = RECALL_SKILL.read_text()
    assert "resolve_memory_dir.py" in body, "recall must resolve the memory dir, not rebuild the path"
    # Claude Code fills ${CLAUDE_PLUGIN_ROOT} in here, so the command is kept as
    # it was; every other host takes the <claudna-root> fallback beside it
    # (SKILL_CONTRACT §1.1), which is also the plugin cache's only way in now.
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_memory_dir.py" in body
    assert "<claudna-root>/scripts/resolve_memory_dir.py" in body
    assert "../_shared/claudna-root.md" in body
    assert "plugins/cache" not in body
    assert RESOLVER_PY.is_file()
