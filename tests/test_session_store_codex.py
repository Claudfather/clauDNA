"""Measured Codex envelope/rollout regressions; no model or real user state."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from claudna.session_store import boundaries, harvest, lineage, transcript  # noqa: E402
from claudna.session_store.cli import run_hook  # noqa: E402
from claudna.session_store.project import load_lifecycle, session_facts  # noqa: E402
from claudna.session_store.store import SessionStore  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/codex"
SID = "00000000-0000-4000-8000-000000000001"


def captured(prefix):
    return json.loads(next(FIXTURES.glob(prefix + "-*.json")).read_text())


def test_procedure_entry_is_local_metadata_not_execution_or_outcome(isolated):
    from claudna.session_store.host_codex import record_skill_start
    from claudna.session_store.fsio import read_jsonl

    store, path = isolated
    env = {"CODEX_THREAD_ID": SID, "CLAUDNA_STATE_DIR": str(store.root)}
    assert "unavailable" in record_skill_start("audit", env)
    assert not store.root.exists()
    boundaries.handle("SessionStart", {"session_id": SID, "source": "startup", "transcript_path": str(path)},
                      store=store, env=env, host=boundaries.HOSTS["codex"])
    assert record_skill_start("claudna:audit", env).startswith("recorded:")
    (event,) = read_jsonl(store.session(SID).paths.segment(1).events).records
    assert event["kind"] == "skill.invoked"
    data = event["data"]
    assert data["observation"] == "agent_procedure_start"
    assert data["skill"] == "claudna:audit"
    assert data["ok"] is data["duration_ms"] is data["args_chars"] is data["tool_use_id"] is None
    assert set(data) == {"skill", "args_chars", "ok", "duration_ms", "tool_use_id", "prompt_id",
                         "observation", "plugin_version", "invocation_id"}
    assert path.read_bytes() == b""


@pytest.mark.parametrize("extra", [
    {"CLAUDNA_SESSION_STORE": "0"}, {"CLAUDNA_SKILL_LOG": "0"}, {"CLAUDNA_SESSION_CHILD": "1"},
    {"CODEX_SESSION_ID": "different"},
])
def test_procedure_entry_respects_explicit_choices_without_creating_state(tmp_path, extra):
    from claudna.session_store.host_codex import record_skill_start

    root = tmp_path / "absent"
    env = {"CODEX_THREAD_ID": SID, "CLAUDNA_STATE_DIR": str(root), **extra}
    assert record_skill_start("audit", env).startswith("ignored:")
    assert not root.exists()


def test_procedure_entry_skips_busy_private_closed_and_wrong_host(isolated):
    from claudna.session_store.host_codex import record_skill_start
    from claudna.session_store.fsio import exclusive_lock

    store, path = isolated
    env = {"CODEX_THREAD_ID": SID, "CLAUDNA_STATE_DIR": str(store.root)}
    payload = {"session_id": SID, "source": "startup", "transcript_path": str(path)}
    boundaries.handle("SessionStart", payload, store=store, env=env, host=boundaries.HOSTS["codex"])
    handle = store.session(SID)
    with exclusive_lock(handle.paths.lock):
        assert record_skill_start("audit", env) == "ignored: session busy"
    handle.set_private(True)
    assert "private" in record_skill_start("audit", env)
    handle.set_private(False)
    handle.end_session(0, "other")
    assert "closed" in record_skill_start("audit", env)
    assert "not selected" in record_skill_start("../../../bad", env)
    assert "identity" in record_skill_start("audit", {"CLAUDNA_STATE_DIR": str(store.root)})
    other = {**payload, "session_id": "claude-session"}
    boundaries.handle("SessionStart", other, store=store, env=env)
    assert "not codex" in record_skill_start("audit", {**env, "CODEX_THREAD_ID": "claude-session"})


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(harvest, "is_due", lambda root, env: False)
    monkeypatch.setattr(boundaries, "spawn_sweep", lambda root, env: None)
    monkeypatch.setattr(lineage, "_parent", lambda pid: (1, "codex"))
    path = tmp_path / "rollout.jsonl"
    path.write_bytes(b"")
    return SessionStore(tmp_path / "state"), path


def test_fixtures_match_actual_native_export_hashes():
    manifest = json.loads((FIXTURES / "MANIFEST.json").read_text())
    for name, digest in manifest["native_hook_fixtures"].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest
    assert hashlib.sha256((FIXTURES / manifest["golden_rollout"]).read_bytes()).hexdigest() == manifest["golden_rollout_sha256"]


@pytest.mark.parametrize("host", ["claude", "codex"])
def test_shared_lifecycle_recorded_runtime_owner_and_compact(isolated, host):
    store, path = isolated
    env = {"CLAUDE_PID": "4242", "CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDNA_SESSION_SUMMARY": "0"}
    def fire(event, **extra):
        return run_hook(event, json.dumps({"session_id": SID, "cwd": str(path.parent),
                        "transcript_path": str(path), **extra}),
                        {**env, "CLAUDNA_STATE_DIR": str(store.root)}, host=host)
    assert fire("SessionStart", source="startup") == "session opened (startup)"
    first = session_facts(load_lifecycle(store.session(SID).paths).events)
    assert first.agent_cli == host
    assert first.claude_pid and first.claude_pid > 0
    assert first.actor["entrypoint"] == ("codex" if host == "codex" else "cli")
    path.write_bytes(b"one\n")
    assert fire("PreCompact", trigger="manual") == "segment sealed"
    path.write_bytes(b"one\ntwo\n")
    assert fire("SessionStart", source="compact") == "segment opened (compact)"
    assert store.session(SID).boundary(2).start == 4
    assert fire("SessionEnd", reason="other") == "session closed (other)"
    assert fire("SessionStart", source="resume") == "session opened (resume)"
    assert session_facts(load_lifecycle(store.session(SID).paths).events).agent_cli == host


def test_captured_native_envelopes_drive_codex_store(isolated):
    store, path = isolated
    env = {"CLAUDNA_STATE_DIR": str(store.root), "CLAUDNA_SESSION_SUMMARY": "0"}
    for prefix, expected in [("sessionstart-startup", "session opened"),
                             ("userpromptsubmit-default", "recorded prompt.submitted"),
                             ("posttooluse-bash", "ignored: nothing"),
                             ("precompact-manual", "segment sealed"),
                             ("sessionstart-compact", "segment opened"),
                             ("sessionend-other", "session closed")]:
        payload = {**captured(prefix), "transcript_path": str(path), "cwd": str(path.parent)}
        assert run_hook(payload["hook_event_name"], json.dumps(payload), env, host="codex").startswith(expected)
    assert session_facts(load_lifecycle(store.session(SID).paths).events).status == "closed"
    prompt_events = [json.loads(line) for line in store.session(SID).paths.segment(1).events.read_text().splitlines()]
    assert prompt_events[0]["kind"] == "prompt.submitted" and prompt_events[0]["data"]["text"]


def test_codex_owner_is_own_ancestor_not_inherited_claude_pid(isolated, monkeypatch):
    from claudna.session_store.host_codex import owner_pid
    seen = []
    def parent(pid):
        seen.append(pid)
        return {9: (8, "sh"), 8: (7, "codex"), 7: (1, "launchd")}.get(pid)
    monkeypatch.setattr(os, "getppid", lambda: 9)
    monkeypatch.setattr(lineage, "_parent", parent)
    assert owner_pid({"CLAUDE_PID": "999"}) == 8
    assert seen == [9, 8]


def test_codex_pid_guard_blocks_foreign_child_but_allows_resume(isolated, monkeypatch):
    store, path = isolated
    env = {"CLAUDNA_STATE_DIR": str(store.root), "CLAUDNA_SESSION_SUMMARY": "0"}
    payload = {"session_id": SID, "cwd": str(path.parent), "transcript_path": str(path), "source": "startup"}
    assert run_hook("SessionStart", json.dumps(payload), env, host="codex").startswith("session opened")
    monkeypatch.setattr(lineage, "_parent", lambda pid: (1, "sh"))
    # A positively different owner, not absence of process observation, is the guard.
    from claudna.session_store import host_codex
    monkeypatch.setattr(host_codex, "owner_pid", lambda env: 999)
    # Host callables are bound: substitute its immutable value for this controlled arm.
    from dataclasses import replace
    monkeypatch.setitem(boundaries.HOSTS, "codex", replace(host_codex.HOST, owner_pid=host_codex.owner_pid))
    assert run_hook("SessionEnd", json.dumps(payload), env, host="codex").startswith("ignored: nested child")
    assert run_hook("SessionStart", json.dumps({**payload, "source": "resume"}), env, host="codex").startswith("session opened")


def test_unknown_host_logs_and_fails_open(tmp_path):
    env = {"CLAUDNA_STATE_DIR": str(tmp_path)}
    assert run_hook("SessionStart", "{}", env, host="unknown") == "ignored: unknown host 'unknown'"
    assert len((tmp_path / "hooks/errors.log").read_text().splitlines()) == 1


def test_codex_golden_reader_uses_response_messages_once():
    turns = transcript.read_range(FIXTURES / "codex-rollout-golden.jsonl", 0, None, agent_cli="codex")
    assert [(t.role, t.text) for t in turns] == [("user", "<redacted-text>"), ("assistant", "<redacted-text>")]


def test_codex_reader_drops_tools_reasoning_context_and_partial_ranges(tmp_path):
    records = [
        {"type": "event_msg", "payload": {"type": "user_message", "message": "duplicate"}},
        {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "system context"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "question"}], "internal_chat_message_metadata_passthrough": {"content_item_kinds": ["user.text"]}}},
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "output": "secret tool output"}},
        {"type": "response_item", "payload": {"type": "reasoning", "content": [{"type": "output_text", "text": "private thinking"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "commentary", "content": [{"type": "output_text", "text": "answer"}]}},
    ]
    path = tmp_path / "rollout.jsonl"
    lines = [json.dumps(r).encode() + b"\n" for r in records]
    path.write_bytes(b"".join(lines))
    assert [t.text for t in transcript.read_range(path, 0, None, agent_cli="codex")] == ["question", "answer"]
    assert transcript.read_range(path, len(b"".join(lines[:2])) + 1, len(b"".join(lines)) - 1, agent_cli="codex") == []


def test_wrapper_explicit_codex_host_is_silent_and_records_runtime(tmp_path):
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "CLAUDNA_STATE_DIR": str(tmp_path / "state"),
           "CLAUDNA_SESSION_SUMMARY": "0", "CLAUDNA_HARVEST": "0"}
    result = subprocess.run(["bash", str(ROOT / "plugin-hooks/session-store.sh"), "--host", "codex", "SessionStart"],
                            input=json.dumps({**captured("sessionstart-startup"), "cwd": str(tmp_path)}),
                            capture_output=True, text=True, env=env, timeout=10)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    facts = session_facts(load_lifecycle(SessionStore(tmp_path / "state").session(SID).paths).events)
    assert facts.agent_cli == "codex"


@pytest.mark.parametrize("metadata", [
    {"content_item_kinds": ["environments.environment_context"]},
    {"content_item_kinds": ["unknown"]}, {},
    {"content_item_kinds": []}, {"content_item_kinds": ["user.text", "user.text"]},
])
def test_codex_user_context_or_unclassified_items_never_become_dialogue(metadata):
    record = {"type": "response_item", "payload": {"type": "message", "role": "user",
              "content": [{"type": "input_text", "text": "private injected context"}],
              "internal_chat_message_metadata_passthrough": metadata}}
    assert transcript.codex_turn_of(record) is None


@pytest.mark.parametrize("phase", ["analysis", "unknown", None])
def test_codex_unmeasured_assistant_phases_never_become_dialogue(phase):
    record = {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": phase,
              "content": [{"type": "output_text", "text": "not conversation prose"}]}}
    assert transcript.codex_turn_of(record) is None


def test_codex_mixed_content_keeps_only_aligned_user_text():
    record = {"type": "response_item", "payload": {"type": "message", "role": "user",
              "content": [{"type": "input_text", "text": "injected"}, {"type": "input_text", "text": "question"}],
              "internal_chat_message_metadata_passthrough": {
                  "content_item_kinds": ["environments.environment_context", "user.text"]}}}
    assert transcript.codex_turn_of(record).text == "question"


def test_codex_host_reader_uses_the_same_classified_golden_prose():
    from claudna.session_store.host_codex import HOST
    turns = HOST.read_range(FIXTURES / "codex-rollout-golden.jsonl", 0, None)
    assert [(t.role, t.text) for t in turns] == [("user", "<redacted-text>"), ("assistant", "<redacted-text>")]
