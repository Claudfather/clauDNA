"""Tests for the session-store canary kit (``scripts/session_canary.py``), with no ``claude`` run.

The kit's verdicts are only worth pasting back if they're right, so each check
is driven with a synthetic hook log (and, for §11.3, a synthetic transcript)
in both its passing and failing shape. §11.5's verdict comes from the store's
own child guard, so those cases also pin that the kit asks the guard and
doesn't re-derive it. The live run is the steps ``setup`` prints, on a plain
machine.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "session_canary.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import session_canary as canary  # noqa: E402

PARENT = {"claude_pid_env": 100, "claude_pid_walked": 100, "entrypoint": "cli"}


def row(event, sid="A", **extra):
    return {"event": event, "session_id": sid, **PARENT, **extra}


def child(event, sid="A", *, env_pid=300, entrypoint="sdk-cli", **extra):
    return {"event": event, "session_id": sid, "claude_pid_env": env_pid, "claude_pid_walked": 300,
            "entrypoint": entrypoint, **extra}


def hook(log, stdin):
    return subprocess.run([sys.executable, str(SCRIPT), "hook", "--log", str(log)], input=stdin, text=True,
                          capture_output=True)


# --- hook -----------------------------------------------------------------------------------------

def test_a_record_keeps_ids_and_sizes_but_never_the_prompt(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("x" * 42)
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "A", "transcript_path": str(transcript),
               "prompt": "my secret plan"}
    rec = canary.record(payload, {"CLAUDE_PID": "100", "CLAUDE_CODE_ENTRYPOINT": "cli"}, walked_pid=100, now=1.0)
    assert rec["transcript_size"] == 42 and rec["claude_pid_env"] == 100 and rec["entrypoint"] == "cli"
    assert "secret" not in json.dumps(rec)


def test_a_record_reads_claude_pid_as_the_store_does():
    assert canary.record({}, {"CLAUDE_PID": "0"}, walked_pid=None, now=1.0)["claude_pid_env"] is None


def test_the_hook_never_fails_on_bad_input(tmp_path):
    log = tmp_path / "canary.jsonl"
    assert hook(log, "not json").returncode == 0
    assert json.loads(log.read_text())["event"] == "canary-error"


def test_the_hook_appends_one_private_line_per_payload(tmp_path):
    log = tmp_path / "canary.jsonl"
    for event in ("SessionStart", "SessionEnd"):
        assert hook(log, json.dumps({"hook_event_name": event, "session_id": "A"})).returncode == 0
    assert [json.loads(line)["event"] for line in log.read_text().splitlines()] == ["SessionStart", "SessionEnd"]
    assert log.stat().st_mode & 0o077 == 0


# --- setup ----------------------------------------------------------------------------------------

def test_setup_writes_a_plugin_whose_hooks_call_the_script(tmp_path):
    log = canary.write_plugin(tmp_path, SCRIPT)
    manifest = json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text())
    hooks = json.loads((tmp_path / "hooks.json").read_text())["hooks"]
    assert manifest["hooks"] == "./hooks.json" and set(hooks) == set(canary.EVENTS)
    command = hooks["SessionStart"][0]["hooks"][0]["command"]
    assert str(SCRIPT) in command and str(log) in command
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

def test_clear_passes_when_claude_pid_is_the_same_on_both_sides():
    [verdict] = canary.check_clear([row("SessionEnd", reason="clear"), row("SessionStart", "B", source="clear")])
    assert verdict.startswith("PASS") and "walked 100 -> 100" in verdict and "new session id: True" in verdict


def test_clear_fails_when_claude_pid_changes():
    after = {**row("SessionStart", "B", source="clear"), "claude_pid_env": 200}
    assert canary.check_clear([row("SessionEnd", reason="clear"), after])[0].startswith("FAIL")


def test_clear_says_when_the_walk_had_nothing_to_corroborate():
    end, start = row("SessionEnd", reason="clear"), row("SessionStart", "B", source="clear")
    end["claude_pid_walked"] = start["claude_pid_walked"] = None
    [verdict] = canary.check_clear([end, start])
    assert verdict.startswith("PASS") and "walk unavailable" in verdict


# --- §11.5 ----------------------------------------------------------------------------------------

def test_a_child_with_a_new_id_is_fresh():
    [result] = canary.check_nested([row("SessionStart", source="startup"), child("SessionStart", "C",
                                                                                 source="startup")])
    assert result.startswith("FRESH")


def test_an_inheriting_child_the_guard_catches_is_reported_as_held():
    rows = [row("SessionStart", source="startup"), child("SessionStart", source="startup"),
            child("UserPromptSubmit"), child("SessionEnd", reason="other")]
    [result] = canary.check_nested(rows)
    assert result.startswith("INHERITS") and "ignores 3 of its 3" in result


def test_a_child_indistinguishable_from_its_parent_leaks_its_activity():
    # Same $CLAUDE_PID and entrypoint as the parent: only its SessionStart(startup) gives it away.
    rows = [row("SessionStart", source="startup"),
            *(child(e, env_pid=100, entrypoint="cli", **x) for e, x in
              (("SessionStart", {"source": "startup"}), ("UserPromptSubmit", {})))]
    [result] = canary.check_nested(rows)
    assert result.startswith("LEAKS") and "would record UserPromptSubmit" in result


def test_nested_is_unknown_without_a_child():
    assert canary.check_nested([row("SessionStart", source="startup")])[0].startswith("UNKNOWN")


@pytest.mark.parametrize("sid", ["A", "B"])
def test_a_child_counts_as_inheriting_any_id_the_parent_used(sid):
    rows = [row("SessionStart", source="startup"), row("SessionEnd", reason="clear"),
            row("SessionStart", "B", source="clear"), child("SessionStart", sid, source="startup")]
    assert canary.check_nested(rows)[0].startswith("INHERITS")


# --- the whole report -----------------------------------------------------------------------------

def test_report_has_a_section_per_canary_and_counts_hook_errors():
    text = canary.report([row("SessionStart", source="startup"), {"event": "canary-error", "error": "boom"}],
                         version="2.1.287 (Claude Code)", system="Darwin 25.0", skipped=2)
    for title in ("§11.3", "§11.4", "§11.5"):
        assert title in text
    assert "1 hook error(s): boom" in text and "Darwin 25.0" in text and "2 unreadable line(s)" in text


def test_report_without_a_log_says_to_run_setup_first(tmp_path, capsys):
    assert canary.main(["report", str(tmp_path)]) == 1
    assert "run the steps from `setup` first" in capsys.readouterr().err
