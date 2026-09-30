"""Tests for clear lineage (lib/claudna/session_store/lineage.py and its use in boundaries.py) — spec §4.3.

What these guard: a ``/clear`` links the new session to the one it cleared
(``parent_sid``, one ``chain_id`` for the whole chain, ``session.child_linked``
in the parent's log), through a link keyed on the ``claude`` pid that is used
once, only while fresh, and never for its own session. No link, no lineage.
"""

from __future__ import annotations

import os
import time

import pytest
from conftest import CLI_ENV
from conftest import fire as fire_hook
from conftest import session_doc as session

from claudna.session_store import lineage

pytestmark = pytest.mark.usefixtures("quiet_hooks")
PID = 4242


def fire(store, event, sid, tmp_path, pid=PID, **fields):
    """A hook whose claude pid is ``pid`` (injected, as the walk or ``$CLAUDE_PID`` would find it)."""
    return fire_hook(store, event, sid, tmp_path, find_pid=lambda: pid, **fields)


class TestClearLineage:
    def test_a_clear_links_the_new_session_to_the_one_it_cleared(self, store, tmp_path):
        fire(store, "SessionStart", "s1", tmp_path, source="startup")
        fire(store, "SessionEnd", "s1", tmp_path, reason="clear")
        fire(store, "SessionStart", "s2", tmp_path, source="clear")
        child, parent = session(store, "s2"), session(store, "s1")
        assert (child["parent_sid"], child["chain_id"]) == ("s1", "s1")
        assert parent["children"] == ["s2"]
        assert not (store.root / "links" / f"{PID}.json").exists()  # consumed

    def test_a_chain_of_clears_keeps_one_root(self, store, tmp_path):
        fire(store, "SessionStart", "s1", tmp_path, source="startup")
        for prev, nxt in (("s1", "s2"), ("s2", "s3"), ("s3", "s4")):
            fire(store, "SessionEnd", prev, tmp_path, reason="clear")
            fire(store, "SessionStart", nxt, tmp_path, source="clear")
        assert [session(store, s)["chain_id"] for s in ("s1", "s2", "s3", "s4")] == ["s1"] * 4
        assert session(store, "s4")["parent_sid"] == "s3"

    def test_no_link_means_no_lineage(self, store, tmp_path):
        fire(store, "SessionStart", "s2", tmp_path, source="clear")
        assert (session(store, "s2")["parent_sid"], session(store, "s2")["chain_id"]) == (None, "s2")

    def test_another_claudes_link_is_not_taken(self, store, tmp_path):
        fire(store, "SessionStart", "s1", tmp_path, source="startup")
        fire(store, "SessionEnd", "s1", tmp_path, reason="clear")
        fire(store, "SessionStart", "s2", tmp_path, pid=PID + 1, source="clear")
        assert session(store, "s2")["parent_sid"] is None
        assert (store.root / "links" / f"{PID}.json").exists()

    def test_a_non_clear_end_leaves_no_link(self, store, tmp_path):
        fire(store, "SessionStart", "s1", tmp_path, source="startup")
        fire(store, "SessionEnd", "s1", tmp_path, reason="prompt_input_exit")
        assert not (store.root / "links").exists() or not any((store.root / "links").iterdir())

    def test_no_claude_pid_means_no_link_and_no_lineage(self, store, tmp_path):
        fire(store, "SessionStart", "s1", tmp_path, source="startup")
        fire(store, "SessionEnd", "s1", tmp_path, pid=None, reason="clear")
        fire(store, "SessionStart", "s2", tmp_path, pid=None, source="clear")
        assert session(store, "s2")["parent_sid"] is None

    def test_a_deleted_parent_is_not_recreated(self, store, tmp_path):
        lineage.write_link(store.root, PID, sid="gone", chain_id="gone")
        fire(store, "SessionStart", "s2", tmp_path, source="clear")
        assert session(store, "s2")["parent_sid"] == "gone" and not store.session("gone").exists()


class TestLinks:
    def test_a_stale_link_is_ignored_and_consumed(self, tmp_path):
        lineage.write_link(tmp_path, PID, sid="s1", chain_id="s1")
        assert lineage.take_link(tmp_path, PID, sid="s2", now=time.time() + lineage.LINK_TTL_S + 1) is None
        assert not (tmp_path / "links" / f"{PID}.json").exists()

    def test_a_link_is_never_taken_by_the_session_that_wrote_it(self, tmp_path):
        lineage.write_link(tmp_path, PID, sid="s1", chain_id="s1")
        assert lineage.take_link(tmp_path, PID, sid="s1") is None

    def test_the_sweep_removes_only_stale_links(self, tmp_path):
        lineage.write_link(tmp_path, 1, sid="a", chain_id="a")
        lineage.write_link(tmp_path, 2, sid="b", chain_id="b")
        old = time.time() - lineage.LINK_TTL_S - 5
        os.utime(tmp_path / "links" / "1.json", (old, old))
        assert lineage.sweep_links(tmp_path) == 1 and (tmp_path / "links" / "2.json").exists()

    def test_links_are_private(self, tmp_path):
        lineage.write_link(tmp_path, PID, sid="s1", chain_id="s1")
        assert (tmp_path / "links").stat().st_mode & 0o077 == 0
        assert (tmp_path / "links" / f"{PID}.json").stat().st_mode & 0o077 == 0


class TestClaudePid:
    def test_the_walk_stops_at_the_first_ancestor_named_claude(self, monkeypatch):
        tree = {30: (20, "python3"), 20: (10, "sh"), 10: (1, "claude")}
        monkeypatch.setattr(lineage, "_parent", lambda pid: tree.get(pid))
        assert lineage.claude_pid(30) == 10

    def test_no_claude_ancestor_is_none(self, monkeypatch):
        tree = {30: (20, "python3"), 20: (1, "bash")}
        monkeypatch.setattr(lineage, "_parent", lambda pid: tree.get(pid))
        assert lineage.claude_pid(30) is None


class TestLinksKeyOnClaudePid:
    """The link is keyed on ``$CLAUDE_PID`` (the same value the nested-child guard records);
    the ancestor walk is only the fallback for a Claude Code that doesn't export it."""

    def fire(self, store, event, sid, tmp_path, env, **fields):
        return fire_hook(store, event, sid, tmp_path, env={**CLI_ENV, **env}, **fields)

    def test_a_clear_links_through_claude_pid_without_walking(self, store, tmp_path, monkeypatch):
        monkeypatch.setattr(lineage, "claude_pid", lambda start=None: pytest.fail("walked the process tree"))
        env = {"CLAUDE_PID": "777"}
        self.fire(store, "SessionStart", "s1", tmp_path, env, source="startup")
        self.fire(store, "SessionEnd", "s1", tmp_path, env, reason="clear")
        assert (store.root / "links" / "777.json").exists()
        self.fire(store, "SessionStart", "s2", tmp_path, env, source="clear")
        assert session(store, "s2")["parent_sid"] == "s1"

    def test_another_claude_pid_does_not_take_the_link(self, store, tmp_path):
        self.fire(store, "SessionStart", "s1", tmp_path, {"CLAUDE_PID": "777"}, source="startup")
        self.fire(store, "SessionEnd", "s1", tmp_path, {"CLAUDE_PID": "777"}, reason="clear")
        self.fire(store, "SessionStart", "s2", tmp_path, {"CLAUDE_PID": "778"}, source="clear")
        assert session(store, "s2")["parent_sid"] is None

    def test_without_claude_pid_the_walk_is_the_fallback(self, store, tmp_path, monkeypatch):
        monkeypatch.setattr(lineage, "claude_pid", lambda start=None: 555)
        self.fire(store, "SessionStart", "s1", tmp_path, {}, source="startup")
        self.fire(store, "SessionEnd", "s1", tmp_path, {}, reason="clear")
        self.fire(store, "SessionStart", "s2", tmp_path, {}, source="clear")
        assert session(store, "s2")["parent_sid"] == "s1"
