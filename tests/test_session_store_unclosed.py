"""Tests for unclosed sessions (lib/claudna/session_store/unclosed.py) — phase 3 plan §3.

What these guard:

* **Only the dead are closed.** A session is closed as ``abandoned`` only when
  it is open, idle past the threshold, and its recorded ``claude`` process is
  gone. A live pid, a recent event, or no recorded pid at all keeps it open.
* **``abandon``** seals the open segment at the transcript's size, closes the
  session, and hands the sealed segment back to be summarized.
* **The sweep is bounded and cheap on the hook path**: at most ``SWEEP_LIMIT``
  sessions, oldest first; SessionStart checks one marker and spawns it detached.
"""

from __future__ import annotations

import json
import os
import time

import pytest
from conftest import ACTOR, CLI_ENV, ORIGIN, fire

from claudna.session_store import boundaries, unclosed
from claudna.session_store.cli import main

DAY = 24 * 3600
DEAD, LIVE = 4001, 4002


def alive(pid: int) -> bool:
    return pid == LIVE


def open_session(store, tmp_path, sid, *, pid=DEAD, idle_s=2 * DAY, size=40):
    transcript = tmp_path / f"{sid}.jsonl"
    transcript.write_text("x" * size)
    h = store.session(sid)
    h.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path=str(transcript), claude_pid=pid)
    h.open_segment("session_open", 0)
    then = time.time() - idle_s
    os.utime(h.paths.lifecycle, (then, then))
    os.utime(transcript, (then, then))
    return h


def status(handle) -> tuple[str, str | None]:
    doc = json.loads(handle.paths.session_json.read_text())
    return doc["status"], doc["close_reason"]


class TestIsUnclosed:
    def test_open_idle_and_dead_is_unclosed(self, store, tmp_path):
        assert unclosed.is_unclosed(open_session(store, tmp_path, "s1"), {}, alive=alive)

    @pytest.mark.parametrize("kwargs", [{"pid": LIVE}, {"idle_s": 3600}, {"pid": None}])
    def test_a_live_pid_a_recent_event_or_no_pid_keeps_it_open(self, store, tmp_path, kwargs):
        assert not unclosed.is_unclosed(open_session(store, tmp_path, "s1", **kwargs), {}, alive=alive)

    def test_a_closed_session_is_not_unclosed(self, store, tmp_path):
        h = open_session(store, tmp_path, "s1")
        h.close_session("other")
        then = time.time() - 2 * DAY
        os.utime(h.paths.lifecycle, (then, then))
        assert not unclosed.is_unclosed(h, {}, alive=alive)

    def test_a_transcript_written_recently_keeps_it_open(self, store, tmp_path):
        h = open_session(store, tmp_path, "s1")
        (tmp_path / "s1.jsonl").touch()  # the lifecycle log is old, but the session is still writing
        assert not unclosed.is_unclosed(h, {}, alive=alive)

    def test_the_threshold_is_configurable_but_never_under_an_hour(self, store, tmp_path):
        h = open_session(store, tmp_path, "s1", idle_s=3 * 3600)
        assert unclosed.is_unclosed(h, {unclosed.AFTER_ENV: "2"}, alive=alive)
        assert not unclosed.is_unclosed(h, {unclosed.AFTER_ENV: "4"}, alive=alive)
        assert unclosed.after_s({unclosed.AFTER_ENV: "0"}) == 3600
        assert unclosed.after_s({unclosed.AFTER_ENV: "junk"}) == unclosed.DEFAULT_AFTER_H * 3600
        assert unclosed.after_s({unclosed.AFTER_ENV: "nan"}) == unclosed.DEFAULT_AFTER_H * 3600

    def test_pid_alive_reads_the_process_table(self):
        assert unclosed.pid_alive(os.getpid())
        assert not unclosed.pid_alive(2**22 + 12345)  # above Linux's pid_max default: never a live process


class TestAbandon:
    def test_it_seals_at_the_transcript_size_and_closes_as_abandoned(self, store, tmp_path):
        h = open_session(store, tmp_path, "s1", size=40)
        assert unclosed.abandon(h) == 1
        seal = h.boundary(1).last_seal["data"]
        assert (seal["end"], seal["sealed_by"]) == (40, "abandoned")
        assert status(h) == ("closed", "abandoned")

    def test_an_already_sealed_segment_is_not_resealed(self, store, tmp_path):
        h = open_session(store, tmp_path, "s1")
        h.seal_segment(10, "precompact")
        assert unclosed.abandon(h) is None and h.boundary(1).last_seal["data"]["end"] == 10

    def test_a_session_that_is_not_open_is_refused(self, store, tmp_path):
        h = open_session(store, tmp_path, "s1")
        h.close_session("other")
        with pytest.raises(ValueError, match="not open"):
            unclosed.abandon(h)

    def test_a_resume_reopens_an_abandoned_session(self, store, tmp_path):
        h = open_session(store, tmp_path, "s1")
        unclosed.abandon(h)
        h.open_session("resume", actor=ACTOR, origin=ORIGIN, transcript_path=None, claude_pid=LIVE)
        assert status(h) == ("open", None)


class TestSweep:
    def test_it_closes_only_the_unclosed_and_summarizes_each_seal(self, store, tmp_path):
        dead = open_session(store, tmp_path, "dead")
        open_session(store, tmp_path, "live", pid=LIVE)
        open_session(store, tmp_path, "recent", idle_s=60)
        closed = []
        report = unclosed.sweep(store, {}, alive=alive, close=lambda h, pid: closed.append(h.sid) or unclosed.abandon(h, pid))
        assert report.closed == closed == ["dead"] and status(dead)[1] == "abandoned"
        assert status(store.session("live"))[0] == status(store.session("recent"))[0] == "open"

    def test_it_is_bounded_and_takes_the_oldest_first(self, store, tmp_path):
        for n in range(unclosed.SWEEP_LIMIT + 2):
            open_session(store, tmp_path, f"s{n}", idle_s=(2 + n) * DAY)
        report = unclosed.sweep(store, {}, alive=alive)
        assert report.closed == [f"s{n}" for n in range(unclosed.SWEEP_LIMIT + 1, 1, -1)]

    def test_a_dry_run_writes_nothing(self, store, tmp_path):
        h = open_session(store, tmp_path, "s1")
        assert unclosed.sweep(store, {}, alive=alive, dry_run=True).closed == ["s1"]
        assert status(h) == ("open", None)

    def test_one_bad_session_never_stops_the_sweep(self, store, tmp_path, monkeypatch):
        open_session(store, tmp_path, "a", idle_s=3 * DAY)
        open_session(store, tmp_path, "b", idle_s=2 * DAY)
        report = unclosed.sweep(store, {}, alive=alive, close=lambda h, pid: 1 / 0 if h.sid == "a" else unclosed.abandon(h, pid))
        assert report.closed == ["b"] and report.errors[0].startswith("a: ZeroDivisionError")

    def test_a_held_lock_skips_the_run(self, store, tmp_path):
        from claudna.session_store.fsio import ensure_dir, exclusive_lock

        open_session(store, tmp_path, "s1")
        with exclusive_lock(ensure_dir(store.root / "hooks") / ".sweep.lock"):
            assert unclosed.sweep(store, {}, alive=alive).closed == []


@pytest.mark.usefixtures("quiet_hooks")
class TestHookSpawnsTheSweep:
    def test_at_most_once_per_interval(self, store, tmp_path, monkeypatch):
        spawned = []
        monkeypatch.setattr(boundaries, "spawn_sweep", lambda root, env: spawned.append(root))
        fire(store, "SessionStart", "s1", tmp_path, source="startup")
        fire(store, "SessionStart", "s2", tmp_path, source="startup")
        assert spawned == [store.root]
        old = time.time() - unclosed.SWEEP_INTERVAL_H * 3600 - 1
        os.utime(store.root / "hooks" / "unclosed-sweep.last", (old, old))
        fire(store, "SessionStart", "s3", tmp_path, source="startup")
        assert len(spawned) == 2

    def test_the_marker_is_private(self, store, tmp_path):
        fire(store, "SessionStart", "s1", tmp_path, source="startup")
        assert (store.root / "hooks" / "unclosed-sweep.last").stat().st_mode & 0o077 == 0

    def test_a_hook_payload_cannot_claim_abandoned(self, store, tmp_path):
        fire(store, "SessionStart", "s1", tmp_path, source="startup")
        assert fire(store, "SessionEnd", "s1", tmp_path, env=CLI_ENV, reason="abandoned") == "session closed (other)"

    def test_the_sweep_drops_stale_clear_links(self, store, tmp_path):
        from claudna.session_store import lineage

        lineage.write_link(store.root, 99, sid="gone", chain_id="gone")
        old = time.time() - lineage.LINK_TTL_S - 5
        os.utime(store.root / "links" / "99.json", (old, old))
        unclosed.sweep(store, {}, alive=alive)
        assert not (store.root / "links" / "99.json").exists()


class TestResumeRace:
    """#383 review: the check and the writes happen under one lock, keyed on the dead owner's pid."""

    def test_a_session_resumed_after_it_was_judged_unclosed_is_left_open(self, store, tmp_path):
        h = open_session(store, tmp_path, "s1")
        owner = unclosed.unclosed_owner(h, {}, alive=alive)
        assert owner == DEAD
        h.open_session("resume", actor=ACTOR, origin=ORIGIN, transcript_path=None, claude_pid=LIVE)  # the race
        with pytest.raises(ValueError, match="resumed by another process"):
            unclosed.abandon(h, owner)
        assert status(h) == ("open", None) and not h.boundary(h.current_segment()).sealed

    def test_the_sweep_passes_the_owner_it_judged(self, store, tmp_path):
        open_session(store, tmp_path, "s1")
        owners = []
        unclosed.sweep(store, {}, alive=alive, close=lambda h, pid: owners.append(pid))
        assert owners == [DEAD]


class TestCli:
    def test_seal_closes_and_summarizes(self, store, tmp_path, monkeypatch, capsys):
        h = open_session(store, tmp_path, "s1", pid=LIVE)  # seal by hand works on any open session
        summarized = []
        monkeypatch.setattr(boundaries, "_summarize_segment", lambda h, i, facts, env, spawn: summarized.append(i))
        assert main(["seal", "s1", "--root", str(store.root)]) == 0
        assert status(h) == ("closed", "abandoned") and summarized == [1]
        assert "closed (abandoned)" in capsys.readouterr().out

    def test_seal_summarizes_a_segment_a_precompact_already_sealed(self, store, tmp_path, monkeypatch):
        h = open_session(store, tmp_path, "s1")
        h.seal_segment(10, "precompact")  # the crash came before SessionStart(compact) summarized it
        summarized = []
        monkeypatch.setattr(boundaries, "_summarize_segment", lambda h, i, facts, env, spawn: summarized.append(i))
        assert main(["seal", "s1", "--root", str(store.root)]) == 0
        assert status(h) == ("closed", "abandoned") and summarized == [1]

    def test_seal_refuses_a_closed_session(self, store, tmp_path, capsys):
        h = open_session(store, tmp_path, "s1")
        h.close_session("other")
        assert main(["seal", "s1", "--root", str(store.root)]) == 1
        assert "not open" in capsys.readouterr().err

    def test_sweep_dry_run_lists_candidates(self, store, tmp_path, capsys):
        open_session(store, tmp_path, "s1", pid=2**22 + 12345)  # a pid no process has
        assert main(["sweep", "--dry-run", "--root", str(store.root)]) == 0
        assert json.loads(capsys.readouterr().out)["closed"] == ["s1"]


def test_the_sweep_ignores_the_spawning_sessions_summary_override(store, tmp_path, monkeypatch, capsys):
    """#383 review: a bot's CLAUDNA_SESSION_SUMMARY=1 must not spend on sessions that never opted in."""
    open_session(store, tmp_path, "s1", pid=2**22 + 12345)  # a pid no process has; OPTED out (no harvest choice)
    seen = []
    monkeypatch.setattr(boundaries, "_summarize_segment", lambda h, i, facts, env, spawn: seen.append(dict(env)))
    monkeypatch.setenv("CLAUDNA_SESSION_SUMMARY", "1")
    assert main(["sweep", "--root", str(store.root)]) == 0
    assert json.loads(capsys.readouterr().out)["closed"] == ["s1"]
    assert seen and "CLAUDNA_SESSION_SUMMARY" not in seen[0]
