"""Tests for lib/claudna/session_store — the session store core (spec phase 1).

What these guard, in the order the spec states the invariants:

* **Logs are truth; JSON is projection.** Projections are rebuilt from logs and
  a golden fixture pins the fold byte-for-byte. Deleting every projection and
  rebuilding gives the same result.
* **The directory is the holder.** Segment indexes come from ``seg-NNN`` dirs;
  a crash between ``mkdir`` and the append still projects correctly.
* **Writers strict, readers lenient.** ``make_event`` rejects bad data; a torn
  line or a newer envelope in a log is skipped and counted, never fatal.
* **Private by default.** Every dir the store creates is 0700, every file 0600.
* **Schemas match code.** Every registry kind fits the envelope schema, the
  projection schemas' vocabularies match the registry's, every ``ts`` pattern is
  the envelope's, and every projection validates against its schema.
* **Incremental equals full.** The hot-path ``refresh`` produces exactly what a
  full ``rebuild`` does.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB = REPO_ROOT / "lib"
sys.path.insert(0, str(LIB))

from claudna.session_store import events as ev  # noqa: E402
from claudna.session_store import readers, retention, schema  # noqa: E402
from claudna.session_store.cli import check_session, main  # noqa: E402
from claudna.session_store.fsio import (  # noqa: E402
    append_jsonl,
    atomic_write_json,
    ensure_dir,
    exclusive_lock,
    read_jsonl,
)
from claudna.session_store.paths import (  # noqa: E402
    InvalidSessionId,
    parse_seg_dirname,
    seg_dirname,
    session_paths,
    state_root,
    validate_sid,
)
from claudna.session_store import project as project_module  # noqa: E402
from claudna.session_store.project import load_lifecycle, session_facts  # noqa: E402
from claudna.session_store.store import NotAppendable, SessionStore, StoreError  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "session-store" / "basic"
FIXTURE_SID = "5f0c2d1e-0000-4000-8000-000000000001"
OLDER_SESSION = FIXTURE / "older" / "session-0.26.json"  # what a 0.26 rebuild leaves: claudna.session/1
STORE_PKG = LIB / "claudna" / "session_store"

ACTOR = {"kind": "interactive", "fleet": None, "bot_id": None, "bot_name": None, "model": None, "entrypoint": "cli"}
ORIGIN = {"cwd": "/work", "repo": None, "branch": None, "head": None}


def opened(store: SessionStore, sid: str = "sess-1"):
    handle = store.session(sid)
    handle.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path="/t.jsonl")
    return handle


def prompt(handle, seg: int | None = None) -> dict:
    """Append one minimal prompt.submitted (to the current segment when ``seg`` is None)."""
    return handle.append("prompt.submitted", {"prompt_id": None, "chars": 1}, seg=seg)


def reopen(handle, transcript_path: str = "/t.jsonl") -> dict:
    """Record a resume of ``handle``'s session."""
    return handle.open_session("resume", actor=ACTOR, origin=ORIGIN, transcript_path=transcript_path)


def load(path: Path) -> dict:
    return json.loads(path.read_text())


# ── paths ────────────────────────────────────────────────────────────────────


class TestPaths:
    @pytest.mark.parametrize("sid", ["3fbbf216-f848-4d8b-b5b5-7839fc98b820", "a", "A.b_c-1", "a..b"])
    def test_accepts_safe_ids(self, sid):
        assert validate_sid(sid) == sid

    @pytest.mark.parametrize("sid", ["", "..", "../etc", "a/b", ".hidden", "abc\n", "ab\u0663", "x" * 200, None, 5])
    def test_rejects_ids_that_are_not_one_safe_path_component(self, sid):
        with pytest.raises(InvalidSessionId):
            validate_sid(sid)

    def test_segment_dirnames_round_trip_and_widen_past_999(self):
        assert seg_dirname(3) == "seg-003"
        assert seg_dirname(1234) == "seg-1234"
        assert parse_seg_dirname("seg-1234") == 1234
        for bad in ("seg-000", "segment-1", "seg-001\n", "seg-0002", "seg-02", "seg-\u0660\u0660\u0662"):
            assert parse_seg_dirname(bad) is None, bad
        with pytest.raises(ValueError):
            seg_dirname(0)
        with pytest.raises(ValueError):
            seg_dirname(True)

    def test_state_root_env_override_and_default(self, tmp_path):
        assert state_root({"CLAUDNA_STATE_DIR": str(tmp_path)}) == tmp_path
        assert state_root({}) == Path("~/.claudna").expanduser()
        with pytest.raises(ValueError, match="absolute"):
            state_root({"CLAUDNA_STATE_DIR": "relative/store"})


# ── fsio ─────────────────────────────────────────────────────────────────────


class TestFsio:
    def test_created_dirs_and_files_are_private_including_parents(self, tmp_path):
        leaf = ensure_dir(tmp_path / "a" / "b" / "c")
        for d in (tmp_path / "a", tmp_path / "a" / "b", leaf):
            assert stat.S_IMODE(d.stat().st_mode) == 0o700, d
        atomic_write_json(leaf / "x.json", {"k": 1})
        append_jsonl(leaf / "y.jsonl", {"k": 1})
        for f in (leaf / "x.json", leaf / "y.jsonl"):
            assert stat.S_IMODE(f.stat().st_mode) == 0o600, f

    def test_ensure_dir_never_chmods_an_existing_parent(self, tmp_path):
        tmp_path.chmod(0o755)
        ensure_dir(tmp_path / "child")
        assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o755

    def test_atomic_write_leaves_no_temp_files(self, tmp_path):
        atomic_write_json(tmp_path / "x.json", {"a": 1})
        atomic_write_json(tmp_path / "x.json", {"a": 2})
        assert load(tmp_path / "x.json") == {"a": 2}
        assert [p.name for p in tmp_path.iterdir()] == ["x.json"]

    def test_read_jsonl_skips_torn_and_non_object_lines(self, tmp_path):
        log = tmp_path / "log.jsonl"
        append_jsonl(log, {"n": 1})
        with log.open("a") as fh:
            fh.write('[1, 2]\n{"n": 2}\n{"torn": ')
        read = read_jsonl(log)
        assert [r["n"] for r in read.records] == [1, 2]
        assert read.skipped == 2
        assert read.lines == 4

    def test_missing_log_reads_as_empty(self, tmp_path):
        read = read_jsonl(tmp_path / "nope.jsonl")
        assert (read.records, read.skipped, read.lines, read.bytes) == ([], 0, 0, 0)

    def test_taking_a_lock_never_creates_directories(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            with exclusive_lock(tmp_path / "missing" / ".lock"):
                pass
        assert not (tmp_path / "missing").exists()



# ── events ───────────────────────────────────────────────────────────────────


class TestEvents:
    def test_make_event_builds_a_valid_envelope(self):
        e = ev.make_event("segment.opened", "s1", {"opened_by": "compact", "start": 10}, seg=2)
        assert e["v"] == ev.ENVELOPE_VERSION and e["seg"] == 2
        assert ev.classify(e) == "ok"
        assert schema.validate(e, schema.load("event")) == []

    @pytest.mark.parametrize(
        "kind,data,seg,needle",
        [
            ("nope.thing", {}, None, "unknown event kind"),
            ("segment.opened", {"opened_by": "compact", "start": 1}, None, "requires a segment"),
            ("session.closed", {"reason": "other"}, 1, "session-scope"),
            ("session.closed", {}, None, "data.reason is required"),
            ("session.closed", {"reason": "bored"}, None, "must be one of"),
            ("segment.opened", {"opened_by": "compact", "start": "10"}, 1, "wrong type"),
            ("segment.opened", {"opened_by": "compact", "start": True}, 1, "wrong type"),
        ],
    )
    def test_make_event_rejects_registry_violations(self, kind, data, seg, needle):
        with pytest.raises(ev.EventError, match=needle):
            ev.make_event(kind, "s1", data, seg=seg)

    @pytest.mark.parametrize(
        "kind,data,seg",
        [
            ("session.opened", {"source": "startup", "parent_sid": None, "chain_id": "s", "actor": {"kind": "x"},
                                "origin": ORIGIN, "transcript_path": None}, None),
            ("session.opened", {"source": "startup", "parent_sid": None, "chain_id": "s", "actor": ACTOR,
                                "origin": {}, "transcript_path": None}, None),
            ("segment.sealed", {"end": -1, "sealed_by": "precompact", "trigger": None}, 1),
            ("segment.opened", {"opened_by": "compact", "start": -1}, 1),
            ("prompt.submitted", {"prompt_id": None, "chars": -3}, 1),
        ],
    )
    def test_writers_reject_values_their_projections_would_reject(self, kind, data, seg):
        with pytest.raises(ev.EventError):
            ev.make_event(kind, "s1", data, seg=seg)

    def test_free_text_is_capped_not_rejected(self):
        e = ev.make_event("prompt.submitted", "s1", {"prompt_id": None, "chars": 9, "text": "t" * 1000}, seg=1)
        n = ev.make_event("summary.failed", "s1", {"job_id": "j", "error": "n" * 5000, "retryable": True}, seg=1)
        assert len(e["data"]["text"]) == 500 and len(n["data"]["error"]) == 200
        assert n["data"]["error"].endswith("…")

    def test_timestamps_are_utc_millisecond_z(self):
        assert re.match(schema.load("event")["properties"]["ts"]["pattern"], ev.now_ts())

    def test_readers_skip_newer_envelopes_and_unknown_kinds(self):
        base = ev.make_event("session.closed", "s1", {"reason": "other"})
        assert ev.classify({**base, "v": 2}) == "unknown"
        assert ev.classify({**base, "kind": "future.thing"}) == "unknown"
        assert ev.classify({**base, "ts": "yesterday"}) == "invalid"
        assert ev.classify({**base, "seg": 1}) == "invalid"
        assert ev.classify({**base, "data": {"reason": "bored"}}) == "invalid"


# ── store: segments and lifecycle ────────────────────────────────────────────


class TestStore:
    def test_open_session_records_the_agent_cli_only_when_given(self, store):
        codex = store.session("codex-1")
        codex.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path="/t.jsonl", agent_cli="codex")
        first = json.loads(codex.paths.lifecycle.read_text().splitlines()[0])
        assert first["data"]["agent_cli"] == "codex"
        plain = opened(store)
        assert "agent_cli" not in json.loads(plain.paths.lifecycle.read_text().splitlines()[0])["data"]
        assert session_facts(load_lifecycle(codex.paths).events).agent_cli == "codex"
        assert session_facts(load_lifecycle(plain.paths).events).agent_cli == "claude"

    def test_the_first_session_opened_decides_the_agent_cli(self, store):
        """Spec §6.4: a log from before 0.27 names none and is claude, whatever a later open records."""
        h = opened(store)
        h.open_session("resume", actor=ACTOR, origin=ORIGIN, transcript_path="/t.jsonl", agent_cli="codex")
        assert session_facts(load_lifecycle(h.paths).events).agent_cli == "claude"
        codex = store.session("codex-2")
        codex.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path="/t.jsonl", agent_cli="codex")
        codex.open_session("resume", actor=ACTOR, origin=ORIGIN, transcript_path="/t.jsonl", agent_cli="claude")
        assert session_facts(load_lifecycle(codex.paths).events).agent_cli == "codex"

    def test_segments_increment_from_the_directories(self, store):
        h = opened(store)
        assert h.current_segment() is None
        assert [h.open_segment("session_open", 0), h.open_segment("compact", 50),
                h.open_segment("compact", 90)] == [1, 2, 3]
        assert h.current_segment() == 3
        assert sorted(p.name for p in h.paths.dir.iterdir() if p.is_dir()) == ["seg-001", "seg-002", "seg-003"]

    def test_crash_between_mkdir_and_event_still_projects(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        h.paths.segment(2).dir.mkdir()  # the event for seg 2 was never written
        assert h.current_segment() == 2
        h.rebuild()
        seg2 = load(h.paths.segment(2).segment_json)
        assert (seg2["opened_by"], seg2["status"]) == ("unknown", "open")
        assert h.open_segment("compact", 70) == 3  # the next index still derives past it

    def test_reseal_moves_the_end_and_is_safe_to_repeat(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        h.seal_segment(100, "precompact", trigger="manual")
        h.seal_segment(140, "precompact", trigger="manual")  # first compaction was blocked
        seg = load(h.paths.segment(1).segment_json)
        assert seg["status"] == "sealed" and seg["transcript"]["range"] == {"start": 0, "end": 140}

    def test_a_lost_lifecycle_refresh_is_detected_and_healed(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        # a hook killed between appending the seal and refreshing
        append_jsonl(h.paths.lifecycle, ev.make_event("segment.sealed", h.sid,
                                                       {"end": 100, "sealed_by": "precompact", "trigger": "auto"}, seg=1))
        h.open_segment("compact", 100)
        h.close_session("other")
        seg1 = load(h.paths.segment(1).segment_json)
        assert (seg1["status"], seg1["sealed_by"], seg1["transcript"]["range"]["end"]) == ("sealed", "precompact", 100)

    def test_opening_a_segment_seals_an_unsealed_predecessor(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        h.open_segment("compact", 50)  # PreCompact was missed
        seg1 = load(h.paths.segment(1).segment_json)
        assert (seg1["status"], seg1["sealed_by"], seg1["transcript"]["range"]) == \
            ("sealed", "compact", {"start": 0, "end": 50})
        h.close_session("other")  # SessionEnd lost its seal, then the session resumes
        reopen(h, "/t.jsonl")
        h.open_segment("session_open", 80)
        assert load(h.paths.segment(2).segment_json)["sealed_by"] == "resume"
        assert load(h.paths.session_json)["segments"]["open"] == 3

    def test_activity_goes_only_to_the_current_segment_of_an_open_session(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        h.seal_segment(10, "precompact", trigger="manual")  # a blocked compaction: sealed, still current
        prompt(h, seg=1)
        h.seal_segment(30, "precompact", trigger="manual")  # the next PreCompact re-seals later
        h.open_segment("compact", 30)
        with pytest.raises(StoreError, match="superseded"):
            prompt(h, seg=1)
        h.close_session("other")
        with pytest.raises(StoreError, match="closed"):
            prompt(h, seg=2)
        assert load(h.paths.segment(1).segment_json)["counts"]["prompts"] == 1

    def test_a_resume_onto_a_new_transcript_seals_the_predecessor_at_the_old_files_end(self, store, tmp_path):
        old, new = tmp_path / "old.jsonl", tmp_path / "new.jsonl"
        old.write_bytes(b"x" * 200)
        new.write_bytes(b"")
        h = store.session("sess-1")
        h.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path=str(old))
        h.open_segment("session_open", 40)
        reopen(h, str(new))  # SessionEnd was lost; the resume writes a fresh transcript
        h.open_segment("session_open", 0)
        seg1 = load(h.paths.segment(1).segment_json)
        assert (seg1["transcript"]["path"], seg1["transcript"]["range"]) == (str(old), {"start": 40, "end": 200})

    def test_unknown_kind_is_an_event_error(self, store):
        with pytest.raises(ev.EventError, match="unknown event kind"):
            opened(store).append("no.such.kind", {})

    def test_a_tagged_but_malformed_projection_is_healed_not_trusted(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        h.paths.session_json.write_text(json.dumps({"schema": "claudna.session/2"}))
        prompt(h)
        assert schema.validate(load(h.paths.session_json), schema.load("session")) == []

    def test_activity_after_a_lost_lifecycle_refresh_heals_the_segment_first(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        append_jsonl(h.paths.lifecycle, ev.make_event("segment.sealed", h.sid,
                                                       {"end": 100, "sealed_by": "precompact", "trigger": "auto"}, seg=1))
        prompt(h)  # a blocked compaction: sealed, still current
        seg1 = load(h.paths.segment(1).segment_json)
        assert (seg1["status"], seg1["counts"]["prompts"]) == ("sealed", 1)

    def test_numbering_skips_indices_named_by_lines_readers_skip(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        future = {**ev.make_event("segment.opened", h.sid, {"opened_by": "compact", "start": 5}, seg=1), "v": 2, "seg": 5}
        append_jsonl(h.paths.lifecycle, future)
        append_jsonl(h.paths.lifecycle, {**future, "v": 1, "kind": "segment.teleported", "seg": 7})
        assert h.open_segment("compact", 10) == 8

    def test_explicit_roots_must_be_absolute(self):
        with pytest.raises(ValueError, match="absolute"):
            SessionStore(Path("relative/store"))

    def test_segment_scoped_appends_without_seg_go_to_the_current_segment(self, store):
        h = opened(store)
        with pytest.raises(StoreError):
            prompt(h)
        h.open_segment("session_open", 0)
        h.open_segment("compact", 5)
        assert prompt(h)["seg"] == 2

    def test_a_seal_cannot_end_before_its_segment_starts(self, store):
        h = opened(store)
        h.open_segment("session_open", 100)
        with pytest.raises(StoreError, match="starts at 100"):
            h.seal_segment(10, "precompact")
        assert load(h.paths.segment(1).segment_json)["status"] == "open"

    def test_each_segment_keeps_the_transcript_it_opened_in(self, store):
        h = opened(store)  # transcript /t.jsonl
        h.open_segment("session_open", 0)
        h.seal_segment(10, "session_end")
        h.close_session("other")
        reopen(h, "/t2.jsonl")
        h.open_segment("session_open", 0)
        assert load(h.paths.segment(1).segment_json)["transcript"]["path"] == "/t.jsonl"
        assert load(h.paths.segment(2).segment_json)["transcript"]["path"] == "/t2.jsonl"
        assert load(h.paths.session_json)["transcript_path"] == "/t2.jsonl"
        files = [h.paths.session_json, h.paths.segment(1).segment_json, h.paths.segment(2).segment_json]
        incremental = [f.read_text() for f in files]
        h.rebuild()
        assert [f.read_text() for f in files] == incremental

    def test_activity_requires_an_existing_segment(self, store):
        h = opened(store)
        with pytest.raises(StoreError):
            prompt(h, seg=1)

    def test_seal_without_a_segment_is_an_error(self, store):
        with pytest.raises(StoreError):
            opened(store).seal_segment(10, "session_end")

    def test_projection_tracks_the_whole_lifecycle(self, store):
        h = opened(store)
        s1 = h.open_segment("session_open", 0)
        h.append("prompt.submitted", {"prompt_id": "p", "chars": 5}, seg=s1)
        h.append("skill.invoked", {"skill": "claudna:ship", "args_chars": 0}, seg=s1)
        h.seal_segment(100, "precompact", trigger="auto")
        s2 = h.open_segment("compact", 100)
        h.append("tool.failed", {"tool": "Bash", "signature": "sig", "exit_code": 1}, seg=s2)
        live = load(h.paths.session_json)
        assert live["status"] == "open" and live["segments"] == {"count": 2, "open": 2, "retired": 0}

        h.seal_segment(300, "session_end")
        h.link_child("child-1")
        h.link_child("child-1")  # duplicate link is idempotent in the projection
        h.set_private(True)
        h.close_session("clear")
        done = load(h.paths.session_json)
        assert done["status"] == "closed" and done["close_reason"] == "clear"
        assert done["segments"] == {"count": 2, "open": None, "retired": 0}
        assert done["children"] == ["child-1"] and done["private"] is True
        assert done["chain_id"] == h.sid  # no parent: its own chain root
        assert load(h.paths.segment(1).segment_json)["counts"] == {"prompts": 1, "skills": 1, "failures": 0, "interrupts": 0}
        assert load(h.paths.segment(2).segment_json)["counts"]["failures"] == 1

    def test_resume_reopens_a_closed_session(self, store):
        h = opened(store)
        h.close_session("other")
        reopen(h, "/t.jsonl")
        s = load(h.paths.session_json)
        assert (s["status"], s["closed_at"], s["opened_by"]) == ("open", None, "startup")

    def test_summary_status_follows_the_last_job_event(self, store):
        h = opened(store)
        seg = h.open_segment("session_open", 0)
        h.append("summary.requested", {"job_id": "j1"}, seg=seg)
        assert load(h.paths.segment(seg).segment_json)["summary"] == {"status": "pending", "job_id": "j1"}
        h.append("summary.failed", {"job_id": "j1", "error": "timeout", "retryable": True}, seg=seg)
        h.append("summary.requested", {"job_id": "j2"}, seg=seg)
        h.append("summary.completed", {"job_id": "j2", "artifact": "seg-001/summary.json",
                                       "input_sha256": "0" * 64, "duration_ms": 5}, seg=seg)
        assert load(h.paths.segment(seg).segment_json)["summary"] == {"status": "done", "job_id": "j2"}
        assert load(h.paths.session_json)["summary"]["segments_done"] == 1

    def test_damaged_log_lines_are_counted_not_fatal(self, store):
        h = opened(store)
        with h.paths.lifecycle.open("a") as fh:
            fh.write('{"v": 99, "kind": "x"}\n{"torn"\n')
        h.rebuild()
        assert load(h.paths.session_json)["projected_from"]["skipped"] == 2

    def test_store_files_are_private(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        for path in (store.root, store.root / "sessions", h.paths.dir, h.paths.segment(1).dir):
            assert stat.S_IMODE(path.stat().st_mode) == 0o700, path
        for path in (h.paths.lifecycle, h.paths.session_json, h.paths.segment(1).segment_json):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600, path

    def test_writes_before_session_opened_land_instead_of_dropping(self, store):
        h = store.session("missed-start")  # SessionStart never fired
        h.open_segment("session_open", 0)
        s = load(h.paths.session_json)
        assert (s["status"], s["segments"]["count"], s["chain_id"]) == ("unknown", 1, "missed-start")

    def test_bools_are_never_ints_anywhere(self):
        assert schema.is_instance(1, int) and not schema.is_instance(True, int)
        assert schema.is_instance(True, bool) and schema.is_instance(True, (bool, int))
        with pytest.raises(ValueError):
            seg_dirname(True)
        assert schema.validate(True, {"type": "integer"}) != []

    def test_each_session_gets_its_own_directory(self, store):
        opened(store, "b")
        opened(store, "a")
        assert sorted(p.name for p in (store.root / "sessions").iterdir()) == ["a", "b"]

    def test_a_torn_tail_never_swallows_the_next_event(self, store):
        h = opened(store)
        with h.paths.lifecycle.open("a") as fh:
            fh.write('{"torn": ')  # a writer killed mid-append
        h.close_session("other")
        assert load(h.paths.session_json)["status"] == "closed"
        assert read_jsonl(h.paths.lifecycle).skipped == 1

    def test_segment_scoped_lifecycle_events_need_an_existing_segment(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        with pytest.raises(StoreError):
            h.seal_segment(10, "precompact", index=7)
        with pytest.raises(StoreError):
            h.append("summary.requested", {"job_id": "j"}, seg=5)
        assert h.paths.segment_indices() == [1] and h.open_segment("compact", 10) == 2

    def test_a_log_named_segment_without_a_directory_is_not_resurrected(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        h.open_segment("compact", 10)
        shutil.rmtree(h.paths.segment(2).dir)
        h.rebuild()
        assert h.paths.segment_indices() == [1]
        assert load(h.paths.session_json)["segments"]["count"] == 1
        assert h.open_segment("compact", 20) == 3  # index 2 is never reused
        assert load(h.paths.segment(3).segment_json)["status"] == "open"

    def test_indexes_are_never_reused_after_retention_deletes_segments(self, store):
        h = opened(store)
        for i in (1, 2, 3):
            h.open_segment("session_open" if i == 1 else "compact", i * 100)
            h.seal_segment(i * 100 + 99, "precompact")
        h.close_session("other")
        for i in (1, 2, 3):
            shutil.rmtree(h.paths.segment(i).dir)
        reopen(h, "/t.jsonl")
        new = h.open_segment("session_open", 400)
        seg = load(h.paths.segment(new).segment_json)
        assert new == 4 and seg["status"] == "open"
        assert seg["transcript"]["range"] == {"start": 400, "end": None}
        assert load(h.paths.session_json)["segments"] == {"count": 1, "open": 4, "retired": 0}

    def test_foreign_session_events_do_not_fold(self, store):
        h = opened(store)
        append_jsonl(h.paths.lifecycle, ev.make_event("session.privacy_set", "someone-else",
                                                       {"private": True, "by": "user"}))
        h.rebuild()
        s = load(h.paths.session_json)
        assert s["private"] is False and s["projected_from"]["skipped"] == 1


# ── projections: golden fixture and round trip ───────────────────────────────


def _copy_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "state"
    shutil.copytree(FIXTURE / "sessions", root / "sessions")
    return root


def _fixture_with_0_26_session_json(tmp_path: Path):
    """The golden fixture, rebuilt, with what a 0.26 rebuild leaves as its ``session.json``."""
    root = _copy_fixture(tmp_path)
    handle = SessionStore(root).session(FIXTURE_SID)
    handle.rebuild()
    atomic_write_json(handle.paths.session_json, load(OLDER_SESSION))
    return root, handle


def spy_rebuilds(monkeypatch, *modules) -> list:
    """Count ``rebuild`` calls through each module's own binding (``store`` imports its own)."""
    calls: list = []
    for module in modules:
        real = module.rebuild
        monkeypatch.setattr(module, "rebuild", lambda paths, real=real: calls.append(paths) or real(paths))
    return calls


class TestProjection:
    def test_golden_fixture_projects_byte_for_byte(self, tmp_path):
        root = _copy_fixture(tmp_path)
        report = SessionStore(root).session(FIXTURE_SID).rebuild()
        assert report.segments == [1, 2] and report.skipped_lines == 0
        paths = session_paths(FIXTURE_SID, root)
        expected = FIXTURE / "expected"
        assert paths.session_json.read_text() == (expected / "session.json").read_text()
        assert paths.segment(1).segment_json.read_text() == (expected / "seg-001.json").read_text()
        assert paths.segment(2).segment_json.read_text() == (expected / "seg-002.json").read_text()

    def test_a_0_23_segment_projection_is_refolded_to_the_current_schema(self, tmp_path):
        """A store written by 0.23 (``claudna.segment/1``, with ``checkpoints`` and ``sha256``) upgrades on read."""
        root = _copy_fixture(tmp_path)
        handle = SessionStore(root).session(FIXTURE_SID)
        handle.rebuild()
        old = load(FIXTURE / "expected" / "seg-001.json")
        old.update(schema="claudna.segment/1")
        old["counts"]["checkpoints"] = 0
        old["transcript"]["sha256"] = "a" * 64
        atomic_write_json(handle.paths.segment(1).segment_json, old)
        doc = next(d for d in readers.show(SessionStore(root), FIXTURE_SID)["segments"] if d["index"] == 1)
        assert doc["schema"] == "claudna.segment/2"
        assert "checkpoints" not in doc["counts"] and "sha256" not in doc["transcript"]
        report = check_session(handle)  # flagged as older, not as broken
        assert report.problems == [] and any("an older projection" in w for w in report.warnings)

    @pytest.mark.parametrize("doc", [[], 5, "x", {"schema": "garbage", "counts": "nonsense"},
                                     {"schema": "claudna.segment/9"}])
    def test_check_reports_a_broken_or_unknown_projection_as_a_problem(self, tmp_path, doc):
        root = _copy_fixture(tmp_path)
        handle = SessionStore(root).session(FIXTURE_SID)
        handle.rebuild()
        atomic_write_json(handle.paths.segment(1).segment_json, doc)
        report = check_session(handle)  # never a crash, and only a known older tag is downgraded
        assert report.problems and not any("an older projection" in w for w in report.warnings)

    def test_the_sweep_rewrites_a_0_23_projection_once(self, tmp_path):
        root = _copy_fixture(tmp_path)
        store = SessionStore(root)
        handle = store.session(FIXTURE_SID)
        handle.rebuild()
        old = load(handle.paths.segment(1).segment_json)
        old.update(schema="claudna.segment/1")
        atomic_write_json(handle.paths.segment(1).segment_json, old)
        report = retention.sweep(store, {})
        assert report.upgraded == [FIXTURE_SID]
        assert load(handle.paths.segment(1).segment_json)["schema"] == "claudna.segment/2"
        assert retention.sweep(store, {}).upgraded == []  # once

    def test_a_0_26_session_projection_is_refolded_to_the_current_schema(self, tmp_path):
        """A ``claudna.session/1`` file (0.26, no ``agent_cli``) is folded from the log, never served."""
        root, handle = _fixture_with_0_26_session_json(tmp_path)
        doc = readers.show(SessionStore(root), FIXTURE_SID)["session"]
        assert doc["schema"] == "claudna.session/2" and doc["agent_cli"] == "claude"
        report = check_session(handle)
        assert report.problems == []
        assert any("an older projection" in w and "session.json" in w for w in report.warnings)

    def test_the_sweep_rewrites_a_0_26_session_projection_once(self, tmp_path):
        root, handle = _fixture_with_0_26_session_json(tmp_path)
        store = SessionStore(root)
        assert retention.sweep(store, {}).upgraded == [FIXTURE_SID]
        assert load(handle.paths.session_json)["schema"] == "claudna.session/2"
        assert retention.sweep(store, {}).upgraded == []  # once

    def test_a_0_26_reader_and_a_0_27_writer_alternating_converge_on_session_2(self, store, monkeypatch):
        """Readers write nothing, so a 0.26 reader never flips a 0.27 file back (epic #2145 P1).

        0.26 differs from 0.27 at one seam: the tag ``read_projection``/``session_doc`` ask for.
        ``store.py`` keeps its own ``/2`` binding, so the writer stays 0.27.
        """
        rebuilds = spy_rebuilds(monkeypatch, project_module)
        h = opened(store)
        h.open_segment("session_open", 0)
        for _ in range(3):
            prompt(h)  # 0.27 write
            h.seal_segment(10, "precompact", trigger="auto")
            h.open_segment("compact", 10)
            assert load(h.paths.session_json)["schema"] == "claudna.session/2"
            before, rebuilds[:] = h.paths.session_json.read_bytes(), []
            with monkeypatch.context() as m:  # 0.26 read
                m.setattr(project_module, "SESSION_SCHEMA", "claudna.session/1")
                m.setattr(project_module, "OLDER_PROJECTIONS", frozenset({"claudna.segment/1"}))
                doc = project_module.session_doc(h.paths)
            assert doc["status"] == "open" and doc["segments"]["open"] == h.current_segment()
            assert h.paths.session_json.read_bytes() == before and rebuilds == []

    def test_a_0_26_writers_file_is_rebuilt_to_session_2_once(self, store, monkeypatch):
        """The writer side, honestly: a 0.26 rebuild leaves ``/1``; the next 0.27 append rebuilds it once."""
        rebuilds = spy_rebuilds(monkeypatch, project_module, store_module)
        h = opened(store)
        h.open_segment("session_open", 0)
        prompt(h)
        atomic_write_json(h.paths.session_json, load(OLDER_SESSION))
        rebuilds.clear()
        prompt(h)
        assert len(rebuilds) == 1
        doc = load(h.paths.session_json)
        assert doc["schema"] == "claudna.session/2" and doc["agent_cli"] == "claude"
        prompt(h)
        assert len(rebuilds) == 1  # the fast path again

    def test_rebuild_is_deterministic_and_never_touches_logs(self, tmp_path):
        root = _copy_fixture(tmp_path)
        handle = SessionStore(root).session(FIXTURE_SID)
        logs = [handle.paths.lifecycle, handle.paths.segment(1).events, handle.paths.segment(2).events]
        before = [p.read_bytes() for p in logs]
        handle.rebuild()
        first = handle.paths.session_json.read_text()
        for p in (handle.paths.session_json, handle.paths.segment(1).segment_json):
            p.unlink()
        handle.rebuild()
        assert handle.paths.session_json.read_text() == first
        assert [p.read_bytes() for p in logs] == before

    def test_incremental_refresh_equals_full_rebuild(self, store):
        h = opened(store)
        s1 = h.open_segment("session_open", 0)
        h.append("prompt.submitted", {"prompt_id": "p", "chars": 3}, seg=s1)
        h.append("summary.requested", {"job_id": "j"}, seg=s1)
        h.seal_segment(50, "precompact", trigger="auto")
        s2 = h.open_segment("compact", 50)
        h.append("tool.failed", {"tool": "Bash", "signature": "s", "exit_code": 1}, seg=s2)
        h.link_child("c")
        h.seal_segment(80, "session_end")
        h.close_session("other")
        files = [h.paths.session_json, h.paths.segment(1).segment_json, h.paths.segment(2).segment_json]
        incremental = [f.read_text() for f in files]
        for f in files:
            f.unlink()
        h.rebuild()
        assert [f.read_text() for f in files] == incremental

    def test_late_session_opened_updates_every_segment_projection(self, store):
        h = store.session("late-open")
        h.open_segment("session_open", 0)  # SessionStart missed; a segment opened first
        h.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path="/t.jsonl")
        assert load(h.paths.segment(1).segment_json)["transcript"]["path"] == "/t.jsonl"
        incremental = h.paths.segment(1).segment_json.read_text()
        h.rebuild()
        assert h.paths.segment(1).segment_json.read_text() == incremental

    def test_activity_fast_path_falls_back_when_the_projection_is_stale(self, store):
        h = opened(store)
        seg = h.open_segment("session_open", 0)
        prompt(h, seg=seg)
        # a second writer appended behind the projection's back
        append_jsonl(h.paths.segment(seg).events, ev.make_event("prompt.submitted", h.sid,
                                                                {"prompt_id": None, "chars": 1}, seg=seg))
        prompt(h, seg=seg)
        assert load(h.paths.segment(seg).segment_json)["counts"]["prompts"] == 3

    def test_refresh_falls_back_to_rebuild_when_a_projection_is_damaged(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        h.open_segment("compact", 10)
        h.paths.segment(1).segment_json.write_text("{not json")
        h.close_session("other")  # session refresh must not trust the damaged seg-001 projection
        assert load(h.paths.segment(1).segment_json)["index"] == 1
        assert load(h.paths.session_json)["segments"]["count"] == 2

    def test_fixture_captures_lineage(self):
        s = load(FIXTURE / "expected" / "session.json")
        assert (s["parent_sid"], s["chain_id"], s["opened_by"]) == ("parent-sid-1", "root-sid-0", "clear")
        assert s["summary"] == {"segments_done": 1, "segments_pending": 0, "segments_failed": 0,
                                "segments_skipped": 1}


# ── schemas ──────────────────────────────────────────────────────────────────


class TestSchemas:
    def test_every_registry_kind_fits_the_envelope_schema(self):
        pattern = schema.load("event")["properties"]["kind"]["pattern"]
        assert all(re.match(pattern, kind) for kind in ev.REGISTRY)

    @pytest.mark.parametrize(
        "schema_name,prop,kind,field,extra",
        [
            ("segment", "opened_by", "segment.opened", "opened_by", ["unknown"]),
            ("segment", "sealed_by", "segment.sealed", "sealed_by", [None]),
            ("session", "opened_by", "session.opened", "source", [None]),
            ("session", "close_reason", "session.closed", "reason", [None]),
            ("session", "agent_cli", "session.opened", "agent_cli", []),
        ],
    )
    def test_projection_vocabularies_match_the_registry(self, schema_name, prop, kind, field, extra):
        enum = schema.load(schema_name)["properties"][prop]["enum"]
        assert enum == list(ev.REGISTRY[kind].choices[field]) + extra

    def test_every_timestamp_pattern_is_the_envelopes(self):
        ts = schema.load("event")["properties"]["ts"]["pattern"]
        seen = [n["pattern"] for n in _schema_nodes() if "\\d{4}-" in n.get("pattern", "")]
        assert seen and all(p == ts for p in seen)

    def test_every_schema_node_uses_only_supported_keywords(self):
        for node in _schema_nodes():
            assert set(node) <= schema._SUPPORTED, sorted(set(node) - schema._SUPPORTED)

    def test_golden_projections_validate(self):
        expected = FIXTURE / "expected"
        assert schema.validate(load(expected / "session.json"), schema.load("session")) == []
        for name in ("seg-001.json", "seg-002.json"):
            assert schema.validate(load(expected / name), schema.load("segment")) == []

    def test_fixture_logs_validate(self):
        event_schema = schema.load("event")
        for log in (FIXTURE / "sessions").rglob("*.jsonl"):
            for record in read_jsonl(log).records:  # 0.23-written, sha256 included: they still fold
                assert schema.validate(record, event_schema) == []
                assert ev.classify(record) == "ok"

    @pytest.mark.parametrize(
        "name,mutate",
        [
            ("session", lambda d: d.update(status="half-open")),
            ("session", lambda d: d.pop("chain_id")),
            ("session", lambda d: d.update(unexpected=1)),
            ("session", lambda d: d["segments"].update(count=-1)),
            ("session", lambda d: d.update(opened_at="2026-09-28 10:00")),
            ("session", lambda d: d.update(agent_cli="gpt")),
            ("session", lambda d: d.pop("agent_cli")),
            ("segment", lambda d: d.update(index=0)),
            ("segment", lambda d: d["transcript"]["range"].update(start=-1)),
            ("segment", lambda d: d["summary"].update(status="maybe")),
        ],
    )
    def test_schemas_reject_malformed_projections(self, name, mutate):
        source = "session.json" if name == "session" else "seg-001.json"
        doc = load(FIXTURE / "expected" / source)
        mutate(doc)
        assert schema.validate(doc, schema.load(name)) != []

    def test_patterns_use_json_schema_semantics(self):
        ts = schema.load("event")["properties"]["ts"]
        assert schema.validate("2026-09-28T17:04:05.123Z", ts) == []
        assert schema.validate("2026-09-28T17:04:05.123Z\n", ts) != []  # $ is end-of-string
        assert schema.validate("\u0662026-09-28T17:04:05.123Z", ts) != []  # \d is ASCII
        assert schema.validate("xax", {"pattern": "a"}) == []  # unanchored patterns search
        alternation = {"pattern": "^a$|^b$"}
        assert schema.validate("b", alternation) == [] and schema.validate("b\n", alternation) != []
        assert schema.validate("a\\", {"pattern": "^a\\\\$"}) == []  # escaped backslash, then the anchor
        assert schema.validate("a$", {"pattern": "^a\\$$"}) == []  # escaped $ is literal
        assert schema.validate("$", {"pattern": "^[$]$"}) == []  # $ in a class is literal

    def test_unsupported_keyword_raises_instead_of_silently_passing(self):
        with pytest.raises(schema.SchemaError):
            schema.validate(1, {"oneOf": [{"type": "integer"}]})


def _schema_nodes():
    """Every schema node in every schema file (the maps under properties/$defs hold names, not keywords)."""
    def walk(node):
        yield node
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for sub in value.values():
                    yield from walk(sub)
            elif isinstance(value, dict):
                yield from walk(value)
    for path in sorted((STORE_PKG / "schemas").glob("*.schema.json")):
        yield from walk(json.loads(path.read_text()))


# ── CLI ──────────────────────────────────────────────────────────────────────


def run_cli(*args: str, as_module: bool = True) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "claudna.session_store"] if as_module else [sys.executable, str(STORE_PKG)]
    env = {**os.environ, "CLAUDNA_STATE_DIR": "/nonexistent-claudna-root", "PYTHONPATH": str(LIB)}
    return subprocess.run([*cmd, *args], capture_output=True, text=True, env=env)


class TestCli:
    def test_rebuild_then_check_passes(self, tmp_path):
        root = _copy_fixture(tmp_path)
        rebuilt = run_cli("rebuild", FIXTURE_SID, "--root", str(root))
        assert rebuilt.returncode == 0, rebuilt.stderr
        assert json.loads(rebuilt.stdout)["segments"] == [1, 2]
        checked = run_cli("check", FIXTURE_SID, "--root", str(root))
        assert checked.returncode == 0, checked.stdout

    def test_check_fails_before_projections_exist(self, tmp_path):
        root = _copy_fixture(tmp_path)
        result = run_cli("check", FIXTURE_SID, "--root", str(root))
        assert result.returncode == 1 and "run rebuild" in result.stdout

    def test_check_flags_a_registry_violation_in_a_log(self, tmp_path):
        root = _copy_fixture(tmp_path)
        run_cli("rebuild", FIXTURE_SID, "--root", str(root))
        bad = ev.make_event("session.closed", FIXTURE_SID, {"reason": "other"})
        bad["data"]["reason"] = "bored"
        append_jsonl(session_paths(FIXTURE_SID, root).lifecycle, bad)
        assert run_cli("check", FIXTURE_SID, "--root", str(root)).returncode == 1
        assert check_session(SessionStore(root).session(FIXTURE_SID)).problems

    def test_unknown_and_invalid_sessions_exit_1(self, tmp_path):
        assert run_cli("rebuild", "missing", "--root", str(tmp_path)).returncode == 1
        assert run_cli("rebuild", "../escape", "--root", str(tmp_path)).returncode == 1

    def test_root_is_accepted_after_the_verb_and_the_directory_form_works(self, tmp_path):
        root = _copy_fixture(tmp_path)
        assert run_cli("rebuild", FIXTURE_SID, "--root", str(root)).returncode == 0
        assert run_cli("check", FIXTURE_SID, "--root", str(root), as_module=False).returncode == 0

    def test_check_skips_newer_envelopes_like_readers_do(self, tmp_path):
        root = _copy_fixture(tmp_path)
        run_cli("rebuild", FIXTURE_SID, "--root", str(root))
        future = {**ev.make_event("session.closed", FIXTURE_SID, {"reason": "other"}), "v": 2, "newfield": 1}
        append_jsonl(session_paths(FIXTURE_SID, root).lifecycle, future)
        assert run_cli("check", FIXTURE_SID, "--root", str(root)).returncode == 0

    def test_check_flags_misplaced_events(self, tmp_path):
        root = _copy_fixture(tmp_path)
        run_cli("rebuild", FIXTURE_SID, "--root", str(root))
        paths = session_paths(FIXTURE_SID, root)
        append_jsonl(paths.segment(2).events, ev.make_event("prompt.submitted", FIXTURE_SID,
                                                            {"prompt_id": None, "chars": 1}, seg=1))
        result = run_cli("check", FIXTURE_SID, "--root", str(root))
        assert result.returncode == 1 and "read from segment 2" in result.stdout

    def test_crash_debris_is_a_warning_not_a_failure(self, tmp_path):
        root = _copy_fixture(tmp_path)
        lifecycle = session_paths(FIXTURE_SID, root).lifecycle
        with lifecycle.open("a") as fh:
            fh.write('{"v":1,"kind":"segment.sea')  # a torn write
        run_cli("rebuild", FIXTURE_SID, "--root", str(root))
        result = run_cli("check", FIXTURE_SID, "--root", str(root))
        assert result.returncode == 0 and "warning:" in result.stdout and "crash debris" in result.stdout

    @pytest.mark.parametrize("line", ["garbage", "[]", "5"])
    def test_corrupt_lines_fail_check(self, tmp_path, line):
        root = _copy_fixture(tmp_path)
        run_cli("rebuild", FIXTURE_SID, "--root", str(root))
        with session_paths(FIXTURE_SID, root).lifecycle.open("a") as fh:
            fh.write(line + "\n")
        result = run_cli("check", FIXTURE_SID, "--root", str(root))
        assert result.returncode == 1 and "corrupt" in result.stdout

    def test_relative_root_is_a_clean_error(self):
        result = run_cli("check", "sess-1", "--root", "relative/store")
        assert result.returncode == 1 and "absolute" in result.stderr and "Traceback" not in result.stderr

    def test_usage_error_exits_2(self):
        assert run_cli("frobnicate").returncode == 2


# ── review follow-ups: a rejected call changes nothing; writers strict about keys ─


class TestARejectedCallChangesNothing:
    def test_a_rejected_open_segment_leaves_the_session_as_it_was(self, store):
        for n, args in enumerate([("bogus", 5), ("compact", -5), ("compact", "5")]):
            h = opened(store, f"s{n}")
            h.open_segment("session_open", 0)
            before = (h.paths.lifecycle.read_bytes(), h.paths.segment_indices())
            with pytest.raises(ev.EventError):
                h.open_segment(*args)
            assert (h.paths.lifecycle.read_bytes(), h.paths.segment_indices()) == before, args

    def test_a_rejected_first_open_segment_creates_no_directory(self, store):
        h = opened(store)
        with pytest.raises(ev.EventError):
            h.open_segment("bogus", 0)
        assert h.paths.segment_indices() == []


class TestWritersAreStrictAboutDataKeys:
    def test_a_key_the_registry_does_not_name_is_rejected(self):
        with pytest.raises(ev.EventError, match="not a field"):
            ev.make_event("prompt.submitted", "s1", {"prompt_id": None, "chars": 1, "prompt": "whole prompt"}, seg=1)

    def test_readers_still_fold_an_event_that_carries_a_newer_field(self):
        e = ev.make_event("prompt.submitted", "s1", {"prompt_id": None, "chars": 1}, seg=1)
        e["data"]["future_field"] = 1
        assert ev.classify(e) == "ok"

    def test_a_failure_signature_is_capped(self):
        e = ev.make_event("tool.failed", "s1", {"tool": "Bash", "signature": "x" * 50_000, "exit_code": 1}, seg=1)
        assert len(e["data"]["signature"]) == ev.REGISTRY["tool.failed"].caps["signature"]

    def test_fork_is_a_session_source(self, store):
        h = store.session("forked")
        h.open_session("fork", actor=ACTOR, origin=ORIGIN, transcript_path="/f.jsonl", parent_sid="sess-1")
        assert load(h.paths.session_json)["opened_by"] == "fork"

    def test_agent_cli_is_an_optional_top_level_choice(self):
        base = {"source": "startup", "parent_sid": None, "chain_id": "s1", "actor": ACTOR, "origin": ORIGIN,
                "transcript_path": None}
        assert ev.classify(ev.make_event("session.opened", "s1", {**base, "agent_cli": "codex"})) == "ok"
        assert ev.classify(ev.make_event("session.opened", "s1", base)) == "ok"
        with pytest.raises(ev.EventError, match="must be one of"):
            ev.make_event("session.opened", "s1", {**base, "agent_cli": "gpt"})
        with pytest.raises(ev.EventError):  # unknown means omit the key, never null
            ev.make_event("session.opened", "s1", {**base, "agent_cli": None})

    def test_agent_cli_never_nests_in_actor(self):
        """Epic #2145 §11: actor is additionalProperties: false, so a 0.23-0.26 reader would classify the
        whole session.opened invalid if agent_cli were nested there."""
        base = {"source": "startup", "parent_sid": None, "chain_id": "s1", "origin": ORIGIN, "transcript_path": None}
        with pytest.raises(ev.EventError):
            ev.make_event("session.opened", "s1", {**base, "actor": {**ACTOR, "agent_cli": "claude"}})


class TestCheckSeesALostRefresh:
    def test_a_projection_behind_its_log_warns_until_the_next_write_heals_it(self, store):
        h = opened(store)
        seg = h.open_segment("session_open", 0)
        append_jsonl(h.paths.lifecycle, ev.make_event("segment.sealed", h.sid,  # a hook killed before its refresh
                                                       {"end": 100, "sealed_by": "precompact", "trigger": "auto"}, seg=seg))
        report = check_session(h)
        assert report.problems == [] and any("refresh was lost" in w for w in report.warnings)
        prompt(h)  # activity heals the stale lifecycle projections first
        assert check_session(h).warnings == []
        assert load(h.paths.segment(seg).segment_json)["status"] == "sealed"

    def test_a_healthy_store_never_warns(self, store):
        h = opened(store)
        h.open_segment("session_open", 0)
        prompt(h)
        h.seal_segment(10, "session_end")
        h.close_session("other")
        assert check_session(h).warnings == []

    def test_the_golden_fixture_checks_clean_after_a_rebuild(self, tmp_path):
        root = _copy_fixture(tmp_path)
        SessionStore(root).session(FIXTURE_SID).rebuild()
        assert check_session(SessionStore(root).session(FIXTURE_SID)).warnings == []


# ── pins for guarantees nothing else holds (each kills a surviving mutant) ────

import contextlib  # noqa: E402
import fcntl  # noqa: E402

import claudna.session_store.store as store_module  # noqa: E402


class TestPinsForUnheldGuarantees:
    def test_the_lock_excludes_a_second_holder_until_it_is_released(self, tmp_path):
        lock = tmp_path / ".lock"
        with exclusive_lock(lock):
            fd = os.open(lock, os.O_RDWR)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
        fd = os.open(lock, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # released: this must not raise
        finally:
            os.close(fd)

    def test_every_mutation_takes_the_session_lock(self, store, monkeypatch):
        taken = []
        real = store_module.exclusive_lock

        def spy(path):
            taken.append(path.name)
            with real(path):
                yield

        monkeypatch.setattr(store_module, "exclusive_lock", contextlib.contextmanager(spy))
        h = opened(store)
        h.open_segment("session_open", 0)
        prompt(h)
        h.seal_segment(5, "precompact")
        h.close_session("other")
        h.rebuild()
        assert taken == [h.paths.lock.name] * 6

    def test_the_store_validates_the_session_id_before_it_builds_a_path(self, store):
        for sid in ("../escape", "a/b", ".hidden", ""):
            with pytest.raises(InvalidSessionId):
                store.session(sid)

    def test_the_activity_fast_path_output_equals_a_full_rebuild(self, store):
        h = opened(store)
        seg = h.open_segment("session_open", 0)
        for i in range(3):
            h.append("prompt.submitted", {"prompt_id": f"p{i}", "chars": i})
        h.append("skill.invoked", {"skill": "claudna:ship", "args_chars": 0})
        h.append("tool.failed", {"tool": "Bash", "signature": "s", "exit_code": 1})
        path = h.paths.segment(seg).segment_json
        incremental = path.read_text()  # no lifecycle event since: this is the fast path's own output
        h.rebuild()
        assert path.read_text() == incremental

    def test_the_directory_form_needs_no_pythonpath_and_ignores_the_cwd(self, tmp_path):
        root = _copy_fixture(tmp_path)
        project = tmp_path / "project"
        project.mkdir()
        (project / "json.py").write_text("raise ImportError('the project shadowed the stdlib')\n")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        run = subprocess.run([sys.executable, str(STORE_PKG), "rebuild", FIXTURE_SID, "--root", str(root)],
                             capture_output=True, text=True, env=env, cwd=project)
        assert run.returncode == 0, run.stderr

    def test_log_appends_are_fsynced(self, tmp_path, monkeypatch):
        synced = []
        real = os.fsync
        monkeypatch.setattr(os, "fsync", lambda fd: synced.append(fd) or real(fd))
        append_jsonl(tmp_path / "l.jsonl", {"k": 1})
        assert len(synced) == 1

    def test_a_short_write_is_finished(self, tmp_path):
        log = tmp_path / "l.jsonl"
        real = os.write
        with pytest.MonkeyPatch.context() as m:
            m.setattr(os, "write", lambda fd, data: real(fd, bytes(data)[:4]))  # every write takes at most 4 bytes
            append_jsonl(log, {"k": "v" * 50})
        assert read_jsonl(log).records == [{"k": "v" * 50}]

    def test_check_validates_projections_against_their_schemas(self, tmp_path):
        root = _copy_fixture(tmp_path)
        run_cli("rebuild", FIXTURE_SID, "--root", str(root))
        seg = session_paths(FIXTURE_SID, root).segment(1).segment_json
        doc = json.loads(seg.read_text())
        doc["status"] = "half-open"
        seg.write_text(json.dumps(doc))
        result = run_cli("check", FIXTURE_SID, "--root", str(root))
        assert result.returncode == 1 and "status" in result.stdout

    def test_open_session_records_its_lineage_arguments(self, store):
        h = store.session("child")
        h.open_session("clear", actor=ACTOR, origin=ORIGIN, transcript_path=None, parent_sid="parent", chain_id="root")
        s = load(h.paths.session_json)
        assert (s["parent_sid"], s["chain_id"]) == ("parent", "root")

    def test_a_seal_still_writes_what_a_0_23_reader_requires(self, store):
        """``trigger`` stays required: a 0.23 reader sharing the store would reject a seal without it."""
        h = opened(store)
        h.open_segment("session_open", 0)
        h.seal_segment(10, "precompact")
        sealed = [e for e in load_lifecycle(h.paths).events if e["kind"] == "segment.sealed"][-1]
        assert sealed["data"] == {"end": 10, "sealed_by": "precompact", "trigger": None}


class TestWritersRedact:
    def test_free_text_is_redacted_before_it_is_capped(self):
        e = ev.make_event("prompt.submitted", "s1", {"prompt_id": None, "chars": 60,
                                                     "text": "curl -H 'Authorization: Bearer " + "tok" * 8 + "'"},
                          seg=1)
        assert "toktok" not in e["data"]["text"] and "[REDACTED]" in e["data"]["text"]


class TestRejectedFirstWrites:
    """A refused call on a session the store doesn't have leaves nothing behind (no phantom directory)."""

    @pytest.mark.parametrize("call, error", [
        (lambda h: h.seal_segment(10, "precompact"), StoreError),
        (lambda h: h.append("prompt.submitted", {"prompt_id": None, "chars": 1}), NotAppendable),
        (lambda h: h.append("summary.skipped", {"reason": "trivial"}, seg=1), StoreError),
        (lambda h: h.close_session("not-a-reason"), ev.EventError),
        (lambda h: h.close_abandoned(), StoreError),
    ], ids=["seal", "activity", "segment-event", "bad-close", "abandon"])
    def test_nothing_is_created(self, store, call, error):
        h = store.session("fresh")
        with pytest.raises(error):
            call(h)
        assert not h.paths.dir.exists() and store.session_ids() == []

    def test_a_refused_call_on_an_existing_session_keeps_it(self, store):
        h = opened(store, "s1")
        with pytest.raises(ev.EventError):
            h.close_session("not-a-reason")
        assert h.paths.lifecycle.is_file()


def test_check_reports_a_projection_missing_projected_from(store, capsys):
    """A hand-edited projection without its watermark is an error for ``check``, never a KeyError."""
    h = opened(store, "s1")
    doc = load(h.paths.session_json)
    del doc["projected_from"]
    h.paths.session_json.write_text(json.dumps(doc))
    assert main(["check", "s1", "--root", str(store.root)]) != 0
    assert "projected_from" in capsys.readouterr().out


def test_check_writes_nothing(store):
    """``check`` is read-only: a stale projection is reported, never rewritten."""
    h = opened(store, "s1")
    h.open_segment("session_open", 0)
    h.paths.session_json.unlink()  # a lost projection: check must not rebuild it

    def files():
        return sorted((p.relative_to(store.root), p.stat().st_mtime_ns) for p in store.root.rglob("*") if p.is_file())

    before = files()
    main(["check", "s1", "--root", str(store.root)])
    assert files() == before
