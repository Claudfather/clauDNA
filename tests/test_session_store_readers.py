"""Tests for the rollup (rollup.py, spec §6.7) and the readers (readers.py, spec §8).

What these guard:

* **The rollup's merge rules.** Title, intent and outcome come from the latest
  segment; arc, done, blocks and procedures are a deduplicated union keeping
  ``from_seg``; in_progress and next are the latest segment's only. A stale
  ``done`` summary (the segment was re-sealed) is left out, and what a retired
  segment contributed survives it.
* **Readers are read-only and trust only valid projections.** A missing or
  corrupt ``session.json`` is folded from the log; nothing is written.
* **list / show / timeline / failures** return what the store holds, filtered
  and ordered as documented, and the CLI prints it as text or JSON.
"""

from __future__ import annotations

import json

import pytest
from conftest import ACTOR, ORIGIN, complete_segment, segment_summary

from claudna.session_store import readers, retention, rollup
from claudna.session_store.cli import main

BLOCK_A = {"home": "entity", "subject_hint": {"name": "staging DB", "kind": "service", "aliases": []},
           "claim": "The staging DB resets nightly.", "asserted_by": "user", "tags": []}
BLOCK_B = {"home": "entity", "subject_hint": {"name": "CI", "kind": "service", "aliases": []},
           "claim": "CI runs on Python 3.9 too.", "asserted_by": "agent", "tags": []}


def summary(sid, index, *, title, blocks, end, **kw):
    return segment_summary(sid, index, blocks, title=title, end=end, **kw)


def session_with(store, sid, segments, *, repo="webapp", bot=None, close=True):
    """``segments``: a list of (summary kwargs or None) — None leaves that segment unsummarized."""
    h = store.session(sid)
    actor = {**ACTOR, "kind": "bot", "bot_name": bot} if bot else ACTOR
    h.open_session("startup", actor=actor, origin={**ORIGIN, "repo": repo}, transcript_path="/t.jsonl")
    for i, kw in enumerate(segments, 1):
        h.open_segment("session_open" if i == 1 else "compact", (i - 1) * 100)
        h.seal_segment(i * 100, "precompact")
        if kw is not None:
            complete_segment(h, i, summary(sid, i, end=i * 100, **kw))
    if close:
        h.close_session("other")
    return h


class TestRollup:
    def test_the_merge_rules(self, store):
        h = session_with(store, "s1", [
            {"title": "first", "blocks": [BLOCK_A], "done": ["wrote the test"], "next_": ["old next"]},
            {"title": "second", "blocks": [BLOCK_A, BLOCK_B], "done": ["Wrote  the TEST", "shipped"],
             "next_": ["new next"], "outcome": "partial"},
        ])
        doc = rollup.refresh(h.paths)
        f = doc["fields"]
        assert (f["title"], f["outcome"]) == ("second", "partial")
        assert [b["claim"] for b in f["blocks"]] == [BLOCK_A["claim"], BLOCK_B["claim"]]
        assert [b["from_seg"] for b in f["blocks"]] == [1, 2]
        assert [d["text"] for d in f["done"]] == ["wrote the test", "shipped"]  # normalized dedup
        assert f["next"] == [{"text": "new next"}]  # latest only, no from_seg
        assert (doc["segments"], doc["through_seg"]) == ([1, 2], 2)
        assert json.loads(rollup.rollup_path(h.paths).read_text()) == doc

    def test_a_stale_done_summary_is_left_out(self, store):
        h = session_with(store, "s1", [{"title": "t", "blocks": [BLOCK_A]}], close=False)
        h.seal_segment(150, "precompact")  # re-sealed: the summary covers only [0, 100)
        assert rollup.refresh(h.paths) is None

    def test_nothing_to_roll_up(self, store):
        h = session_with(store, "s1", [None])
        assert rollup.refresh(h.paths) is None and not rollup.rollup_path(h.paths).exists()

    def test_a_retired_segments_contribution_survives(self, store):
        h = session_with(store, "s1", [{"title": "a", "blocks": [BLOCK_A]}, {"title": "b", "blocks": [BLOCK_B]}])
        retention.retire(h, [(1, "acked")])  # archives seg-001's summary, then removes its directory
        assert not h.paths.segment(1).dir.exists() and h.paths.archived_summary(1).is_file()
        doc = json.loads(rollup.rollup_path(h.paths).read_text())
        assert [b["claim"] for b in doc["fields"]["blocks"]] == [BLOCK_A["claim"], BLOCK_B["claim"]]
        assert doc["segments"] == [1, 2]

    def test_a_stale_summary_is_not_archived_on_retirement(self, store):
        h = session_with(store, "s1", [{"title": "stale", "blocks": [BLOCK_A]}], close=False)
        h.seal_segment(150, "precompact")  # re-sealed: the summary covers only [0, 100)
        h.close_session("other")
        assert retention.retire(h, [(1, "age")]) == [(1, "age")]
        assert not h.paths.archived_summary(1).exists() and rollup.refresh(h.paths) is None

    def test_a_segment_a_summarizer_holds_is_left_for_later(self, store):
        from claudna.session_store.fsio import exclusive_lock

        h = session_with(store, "s1", [{"title": "a", "blocks": [BLOCK_A]}, None])
        with exclusive_lock(h.paths.segment(1).dir / ".summarize.lock"):
            assert retention.retire(h, [(1, "acked")]) == []
        assert h.paths.segment(1).dir.is_dir()

    def test_show_computes_a_missing_rollup_without_writing_it(self, store):
        h = session_with(store, "s1", [{"title": "t", "blocks": [BLOCK_A]}])
        rollup.rollup_path(h.paths).unlink(missing_ok=True)
        assert readers.show(store, "s1")["rollup"]["fields"]["title"] == "t"
        assert not rollup.rollup_path(h.paths).exists()

    def test_the_summarizer_refreshes_it(self, store, tmp_path):
        from claudna.session_store import summarize
        from test_session_store_summarize import DIALOGUE, FakeRunner, OPTED_IN, write_transcript

        path = tmp_path / "t.jsonl"
        write_transcript(path, DIALOGUE)
        h = store.session("s2")
        h.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path=str(path), harvest=OPTED_IN)
        h.open_segment("session_open", 0)
        h.seal_segment(path.stat().st_size, "precompact")
        summarize.summarize(h, 1, env={}, runner=FakeRunner())
        assert json.loads(rollup.rollup_path(h.paths).read_text())["fields"]["title"] == "Fix the flaky auth test"


class TestReaders:
    def test_list_is_newest_first_and_filters(self, store):
        session_with(store, "old", [None], repo="api")
        session_with(store, "new", [{"title": "the new one", "blocks": []}], repo="webapp", bot="scout")
        rollup.refresh(store.session("new").paths)
        rows = readers.list_sessions(store)
        assert rows[0]["opened_at"] >= rows[1]["opened_at"] and {r["sid"] for r in rows} == {"new", "old"}
        assert [r["sid"] for r in readers.list_sessions(store, repo="api")] == ["old"]
        assert [r["sid"] for r in readers.list_sessions(store, bot="scout")] == ["new"]
        assert next(r for r in rows if r["sid"] == "new")["title"] == "the new one"
        assert readers.list_sessions(store, since="2999-01-01") == []

    def test_a_corrupt_projection_is_folded_from_the_log_and_never_written(self, store):
        h = session_with(store, "s1", [None, None])
        h.paths.session_json.write_text("{ not json")
        (row,) = readers.list_sessions(store)
        assert (row["status"], row["segments"]) == ("closed", 2)
        assert h.paths.session_json.read_text() == "{ not json"

    def test_show_has_lineage_segments_and_the_rollup(self, store):
        h = session_with(store, "s1", [{"title": "t", "blocks": [BLOCK_A]}])
        h.link_child("s2")
        rollup.refresh(h.paths)
        doc = readers.show(store, "s1")
        assert doc["session"]["children"] == ["s2"] and [s["index"] for s in doc["segments"]] == [1]
        assert doc["rollup"]["fields"]["title"] == "t"
        with pytest.raises(LookupError):
            readers.show(store, "nope")

    def test_the_timeline_merges_both_logs_in_order(self, store):
        h = session_with(store, "s1", [None], close=False)
        h.append("prompt.submitted", {"prompt_id": "p", "chars": 3})
        h.append("tool.failed", {"tool": "Bash", "signature": "Bash: boom", "exit_code": 1})
        h.close_session("other")
        kinds = [e["kind"] for e in readers.timeline(store, "s1")]
        assert kinds == ["session.opened", "segment.opened", "segment.sealed", "prompt.submitted", "tool.failed",
                         "session.closed"]
        assert all(a["ts"] <= b["ts"] for a, b in zip(readers.timeline(store, "s1"), readers.timeline(store, "s1")[1:]))

    def test_failures_group_by_signature_across_sessions(self, store):
        for sid in ("a", "b"):
            h = session_with(store, sid, [None], close=False)
            h.append("tool.failed", {"tool": "Bash", "signature": "Bash: gh: not logged in", "exit_code": 4,
                                     "tool_use_id": f"toolu_{sid}"})
        store.session("a").append("tool.failed", {"tool": "Bash", "signature": "Bash: other", "exit_code": 1})
        (top, other) = readers.failures(store, group=True)
        assert (top["signature"], top["count"], top["sessions"], top["exit_codes"]) == \
            ("Bash: gh: not logged in", 2, 2, [4])
        assert top["last"]["tool_use_id"] in ("toolu_a", "toolu_b") and other["count"] == 1
        assert [r["signature"] for r in readers.failures(store, "b")] == ["Bash: gh: not logged in"]

    @pytest.mark.parametrize("since, ok", [("7d", True), ("12h", True), ("2w", True), ("2026-01-01", True),
                                           ("yesterday", False)])
    def test_since(self, since, ok):
        if ok:
            assert readers.since_cutoff(since).endswith("Z")
        else:
            with pytest.raises(ValueError):
                readers.since_cutoff(since)


class TestCli:
    def test_the_verbs_print_text_and_json(self, store, capsys):
        h = session_with(store, "s1", [{"title": "the title", "blocks": [BLOCK_A]}], close=False)
        h.append("tool.failed", {"tool": "Bash", "signature": "Bash: boom", "exit_code": 1})
        rollup.refresh(h.paths)
        root = ["--root", str(store.root)]
        assert main(["list", *root]) == 0 and "the title" in capsys.readouterr().out
        assert main(["show", "s1", *root]) == 0 and BLOCK_A["claim"] in capsys.readouterr().out
        assert main(["timeline", "s1", *root]) == 0 and "tool.failed" in capsys.readouterr().out
        assert main(["failures", "--group", *root]) == 0 and "1x" in capsys.readouterr().out
        assert main(["failures", "--json", *root]) == 0
        assert json.loads(capsys.readouterr().out)[0]["signature"] == "Bash: boom"

    def test_an_unknown_session_is_an_error(self, store, capsys):
        assert main(["show", "nope", "--root", str(store.root)]) == 1
        assert "no session nope" in capsys.readouterr().err


def test_a_summarizer_for_a_retired_segment_is_ignored(store):
    from claudna.session_store import summarize

    h = session_with(store, "s1", [{"title": "a", "blocks": [BLOCK_A]}])
    retention.retire(h, [(1, "age")])
    assert summarize.summarize(h, 1, runner=lambda *a, **k: pytest.fail("no model call")) == "ignored: no segment 1"
