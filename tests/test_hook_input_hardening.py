"""Input-hardening invariants for two hooks (#260, defense-in-depth).

Neither is exploitable today — `session_id` is a Claude-Code-generated UUID and
the telemetry slug arrives quote-free through a `grep -o` — but both place an
externally-derived value into a structural position (a filesystem path, a
hand-built JSON line) without validating its charset. These tests pin the
guard so a future refactor that changes the value's provenance cannot silently
reopen the gap.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRECOMPACT = REPO_ROOT / "plugin-hooks" / "precompact-reflect.sh"
TELEMETRY = REPO_ROOT / "plugin-hooks" / "telemetry-emit.sh"


class TestPrecompactSessionIdIsPathSafe:
    """`session_id` becomes part of a marker path — a `/`-bearing value must
    not be used to build it."""

    def _run(self, tmp_path: Path, session_id: str) -> tuple[int, str]:
        marker_dir = tmp_path / "mtmp"
        marker_dir.mkdir(exist_ok=True)
        env = {
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(marker_dir),
            # Ensure jq is used for extraction where present; also clear any
            # ambient session id so only the payload drives the path.
            "CLAUDE_SESSION_ID": "",
        }
        proc = subprocess.run(
            ["bash", str(PRECOMPACT)],
            input=json.dumps({"session_id": session_id}),
            capture_output=True, text=True, cwd=tmp_path, env=env, timeout=10,
        )
        return proc.returncode, proc.stdout

    def test_valid_session_id_blocks_first_then_allows(self, tmp_path):
        code, out = self._run(tmp_path, "sess-abc123.DEF_456")
        assert code == 0
        assert '"decision":"block"' in out  # first attempt blocks
        code, out = self._run(tmp_path, "sess-abc123.DEF_456")
        assert code == 0
        assert out.strip() == ""  # marker existed → second attempt allows

    def test_slash_bearing_session_id_is_rejected_cleanly(self, tmp_path):
        # A traversal-shaped id must not crash the hook nor build a marker path
        # from it. Fail-open (exit 0, no block) like the no-id case.
        code, out = self._run(tmp_path, "../../pwn-260")
        assert code == 0, f"hook crashed on a malformed session_id (exit {code})"
        # No marker file bearing the injected name anywhere under tmp_path.
        strays = [p.name for p in tmp_path.rglob("*pwn-260*")]
        assert strays == [], f"marker built from unsafe id: {strays}"

    def test_dotdot_only_id_creates_no_traversal(self, tmp_path):
        code, _ = self._run(tmp_path, "../evil")
        assert code == 0
        assert list(tmp_path.rglob("*evil*")) == []


class TestTelemetryEmitsValidJson:
    """The jq-less fallback hand-builds a JSON line; whatever the slug, the
    emitted line must be valid JSON or nothing at all."""

    def _run_without_jq(self, tmp_path: Path, event: dict) -> list[str]:
        # Force the hand-built JSON branch by pointing PATH at a curated dir of
        # symlinks that includes the coreutils the hook needs but NOT jq — a
        # failing stub wouldn't work, since `command -v jq` would still find it.
        import shutil

        curated = tmp_path / "curated-bin"
        curated.mkdir(exist_ok=True)
        # `bash`/`sh` included so the child interpreter itself resolves under
        # this PATH (subprocess looks up the executable via the child env);
        # jq is deliberately excluded to force the hand-built branch.
        for tool in ("bash", "sh", "grep", "cut", "head", "date", "mkdir",
                     "dirname", "cat", "wc", "mv", "rm", "touch", "sed", "sort", "find"):
            real = shutil.which(tool)
            if real:
                (curated / tool).symlink_to(real)
        assert shutil.which("jq", path=str(curated)) is None, "jq leaked into the no-jq PATH"

        out_path = tmp_path / "events.jsonl"
        env = {
            "PATH": str(curated),
            "CLAUDNA_TELEMETRY": "1",
            "CLAUDNA_TELEMETRY_PATH": str(out_path),
            "HOME": str(tmp_path),
        }
        # Compact JSON: the no-jq branch extracts with a whitespace-free
        # `"skill":"…"` grep, which is the contract this branch already assumes.
        subprocess.run(
            ["bash", str(TELEMETRY)], input=json.dumps(event, separators=(",", ":")),
            capture_output=True, text=True, cwd=tmp_path, env=env, timeout=10,
        )
        return out_path.read_text().splitlines() if out_path.exists() else []

    def test_backslash_slug_does_not_emit_broken_json(self, tmp_path):
        # `\z` is an invalid JSON escape; a hand-built line carrying it would be
        # unparseable. The guard must drop such a slug, not emit corrupt JSON.
        lines = self._run_without_jq(
            tmp_path, {"tool_input": {"skill": "claudna:bad\\zslug"}}
        )
        assert lines == [], f"a malformed slug was emitted: {lines}"

    def test_normal_slug_emits_one_valid_event(self, tmp_path):
        lines = self._run_without_jq(
            tmp_path, {"tool_input": {"skill": "claudna:capture"}}
        )
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["data"]["skill_slug"] == "capture"
