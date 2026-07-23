"""F1 capture-prompt defer — the fail-safe matrix (clauDNA #254).

`precompact-reflect.sh` hands the compaction prompt to Claudron's engine ONLY
when it can prove two things at once:

  (1) the engine's PreCompact hook is registered in the host's settings — the
      normative `hook pre-compact` command suffix (Claudron CLI_CONTRACT.md
      §Session-loop protocol) — so the engine WILL prompt; and
  (2) the probed `engine_version` (`claudron status --json` → data.engine_version)
      is >= SHIM_REMOVAL_RELEASE, the release that removed the engine's
      transitional glob shim — so the engine's prompt is front-end-neutral and
      it no longer yields the role back to us.

The whole reason for the version gate is the F1 ordering hazard: an OLDER engine
still carries a shim that ALSO yields to the clauDNA plugin. If this hook
deferred there, BOTH sides would yield and *nobody* would prompt — durable
capture would stop, silently. So the guard is fail-safe by construction: a
missing / old / unparseable version, or an engine hook that is not actually
registered, must resolve to "prompt" (at worst a bounded double-prompt with the
engine), never to "defer" (the silent no-prompt).

These tests pin that matrix. A regression that lets any non-DEFER row go silent
is exactly the failure the gate exists to prevent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "plugin-hooks" / "precompact-reflect.sh"

# Must equal SHIM_REMOVAL_RELEASE in the hook. If the hook's constant is
# finalized to the real Claudron shim-removal release, update this too.
SHIM_REMOVAL_RELEASE = "0.4.0"

# A settings.json fragment registering the engine's PreCompact hook — the
# normative shape from CLI_CONTRACT.md §Session-loop protocol (identity is the
# `hook pre-compact` command suffix).
ENGINE_HOOK = {
    "hooks": {
        "PreCompact": [
            {"matcher": "", "hooks": [
                {"type": "command", "command": "/opt/claudron/bin/claudron hook pre-compact"},
            ]},
        ],
    },
}

# clauDNA's own PreCompact hook — command does NOT end in `hook pre-compact`, so
# it must never be mistaken for the engine's registered entry.
CLAUDNA_OWN_HOOK = {
    "hooks": {
        "PreCompact": [
            {"matcher": "", "hooks": [
                {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/plugin-hooks/precompact-reflect.sh"},
            ]},
        ],
    },
}

# Tools the hook (and the fake claudron's shebang) resolve by name. jq is found
# via shutil.which so the test does not assume a fixed path (macOS vs Linux CI).
_TOOLS = ("bash", "sh", "env", "jq", "cat", "touch", "rm", "mkdir", "grep")


def _curated_bin(tmp_path: Path, engine_version: str | None) -> Path:
    """A PATH dir with real tools symlinked in, plus a fake `claudron`.

    engine_version:
      * a version string -> `claudron status --json` emits it and exits 0
      * ""               -> `claudron status --json` exits 3 (no vault; version absent)
      * None             -> no `claudron` on PATH at all
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for tool in _TOOLS:
        real = shutil.which(tool)
        if real:
            link = bindir / tool
            if not link.exists():
                link.symlink_to(real)
    assert shutil.which("jq", path=str(bindir)), "jq must resolve for this test to be meaningful"
    if engine_version is not None:
        claudron = bindir / "claudron"
        claudron.write_text(
            "#!/usr/bin/env bash\n"
            'if [ "$1" = "status" ]; then\n'
            '  if [ -n "${FAKE_ENGINE_VERSION:-}" ]; then\n'
            "    printf '{\"ok\":true,\"command\":\"status\",\"data\":"
            '{"engine_version":"%s","root":"/v","tiers":{},"total_docs":0,'
            '"total_stale":0,"projects":[],"fleets":[],"quarantined":0,'
            '"index_present":true,"index_fresh":true,"warnings":[]}}'
            "\\n' \"$FAKE_ENGINE_VERSION\"\n"
            "    exit 0\n"
            "  fi\n"
            '  echo "no vault found" >&2\n'
            "  exit 3\n"
            "fi\n"
            "exit 0\n"
        )
        claudron.chmod(0o755)
    return bindir


def run_hook(
    tmp_path: Path,
    *,
    user_settings: dict | None = None,
    project_settings: dict | None = None,
    local_settings: dict | None = None,
    engine_version: str | None,
    session_id: str = "sess-defer-1",
) -> tuple[int, str]:
    """Invoke the hook with an isolated HOME/cwd and the given settings + engine.

    Returns (exit_code, stdout). HOME and cwd are distinct dirs so the user
    settings file and the project settings file never collapse onto each other.
    """
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (proj / ".claude").mkdir(parents=True, exist_ok=True)
    if user_settings is not None:
        (home / ".claude" / "settings.json").write_text(json.dumps(user_settings))
    if project_settings is not None:
        (proj / ".claude" / "settings.json").write_text(json.dumps(project_settings))
    if local_settings is not None:
        (proj / ".claude" / "settings.local.json").write_text(json.dumps(local_settings))

    bindir = _curated_bin(tmp_path, engine_version)
    tmpdir = tmp_path / "tmpd"
    tmpdir.mkdir(exist_ok=True)
    env = {
        "HOME": str(home),
        "PATH": str(bindir),
        "TMPDIR": str(tmpdir),
        "CLAUDE_SESSION_ID": "",
        "FAKE_ENGINE_VERSION": engine_version or "",
    }
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"session_id": session_id}),
        capture_output=True, text=True, cwd=proj, env=env, timeout=15,
    )
    return proc.returncode, proc.stdout


def defers(code: int, out: str) -> bool:
    """The hook stood aside: exit 0 and NOTHING on stdout (no block decision)."""
    return code == 0 and out.strip() == ""


def prompts(out: str) -> bool:
    """The hook claimed the prompt: a block decision on stdout."""
    return '"decision":"block"' in out


class TestDefersOnlyWhenEngineOwnsThePrompt:
    """The engine hook is registered AND engine_version >= the shim-removal
    release: the engine prompts and no longer yields, so we stand aside."""

    @pytest.mark.parametrize("version", ["0.4.0", "0.4.1", "0.10.0", "1.0.0", "2.3.4"])
    def test_registered_and_new_enough_defers(self, tmp_path, version):
        code, out = run_hook(tmp_path, user_settings=ENGINE_HOOK, engine_version=version)
        assert defers(code, out), f"v{version}: expected DEFER, got exit={code} out={out!r}"

    def test_numeric_not_lexical_compare(self, tmp_path):
        # 0.10.0 > 0.4.0 numerically but sorts BEFORE it lexically — a string
        # compare would wrongly prompt here.
        code, out = run_hook(tmp_path, user_settings=ENGINE_HOOK, engine_version="0.10.0")
        assert defers(code, out)

    def test_engine_hook_in_project_settings_is_detected(self, tmp_path):
        code, out = run_hook(tmp_path, project_settings=ENGINE_HOOK, engine_version="0.4.0")
        assert defers(code, out)

    def test_engine_hook_in_local_settings_is_detected(self, tmp_path):
        code, out = run_hook(tmp_path, local_settings=ENGINE_HOOK, engine_version="0.4.0")
        assert defers(code, out)


class TestPromptsFailSafe:
    """Every not-provably-safe case resolves to PROMPT — never a silent defer."""

    @pytest.mark.parametrize("version", ["0.3.0", "0.2.0", "0.3.9", "0.0.1"])
    def test_old_engine_still_shimmed_prompts(self, tmp_path, version):
        # Below the shim-removal release: the engine may still yield to us, so
        # we MUST prompt or nobody does.
        code, out = run_hook(tmp_path, user_settings=ENGINE_HOOK, engine_version=version)
        assert prompts(out), f"v{version}: expected PROMPT, got exit={code} out={out!r}"

    def test_uninstalled_checkout_version_prompts(self, tmp_path):
        # "0.0.0-dev" is what an uninstalled engine checkout reports.
        code, out = run_hook(tmp_path, user_settings=ENGINE_HOOK, engine_version="0.0.0-dev")
        assert prompts(out)

    def test_git_between_tags_version_prompts(self, tmp_path):
        # A git install between tags reports a dev version below the next tag;
        # it may pre-date the removal, so the fail-safe answer is to prompt.
        code, out = run_hook(tmp_path, user_settings=ENGINE_HOOK, engine_version="0.3.9.dev4+g1a2b3c")
        assert prompts(out)

    def test_unparseable_version_prompts(self, tmp_path):
        code, out = run_hook(tmp_path, user_settings=ENGINE_HOOK, engine_version="not-a-version")
        assert prompts(out)

    def test_version_absent_prompts(self, tmp_path):
        # Engine hook registered, but `status` exits 3 (no vault) — no version
        # to read → cannot prove the engine will prompt neutrally → we prompt.
        code, out = run_hook(tmp_path, user_settings=ENGINE_HOOK, engine_version="")
        assert prompts(out)

    def test_engine_not_on_path_prompts(self, tmp_path):
        # Hook entry present but `claudron` is not installed → cannot probe → prompt.
        code, out = run_hook(tmp_path, user_settings=ENGINE_HOOK, engine_version=None)
        assert prompts(out)

    def test_high_version_but_no_registered_hook_prompts(self, tmp_path):
        # THE critical row: a new engine is installed, but its PreCompact hook is
        # NOT registered on this host, so it will NOT prompt. Version alone must
        # never license a defer — that would be the silent no-prompt failure.
        code, out = run_hook(tmp_path, user_settings={"hooks": {}}, engine_version="1.0.0")
        assert prompts(out)

    def test_only_claudna_own_hook_prompts(self, tmp_path):
        # clauDNA's own PreCompact command must not be mistaken for the engine's.
        code, out = run_hook(tmp_path, user_settings=CLAUDNA_OWN_HOOK, engine_version="1.0.0")
        assert prompts(out)

    def test_no_settings_at_all_prompts(self, tmp_path):
        code, out = run_hook(tmp_path, engine_version="1.0.0")
        assert prompts(out)


class TestTwoAttemptProtocolIntactWhenPrompting:
    """When clauDNA owns the prompt, the block-then-allow marker cycle still
    works (unchanged behavior from before the defer landed)."""

    def test_first_blocks_second_allows(self, tmp_path):
        code1, out1 = run_hook(tmp_path, user_settings=CLAUDNA_OWN_HOOK,
                               engine_version=None, session_id="two-attempt")
        assert code1 == 0 and prompts(out1)
        code2, out2 = run_hook(tmp_path, user_settings=CLAUDNA_OWN_HOOK,
                               engine_version=None, session_id="two-attempt")
        assert code2 == 0 and out2.strip() == ""


class TestOptOutStillWins:
    """The historical opt-out short-circuits before any defer logic."""

    def test_disabled_never_prompts_and_never_probes(self, tmp_path):
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True, exist_ok=True)
        bindir = _curated_bin(tmp_path, "0.3.0")  # old engine present
        env = {
            "HOME": str(home),
            "PATH": str(bindir),
            "TMPDIR": str(tmp_path / "tmpd"),
            "CLAUDNA_PRECOMPACT_REFLECT": "0",
        }
        (tmp_path / "tmpd").mkdir(exist_ok=True)
        proc = subprocess.run(
            ["bash", str(HOOK)], input=json.dumps({"session_id": "x"}),
            capture_output=True, text=True, cwd=tmp_path, env=env, timeout=15,
        )
        assert proc.returncode == 0 and proc.stdout.strip() == ""
