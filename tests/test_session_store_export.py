"""Tests for the export door (export.py, spec §8) and retention (retention.py, spec §9).

What these guard:

* **Export** hands a consumer each final, done segment it hasn't acked, with a
  ``next`` cursor that stops at the first segment still in flight and passes
  skipped ones. Private sessions are never exported; acks never move back.
* **Retention** retires a final segment once every registered consumer acked
  it (after the 7-day floor) or past the 30-day cap, logs ``segment.retired``
  first, keeps its knowledge in the rollup, never touches a current segment,
  and never lets an index be reused.
"""

from __future__ import annotations

import json
import time

import pytest
from conftest import ACTOR, ORIGIN, complete_segment, segment_summary
from test_session_store_readers import BLOCK_A

from claudna.session_store import export, fsio, retention, rollup
from claudna.session_store.cli import check_session, main

DAY = 86400


def session_with(store, sid, statuses, *, close=True, private=False):
    """One segment per entry: "done", "skipped", "pending" or None (never summarized)."""
    h = store.session(sid)
    h.open_session("startup", actor=ACTOR, origin={**ORIGIN, "repo": "webapp"}, transcript_path="/t.jsonl")
    if private:
        h.set_private(True)
    for i, status in enumerate(statuses, 1):
        h.open_segment("session_open" if i == 1 else "compact", (i - 1) * 100)
        h.seal_segment(i * 100, "precompact")
        if status == "done":
            complete_segment(h, i, segment_summary(sid, i, [BLOCK_A], title=f"t{i}", end=i * 100))
        elif status == "skipped":
            h.append("summary.skipped", {"reason": "trivial"}, seg=i)
        elif status == "pending":
            h.append("summary.requested", {"job_id": f"j{i}"}, seg=i)
    if close:
        h.close_session("other")
    return h


class TestExport:
    def test_items_and_the_next_cursor(self, store):
        session_with(store, "s1", ["done", "skipped", "done", "pending", "done"])
        env = export.export(store, "claudron")
        assert env["schema"] == "claudna.export/1" and env["consumer"] == "claudron"
        assert [(i["sid"], i["seg"]) for i in env["items"]] == [("s1", 1), ("s1", 3)]  # stops at the pending one
        assert env["next"] == {"s1": 3}
        item = env["items"][0]
        assert item["session"]["sid"] == "s1" and item["summary"]["journey"]["title"] == "t1"
        assert set(item["session"]) == set(export.SESSION_FIELDS)

    def test_the_current_segment_of_an_open_session_waits(self, store):
        session_with(store, "s1", ["done", "done"], close=False)
        assert [i["seg"] for i in export.export(store, "c")["items"]] == [1]

    def test_an_ack_moves_the_cursor_forward_only(self, store):
        session_with(store, "s1", ["done", "done"])
        assert export.ack(store, "claudron", "s1", 1) == 1
        assert [i["seg"] for i in export.export(store, "claudron")["items"]] == [2]
        assert export.ack(store, "claudron", "s1", 0) == 1  # never back
        assert export.export(store, "other")["next"] == {"s1": 2}  # each consumer has its own cursor

    def test_since_seg_and_limit(self, store):
        session_with(store, "s1", ["done", "done", "done"])
        assert [i["seg"] for i in export.export(store, "c", since_seg=1)["items"]] == [2, 3]
        env = export.export(store, "c", limit=1)
        assert len(env["items"]) == 1 and env["next"] == {"s1": 1}

    def test_private_sessions_are_never_exported(self, store):
        session_with(store, "p", ["done"], private=True)
        assert export.export(store, "c") == {"schema": "claudna.export/1", "consumer": "c", "items": [], "next": {}}

    @pytest.mark.parametrize("name", ["", "Claudron", "a/b", "x" * 40])
    def test_consumer_names_are_checked(self, store, name):
        with pytest.raises(ValueError):
            export.export(store, name)

    def test_the_cli(self, store, capsys):
        session_with(store, "s1", ["done"])
        root = ["--root", str(store.root)]
        assert main(["export", "--consumer", "claudron", "--json", *root]) == 0
        assert json.loads(capsys.readouterr().out)["next"] == {"s1": 1}
        assert main(["export", "--consumer", "claudron", "--ack", "--sid", "s1", "--through", "1", *root]) == 0
        assert json.loads(capsys.readouterr().out)["through_seg"] == 1
        assert main(["export", "--consumer", "claudron", "--ack", "--sid", "s1", *root]) == 1
        assert "--ack needs" in capsys.readouterr().err


class TestRetention:
    def later(self, days):
        return time.time() + days * DAY

    def test_age_cap_retires_final_segments_and_logs_first(self, store):
        h = session_with(store, "s1", ["done", "done"])
        rollup.refresh(h.paths)
        report = retention.sweep(store, {}, now=self.later(31))
        assert report.retired == ["s1/seg-001 (age)", "s1/seg-002 (age)"] and h.paths.segment_indices() == []
        kinds = [json.loads(line)["kind"] for line in h.paths.lifecycle.read_text().splitlines()]
        assert kinds.count("segment.retired") == 2
        assert json.loads(h.paths.session_json.read_text())["segments"] == {"count": 0, "open": None, "retired": 2}
        assert json.loads(rollup.rollup_path(h.paths).read_text())["fields"]["blocks"][0]["claim"] == BLOCK_A["claim"]
        assert check_session(h).problems == []

    def test_acked_segments_wait_for_the_floor(self, store):
        h = session_with(store, "s1", ["done", "done"])
        h.ack("harvest", 1)
        assert retention.due(h, {}, now=self.later(1)) == []
        assert retention.due(h, {}, now=self.later(8)) == [(1, "acked")]

    def test_every_registered_consumer_must_have_acked(self, store):
        h = session_with(store, "s1", ["done", "done"])
        h.ack("harvest", 2)
        h.ack("claudron", 1)  # registered, but behind on seg 2
        assert retention.due(h, {}, now=self.later(8)) == [(1, "acked")]

    def test_no_registered_consumer_means_the_cap_alone(self, store):
        h = session_with(store, "s1", ["done"])
        assert retention.due(h, {}, now=self.later(8)) == []
        assert retention.due(h, {retention.CAP_ENV: "5"}, now=self.later(8)) == [(1, "age")]

    def test_the_current_segment_of_an_open_session_is_never_retired(self, store):
        h = session_with(store, "s1", ["done", "done"], close=False)
        assert retention.due(h, {}, now=self.later(99)) == [(1, "age")]

    def test_an_index_is_never_reused_after_retirement(self, store):
        h = session_with(store, "s1", ["done", "done"], close=False)
        retention.sweep(store, {}, now=self.later(31))
        assert h.open_segment("compact", 200) == 3

    def test_the_limit_bounds_a_run(self, store):
        session_with(store, "s1", ["done", "done", "done"])
        assert len(retention.sweep(store, {}, now=self.later(31), limit=2).retired) == 2

    @pytest.mark.parametrize("value", ["nan", "inf", "-1", "junk"])
    def test_bad_settings_fall_back(self, value):
        assert fsio.env_number({retention.CAP_ENV: value}, retention.CAP_ENV, 30.0) == 30.0

    def test_the_sweep_verb_runs_retention(self, store, capsys, monkeypatch):
        session_with(store, "s1", ["done"]).ack("claudron", 1)
        monkeypatch.setenv(retention.FLOOR_ENV, "0")  # acked and no floor: due at once, whatever the clock
        assert main(["sweep", "--root", str(store.root)]) == 0
        assert json.loads(capsys.readouterr().out)["retention"]["retired"] == ["s1/seg-001 (acked)"]

    def test_a_cap_of_zero_means_no_age_cap(self, store):
        h = session_with(store, "s1", ["done"])
        assert retention.due(h, {retention.CAP_ENV: "0"}, now=time.time() + 365 * DAY) == []
        assert retention.due(h, {}, now=time.time() + 31 * DAY) == [(1, "age")]



class TestExportReviewFixes:
    """The full-range review: a summary that will never come, reserved names, and an ack's bound."""

    def failed_for_good(self, store, sid, *, harvest_on=True):
        h = store.session(sid)
        h.open_session("startup", actor=ACTOR, origin={**ORIGIN, "repo": "webapp"}, transcript_path="/t.jsonl",
                       harvest={"enabled": harvest_on, "vault": None})
        for i in (1, 2):
            h.open_segment("session_open" if i == 1 else "compact", (i - 1) * 100)
            h.seal_segment(i * 100, "precompact")
        h.append("summary.failed", {"job_id": "j1", "error": "bad", "retryable": False}, seg=1)
        complete_segment(h, 2, segment_summary(sid, 2, [BLOCK_A], end=200))
        h.close_session("other")
        return h

    def test_a_summary_that_failed_for_good_is_stepped_over(self, store):
        self.failed_for_good(store, "s1")
        env = export.export(store, "claudron")
        assert [(i["sid"], i["seg"]) for i in env["items"]] == [("s1", 2)] and env["next"] == {"s1": 2}

    def test_a_retryable_failure_waits_for_harvest_when_harvest_runs(self, store):
        h = self.failed_for_good(store, "s1")
        h.append("summary.failed", {"job_id": "j2", "error": "net", "retryable": True}, seg=1)
        assert export.export(store, "claudron")["items"] == []  # harvest will retry it: hold

    def test_without_harvest_nothing_retries_so_it_is_stepped_over(self, store):
        h = self.failed_for_good(store, "s1", harvest_on=False)
        h.append("summary.failed", {"job_id": "j2", "error": "net", "retryable": True}, seg=1)
        assert [i["seg"] for i in export.export(store, "claudron")["items"]] == [2]

    def test_the_stores_own_consumer_names_are_reserved(self, store):
        session_with(store, "s1", ["done"])
        with pytest.raises(ValueError, match="reserved"):
            export.ack(store, "harvest", "s1", 1)
        with pytest.raises(ValueError, match="reserved"):
            export.export(store, "harvest")

    def test_an_ack_past_the_last_segment_is_refused(self, store):
        h = session_with(store, "s1", ["done", "done"])
        with pytest.raises(ValueError, match="past"):
            export.ack(store, "claudron", "s1", 3)
        assert export.ack(store, "claudron", "s1", 2) == 2 and h.cursor("claudron") == 2
