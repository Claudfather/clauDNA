"""Tests for the segment summarizer (lib/claudna/session_store/summarize.py) and the
transcript reader it feeds on (transcript.py) — spec §6.6 and §7.1.

What these guard:

* **What the model sees.** Only user and assistant prose inside the segment's
  byte range: no tool I/O, thinking, sidechains, injected context, or lines the
  range cuts.
* **The gates.** Private, disabled, headless and bot sessions, a missing
  transcript, and a slice with no user turn are recorded as ``summary.skipped``
  and never reach the model.
* **The write.** A valid result lands atomically as ``seg-NNN/summary.json``,
  then ``summary.completed``; an invalid or failed call records
  ``summary.failed`` and writes nothing; a repeat over the same input is a no-op.
* **The real command line.** ``run_claude`` isolates the child: fresh session
  id, no settings, no tools, clauDNA's child marker, the transcript on stdin.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from claudna.session_store import schema, summarize, transcript

ACTOR = {"kind": "interactive", "fleet": None, "bot_id": None, "bot_name": None, "model": None, "entrypoint": "cli"}
ORIGIN = {"cwd": "/work", "repo": None, "branch": None, "head": None}

GOOD_OUTPUT = {
    "journey": {"title": "Fix the flaky auth test", "intent": "Make CI green", "outcome": "shipped",
                "arc": [{"step": "pinned the clock", "result": "tests pass"}],
                "done": [{"text": "pinned the clock in the auth test"}], "in_progress": [], "next": []},
    "blocks": [{"home": "entity", "subject_hint": {"name": "auth service", "kind": "service", "aliases": []},
                "claim": "The auth test is flaky unless the clock is pinned.", "asserted_by": "agent",
                "tags": ["tech:python"]}],
    "procedures": [],
}


def record(kind: str, content, **extra) -> dict:
    return {"type": kind, "message": {"role": kind, "content": content}, **extra}


def write_transcript(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


DIALOGUE = [
    record("user", "<system-reminder>injected context</system-reminder>fix the flaky auth test"),
    record("assistant", [{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Looking at it."},
                         {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}]),
    record("user", [{"type": "tool_result", "content": "SECRET=abc 1 failed"}]),
    record("assistant", "subagent chatter", isSidechain=True),
    {"type": "attachment", "attachment": {"type": "environment"}},
    record("assistant", [{"type": "text", "text": "Fixed it by pinning the clock."}]),
]


class FakeRunner:
    def __init__(self, output=None, error=None):
        self.output, self.error, self.calls = output or GOOD_OUTPUT, error, []

    def __call__(self, system_prompt, dialogue, output_schema, model, env):
        self.calls.append({"system": system_prompt, "dialogue": dialogue, "schema": output_schema, "model": model})
        if self.error:
            raise self.error
        return self.output, 0.003


@pytest.fixture
def sealed(store, tmp_path):
    """A session whose first segment covers DIALOGUE and is sealed."""
    path = tmp_path / "t.jsonl"
    write_transcript(path, DIALOGUE)
    h = store.session("sess-1")
    h.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path=str(path))
    h.open_segment("session_open", 0)
    h.seal_segment(path.stat().st_size, "precompact")
    return h


def events(handle) -> list[str]:
    return [json.loads(line)["kind"] for line in handle.paths.lifecycle.read_text().splitlines()]


def summary_status(handle) -> str:
    return json.loads(handle.paths.segment(1).segment_json.read_text())["summary"]["status"]


# ── the transcript reader ────────────────────────────────────────────────────


class TestTranscript:
    def test_only_user_and_assistant_prose_is_kept(self, tmp_path):
        path = tmp_path / "t.jsonl"
        write_transcript(path, DIALOGUE)
        turns = transcript.read_range(path, 0, None)
        assert [(t.role, t.text) for t in turns] == [
            ("user", "fix the flaky auth test"),
            ("assistant", "Looking at it."),
            ("assistant", "Fixed it by pinning the clock."),
        ]

    def test_lines_the_range_cuts_are_skipped(self, tmp_path):
        path = tmp_path / "t.jsonl"
        write_transcript(path, [record("user", "one"), record("user", "two"), record("user", "three")])
        data = path.read_bytes()
        first_end = data.index(b"\n") + 1
        mid_second = first_end + 10
        turns = transcript.read_range(path, mid_second, len(data) - 5)
        assert [t.text for t in turns] == []  # "two" starts before the range, "three" ends after it
        assert [t.text for t in transcript.read_range(path, first_end - 1, len(data))] == ["two", "three"]

    def test_render_keeps_the_most_recent_text(self):
        turns = [transcript.Turn("user", "a" * 50), transcript.Turn("assistant", "b" * 50)]
        out = transcript.render(turns, limit=60)
        assert out.startswith("[…earlier turns cut…]") and out.endswith("b" * 50)

    def test_unknown_records_are_skipped_not_fatal(self, tmp_path):
        path = tmp_path / "t.jsonl"
        path.write_text('{"type":"user","message":"not a dict"}\nnot json\n' + json.dumps(record("user", "ok")) + "\n")
        assert [t.text for t in transcript.read_range(path, 0, None)] == ["ok"]


# ── the summarizer ───────────────────────────────────────────────────────────


class TestSummarize:
    def test_a_sealed_segment_is_summarized_validated_and_recorded(self, sealed):
        runner = FakeRunner()
        assert summarize.summarize(sealed, 1, env={}, runner=runner) == "summarized: 1 block(s)"
        (call,) = runner.calls
        assert "untrusted" in call["system"] and call["model"] == "haiku"
        assert "SECRET" not in call["dialogue"] and "injected" not in call["dialogue"]
        assert call["schema"] == schema.load("segment-summary")["$defs"]["model_output"]
        artifact = json.loads((sealed.paths.segment(1).dir / "summary.json").read_text())
        assert schema.validate(artifact, schema.load("segment-summary")) == []
        assert artifact["summary"] == GOOD_OUTPUT and artifact["input"]["turns"] == 3
        assert events(sealed)[-2:] == ["summary.requested", "summary.completed"]
        assert summary_status(sealed) == "done"

    def test_a_repeat_over_the_same_input_is_a_no_op(self, sealed):
        summarize.summarize(sealed, 1, env={}, runner=FakeRunner())
        runner = FakeRunner()
        assert summarize.summarize(sealed, 1, env={}, runner=runner) == "ignored: already summarized"
        assert runner.calls == []

    def test_an_invalid_result_is_a_failure_and_writes_nothing(self, sealed):
        bad = {**GOOD_OUTPUT, "blocks": [{"home": "galaxy", "claim": "x"}]}
        out = summarize.summarize(sealed, 1, env={}, runner=FakeRunner(output=bad))
        assert out.startswith("failed: invalid summary")
        assert not (sealed.paths.segment(1).dir / "summary.json").exists()
        assert events(sealed)[-1] == "summary.failed" and summary_status(sealed) == "failed"

    def test_a_failed_call_is_recorded(self, sealed):
        err = summarize.SummarizerError("claude timed out after 180s", retryable=True)
        assert summarize.summarize(sealed, 1, env={}, runner=FakeRunner(error=err)).startswith("failed")
        last = json.loads(sealed.paths.lifecycle.read_text().splitlines()[-1])
        assert last["data"] == {"job_id": last["data"]["job_id"], "error": "claude timed out after 180s",
                                "retryable": True}

    @pytest.mark.parametrize("setup,env,reason", [
        (lambda h: h.set_private(True), {}, "private"),
        (lambda h: None, {"CLAUDNA_SESSION_SUMMARY": "0"}, "disabled"),
    ])
    def test_gates_skip_without_calling_the_model(self, sealed, setup, env, reason):
        setup(sealed)
        runner = FakeRunner()
        assert summarize.summarize(sealed, 1, env=env, runner=runner) == f"skipped: {reason}"
        assert runner.calls == [] and summary_status(sealed) == "skipped"

    @pytest.mark.parametrize("kind", ["headless", "bot"])
    def test_headless_and_bot_sessions_are_off_unless_switched_on(self, store, tmp_path, kind):
        path = tmp_path / "t.jsonl"
        write_transcript(path, DIALOGUE)
        h = store.session("sess-h")
        h.open_session("startup", actor={**ACTOR, "kind": kind}, origin=ORIGIN, transcript_path=str(path))
        h.open_segment("session_open", 0)
        h.seal_segment(path.stat().st_size, "session_end")
        assert summarize.summarize(h, 1, env={}, runner=FakeRunner()) == "skipped: headless"
        assert summarize.summarize(h, 1, env={"CLAUDNA_SESSION_SUMMARY": "1"}, runner=FakeRunner()) \
            == "summarized: 1 block(s)"

    def test_a_missing_transcript_and_a_slice_without_user_turns_are_skipped(self, sealed, tmp_path):
        (tmp_path / "t.jsonl").unlink()
        assert summarize.summarize(sealed, 1, env={}, runner=FakeRunner()) == "skipped: no_transcript"
        write_transcript(tmp_path / "t.jsonl", [record("assistant", "only me")] * 20)
        assert summarize.summarize(sealed, 1, env={}, runner=FakeRunner()) == "skipped: trivial"

    def test_an_unsealed_segment_or_a_missing_one_is_left_alone(self, store, tmp_path):
        h = store.session("sess-u")
        h.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path=None)
        h.open_segment("session_open", 0)
        assert summarize.summarize(h, 1, env={}, runner=FakeRunner()).startswith("ignored: segment 1 is not")
        assert summarize.summarize(h, 9, env={}, runner=FakeRunner()) == "ignored: no segment 9"

    def test_one_summarizer_per_segment(self, sealed):
        from claudna.session_store.fsio import try_exclusive_lock

        with try_exclusive_lock(sealed.paths.segment(1).dir / ".summarize.lock") as taken:
            assert taken
            out = summarize.summarize(sealed, 1, env={}, runner=FakeRunner())
        assert out == "ignored: another summarizer holds the segment"


# ── the real command line, against a fake claude ─────────────────────────────


FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys
dialogue = sys.stdin.read()
with open(os.environ["FAKE_LOG"], "w") as fh:
    json.dump({"argv": sys.argv[1:], "stdin": dialogue, "child": os.environ.get("CLAUDNA_SESSION_CHILD"),
               "inherited": os.environ.get("CLAUDE_CODE_SESSION_ID")}, fh)
print(json.dumps({"is_error": False, "structured_output": json.loads(os.environ["FAKE_OUTPUT"]),
                  "total_cost_usd": 0.001}))
"""


class TestRunClaude:
    def test_the_child_is_isolated_and_reads_the_transcript_from_stdin(self, tmp_path):
        fake = tmp_path / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        log = tmp_path / "log.json"
        env = {"PATH": os.environ["PATH"], "CLAUDNA_CLAUDE_BIN": str(fake), "FAKE_LOG": str(log),
               "FAKE_OUTPUT": json.dumps(GOOD_OUTPUT), "CLAUDE_CODE_SESSION_ID": "parent-sid"}
        output, cost = summarize.run_claude("SYSTEM", "the dialogue", {"type": "object"}, "haiku", env)
        seen = json.loads(log.read_text())
        argv = seen["argv"]
        assert (output, cost) == (GOOD_OUTPUT, 0.001)
        assert seen["stdin"] == "the dialogue" and seen["child"] == "1" and seen["inherited"] is None
        assert argv[argv.index("--setting-sources") + 1] == "" and argv[argv.index("--tools") + 1] == ""
        assert argv[argv.index("--system-prompt") + 1] == "SYSTEM"
        assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
        assert argv[argv.index("--session-id") + 1] != "parent-sid"

    def test_a_missing_binary_is_a_permanent_failure(self, tmp_path):
        with pytest.raises(summarize.SummarizerError) as exc:
            summarize.run_claude("s", "d", {}, "haiku", {"CLAUDNA_CLAUDE_BIN": str(tmp_path / "nope")})
        assert exc.value.retryable is False

    def test_output_that_is_not_json_is_a_retryable_failure(self, tmp_path):
        fake = tmp_path / "claude"
        fake.write_text("#!/bin/sh\necho 'rate limited' >&2\nexit 1\n")
        fake.chmod(0o755)
        with pytest.raises(summarize.SummarizerError) as exc:
            summarize.run_claude("s", "d", {}, "haiku", {"CLAUDNA_CLAUDE_BIN": str(fake), "PATH": os.environ["PATH"]})
        assert exc.value.retryable and "rate limited" in str(exc.value)
