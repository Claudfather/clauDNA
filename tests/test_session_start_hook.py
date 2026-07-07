"""Invariants for the SessionStart briefing hook (epic #165 P7, fork F3).

The hook is on-by-default and fires at every session start, so its failure
modes are continuously enforced here (not just launch-verified): always
exit 0, silent under the opt-out, silent when there is nothing to say,
and fast without network access.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "plugin-hooks" / "session-start.sh"


def _no_gh_path(tmp_root: Path) -> str:
    """A PATH whose gh always fails fast — CI runners preinstall /usr/bin/gh,
    so excluding directories is not enough; shadow it with a failing stub."""
    shim = tmp_root / "shim-bin"
    shim.mkdir(exist_ok=True)
    stub = shim / "gh"
    stub.write_text("#!/bin/sh\nexit 1\n")
    stub.chmod(0o755)
    return f"{shim}:/usr/bin:/bin"


def run_hook(cwd: Path, env_overrides: dict | None = None) -> tuple[int, str, float]:
    env = os.environ.copy()
    env.pop("CLAUDNA_SESSION_BRIEFING", None)
    # No probe may make a network call: shadow gh with a failing stub.
    env["PATH"] = _no_gh_path(cwd)
    if env_overrides:
        env.update(env_overrides)
    start = time.monotonic()
    proc = subprocess.run(
        ["bash", str(HOOK)], input="{}", capture_output=True, text=True,
        cwd=cwd, env=env, timeout=10,
    )
    return proc.returncode, proc.stdout, time.monotonic() - start


class TestSessionStartHook:
    def test_opt_out_is_silent_and_zero(self, tmp_path):
        code, out, _ = run_hook(tmp_path, {"CLAUDNA_SESSION_BRIEFING": "0"})
        assert code == 0
        assert out == ""

    def test_cold_dir_no_repo_no_handoff_is_silent(self, tmp_path):
        code, out, _ = run_hook(tmp_path)
        assert code == 0
        assert out == ""

    def test_handoff_renders_next_steps_and_staleness(self, tmp_path):
        claude = tmp_path / ".claude"
        claude.mkdir()
        (claude / "session.md").write_text(
            "## Next Steps\n- finish the refactor\n\n## Open Questions\n- cache warm?\n"
        )
        code, out, _ = run_hook(tmp_path)
        assert code == 0
        assert "<claudna-session-briefing>" in out
        assert "finish the refactor" in out
        assert "cache warm?" in out
        assert "Briefing directive" in out
        assert "never paste the raw briefing" in out

    def test_repo_without_handoff_points_at_session_engine(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        code, out, _ = run_hook(tmp_path)
        assert code == 0
        assert "/claudna:session handoff" in out

    def test_time_budget_without_network(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        code, _, elapsed = run_hook(tmp_path)
        assert code == 0
        assert elapsed < 2.0, f"hook took {elapsed:.2f}s — over the 2s budget"

    def test_wired_in_hooks_json_without_compact(self):
        import json

        d = json.loads((REPO_ROOT / "plugin-hooks" / "hooks.json").read_text())
        entries = d["hooks"]["SessionStart"]
        assert entries and "session-start.sh" in entries[0]["hooks"][0]["command"]
        assert "compact" not in entries[0]["matcher"], "compact trigger is #176's decision"
