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
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def test_local_overrides_shared_in_the_same_directory(tmp_path):
    home, cwd, _memory = _fleet_bot_layout(tmp_path)
    shared = tmp_path / "shared-memory"
    local = tmp_path / "local-memory"
    for d in (shared, local):
        d.mkdir()
    _write_settings(cwd, "settings.json", {"autoMemoryDirectory": str(shared)})
    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": str(local)})

    assert resolve_memory_dir(cwd, home) == local


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


# --- setting-value handling --------------------------------------------------


def test_tilde_and_relative_values_resolve_to_absolute(tmp_path):
    home, cwd, _memory = _fleet_bot_layout(tmp_path)

    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": "~/tilde-memory"})
    assert resolve_memory_dir(cwd, home).is_absolute()

    _write_settings(cwd, "settings.local.json", {"autoMemoryDirectory": "./rel-memory"})
    resolved = resolve_memory_dir(cwd, home)
    assert resolved.is_absolute()
    assert resolved == (cwd / "rel-memory").resolve()


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


def _run(cwd: Path, home: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RESOLVER_PY)],
        cwd=cwd,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
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


# --- the skill must delegate, not reconstruct --------------------------------


def test_recall_skill_invokes_the_resolver(tmp_path):
    """Pins the fix at the skill surface — the prose is what actually ships."""
    body = RECALL_SKILL.read_text()
    assert "resolve_memory_dir.py" in body, "recall must resolve the memory dir, not rebuild the path"
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_memory_dir.py" in body
    # Same plugin-root fallback convention redact.py established.
    assert "~/.claude/plugins/cache/Claudfather/claudna/*/scripts/resolve_memory_dir.py" in body
    assert RESOLVER_PY.is_file()
