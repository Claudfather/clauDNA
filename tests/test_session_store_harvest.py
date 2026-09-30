"""Tests for harvest's thin slice (lib/claudna/session_store/harvest.py) — spec §7.2.

What these guard:

* **Drafts through the door.** Every block of a summarized segment becomes one
  ``claudron capture --stdin --json`` finding, scoped to the session's repo;
  ``person`` blocks are held back.
* **The cursor.** A segment is taken once; the cursor moves only after its
  captures return, holds at a segment whose summary isn't done, and stays put
  when Claudron fails.
* **Single-flight and bounded.** A held lock, a recent run, or the switch skip
  the run; at most ``MAX_CAPTURES`` writes per run, whole segments only.
* **Liveness.** Each run leaves ``last_run.json`` and the one line SessionStart shows.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from conftest import ACTOR, ORIGIN

from claudna.session_store import harvest
from claudna.session_store.fsio import atomic_write_json, exclusive_lock

BLOCK = {"home": "entity", "subject_hint": {"name": "staging DB", "kind": "service", "aliases": []},
         "claim": "The staging DB is reset nightly at 02:00 UTC.", "asserted_by": "user", "tags": ["env:staging"]}
PERSON = {"home": "person", "subject_hint": {"name": "Dana", "kind": "person"}, "claim": "Dana owns billing.",
          "asserted_by": "user"}


class FakeCapture:
    def __init__(self, answers=None, error_after=None):
        self.findings, self.answers, self.error_after = [], list(answers or []), error_after

    def __call__(self, finding, cwd, env):
        if self.error_after is not None and len(self.findings) >= self.error_after:
            raise harvest.CaptureError("claudron capture exited 3: vault not found")
        self.findings.append((finding, cwd))
        return self.answers.pop(0) if self.answers else "created"


def summarized_session(store, sid: str, blocks_per_segment: list[list[dict]], *, repo="webapp", done=True):
    """A session whose segments each carry a completed summary with the given blocks."""
    h = store.session(sid)
    h.open_session("startup", actor=ACTOR, origin={**ORIGIN, "repo": repo}, transcript_path="/t.jsonl")
    for i, blocks in enumerate(blocks_per_segment, 1):
        h.open_segment("session_open" if i == 1 else "compact", i * 10)
        h.seal_segment(i * 10 + 5, "precompact")
        atomic_write_json(h.paths.segment(i).dir / "summary.json", artifact(sid, i, blocks))
        if done or i < len(blocks_per_segment):
            h.append("summary.completed", {"job_id": f"j{i}", "artifact": f"seg-00{i}/summary.json",
                                           "input_sha256": "0" * 64, "duration_ms": 1}, seg=i)
        else:
            h.append("summary.requested", {"job_id": f"j{i}"}, seg=i)
    return h


def artifact(sid: str, index: int, blocks: list[dict]) -> dict:
    """A schema-valid seg-NNN/summary.json carrying ``blocks``."""
    return {
        "schema": "claudna.segment-summary/1", "sid": sid, "index": index,
        "input": {"transcript_path": "/t.jsonl", "range": {"start": 0, "end": 1}, "sha256": "0" * 64, "turns": 1},
        "producer": {"model": "haiku", "prompt_version": "segment-summary/1", "duration_ms": 1, "cost_usd": None},
        "journey": {"title": "t", "intent": "i", "outcome": "shipped", "arc": [], "done": [], "in_progress": [],
                    "next": []},
        "blocks": blocks, "procedures": [],
    }


def cursor(handle) -> int:
    return json.loads((handle.paths.dir / "consumers.json").read_text())["consumers"]["harvest"]["through_seg"]


class TestHarvest:
    def test_blocks_become_draft_findings_scoped_to_the_repo(self, store):
        h = summarized_session(store, "s1", [[BLOCK, PERSON]])
        capture = FakeCapture()
        report = harvest.harvest(store, env={}, capture=capture)
        ((finding, cwd),) = capture.findings
        assert finding["type"] == "knowledge" and finding["project"] == "webapp" and cwd == "/work"
        assert finding["title"].startswith("staging DB: ") and finding["body"].startswith(BLOCK["claim"])
        assert "Harvested from session s1, segment 1" in finding["body"]
        assert {"origin:session-harvest", "home:entity", "asserted-by:user", "env:staging"} <= set(finding["tags"])
        assert "maturity" not in finding  # the engine stamps draft; consumers never set it
        assert (report.status, report.created, report.held_back, report.segments) == ("ok", 1, 1, 1)
        assert cursor(h) == 1

    def test_a_decision_block_is_a_decision_note_and_no_repo_means_shared(self, store):
        summarized_session(store, "s1", [[{**BLOCK, "home": "decision"}]], repo=None)
        capture = FakeCapture()
        harvest.harvest(store, env={}, capture=capture)
        ((finding, _),) = capture.findings
        assert finding["type"] == "decision" and "project" not in finding

    def test_a_long_title_is_cut_at_a_word(self):
        long = {**BLOCK, "claim": "Do not keep persistent test fixtures in the staging database because it is reset "
                                  "every night at two in the morning UTC"}
        title = harvest.finding_of(long, sid="s1", index=1, project=None)["title"]
        assert len(title) <= 101 and title.endswith("…") and not title[:-1].endswith(" ")

    def test_a_segment_is_taken_once(self, store):
        summarized_session(store, "s1", [[BLOCK]])
        harvest.harvest(store, env={}, capture=FakeCapture())
        again = FakeCapture()
        harvest.harvest(store, env={}, capture=again, force=True)
        assert again.findings == []

    def test_dedup_answers_count_as_known_and_rejections_are_counted(self, store):
        summarized_session(store, "s1", [[BLOCK, BLOCK, BLOCK]])
        report = harvest.harvest(store, env={}, capture=FakeCapture(["created", "suggest_update", "rejected"]))
        assert (report.created, report.known, report.rejected) == (1, 1, 1)

    def test_the_cursor_holds_at_a_segment_still_being_summarized(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK], [BLOCK]], done=False)
        report = harvest.harvest(store, env={}, capture=FakeCapture())
        assert report.segments == 2 and cursor(h) == 2

    def test_a_claudron_failure_stops_the_run_and_keeps_the_cursor(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK, BLOCK]])
        report = harvest.harvest(store, env={}, capture=FakeCapture(error_after=2))
        assert report.status == "error" and "vault not found" in report.errors[0]
        assert cursor(h) == 1  # segment 2 failed half-way: it is retried whole next run
        line = (store.root / "harvest" / "liveness.txt").read_text()
        assert "FAILED" in line and "vault not found" in line

    def test_a_segment_bigger_than_the_budget_is_still_taken_whole(self, store, monkeypatch):
        monkeypatch.setattr(harvest, "MAX_CAPTURES", 2)
        h = summarized_session(store, "s1", [[BLOCK, BLOCK, BLOCK], [BLOCK]])
        capture = FakeCapture()
        harvest.harvest(store, env={}, capture=capture)
        assert len(capture.findings) == 3 and cursor(h) == 1  # never stuck behind its own size

    def test_person_facts_are_queued_for_review(self, store):
        summarized_session(store, "s1", [[PERSON]])
        harvest.harvest(store, env={}, capture=FakeCapture())
        (held,) = [json.loads(line) for line in (store.root / "harvest" / "held.jsonl").read_text().splitlines()]
        assert (held["sid"], held["seg"], held["reason"], held["block"]) == ("s1", 1, "person", PERSON)

    def test_private_sessions_are_never_harvested(self, store):
        h = summarized_session(store, "s1", [[BLOCK]])
        h.set_private(True)
        capture = FakeCapture()
        harvest.harvest(store, env={}, capture=capture)
        assert capture.findings == []

    def test_a_run_is_bounded_to_whole_segments(self, store, monkeypatch):
        monkeypatch.setattr(harvest, "MAX_CAPTURES", 3)
        h = summarized_session(store, "s1", [[BLOCK, BLOCK], [BLOCK, BLOCK]])
        capture = FakeCapture()
        harvest.harvest(store, env={}, capture=capture)
        assert len(capture.findings) == 2 and cursor(h) == 1


    def test_an_unreadable_summary_holds_the_cursor_and_is_reported(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK]])
        atomic_write_json(h.paths.segment(2).dir / "summary.json", {"summary": {"blocks": [BLOCK]}})  # old shape
        report = harvest.harvest(store, env={}, capture=FakeCapture())
        assert cursor(h) == 1 and "seg-002/summary.json is missing or invalid" in report.errors[0]


class TestScheduling:
    def test_a_recent_run_is_not_repeated_unless_forced(self, store):
        summarized_session(store, "s1", [[BLOCK]])
        harvest.harvest(store, env={}, capture=FakeCapture())
        assert harvest.harvest(store, env={}, capture=FakeCapture()).reason == "not due"
        assert harvest.harvest(store, env={"CLAUDNA_HARVEST_INTERVAL_H": "0"}, capture=FakeCapture()).status == "ok"

    def test_one_harvest_at_a_time_and_the_switch(self, store):
        (store.root / "harvest").mkdir(parents=True)
        with exclusive_lock(store.root / "harvest" / "lock", blocking=False):
            assert harvest.harvest(store, env={}, capture=FakeCapture()).reason == "another harvest is running"
        assert harvest.harvest(store, env={"CLAUDNA_HARVEST": "0"}, capture=FakeCapture()).reason == "disabled"

    def test_is_due_needs_claudron_and_an_old_last_run(self, store, tmp_path):
        fake = tmp_path / "bin" / "claudron"
        fake.parent.mkdir()
        fake.write_text("#!/bin/sh\n")
        fake.chmod(0o755)
        env = {"PATH": str(fake.parent)}
        assert harvest.is_due(store.root, env, now=1000.0)
        assert not harvest.is_due(store.root, {"PATH": str(tmp_path)}, now=1000.0)  # no claudron
        assert not harvest.is_due(store.root, {**env, "CLAUDNA_HARVEST": "0"}, now=1000.0)
        atomic_write_json((store.root / "harvest").mkdir(parents=True) or store.root / "harvest" / "last_run.json",
                          {"started_epoch": 1000.0})
        assert not harvest.is_due(store.root, env, now=1000.0 + 3600)
        assert harvest.is_due(store.root, env, now=1000.0 + 7 * 3600)


FAKE_CLAUDRON = """#!/usr/bin/env python3
import json, os, sys
finding = json.loads(sys.stdin.read())
with open(os.environ["FAKE_LOG"], "w") as fh:
    json.dump({"argv": sys.argv[1:], "finding": finding, "cwd": os.getcwd()}, fh)
print(json.dumps({"ok": True, "command": "capture", "errors": [], "warnings": [],
                  "data": {"action": os.environ.get("FAKE_ACTION", "created"), "path": "p.md", "reason": None,
                           "written": True}}))
"""


class TestRunClaudronCapture:
    def make(self, tmp_path: Path) -> dict:
        fake = tmp_path / "claudron"
        fake.write_text(FAKE_CLAUDRON)
        fake.chmod(0o755)
        return {"PATH": os.environ["PATH"], "CLAUDNA_CLAUDRON_BIN": str(fake), "FAKE_LOG": str(tmp_path / "log")}

    def test_the_finding_goes_on_stdin_as_json_never_as_an_argument(self, tmp_path):
        env = self.make(tmp_path)
        finding = {"type": "knowledge", "title": "t", "body": "has $(rm -rf) and `quotes`", "tags": []}
        assert harvest.run_claudron_capture(finding, str(tmp_path), env) == "created"
        seen = json.loads((tmp_path / "log").read_text())
        assert seen["argv"] == ["capture", "--stdin", "--json"] and seen["finding"] == finding
        assert seen["cwd"] == str(tmp_path)

    def test_a_not_ok_envelope_is_an_error(self, tmp_path):
        fake = tmp_path / "claudron"
        fake.write_text('#!/bin/sh\necho \'{"ok": false, "command": "capture", "errors": ["vault not found"], '
                        '"data": null}\'\nexit 3\n')
        fake.chmod(0o755)
        with pytest.raises(harvest.CaptureError, match="vault not found"):
            harvest.run_claudron_capture({"type": "knowledge", "title": "t"}, None,
                                         {"PATH": os.environ["PATH"], "CLAUDNA_CLAUDRON_BIN": str(fake)})

    def test_an_unexpected_answer_is_an_error(self, tmp_path):
        env = {**self.make(tmp_path), "FAKE_ACTION": "exploded"}
        with pytest.raises(harvest.CaptureError):
            harvest.run_claudron_capture({"type": "knowledge", "title": "t"}, None, env)
