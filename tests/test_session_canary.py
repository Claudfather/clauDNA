"""Tests for the session-store canary kit (``scripts/session_canary.py``), with no ``claude`` run.

The kit's verdicts are only worth pasting back if they're right, so each check
is driven with a synthetic hook log (and, for §11.3, a synthetic transcript)
in both its passing and failing shape. The live run is the steps ``setup``
prints, on a plain machine.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import session_canary as canary  # noqa: E402

PARENT = {"claude_pid_env": "100", "claude_pid_walked": 100}


def row(event, sid="A", **extra):
    return {"event": event, "session_id": sid, **PARENT, **extra}


# --- hook -----------------------------------------------------------------------------------------

def test_a_record_keeps_ids_and_sizes_but_never_the_prompt(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("x" * 42)
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "A", "transcript_path": str(transcript),
               "prompt": "my secret plan"}
    rec = canary.record(payload, {"CLAUDE_PID": "100", "CLAUDE_CODE_ENTRYPOINT": "cli"}, walked_pid=100, now=1.0)
    assert rec["transcript_size"] == 42 and rec["claude_pid_env"] == "100" and rec["entrypoint"] == "cli"
    assert "secret" not in json.dumps(rec) and "prompt" in rec["payload_keys"]


def test_a_failure_record_keeps_only_the_head_of_its_error():
    payload = {"hook_event_name": "PostToolUseFailure", "tool_name": "Skill", "error": "e" * 1000}
    rec = canary.record(payload, {}, walked_pid=None, now=1.0)
    assert rec["error_head"] == "e" * canary.ERROR_HEAD


def test_the_hook_never_fails_on_bad_input(tmp_path):
    log = tmp_path / "canary.jsonl"
    done = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "session_canary.py"), "hook", "--log",
                           str(log)], input="not json", text=True, capture_output=True)
    assert done.returncode == 0 and json.loads(log.read_text())["event"] == "canary-error"


def test_the_hook_appends_one_line_per_payload(tmp_path):
    log = tmp_path / "canary.jsonl"
    for event in ("SessionStart", "SessionEnd"):
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "session_canary.py"), "hook", "--log",
                        str(log)], input=json.dumps({"hook_event_name": event, "session_id": "A"}), text=True,
                       check=True)
    assert [r["event"] for r in canary.load(log)] == ["SessionStart", "SessionEnd"]


# --- setup ----------------------------------------------------------------------------------------

def test_setup_writes_a_plugin_whose_hooks_call_the_script(tmp_path):
    script = REPO_ROOT / "scripts" / "session_canary.py"
    log = canary.write_plugin(tmp_path, script)
    manifest = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
    hooks = json.loads((tmp_path / "hooks.json").read_text())["hooks"]
    assert manifest["hooks"] == "./hooks.json" and set(hooks) == set(canary.EVENTS)
    command = hooks["SessionStart"][0]["hooks"][0]["command"]
    assert str(script) in command and str(log) in command
    assert hooks["PostToolUseFailure"][0]["matcher"] == "*" and "matcher" not in hooks["SessionStart"][0]


# --- §11.3 ----------------------------------------------------------------------------------------

def _compact_log(tmp_path, before_boundary):
    head = json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n"
    tail = "".join(json.dumps(r) + "\n" for r in [*before_boundary, {"type": "system", "subtype": "compact_boundary"},
                                                   {"type": "user", "isCompactSummary": True}])
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(head + tail)
    return [row("PreCompact", transcript_path=str(transcript), transcript_size=len(head.encode())),
            row("SessionStart", source="compact")]


def test_compact_passes_when_only_bookkeeping_sits_before_the_boundary(tmp_path):
    rows = _compact_log(tmp_path, [{"type": "queue-operation"}, {"type": "last-prompt"}])
    [verdict] = canary.check_compact(rows)
    assert verdict.startswith("PASS") and "queue-operation, last-prompt" in verdict


def test_compact_fails_when_conversation_lands_before_the_boundary(tmp_path):
    rows = _compact_log(tmp_path, [{"type": "assistant", "message": {"role": "assistant"}}])
    assert canary.check_compact(rows)[0].startswith("FAIL")


def test_compact_fails_when_the_offset_splits_a_line(tmp_path):
    rows = _compact_log(tmp_path, [])
    rows[0]["transcript_size"] -= 3
    [verdict] = canary.check_compact(rows)
    assert verdict.startswith("FAIL") and "is NOT a line start" in verdict


def test_compact_is_unknown_without_a_compaction():
    assert canary.check_compact([row("SessionStart", source="startup")])[0].startswith("UNKNOWN")


# --- §11.4 ----------------------------------------------------------------------------------------

def test_clear_passes_when_one_claude_runs_both_sides():
    [verdict] = canary.check_clear([row("SessionEnd", reason="clear"), row("SessionStart", "B", source="clear")])
    assert verdict.startswith("PASS") and "new session id: True" in verdict


def test_clear_fails_when_the_pid_changes():
    after = {**row("SessionStart", "B", source="clear"), "claude_pid_env": "200", "claude_pid_walked": 200}
    assert canary.check_clear([row("SessionEnd", reason="clear"), after])[0].startswith("FAIL")


# --- §11.5 ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("child_sid,verdict", [("A", "INHERITS"), ("C", "FRESH")])
def test_nested_reports_whether_the_child_took_its_parents_id(child_sid, verdict):
    child = {"event": "SessionStart", "session_id": child_sid, "claude_pid_env": "300", "claude_pid_walked": 300,
             "entrypoint": "sdk-cli"}
    [result] = canary.check_nested([row("SessionStart", source="startup"), child])
    assert result.startswith(verdict) and "$CLAUDE_PID is 300" in result


def test_nested_flags_a_child_that_sees_its_parents_claude_pid():
    child = {"event": "SessionStart", "session_id": "C", "claude_pid_env": "100", "claude_pid_walked": 300}
    [result] = canary.check_nested([row("SessionStart", source="startup"), child])
    assert "can't tell them apart" in result


def test_nested_is_unknown_without_a_child():
    assert canary.check_nested([row("SessionStart", source="startup")])[0].startswith("UNKNOWN")


# --- Skill failure, and the whole report -----------------------------------------------------------

def test_skill_failure_shows_its_keys_and_error():
    hit = row("PostToolUseFailure", tool_name="Skill", payload_keys=["error", "tool_name"], error_head="Unknown skill")
    [result] = canary.check_skill_failure([hit])
    assert result.startswith("SEEN") and "Unknown skill" in result


def test_skill_failure_notes_a_failure_that_came_back_as_success():
    [result] = canary.check_skill_failure([row("PostToolUse", tool_name="Skill")])
    assert "came back as PostToolUse" in result


def test_skill_failure_says_when_no_skill_hook_fired_at_all():
    [result] = canary.check_skill_failure([row("SessionStart", source="startup")])
    assert result.startswith("NONE") and "rejected before the tool ran" in result


def test_report_has_a_section_per_canary_and_counts_hook_errors():
    text = canary.report([row("SessionStart", source="startup"), {"event": "canary-error", "error": "boom"}],
                         version="2.1.287 (Claude Code)", system="Darwin 25.0")
    for title in ("§11.3", "§11.4", "§11.5", "Skill failure"):
        assert title in text
    assert "1 hook error(s): boom" in text and "Darwin 25.0" in text


def test_report_without_a_log_says_to_run_setup_first(tmp_path, capsys):
    assert canary.main(["report", str(tmp_path)]) == 1
    assert "run the steps from `setup` first" in capsys.readouterr().err
