"""Tests for activity (lib/claudna/session_store/activity.py, telemetry.py, and their use
in boundaries.py and cli.py) — session store phase 4.

What these guard:

* **One event per hook, mapped from the canaried payloads.** ``prompt.submitted``
  carries ``chars`` and no text unless ``CLAUDNA_CAPTURE_PROMPTS=1``;
  ``skill.invoked`` carries the real ``ok`` and ``duration_ms``; a failure is
  ``tool.failed`` with an exit code and a normalized, redacted signature, and
  an interrupt is ``tool.interrupted``, never a failure.
* **Pointers, not copies.** No tool event stores the command or its stderr.
* **Async-safe.** An activity hook with no open session (it raced SessionEnd)
  records nothing and logs nothing; a nested child's is ignored.
* **Telemetry** keeps Claudosseum's line shape, with real values, independent of
  the store, and is pruned by the sweep.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from conftest import CLI_ENV, fire

from claudna.session_store import activity, telemetry
from claudna.session_store.fsio import read_jsonl

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "plugin-hooks" / "session-store.sh"
TELEMETRY_HOOK = REPO_ROOT / "plugin-hooks" / "telemetry-emit.sh"
FAKE_TOKEN = "ghp" + "_" + "aB3" * 12  # assembled: never a contiguous literal
BASH_FAILURE = {"tool_name": "Bash", "tool_input": {"command": "ls /nope"}, "tool_use_id": "toolu_1",
                "prompt_id": "p1", "duration_ms": 414, "is_interrupt": False,
                "error": "Exit code 2\nls: cannot access '/nonexistent-canary-dir-xyz': No such file or directory"}
SKILL_CALL = {"tool_name": "Skill", "tool_input": {"skill": "claudna:recall", "args": "abc"},
              "tool_response": {"success": True, "commandName": "claudna:recall"}, "tool_use_id": "toolu_2",
              "prompt_id": "p1", "duration_ms": 12}


def events(store, sid, seg=1) -> list[dict]:
    return read_jsonl(store.session(sid).paths.segment(seg).events).records


def counts(store, sid, seg=1) -> dict:
    return json.loads(store.session(sid).paths.segment(seg).segment_json.read_text())["counts"]


class TestEventFor:
    def test_a_prompt_is_counted_not_copied(self):
        kind, data = activity.event_for("UserPromptSubmit", {"prompt": "fix the bug", "prompt_id": "p1"}, {})
        assert (kind, data) == ("prompt.submitted", {"prompt_id": "p1", "chars": 11})

    def test_prompt_text_only_with_the_opt_in(self):
        _, data = activity.event_for("UserPromptSubmit", {"prompt": "hi"}, {activity.CAPTURE_PROMPTS_ENV: "1"})
        assert data["text"] == "hi" and data["prompt_id"] is None

    def test_a_skill_call_carries_its_real_outcome(self):
        kind, data = activity.event_for("PostToolUse", SKILL_CALL, {})
        assert kind == "skill.invoked"
        assert data == {"skill": "claudna:recall", "args_chars": 3, "ok": True, "duration_ms": 12,
                        "prompt_id": "p1", "tool_use_id": "toolu_2"}

    @pytest.mark.parametrize("payload", [{"tool_name": "Bash", "tool_input": {"command": "ls"}},
                                         {"tool_name": "Skill", "tool_input": {}}, {"tool_input": {"skill": "x"}}])
    def test_other_tools_and_malformed_skill_calls_record_nothing(self, payload):
        assert activity.event_for("PostToolUse", payload, {}) is None

    def test_a_failure_points_into_the_transcript_and_copies_nothing(self):
        kind, data = activity.event_for("PostToolUseFailure", BASH_FAILURE, {})
        assert kind == "tool.failed"
        assert data == {"tool": "Bash", "signature": "Bash: ls: cannot access <str>: No such file or directory",
                        "exit_code": 2, "duration_ms": 414, "prompt_id": "p1", "tool_use_id": "toolu_1"}
        assert "command" not in data and "error" not in data

    def test_an_interrupt_is_not_a_failure(self):
        kind, data = activity.event_for("PostToolUseFailure", {**BASH_FAILURE, "is_interrupt": True}, {})
        assert kind == "tool.interrupted" and "signature" not in data and data["tool"] == "Bash"

    def test_bad_types_are_dropped_not_recorded(self):
        _, data = activity.event_for("PostToolUse", {**SKILL_CALL, "duration_ms": -1, "prompt_id": 7,
                                                     "tool_response": {"success": "yes"}}, {})
        assert (data["duration_ms"], data["prompt_id"], data["ok"]) == (None, None, None)


class TestSignature:
    @pytest.mark.parametrize("error, expected", [
        ("Exit code 1\nFAILED tests/test_x.py::test_y - AssertionError: 3 != 4",
         "Bash: FAILED <path>::test_y - AssertionError: <n> != <n>"),
        ("fatal: repository 'https://github.com/o/r/' not found",
         "Bash: fatal: repository <str> not found"),
        ("error: 2f1e8c0a-1111-4222-8333-444455556666 at 0xdeadbeefcafe1234", "Bash: error: <id> at <id>"),
        ("curl: (22) The requested URL returned error: 404 https://api.example.com/v1/x",
         "Bash: curl: (<n>) The requested URL returned error: <n> <url>"),
        ("", "Bash"),
        ("Exit code 127", "Bash"),
    ])
    def test_normalization_groups_the_same_failure(self, error, expected):
        assert activity.signature("Bash", error) == expected

    def test_the_same_failure_in_two_places_has_one_signature(self):
        a = activity.signature("Bash", "Exit code 2\nls: cannot access '/a/b': No such file or directory")
        b = activity.signature("Bash", "Exit code 2\nls: cannot access '/c/d/e': No such file or directory")
        assert a == b

    def test_a_contraction_does_not_pair_with_a_quote(self):
        a = activity.signature("Bash", "Exit code 1\nerror: can't open 'a.txt'")
        b = activity.signature("Bash", "Exit code 1\nerror: can't open 'b.txt'")
        assert a == b == "Bash: error: can't open <str>"

    def test_a_secret_in_the_error_line_is_redacted(self):
        sig = activity.signature("Bash", f"curl: auth failed with token {FAKE_TOKEN}")
        assert "aB3aB3" not in sig and "[REDACTED]" in sig

    def test_exit_codes(self):
        assert activity.exit_code("Exit code 2\nboom") == 2
        assert activity.exit_code("Exit code -1") == -1
        assert activity.exit_code("boom") is None


@pytest.mark.usefixtures("quiet_hooks")
class TestAdapter:
    def open(self, store, tmp_path, sid="s1", env=CLI_ENV):
        fire(store, "SessionStart", sid, tmp_path, env=env, source="startup")

    def test_each_hook_lands_in_the_current_segment_and_is_counted(self, store, tmp_path):
        self.open(store, tmp_path)
        assert fire(store, "UserPromptSubmit", "s1", tmp_path, prompt="go", prompt_id="p1") == \
            "recorded prompt.submitted"
        fire(store, "PostToolUse", "s1", tmp_path, **SKILL_CALL)
        fire(store, "PostToolUseFailure", "s1", tmp_path, **BASH_FAILURE)
        fire(store, "PostToolUseFailure", "s1", tmp_path, **{**BASH_FAILURE, "is_interrupt": True})
        assert [e["kind"] for e in events(store, "s1")] == \
            ["prompt.submitted", "skill.invoked", "tool.failed", "tool.interrupted"]
        assert counts(store, "s1") == {"prompts": 1, "skills": 1, "failures": 1, "interrupts": 1, "checkpoints": 0}

    def test_the_counts_survive_a_rebuild(self, store, tmp_path):
        self.open(store, tmp_path)
        fire(store, "PostToolUseFailure", "s1", tmp_path, **BASH_FAILURE)
        before = counts(store, "s1")
        store.session("s1").rebuild()
        assert counts(store, "s1") == before

    def test_prompt_text_is_redacted_when_captured(self, store, tmp_path):
        self.open(store, tmp_path)
        fire(store, "UserPromptSubmit", "s1", tmp_path, env={**CLI_ENV, activity.CAPTURE_PROMPTS_ENV: "1"},
             prompt=f"use {FAKE_TOKEN}", prompt_id="p1")
        (e,) = events(store, "s1")
        assert "aB3aB3" not in e["data"]["text"] and "[REDACTED]" in e["data"]["text"]

    def test_activity_after_session_end_records_nothing_and_logs_nothing(self, store, tmp_path):
        self.open(store, tmp_path)
        fire(store, "SessionEnd", "s1", tmp_path, reason="other")
        assert fire(store, "UserPromptSubmit", "s1", tmp_path, prompt="late") == "ignored: no open session"
        assert events(store, "s1") == [] and not (store.root / "hooks" / "errors.log").exists()

    def test_activity_for_an_unknown_session_records_nothing(self, store, tmp_path):
        assert fire(store, "UserPromptSubmit", "never-opened", tmp_path, prompt="x") == "ignored: no open session"

    def test_a_nested_childs_activity_is_ignored(self, store, tmp_path):
        self.open(store, tmp_path, env={**CLI_ENV, "CLAUDE_PID": "100"})
        out = fire(store, "PostToolUseFailure", "s1", tmp_path, env={**CLI_ENV, "CLAUDE_PID": "200"}, **BASH_FAILURE)
        assert out.startswith("ignored: nested") and events(store, "s1") == []

    def test_a_022_projection_without_interrupts_still_counts(self, store, tmp_path):
        self.open(store, tmp_path)
        fire(store, "UserPromptSubmit", "s1", tmp_path, prompt="a")
        path = store.session("s1").paths.segment(1).segment_json
        doc = json.loads(path.read_text())
        del doc["counts"]["interrupts"]  # what 0.22 wrote
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        fire(store, "PostToolUseFailure", "s1", tmp_path, **{**BASH_FAILURE, "is_interrupt": True})
        assert counts(store, "s1")["interrupts"] == 1


class TestTelemetry:
    def env(self, tmp_path, **extra):
        return {"CLAUDNA_TELEMETRY": "1", "CLAUDNA_TELEMETRY_PATH": str(tmp_path / "t.jsonl"), **extra}

    def lines(self, tmp_path):
        return read_jsonl(tmp_path / "t.jsonl").records

    def test_the_line_keeps_claudosseums_shape_with_real_values(self, tmp_path):
        assert telemetry.emit({**SKILL_CALL, "session_id": "sess-9"}, self.env(tmp_path, BOT_NAME="scout"))
        (rec,) = self.lines(tmp_path)
        assert set(rec) == {"ts", "bot", "type", "source", "data"}
        assert (rec["bot"], rec["type"], rec["source"]) == ("scout", "skill_invocation", "vitals")
        assert rec["data"] == {"skill_slug": "recall", "duration_ms": 12, "success": True, "session_id": "sess-9"}
        assert time.strptime(rec["ts"], "%Y-%m-%dT%H:%M:%SZ")

    def test_only_claudna_skills_only_when_enabled(self, tmp_path):
        other = {**SKILL_CALL, "tool_input": {"skill": "canary:hello"}}
        assert not telemetry.emit(other, self.env(tmp_path))
        assert not telemetry.emit(SKILL_CALL, {"CLAUDNA_TELEMETRY_PATH": str(tmp_path / "t.jsonl")})
        assert self.lines(tmp_path) == []

    def test_the_bot_defaults_to_interactive(self, tmp_path):
        telemetry.emit(SKILL_CALL, self.env(tmp_path))
        assert self.lines(tmp_path)[0]["bot"] == "interactive"

    def test_prune_drops_old_lines_and_keeps_new_and_unparseable_ones(self, tmp_path):
        path = tmp_path / "t.jsonl"
        path.write_text('{"ts":"2000-01-01T00:00:00Z"}\nnot json\n{"ts":"2999-01-01T00:00:00Z"}\n')
        assert telemetry.prune(self.env(tmp_path)) == 1
        assert path.read_text() == 'not json\n{"ts":"2999-01-01T00:00:00Z"}\n'
        assert not path.with_name("t.jsonl.pruning").exists()

    def test_prune_with_nothing_due_rewrites_nothing(self, tmp_path):
        path = tmp_path / "t.jsonl"
        path.write_text('{"ts":"2999-01-01T00:00:00Z"}\n')
        inode = path.stat().st_ino
        assert telemetry.prune(self.env(tmp_path)) == 0
        assert path.stat().st_ino == inode

    def test_a_killed_prunes_lines_are_put_back_not_overwritten(self, tmp_path):
        path = tmp_path / "t.jsonl"
        path.with_name("t.jsonl.pruning").write_text('{"ts":"2998-01-01T00:00:00Z"}\n{"ts":"2000-01-01T00:00:00Z"}\n')
        path.write_text('{"ts":"2999-01-01T00:00:00Z"}\n')
        assert telemetry.prune(self.env(tmp_path)) == 1
        assert sorted(path.read_text().splitlines()) == ['{"ts":"2998-01-01T00:00:00Z"}', '{"ts":"2999-01-01T00:00:00Z"}']
        assert not path.with_name("t.jsonl.pruning").exists()

    def test_a_failure_is_captured_not_swallowed(self, tmp_path):
        env = {**self.env(tmp_path), "PATH": os.environ["PATH"], "HOME": str(tmp_path)}
        proc = subprocess.run(["bash", str(TELEMETRY_HOOK)], input="{not json", capture_output=True,
                              text=True, env=env, cwd=tmp_path, timeout=20)
        assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")
        assert "JSONDecodeError" in (tmp_path / "t.jsonl.stderr").read_text()

    def test_the_hook_prunes_at_most_daily_even_with_the_store_off(self, tmp_path):
        path = tmp_path / "t.jsonl"
        path.write_text('{"ts":"2000-01-01T00:00:00Z"}\n')
        env = self.env(tmp_path, CLAUDNA_SESSION_STORE="0")
        assert telemetry.run_hook(json.dumps(SKILL_CALL), env) == "emitted"
        (rec,) = self.lines(tmp_path)  # the old line is gone, the new one kept
        assert rec["data"]["skill_slug"] == "recall"
        path.write_text(path.read_text() + '{"ts":"2000-01-02T00:00:00Z"}\n')
        telemetry.run_hook(json.dumps(SKILL_CALL), env)  # within the day: no second prune
        assert len(self.lines(tmp_path)) == 3

    def test_a_failed_skill_call_reports_success_false_and_an_interrupt_nothing(self, tmp_path):
        failed = {**SKILL_CALL, "hook_event_name": "PostToolUseFailure", "error": "boom"}
        failed.pop("tool_response")
        assert telemetry.record_for(failed, {})["data"]["success"] is False
        assert telemetry.record_for({**failed, "is_interrupt": True}, {}) is None

    def test_its_own_hook_writes_it_even_with_the_store_off(self, tmp_path):
        env = {**self.env(tmp_path, CLAUDNA_SESSION_STORE="0"), "PATH": os.environ["PATH"], "HOME": str(tmp_path)}
        proc = subprocess.run(["bash", str(TELEMETRY_HOOK)], input=json.dumps(SKILL_CALL), capture_output=True,
                              text=True, env=env, cwd=tmp_path, timeout=20)
        assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")
        assert len(self.lines(tmp_path)) == 1 and not (tmp_path / ".claudna").exists()

    def test_the_line_is_private(self, tmp_path):
        telemetry.emit(SKILL_CALL, self.env(tmp_path))
        assert (tmp_path / "t.jsonl").stat().st_mode & 0o077 == 0

    def test_a_bad_payload_never_raises(self, tmp_path):
        assert telemetry.run_hook(b"\xff{not json", self.env(tmp_path)).startswith("error:")
        assert telemetry.run_hook(b"", self.env(tmp_path)) == "ignored"

    def test_telemetry_and_skill_invoked_agree(self, tmp_path):
        payload = {**SKILL_CALL, "duration_ms": -5, "tool_response": {"success": False}}
        _, data = activity.event_for("PostToolUse", payload, {})
        rec = telemetry.record_for(payload, {})
        assert (rec["data"]["duration_ms"], rec["data"]["success"]) == (data["duration_ms"], data["ok"]) == (None, False)


class TestWrapper:
    def test_an_async_activity_hook_through_the_real_wrapper(self, tmp_path):
        home = tmp_path / "home"
        transcript = tmp_path / "t.jsonl"
        transcript.touch()
        env = {"HOME": str(home), "PATH": os.environ["PATH"], **CLI_ENV}
        base = {"session_id": "s-w", "transcript_path": str(transcript), "cwd": str(tmp_path)}
        for event, payload in (("SessionStart", {"source": "startup"}), ("UserPromptSubmit", {"prompt": "hi"})):
            proc = subprocess.run(["bash", str(WRAPPER), event], input=json.dumps({**base, **payload}),
                                  capture_output=True, text=True, env=env, cwd=tmp_path, timeout=20)
            assert (proc.returncode, proc.stdout) == (0, "")
        log = home / ".claudna" / "sessions" / "s-w" / "seg-001" / "events.jsonl"
        assert json.loads(log.read_text())["kind"] == "prompt.submitted"
