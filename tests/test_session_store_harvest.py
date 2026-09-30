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
import time
from pathlib import Path

import pytest
from conftest import ACTOR, ORIGIN

from claudna.session_store import harvest
from claudna.session_store.fsio import atomic_write_json, exclusive_lock

BLOCK = {"home": "entity", "subject_hint": {"name": "staging DB", "kind": "service", "aliases": []},
         "claim": "The staging DB is reset nightly at 02:00 UTC.", "asserted_by": "user", "tags": ["env:staging"]}
PERSON = {"home": "person", "subject_hint": {"name": "Dana", "kind": "person"}, "claim": "Dana owns billing.",
          "asserted_by": "user"}


REAL_CAPTURE = harvest.run_claudron_capture  # taken before any stub; only TestRunClaudronCapture calls it
ON = {"CLAUDNA_HARVEST": "1"}  # the run's own opt-in (each session records its own, too)


@pytest.fixture(autouse=True)
def _never_the_real_tools(monkeypatch):
    """No test may reach the real summarizer or claudron through a default (#373 review, M1)."""
    monkeypatch.setattr(harvest, "_resummarize", lambda h, i, e: pytest.fail("reached the real summarizer"))
    monkeypatch.setattr(harvest, "run_claudron_capture", lambda *a, **k: pytest.fail("reached the real claudron"))


class FakeCapture:
    def __init__(self, answers=None, error_after=None):
        self.findings, self.answers, self.error_after = [], list(answers or []), error_after

    def __call__(self, finding, cwd, env, vault=None):
        if self.error_after is not None and len(self.findings) >= self.error_after:
            raise harvest.CaptureError("claudron capture exited 3: vault not found")
        self.findings.append((finding, cwd))
        self.vaults = [*getattr(self, "vaults", []), vault]
        return self.answers.pop(0) if self.answers else "created"


def summarized_session(store, sid: str, blocks_per_segment: list[list[dict]], *, repo="webapp", done=True,
                       closed=True, opted_in=True, vault="/vaults/default", cwd="/work"):
    """A session whose segments each carry a completed summary with the given blocks (closed: all final)."""
    h = store.session(sid)
    h.open_session("startup", actor=ACTOR, origin={**ORIGIN, "repo": repo, "cwd": cwd}, transcript_path="/t.jsonl",
                   harvest={"enabled": opted_in, "vault": vault})
    for i, blocks in enumerate(blocks_per_segment, 1):
        h.open_segment("session_open" if i == 1 else "compact", i * 10)
        h.seal_segment(i * 10 + 5, "precompact")
        atomic_write_json(h.paths.segment(i).dir / "summary.json", artifact(sid, i, blocks, start=i * 10, end=i * 10 + 5))
        if done or i < len(blocks_per_segment):
            h.append("summary.completed", {"job_id": f"j{i}", "artifact": f"seg-00{i}/summary.json",
                                           "input_sha256": "0" * 64, "duration_ms": 1}, seg=i)
        else:
            h.append("summary.requested", {"job_id": f"j{i}"}, seg=i)
    if closed:
        h.close_session("other")
    return h


def artifact(sid: str, index: int, blocks: list[dict], *, start: int = 0, end: int = 1) -> dict:
    """A schema-valid seg-NNN/summary.json carrying ``blocks``, summarizing ``[start, end)``."""
    return {
        "schema": "claudna.segment-summary/1", "sid": sid, "index": index,
        "input": {"transcript_path": "/t.jsonl", "range": {"start": start, "end": end}, "sha256": "0" * 64,
                  "turns": 1},
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
        report = harvest.harvest(store, env=ON, capture=capture)
        ((finding, cwd),) = capture.findings
        assert finding["type"] == "knowledge" and finding["project"] == "webapp" and cwd == "/work"
        assert finding["title"].startswith("(unverified) staging DB: ") and finding["body"].startswith(BLOCK["claim"])
        assert "Harvested from session s1, segment 1" in finding["body"]
        assert {"origin:session-harvest", "home:entity", "asserted-by:user", "env:staging"} <= set(finding["tags"])
        assert "maturity" not in finding  # the engine stamps draft; consumers never set it
        assert (report.status, report.created, report.held_back, report.segments) == ("ok", 1, 1, 1)
        assert cursor(h) == 1

    def test_a_decision_block_is_a_decision_note(self, store):
        summarized_session(store, "s1", [[{**BLOCK, "home": "decision"}]])
        capture = FakeCapture()
        harvest.harvest(store, env=ON, capture=capture)
        ((finding, _),) = capture.findings
        assert finding["type"] == "decision"

    def test_a_session_outside_a_repo_is_not_harvested(self, store):
        summarized_session(store, "s1", [[BLOCK]], repo=None)  # it would land in the vault's shared tree
        capture = FakeCapture()
        harvest.harvest(store, env=ON, capture=capture)
        assert capture.findings == []

    def test_a_session_that_did_not_opt_in_is_not_harvested(self, store):
        summarized_session(store, "s1", [[BLOCK]], opted_in=False)
        capture = FakeCapture()
        harvest.harvest(store, env=ON, capture=capture)
        assert capture.findings == []

    def test_a_session_with_nowhere_to_route_is_reported_not_guessed(self, store):
        summarized_session(store, "s1", [[BLOCK]], vault=None, cwd="/no/such/dir")
        capture = FakeCapture()
        report = harvest.harvest(store, env=ON, capture=capture)
        assert capture.findings == [] and "no vault to route to" in report.errors[0]

    def test_each_session_is_captured_into_its_own_vault(self, store):
        """B2: the run's own CLAUDRON_VAULT_PATH never redirects another session's drafts."""
        summarized_session(store, "work", [[BLOCK]], vault="/vaults/work")
        summarized_session(store, "home", [[BLOCK]], vault=None, cwd=str(store.root.parent))  # cwd walk-up
        capture = FakeCapture()
        harvest.harvest(store, env={**ON, "CLAUDRON_VAULT_PATH": "/vaults/personal"}, capture=capture)
        assert capture.vaults == [None, "/vaults/work"]  # sorted: "home", then "work"

    def test_every_draft_carries_the_unverified_banner_and_is_redacted(self, store):
        leaky = {**BLOCK, "claim": "Deploy with " + "sk-" + "ant-" + "api03-" + "aB3_cD4-eF5" * 4 + " as the key."}
        summarized_session(store, "s1", [[leaky]])
        capture = FakeCapture()
        harvest.harvest(store, env=ON, capture=capture)
        ((finding, _),) = capture.findings
        assert finding["title"].startswith("(unverified) ") and "aB3_cD4" not in json.dumps(finding)

    def test_a_long_title_is_cut_at_a_word(self):
        long = {**BLOCK, "claim": "Do not keep persistent test fixtures in the staging database because it is reset "
                                  "every night at two in the morning UTC"}
        title = harvest.finding_of(long, sid="s1", index=1, project=None)["title"]
        assert len(title) <= len(harvest.DRAFT_BANNER) + 101 and title.endswith("…") and not title[:-1].endswith(" ")

    def test_a_segment_is_taken_once(self, store):
        summarized_session(store, "s1", [[BLOCK]])
        harvest.harvest(store, env=ON, capture=FakeCapture())
        again = FakeCapture()
        harvest.harvest(store, env=ON, capture=again, force=True)
        assert again.findings == []

    def test_dedup_answers_count_as_known_and_rejections_are_counted(self, store):
        summarized_session(store, "s1", [[BLOCK, BLOCK, BLOCK]])
        report = harvest.harvest(store, env=ON, capture=FakeCapture(["created", "suggest_update", "rejected"]))
        assert (report.created, report.known, report.rejected) == (1, 1, 1)

    def test_the_cursor_holds_at_a_segment_still_being_summarized(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK], [BLOCK]], done=False)
        report = harvest.harvest(store, env=ON, capture=FakeCapture())
        assert report.segments == 2 and cursor(h) == 2

    def test_a_claudron_failure_stops_the_run_and_keeps_the_cursor(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK, BLOCK]])
        report = harvest.harvest(store, env=ON, capture=FakeCapture(error_after=2))
        assert report.status == "error" and "vault not found" in report.errors[0]
        assert cursor(h) == 1  # segment 2 failed half-way: it is retried whole next run
        line = (store.root / "harvest" / "liveness.txt").read_text()
        assert "FAILED" in line and "vault not found" in line

    def test_a_segment_bigger_than_the_budget_is_still_taken_whole(self, store, monkeypatch):
        monkeypatch.setattr(harvest, "MAX_CAPTURES", 2)
        h = summarized_session(store, "s1", [[BLOCK, BLOCK, BLOCK], [BLOCK]])
        capture = FakeCapture()
        harvest.harvest(store, env=ON, capture=capture)
        assert len(capture.findings) == 3 and cursor(h) == 1  # never stuck behind its own size

    def test_person_facts_are_queued_for_review(self, store):
        summarized_session(store, "s1", [[PERSON]])
        harvest.harvest(store, env=ON, capture=FakeCapture())
        (held,) = [json.loads(line) for line in (store.root / "harvest" / "held.jsonl").read_text().splitlines()]
        assert (held["sid"], held["seg"], held["reason"], held["block"]) == ("s1", 1, "person", PERSON)

    def test_private_sessions_are_never_harvested(self, store):
        h = summarized_session(store, "s1", [[BLOCK]])
        h.set_private(True)
        capture = FakeCapture()
        harvest.harvest(store, env=ON, capture=capture)
        assert capture.findings == []

    def test_a_run_is_bounded_to_whole_segments(self, store, monkeypatch):
        monkeypatch.setattr(harvest, "MAX_CAPTURES", 3)
        h = summarized_session(store, "s1", [[BLOCK, BLOCK], [BLOCK, BLOCK]])
        capture = FakeCapture()
        harvest.harvest(store, env=ON, capture=capture)
        assert len(capture.findings) == 2 and cursor(h) == 1


    def test_an_unreadable_summary_holds_the_cursor_and_is_reported(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK]])
        atomic_write_json(h.paths.segment(2).dir / "summary.json", {"summary": {"blocks": [BLOCK]}})  # old shape
        report = harvest.harvest(store, env=ON, capture=FakeCapture())
        assert cursor(h) == 1 and "seg-002/summary.json is missing or invalid" in report.errors[0]

    def test_a_skipped_segment_never_holds_the_cursor(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK]])
        h.append("summary.skipped", {"reason": "trivial"}, seg=1)  # final: nothing will summarize it again
        capture = FakeCapture()
        harvest.harvest(store, env=ON, capture=capture)
        assert len(capture.findings) == 1 and cursor(h) == 2


class TestFinalSegmentsOnly:
    def test_the_current_segment_of_an_open_session_waits(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK]], closed=False)
        report = harvest.harvest(store, env=ON, capture=FakeCapture())
        assert report.segments == 1 and cursor(h) == 1  # seg 2 may still be re-sealed and re-summarized

    def test_once_closed_the_last_segment_is_taken(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK]], closed=False)
        harvest.harvest(store, env=ON, capture=FakeCapture())
        h.close_session("other")
        harvest.harvest(store, env=ON, capture=FakeCapture(), force=True)
        assert cursor(h) == 2


class TestStrandedSummaries:
    def stranded(self, store, kind: str, *, retryable=True, attempts=1, age_s=3600):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK]])
        for n in range(attempts):
            h.append("summary.requested", {"job_id": f"r{n}"}, seg=2)
            if kind == "failed":
                h.append("summary.failed", {"job_id": f"r{n}", "error": "claude timed out", "retryable": retryable},
                         seg=2)
        if kind == "pending" and age_s:
            lines = h.paths.lifecycle.read_text().splitlines()
            last = json.loads(lines[-1])
            last["ts"] = "2000-01-01T00:00:00.000Z"
            h.paths.lifecycle.write_text("\n".join([*lines[:-1], json.dumps(last)]) + "\n")
        h.rebuild()
        return h

    def test_a_retryable_failure_is_summarized_again(self, store):
        h = self.stranded(store, "failed")
        calls = []

        def resummarize(handle, index, env):
            calls.append(index)
            handle.append("summary.requested", {"job_id": "again"}, seg=index)
            handle.append("summary.completed", {"job_id": "again", "artifact": "seg-002/summary.json",
                                                "input_sha256": "0" * 64, "duration_ms": 1}, seg=index)
            return "summarized"

        report = harvest.harvest(store, env=ON, capture=FakeCapture(), resummarize=resummarize)
        assert calls == [2] and report.retried == 1 and cursor(h) == 2

    def test_a_pending_summary_whose_worker_died_is_retried_but_a_fresh_one_is_left(self, store):
        calls = []
        self.stranded(store, "pending")
        harvest.harvest(store, env=ON, capture=FakeCapture(), resummarize=lambda h, i, e: calls.append(i) or "x")
        assert calls == [2]

    def test_a_fresh_pending_summary_is_left_to_its_worker(self, tmp_path):
        from claudna.session_store.store import SessionStore

        store = SessionStore(tmp_path / "fresh")
        self.stranded(store, "pending", age_s=0)
        report = harvest.harvest(store, env=ON, capture=FakeCapture(), resummarize=lambda h, i, e: pytest.fail("retried"))
        assert report.retried == 0 and report.segments == 1

    def test_after_the_last_attempt_harvest_gives_up_and_moves_on(self, store):
        h = self.stranded(store, "failed", attempts=harvest.MAX_ATTEMPTS)
        report = harvest.harvest(store, env=ON, capture=FakeCapture(), resummarize=lambda h, i, e: pytest.fail("retried"))
        assert report.gave_up == 1 and cursor(h) == 2 and "never summarized" in report.errors[0]

    def test_a_permanent_failure_is_given_up_at_once(self, store):
        h = self.stranded(store, "failed", retryable=False)
        report = harvest.harvest(store, env=ON, capture=FakeCapture(), resummarize=lambda h, i, e: pytest.fail("retried"))
        assert report.gave_up == 1 and cursor(h) == 2


    def test_retries_are_capped_per_run(self, store):
        for sid in ("s1", "s2", "s3"):
            h = summarized_session(store, sid, [[BLOCK]])
            h.append("summary.requested", {"job_id": "r"}, seg=1)
            h.append("summary.failed", {"job_id": "r", "error": "timeout", "retryable": True}, seg=1)
            h.rebuild()
        calls = []
        report = harvest.harvest(store, env=ON, capture=FakeCapture(),
                                 resummarize=lambda h, i, e: calls.append(h.sid) or "failed")
        assert len(calls) == harvest.MAX_RETRIES_PER_RUN == report.retried


class TestScheduling:
    def test_a_recent_run_is_not_repeated_unless_forced(self, store):
        summarized_session(store, "s1", [[BLOCK]])
        harvest.harvest(store, env=ON, capture=FakeCapture())
        assert harvest.harvest(store, env=ON, capture=FakeCapture()).reason == "not due"
        assert harvest.harvest(store, env={**ON, "CLAUDNA_HARVEST_INTERVAL_H": "0"}, capture=FakeCapture()).status == "ok"

    def test_one_harvest_at_a_time_and_the_switch(self, store):
        (store.root / "harvest").mkdir(parents=True)
        with exclusive_lock(store.root / "harvest" / "lock", blocking=False):
            assert harvest.harvest(store, env=ON, capture=FakeCapture()).reason == "another harvest is running"
        assert harvest.harvest(store, env={"CLAUDNA_HARVEST": "0"}, capture=FakeCapture()).reason == "disabled"
        assert harvest.harvest(store, env={}, capture=FakeCapture()).reason == "disabled"  # opt-in

    def test_is_due_needs_claudron_and_an_old_last_run(self, store, tmp_path):
        fake = tmp_path / "bin" / "claudron"
        fake.parent.mkdir()
        fake.write_text("#!/bin/sh\n")
        fake.chmod(0o755)
        env = {"PATH": str(fake.parent), "CLAUDNA_HARVEST": "1"}
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
    json.dump({"argv": sys.argv[1:], "finding": finding, "cwd": os.getcwd(),
               "env_vault": os.environ.get("CLAUDRON_VAULT_PATH")}, fh)
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
        assert REAL_CAPTURE(finding, str(tmp_path), env) == "created"
        seen = json.loads((tmp_path / "log").read_text())
        assert seen["argv"] == ["capture", "--stdin", "--json"] and seen["finding"] == finding
        assert seen["cwd"] == str(tmp_path)

    def test_the_sessions_vault_is_passed_and_the_runs_is_stripped(self, tmp_path):
        env = {**self.make(tmp_path), "CLAUDRON_VAULT_PATH": "/vaults/personal"}
        REAL_CAPTURE({"type": "knowledge", "title": "t"}, str(tmp_path), env, "/vaults/work")
        seen = json.loads((tmp_path / "log").read_text())
        assert seen["argv"][:2] == ["--vault", "/vaults/work"] and seen["env_vault"] is None

    def test_a_not_ok_envelope_is_an_error(self, tmp_path):
        fake = tmp_path / "claudron"
        fake.write_text('#!/bin/sh\necho \'{"ok": false, "command": "capture", "errors": ["vault not found"], '
                        '"data": null}\'\nexit 3\n')
        fake.chmod(0o755)
        with pytest.raises(harvest.CaptureError, match="vault not found"):
            REAL_CAPTURE({"type": "knowledge", "title": "t"}, None,
                                         {"PATH": os.environ["PATH"], "CLAUDNA_CLAUDRON_BIN": str(fake)})

    @pytest.mark.parametrize("reply", ["[1, 2]", '"created"', "null"])
    def test_a_reply_that_is_not_an_object_is_an_error(self, tmp_path, reply):
        fake = tmp_path / "claudron"
        fake.write_text(f"#!/bin/sh\ncat > /dev/null\necho '{reply}'\n")
        fake.chmod(0o755)
        with pytest.raises(harvest.CaptureError, match="not a JSON object"):
            REAL_CAPTURE({"type": "knowledge", "title": "t"}, None,
                         {"PATH": os.environ["PATH"], "CLAUDNA_CLAUDRON_BIN": str(fake)})

    def test_an_unexpected_answer_is_an_error(self, tmp_path):
        env = {**self.make(tmp_path), "FAKE_ACTION": "exploded"}
        with pytest.raises(harvest.CaptureError):
            REAL_CAPTURE({"type": "knowledge", "title": "t"}, None, env)


class TestReviewRound373:
    """M1 and M2 from the #373 review."""

    def test_a_fresh_request_is_not_stale_in_a_dst_timezone(self, monkeypatch):
        monkeypatch.setenv("TZ", "America/New_York")
        time.tzset()
        try:
            now = time.time()
            ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now - 1))
            events = [{"kind": "segment.sealed", "ts": ts, "data": {}},
                      {"kind": "summary.requested", "ts": ts, "data": {"job_id": "j"}}]
            assert harvest._stranded(events, now) is None  # 1 s old, not 3,601
        finally:
            monkeypatch.delenv("TZ")
            time.tzset()

    def test_a_sealed_segment_never_summarized_is_retried_after_its_grace(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK]])
        lines = h.paths.lifecycle.read_text().splitlines()
        # drop seg 2's summary.completed: the spawn died, the status stayed "none"
        kept = [ln for ln in lines if not (json.loads(ln)["kind"] == "summary.completed" and json.loads(ln)["seg"] == 2)]
        old = [json.loads(ln) for ln in kept]
        for e in old:
            if e["kind"] == "segment.sealed" and e["seg"] == 2:
                e["ts"] = "2000-01-01T00:00:00.000Z"
        h.paths.lifecycle.write_text("".join(json.dumps(e) + "\n" for e in old))
        h.rebuild()
        calls = []
        harvest.harvest(store, env=ON, capture=FakeCapture(), resummarize=lambda hh, i, e: calls.append(i) or "x")
        assert calls == [2]

    def test_a_done_summary_older_than_the_last_seal_is_summarized_again(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK]])
        h.seal_segment(99, "session_end", index=2)  # a re-seal after the summary was written
        calls = []
        harvest.harvest(store, env=ON, capture=FakeCapture(), resummarize=lambda hh, i, e: calls.append(i) or "x")
        assert calls == [2] and cursor(h) == 1

    def test_a_re_seal_restarts_the_attempt_budget(self):
        seal = {"kind": "segment.sealed", "ts": "2000-01-01T00:00:00.000Z", "data": {}}
        failed = [{"kind": "summary.requested", "ts": seal["ts"], "data": {"job_id": f"j{n}"}} for n in range(3)] + \
            [{"kind": "summary.failed", "ts": seal["ts"], "data": {"job_id": "j2", "error": "x", "retryable": True}}]
        assert harvest._stranded([seal, *failed], time.time()) == "give up"
        assert harvest._stranded([seal, *failed, seal, failed[0], failed[-1]], time.time()) == "retry"

    def test_a_crash_in_one_session_still_leaves_the_run_record(self, store, monkeypatch):
        summarized_session(store, "s1", [[BLOCK]])
        monkeypatch.setattr(harvest, "_latest_origin", lambda lifecycle: 1 / 0)
        report = harvest.harvest(store, env=ON, capture=FakeCapture())
        last = json.loads((store.root / "harvest" / "last_run.json").read_text())
        assert "ZeroDivisionError" in report.errors[0] and last["errors"] == report.errors

    def test_an_empty_run_debounces_for_an_hour_only(self, store):
        report = harvest.harvest(store, env=ON, capture=FakeCapture())
        assert report.idle
        assert not harvest.is_due(store.root, {**ON, "PATH": ""}, now=report.started_epoch + 60)
        assert harvest._skip_reason(store.root, ON, report.started_epoch + 2 * 3600) is None

    def test_resummarize_gets_the_runs_env(self, store):
        h = summarized_session(store, "s1", [[BLOCK], [BLOCK]])
        h.seal_segment(99, "session_end", index=2)
        seen = []
        harvest.harvest(store, env={**ON, "MARK": "1"}, capture=FakeCapture(),
                        resummarize=lambda hh, i, e: seen.append(e.get("MARK")) or "x")
        assert seen == ["1"]
