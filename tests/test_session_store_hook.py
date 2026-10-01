"""Tests for the session store's hook adapter (lib/claudna/session_store/boundaries.py)
and its wrapper (plugin-hooks/session-store.sh) — spec §4.2 and §4.4.

What these guard:

* **The boundary table.** SessionStart opens a session and a segment at the
  transcript's size; PreCompact seals it; SessionStart(compact) opens the next
  segment where the seal ended; SessionEnd seals and closes; a resume reopens.
* **R-record's invariants.** The wrapper always exits 0 and prints nothing; it
  is silent in clauDNA's children, when switched off, and for a nested child
  that inherited its parent's session id; failures land in the error log.
* **Durability.** Lifecycle events are fsynced; activity lines are not.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import claudna.session_store.store as store_module  # noqa: E402
from claudna.session_store import boundaries, harvest, paths  # noqa: E402
from claudna.session_store.cli import run_hook  # noqa: E402
from claudna.session_store.fsio import append_jsonl  # noqa: E402

WRAPPER = REPO_ROOT / "plugin-hooks" / "session-store.sh"
HOOKS_JSON = REPO_ROOT / "plugin-hooks" / "hooks.json"
SID = "3fbbf216-f848-4d8b-b5b5-7839fc98b820"
CLI_ENV = {"CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDNA_HARVEST": "1"}  # opted in: summaries have a reader


@pytest.fixture
def transcript(tmp_path: Path) -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_bytes(b"x" * 100)
    return path


@pytest.fixture(autouse=True)
def spawned(monkeypatch) -> list[tuple[str, int]]:
    """Tests never start a real summarizer: each spawn is recorded instead."""
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(boundaries, "spawn_summarizer", lambda handle, index, env: calls.append((handle.sid, index)))
    monkeypatch.setattr(boundaries, "spawn_harvest", lambda root, env: pytest.fail("unexpected harvest spawn"))
    monkeypatch.setattr(harvest, "is_due", lambda root, env: False)  # whatever this machine has installed
    monkeypatch.setattr(boundaries, "spawn_sweep", lambda root, env: None)  # tested in test_session_store_unclosed
    return calls


def fire(store, event: str, transcript: Path, env=CLI_ENV, **fields) -> str:
    payload = {"session_id": SID, "transcript_path": str(transcript), "cwd": str(transcript.parent),
               "hook_event_name": event, **fields}
    return boundaries.handle(event, payload, store=store, env=env)


def grow(transcript: Path, n: int) -> None:
    with transcript.open("ab") as fh:
        fh.write(b"y" * n)


def session(store) -> dict:
    return json.loads(store.session(SID).paths.session_json.read_text())


def segment(store, index: int) -> dict:
    return json.loads(store.session(SID).paths.segment(index).segment_json.read_text())


# ── the boundary table ───────────────────────────────────────────────────────


class TestBoundaries:
    def test_a_session_start_opens_the_session_and_a_segment_at_the_transcripts_size(self, store, transcript):
        assert fire(store, "SessionStart", transcript, source="startup") == "session opened (startup)"
        s = session(store)
        assert (s["status"], s["opened_by"], s["actor"]["kind"], s["transcript_path"]) == \
            ("open", "startup", "interactive", str(transcript))
        assert segment(store, 1)["transcript"]["range"] == {"start": 100, "end": None}

    def test_a_compaction_seals_then_opens_the_next_segment_where_the_seal_ended(self, store, transcript):
        fire(store, "SessionStart", transcript, source="startup")
        grow(transcript, 50)
        assert fire(store, "PreCompact", transcript, trigger="auto") == "segment sealed"
        grow(transcript, 7)  # the compaction summary lands after the seal
        assert fire(store, "SessionStart", transcript, source="compact") == "segment opened (compact)"
        seg1, seg2 = segment(store, 1), segment(store, 2)
        assert (seg1["status"], seg1["sealed_by"], seg1["transcript"]["range"]) == \
            ("sealed", "precompact", {"start": 100, "end": 150})
        assert (seg2["opened_by"], seg2["transcript"]["range"]["start"]) == ("compact", 150)

    def test_each_seal_starts_the_summarizer_for_that_segment(self, store, transcript, spawned):
        fire(store, "SessionStart", transcript, source="startup")
        fire(store, "PreCompact", transcript, trigger="auto")
        fire(store, "SessionStart", transcript, source="compact")
        fire(store, "SessionEnd", transcript, reason="other")
        assert spawned == [(SID, 1), (SID, 2)]

    @pytest.mark.parametrize("env,reason", [({"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}, "headless"),
                                            ({**CLI_ENV, "CLAUDNA_SESSION_SUMMARY": "0"}, "disabled")])
    def test_a_closed_summary_gate_is_recorded_by_the_hook_and_spawns_nothing(self, store, transcript, spawned,
                                                                             env, reason):
        fire(store, "SessionStart", transcript, env=env, source="startup")
        fire(store, "SessionEnd", transcript, env=env, reason="other")
        last = json.loads(store.session(SID).paths.lifecycle.read_text().splitlines()[-1])
        assert spawned == [] and (last["kind"], last["data"]) == ("summary.skipped", {"reason": reason})

    def test_a_session_start_starts_a_harvest_when_one_is_due(self, store, transcript, monkeypatch):
        harvests = []
        monkeypatch.setattr(harvest, "is_due", lambda root, env: True)
        monkeypatch.setattr(boundaries, "spawn_harvest", lambda root, env: harvests.append(root))
        fire(store, "SessionStart", transcript, source="startup")
        fire(store, "PreCompact", transcript, trigger="auto")
        fire(store, "SessionStart", transcript, source="compact")  # a compaction never starts one
        assert harvests == [store.root]

    def test_a_blocked_compaction_reseals_later(self, store, transcript):
        fire(store, "SessionStart", transcript, source="startup")
        fire(store, "PreCompact", transcript, trigger="manual")
        grow(transcript, 30)
        fire(store, "PreCompact", transcript, trigger="manual")
        assert segment(store, 1)["transcript"]["range"] == {"start": 100, "end": 130}

    def test_session_end_seals_and_closes_then_a_resume_reopens(self, store, transcript):
        fire(store, "SessionStart", transcript, source="startup")
        grow(transcript, 20)
        assert fire(store, "SessionEnd", transcript, reason="prompt_input_exit") == \
            "session closed (prompt_input_exit)"
        assert (session(store)["status"], segment(store, 1)["transcript"]["range"]["end"]) == ("closed", 120)
        assert fire(store, "SessionEnd", transcript, reason="other") == "ignored: no open session"
        grow(transcript, 5)
        fire(store, "SessionStart", transcript, source="resume")
        assert (session(store)["status"], segment(store, 2)["transcript"]["range"]["start"]) == ("open", 125)

    def test_a_segment_the_store_sealed_itself_is_still_summarized(self, store, transcript, spawned):
        fire(store, "SessionStart", transcript, source="startup")
        grow(transcript, 20)  # a crash: no SessionEnd, so segment 1 is still open
        fire(store, "SessionStart", transcript, source="resume")
        assert segment(store, 1)["status"] == "sealed" and (SID, 1) in spawned

    def test_an_unknown_close_reason_is_recorded_as_other(self, store, transcript):
        fire(store, "SessionStart", transcript, source="startup")
        fire(store, "SessionEnd", transcript, reason="bypass_permissions_disabled")
        assert session(store)["close_reason"] == "other"

    def test_a_missing_transcript_never_seals_before_the_start(self, store, transcript):
        fire(store, "SessionStart", transcript, source="startup")
        transcript.unlink()
        fire(store, "PreCompact", transcript, trigger="auto")
        assert segment(store, 1)["transcript"]["range"] == {"start": 100, "end": 100}

    def test_a_precompact_without_a_segment_records_nothing(self, store, transcript):
        assert fire(store, "PreCompact", transcript, trigger="auto") == "ignored: no open session"
        assert not store.session(SID).paths.lifecycle.exists()

    def test_a_fork_opens_a_session(self, store, transcript):
        fire(store, "SessionStart", transcript, source="fork")
        assert session(store)["opened_by"] == "fork"


class TestGuards:
    def test_clauDNAs_own_children_record_nothing(self, store, transcript):
        out = fire(store, "SessionStart", transcript, env={**CLI_ENV, "CLAUDNA_SESSION_CHILD": "1"}, source="startup")
        assert out == "ignored: clauDNA child" and not store.session(SID).exists()

    def test_a_nested_child_with_an_inherited_session_id_cannot_close_its_parent(self, store, transcript):
        fire(store, "SessionStart", transcript, source="startup")
        child = {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}
        assert fire(store, "SessionStart", transcript, env=child, source="startup").startswith("ignored: nested")
        assert fire(store, "SessionEnd", transcript, env=child, reason="other").startswith("ignored: nested")
        assert session(store)["status"] == "open" and store.session(SID).paths.segment_indices() == [1]

    @pytest.mark.parametrize("event,payload", [
        ("Stop", {"session_id": SID}),
        ("SessionStart", ["not", "an", "object"]),
        ("SessionStart", {"session_id": "../escape", "source": "startup"}),
        ("SessionStart", {"source": "startup"}),
        ("SessionStart", {"session_id": SID, "source": "teleport"}),
    ])
    def test_unknown_events_and_bad_payloads_are_ignored(self, store, event, payload):
        assert boundaries.handle(event, payload, store=store, env=CLI_ENV).startswith("ignored")
        assert not (store.root / "sessions").exists() or not any((store.root / "sessions").iterdir())


class TestActorAndOrigin:
    @pytest.mark.parametrize("env,kind", [
        ({"CLAUDE_CODE_ENTRYPOINT": "cli"}, "interactive"),
        ({"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}, "headless"),
        ({}, "interactive"),
        ({"CLAUDE_CODE_ENTRYPOINT": "sdk-cli", "BOT_ID": "astrid", "BOT_NAME": "Astrid", "FLEET_NAME": "ops"}, "bot"),
    ])
    def test_the_actor_comes_from_the_environment(self, env, kind):
        actor = boundaries.actor_from_env(env)
        assert actor["kind"] == kind
        if kind == "bot":
            assert (actor["bot_id"], actor["bot_name"], actor["fleet"]) == ("astrid", "Astrid", "ops")

    def test_the_origin_reads_the_branch_and_head_of_a_repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run([*git, "init", "-q", "-b", "trunk"], check=True)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "c"], check=True)
        origin = boundaries.origin_from_cwd(str(repo))
        assert (origin["repo"], origin["branch"], len(origin["head"])) == ("repo", "trunk", 40)

    def test_a_repo_with_no_commits_yet_still_has_a_name(self, tmp_path):
        """A fresh ``git init``: HEAD can't resolve, but the repo is known (harvest scopes drafts to it)."""
        repo = tmp_path / "fresh"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        assert boundaries.origin_from_cwd(str(repo)) == {"cwd": str(repo), "repo": "fresh", "branch": None,
                                                         "head": None}

    def test_the_origin_outside_a_repo_has_no_branch(self, tmp_path):
        assert boundaries.origin_from_cwd(str(tmp_path)) == {"cwd": str(tmp_path), "repo": None,
                                                              "branch": None, "head": None}


class TestDurability:
    def test_lifecycle_events_are_fsynced_and_activity_lines_are_not(self, store, transcript, monkeypatch):
        fire(store, "SessionStart", transcript, source="startup")
        calls = []
        real = store_module.append_jsonl
        monkeypatch.setattr(store_module, "append_jsonl",
                            lambda path, record, *, durable=True: calls.append((path.name, durable))
                            or real(path, record, durable=durable))
        h = store.session(SID)
        h.append("prompt.submitted", {"prompt_id": None, "chars": 1})
        h.seal_segment(100, "precompact")
        assert calls == [("events.jsonl", False), ("lifecycle.jsonl", True)]

    def test_append_jsonl_can_skip_the_fsync(self, tmp_path, monkeypatch):
        monkeypatch.setattr(os, "fsync", lambda fd: pytest.fail("fsynced"))
        append_jsonl(tmp_path / "l.jsonl", {"k": 1}, durable=False)


# ── the CLI verb and the wrapper ─────────────────────────────────────────────


class TestRunHook:
    def test_a_store_failure_is_logged_and_never_raised(self, tmp_path, transcript):
        root = tmp_path / "state"
        root.mkdir()
        (root / "sessions").write_text("not a directory")
        payload = json.dumps({"session_id": SID, "transcript_path": str(transcript), "source": "startup"})
        out = run_hook("SessionStart", payload, env={"CLAUDNA_STATE_DIR": str(root), **CLI_ENV})
        assert out.startswith("error:")
        logged = [json.loads(line) for line in (root / "hooks" / "errors.log").read_text().splitlines()]
        assert logged[0]["event"] == "SessionStart" and "prompt" not in json.dumps(logged)

    def test_unparseable_input_is_logged(self, tmp_path):
        root = tmp_path / "state"
        assert run_hook("SessionStart", "{not json", env={"CLAUDNA_STATE_DIR": str(root)}).startswith("error:")
        assert (root / "hooks" / "errors.log").is_file()

    def test_a_failing_prompt_payload_never_reaches_the_log(self, tmp_path, transcript):
        root = tmp_path / "state"
        root.mkdir()
        (root / "sessions").write_text("not a directory")
        payload = json.dumps({"session_id": SID, "transcript_path": str(transcript), "source": "startup",
                              "prompt": "PROMPT-TEXT-THAT-MUST-NOT-BE-LOGGED"})
        assert run_hook("SessionStart", payload, env={"CLAUDNA_STATE_DIR": str(root), **CLI_ENV}).startswith("error:")
        assert "PROMPT-TEXT" not in (root / "hooks" / "errors.log").read_text()

    def test_invalid_utf8_on_stdin_is_logged_not_raised(self, tmp_path):
        root = tmp_path / "state"
        out = run_hook("SessionStart", b'{"session_id": "\xff"}', env={"CLAUDNA_STATE_DIR": str(root)})
        assert out.startswith("error: UnicodeDecodeError")
        assert "UnicodeDecodeError" in (root / "hooks" / "errors.log").read_text()

    def test_logging_an_error_rotates_both_hook_logs(self, tmp_path):
        from claudna.session_store.fsio import LOG_LIMIT

        root = tmp_path / "state"
        hooks = root / "hooks"
        hooks.mkdir(parents=True)
        for name in ("errors.log", "session-store.stderr"):
            (hooks / name).write_text("x" * (LOG_LIMIT + 1))
        run_hook("SessionStart", "{not json", env={"CLAUDNA_STATE_DIR": str(root)})
        assert (hooks / "errors.log.old").stat().st_size == LOG_LIMIT + 1
        assert (hooks / "errors.log").stat().st_size < 1024
        assert (hooks / "session-store.stderr.old").is_file() and not (hooks / "session-store.stderr").exists()


def run_wrapper(tmp_path: Path, event: str, payload: dict, extra_env: dict | None = None, cwd: Path | None = None):
    env = {"HOME": str(tmp_path / "home"), "PATH": os.environ["PATH"], "CLAUDNA_HARVEST": "0", **CLI_ENV,
           **(extra_env or {})}
    return subprocess.run(["bash", str(WRAPPER), event], input=json.dumps(payload), capture_output=True,
                          text=True, env=env, cwd=cwd or tmp_path, timeout=20)


class TestWrapper:
    def payload(self, transcript: Path) -> dict:
        return {"session_id": SID, "transcript_path": str(transcript), "cwd": str(transcript.parent),
                "source": "startup"}

    def test_it_records_prints_nothing_and_exits_0(self, tmp_path, transcript):
        proc = run_wrapper(tmp_path, "SessionStart", self.payload(transcript))
        assert (proc.returncode, proc.stdout) == (0, "")
        state = tmp_path / "home" / ".claudna"
        assert (state / "sessions" / SID / "seg-001").is_dir()
        assert state.stat().st_mode & 0o077 == 0

    @pytest.mark.parametrize("env", [{"CLAUDNA_SESSION_STORE": "0"}, {"CLAUDNA_SESSION_CHILD": "1"},
                                     {"CLAUDNA_STATE_DIR": "relative/state"}])
    def test_it_is_silent_when_off_in_children_and_without_a_safe_root(self, tmp_path, transcript, env):
        proc = run_wrapper(tmp_path, "SessionStart", self.payload(transcript), env)
        assert (proc.returncode, proc.stdout) == (0, "")
        assert not (tmp_path / "home" / ".claudna" / "sessions").exists()
        assert not (tmp_path / "relative").exists()

    def test_a_project_module_named_like_the_stdlib_cannot_shadow_it(self, tmp_path, transcript):
        project = tmp_path / "project"
        project.mkdir()
        (project / "json.py").write_text("raise ImportError('the project shadowed the stdlib')\n")
        proc = run_wrapper(tmp_path, "SessionStart", self.payload(transcript), cwd=project)
        assert proc.returncode == 0
        assert (tmp_path / "home" / ".claudna" / "sessions" / SID).is_dir(), proc.stderr

    def test_a_python_that_cannot_start_is_logged_not_swallowed(self, tmp_path, transcript):
        fake = tmp_path / "bin"
        fake.mkdir()
        (fake / "python3").write_text("#!/bin/sh\necho 'ImportError: no module named claudna' >&2\nexit 1\n")
        (fake / "python3").chmod(0o755)
        proc = run_wrapper(tmp_path, "SessionStart", self.payload(transcript),
                           {"PATH": f"{fake}:{os.environ['PATH']}"})
        assert (proc.returncode, proc.stdout) == (0, "")
        assert "ImportError" in (tmp_path / "home" / ".claudna" / "hooks" / "session-store.stderr").read_text()

    def test_the_wrapper_rotates_its_stderr_capture_even_when_python_cannot_start(self, tmp_path, transcript):
        fake = tmp_path / "bin"
        fake.mkdir()
        (fake / "python3").write_text("#!/bin/sh\necho 'ImportError: again' >&2\nexit 1\n")
        (fake / "python3").chmod(0o755)
        hooks = tmp_path / "home" / ".claudna" / "hooks"
        hooks.mkdir(parents=True)
        (hooks / "session-store.stderr").write_text("x" * (1024 * 1024 + 1))
        run_wrapper(tmp_path, "SessionStart", self.payload(transcript), {"PATH": f"{fake}:{os.environ['PATH']}"})
        assert (hooks / "session-store.stderr.old").stat().st_size == 1024 * 1024 + 1
        assert (hooks / "session-store.stderr").read_text().strip() == "ImportError: again"

    def test_the_wrapper_limit_matches_the_python_one(self):
        from claudna.session_store.fsio import LOG_LIMIT

        assert f"-gt {LOG_LIMIT}" in WRAPPER.read_text()


STATE_DIR_SH = REPO_ROOT / "plugin-hooks" / "lib" / "state-dir.sh"


class TestStateRootParity:
    """plugin-hooks/lib/state-dir.sh and paths.state_root must agree on every input."""

    @pytest.mark.parametrize("override", [None, "/abs/state", "~/state", "~", "relative/state", ""])
    def test_bash_and_python_resolve_the_same_root(self, tmp_path, monkeypatch, override):
        monkeypatch.setenv("HOME", str(tmp_path))  # Path.expanduser reads the process's HOME
        env = {"HOME": str(tmp_path), "PATH": os.environ["PATH"]}
        if override is not None:
            env["CLAUDNA_STATE_DIR"] = override
        bash = subprocess.run(["bash", "-c", f". {STATE_DIR_SH}; claudna_state_dir"], env=env,
                              capture_output=True, text=True, check=True).stdout
        try:
            python = str(paths.state_root(env))
        except ValueError:
            python = ""
        assert bash == python


class TestWiring:
    def test_the_store_is_wired_for_its_three_events_and_session_end_has_a_timeout(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]

        def store_hooks(event):
            return [h for entry in hooks.get(event, []) for h in entry["hooks"] if "session-store.sh" in h["command"]]

        for event in ("SessionStart", "PreCompact", "SessionEnd"):
            (h,) = store_hooks(event)
            assert h["command"].endswith(f"session-store.sh {event}")
            assert not h.get("async")  # a seal fixes a byte range: boundaries stay synchronous
        assert store_hooks("SessionEnd")[0]["timeout"] == 5
        wired = ("SessionStart", "PreCompact", "SessionEnd", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure")
        assert not any(store_hooks(e) for e in hooks if e not in wired)

    def test_activity_hooks_are_async_and_matched(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
        for event, matcher in (("UserPromptSubmit", None), ("PostToolUse", "Skill"), ("PostToolUseFailure", None)):
            (entry,) = [e for e in hooks[event] if any("session-store.sh" in h["command"] for h in e["hooks"])]
            (h,) = [h for h in entry["hooks"] if "session-store.sh" in h["command"]]
            assert entry.get("matcher") == matcher
            assert h["command"].endswith(f"session-store.sh {event}") and h["async"] is True  # no prompt waits on it

    @pytest.mark.parametrize("event", ["PostToolUse", "PostToolUseFailure"])  # a failed Skill call fires the latter
    def test_telemetry_has_its_own_async_hook_on_skill_calls(self, event):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"][event]
        (h,) = [h for e in hooks if e.get("matcher") == "Skill" for h in e["hooks"] if "telemetry-emit.sh" in h["command"]]
        assert h["async"] is True

    def test_the_store_sees_every_session_start_source(self):
        entries = json.loads(HOOKS_JSON.read_text())["hooks"]["SessionStart"]
        (entry,) = [e for e in entries if any("session-store.sh" in h["command"] for h in e["hooks"])]
        assert "matcher" not in entry  # startup, resume, clear, compact and fork all matter


class TestLogsAreCapped:
    def test_a_log_past_the_limit_is_rotated_to_old(self, tmp_path):
        from claudna.session_store.fsio import cap_log

        log = tmp_path / "errors.log"
        log.write_text("x" * 20)
        assert cap_log(log, limit=10) == log and not log.exists()
        assert (tmp_path / "errors.log.old").read_text() == "x" * 20
        cap_log(log, limit=10)  # a missing log is fine

    def test_a_worker_spawn_rotates_its_stderr_log(self, tmp_path, monkeypatch):
        import subprocess as sp

        from claudna.session_store import boundaries
        from claudna.session_store.fsio import LOG_LIMIT

        monkeypatch.setattr(sp, "Popen", lambda *a, **k: None)
        (tmp_path / "hooks").mkdir()
        (tmp_path / "hooks" / "summarizer.stderr").write_text("x" * (LOG_LIMIT + 1))
        boundaries.spawn_worker(tmp_path, ["summarize", SID, "1"], {}, log="summarizer.stderr")
        assert (tmp_path / "hooks" / "summarizer.stderr.old").stat().st_size == LOG_LIMIT + 1


# ── #373 review: M3 (nested children), M5 (spend), M2 (a closed end) ──────────


class TestNestedChildren:
    def env(self, entrypoint, pid):
        return {"CLAUDE_CODE_ENTRYPOINT": entrypoint, "CLAUDE_PID": str(pid), "CLAUDNA_HARVEST": "1"}

    @pytest.mark.parametrize("entrypoint", ["claude-vscode", "claude-desktop", "sdk-cli"])
    def test_a_nested_child_under_any_entrypoint_cannot_touch_its_parent(self, store, transcript, entrypoint):
        parent, child = self.env(entrypoint, 100), self.env(entrypoint, 200)  # same entrypoint, other process
        fire(store, "SessionStart", transcript, env=parent, source="startup")
        assert fire(store, "SessionStart", transcript, env=child, source="startup").startswith("ignored: nested")
        assert fire(store, "PreCompact", transcript, env=child, trigger="auto").startswith("ignored: nested")
        assert fire(store, "SessionEnd", transcript, env=child, reason="other").startswith("ignored: nested")
        assert session(store)["status"] == "open" and store.session(SID).paths.segment_indices() == [1]
        assert fire(store, "SessionEnd", transcript, env=parent, reason="other") == "session closed (other)"

    def test_a_fresh_start_never_reopens_an_open_session_even_without_pids(self, store, transcript):
        fire(store, "SessionStart", transcript, env={"CLAUDE_CODE_ENTRYPOINT": "claude-vscode"}, source="startup")
        out = fire(store, "SessionStart", transcript, env={"CLAUDE_CODE_ENTRYPOINT": "claude-vscode"},
                   source="startup")
        assert out.startswith("ignored: nested") and store.session(SID).paths.segment_indices() == [1]

    def test_a_resume_from_another_process_reopens_a_session_a_crash_left_open(self, store, transcript):
        fire(store, "SessionStart", transcript, env=self.env("cli", 100), source="startup")
        assert fire(store, "SessionStart", transcript, env=self.env("cli", 300), source="resume") == \
            "session opened (resume)"
        assert session(store)["status"] == "open" and store.session(SID).paths.segment_indices() == [1, 2]

    @pytest.mark.parametrize("source", ["startup", "clear", "fork"])
    def test_a_child_outliving_its_parent_cannot_reopen_it(self, store, transcript, source):
        parent, child = self.env("cli", 100), self.env("sdk-cli", 200)
        fire(store, "SessionStart", transcript, env=parent, source="startup")
        fire(store, "SessionEnd", transcript, env=parent, reason="other")
        assert fire(store, "SessionStart", transcript, env=child, source=source).startswith("ignored: nested")
        assert session(store)["status"] == "closed" and store.session(SID).paths.segment_indices() == [1]

    def test_a_child_outliving_its_parent_cannot_reseal_it(self, store, transcript):
        parent, child = self.env("cli", 100), self.env("cli", 200)
        fire(store, "SessionStart", transcript, env=parent, source="startup")
        fire(store, "SessionEnd", transcript, env=parent, reason="other")
        sealed = len(store.session(SID).paths.lifecycle.read_text().splitlines())
        assert fire(store, "PreCompact", transcript, env=child, trigger="auto").startswith("ignored: nested")
        assert fire(store, "SessionStart", transcript, env=child, source="compact").startswith("ignored: nested")
        assert len(store.session(SID).paths.lifecycle.read_text().splitlines()) == sealed

    def test_a_closed_sessions_precompact_never_reseals_even_without_pids(self, store, transcript):
        fire(store, "SessionStart", transcript, source="startup")
        fire(store, "SessionEnd", transcript, reason="other")
        assert fire(store, "PreCompact", transcript, trigger="auto") == "ignored: no open session"

    def test_a_compaction_never_opens_a_segment_in_a_closed_session(self, store, transcript):
        fire(store, "SessionStart", transcript, source="startup")
        fire(store, "SessionEnd", transcript, reason="other")
        assert fire(store, "SessionStart", transcript, source="compact") == "ignored: no open session"
        assert store.session(SID).paths.segment_indices() == [1]

    def test_a_compaction_of_a_session_the_store_never_opened_makes_no_directory(self, store, transcript):
        assert fire(store, "SessionStart", transcript, source="compact") == "ignored: no open session"
        assert not store.session(SID).exists()

    def test_a_resume_of_a_closed_session_from_another_process_reopens_it(self, store, transcript):
        fire(store, "SessionStart", transcript, env=self.env("cli", 100), source="startup")
        fire(store, "SessionEnd", transcript, env=self.env("cli", 100), reason="other")
        assert fire(store, "SessionStart", transcript, env=self.env("cli", 300), source="resume") == \
            "session opened (resume)"
        assert fire(store, "SessionEnd", transcript, env=self.env("cli", 300), reason="other") == \
            "session closed (other)"

    def test_the_owning_claude_pid_is_recorded(self, store, transcript):
        fire(store, "SessionStart", transcript, env=self.env("cli", 4242), source="startup")
        opened = json.loads(store.session(SID).paths.lifecycle.read_text().splitlines()[0])
        assert opened["data"]["claude_pid"] == 4242


class TestSpend:
    def test_a_blocked_compaction_is_summarized_once(self, store, transcript, spawned):
        """precompact-reflect.sh blocks the first attempt, so PreCompact fires twice; one summary."""
        fire(store, "SessionStart", transcript, source="startup")
        fire(store, "PreCompact", transcript, trigger="manual")  # blocked
        grow(transcript, 10)
        fire(store, "PreCompact", transcript, trigger="manual")  # allowed
        assert spawned == []  # nothing yet: the compaction hasn't happened
        fire(store, "SessionStart", transcript, source="compact")
        assert spawned == [(SID, 1)]

    @pytest.mark.parametrize("entrypoint", ["claude-code-github-action", "claude-in-slack", "sdk-ts"])
    def test_automation_entrypoints_are_headless(self, entrypoint):
        assert boundaries.actor_from_env({"CLAUDE_CODE_ENTRYPOINT": entrypoint})["kind"] == "headless"

    @pytest.mark.parametrize("entrypoint", ["cli", "claude-vscode", "claude-desktop"])
    def test_the_interactive_entrypoints(self, entrypoint):
        assert boundaries.actor_from_env({"CLAUDE_CODE_ENTRYPOINT": entrypoint})["kind"] == "interactive"

    def test_no_reader_no_summary(self, store, transcript, spawned):
        env = {"CLAUDE_CODE_ENTRYPOINT": "cli"}  # harvest not opted in, summaries not asked for
        fire(store, "SessionStart", transcript, env=env, source="startup")
        fire(store, "SessionEnd", transcript, env=env, reason="other")
        last = json.loads(store.session(SID).paths.lifecycle.read_text().splitlines()[-1])
        assert spawned == [] and (last["kind"], last["data"]["reason"]) == ("summary.skipped", "disabled")

    def test_a_failed_spawn_still_closes_the_session_and_is_recorded(self, store, transcript, monkeypatch):
        def broken(handle, index, env):
            raise OSError("fork failed")

        fire(store, "SessionStart", transcript, source="startup")
        payload = {"session_id": SID, "transcript_path": str(transcript), "reason": "other"}
        boundaries.handle("SessionEnd", payload, store=store, env=CLI_ENV, spawn=broken)
        kinds = [json.loads(line)["kind"] for line in store.session(SID).paths.lifecycle.read_text().splitlines()]
        assert kinds[-2:] == ["session.closed", "summary.failed"] and session(store)["status"] == "closed"


class TestPrivateVerb:
    def test_private_marks_and_clears(self, store, transcript):
        fire(store, "SessionStart", transcript, source="startup")
        cmd = [sys.executable, str(REPO_ROOT / "lib" / "claudna" / "session_store"), "private", SID,
               "--root", str(store.root)]
        assert subprocess.run(cmd, capture_output=True, text=True).returncode == 0
        assert session(store)["private"] is True
        subprocess.run([*cmd, "--off"], capture_output=True, text=True, check=True)
        assert session(store)["private"] is False
