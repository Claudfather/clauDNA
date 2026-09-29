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
from claudna.session_store import schema  # noqa: E402
from claudna.session_store.cli import check_session  # noqa: E402
from claudna.session_store.fsio import (  # noqa: E402
    LockBusy,
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
from claudna.session_store.store import SessionStore, StoreError  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "session-store" / "basic"
FIXTURE_SID = "5f0c2d1e-0000-4000-8000-000000000001"
STORE_PKG = LIB / "claudna" / "session_store"

ACTOR = {"kind": "interactive", "fleet": None, "bot_id": None, "bot_name": None, "model": None, "entrypoint": "cli"}
ORIGIN = {"cwd": "/work", "repo": None, "branch": None, "head": None}


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "state")


def opened(store: SessionStore, sid: str = "sess-1"):
    handle = store.session(sid)
    handle.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path="/t.jsonl")
    return handle


def load(path: Path) -> dict:
    return json.loads(path.read_text())


# ── paths ────────────────────────────────────────────────────────────────────


class TestPaths:
    @pytest.mark.parametrize("sid", ["3fbbf216-f848-4d8b-b5b5-7839fc98b820", "a", "A.b_c-1", "a..b"])
    def test_accepts_safe_ids(self, sid):
        assert validate_sid(sid) == sid

    @pytest.mark.parametrize("sid", ["", "..", "../etc", "a/b", ".hidden", "x" * 200, None, 5])
    def test_rejects_ids_that_are_not_one_safe_path_component(self, sid):
        with pytest.raises(InvalidSessionId):
            validate_sid(sid)

    def test_segment_dirnames_round_trip_and_widen_past_999(self):
        assert seg_dirname(3) == "seg-003"
        assert seg_dirname(1234) == "seg-1234"
        assert parse_seg_dirname("seg-1234") == 1234
        assert parse_seg_dirname("seg-000") is None
        assert parse_seg_dirname("segment-1") is None
        with pytest.raises(ValueError):
            seg_dirname(0)
        with pytest.raises(ValueError):
            seg_dirname(True)

    def test_state_root_env_override_and_default(self, tmp_path):
        assert state_root({"CLAUDNA_STATE_DIR": str(tmp_path)}) == tmp_path
        assert state_root({}) == Path("~/.claudna").expanduser()


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

    def test_non_blocking_lock_reports_busy_while_held(self, tmp_path):
        lock = tmp_path / ".lock"
        with exclusive_lock(lock):
            with pytest.raises(LockBusy):
                with exclusive_lock(lock, blocking=False):
                    pass
        with exclusive_lock(lock, blocking=False):
            pass  # released after the outer block


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
            ("segment.sealed", {"end": 10, "sealed_by": "precompact", "trigger": None, "sha256": "abc"}, 1),
            ("segment.opened", {"opened_by": "compact", "start": -1}, 1),
            ("prompt.submitted", {"prompt_id": None, "chars": -3}, 1),
        ],
    )
    def test_writers_reject_values_their_projections_would_reject(self, kind, data, seg):
        with pytest.raises(ev.EventError):
            ev.make_event(kind, "s1", data, seg=seg)

    def test_free_text_is_capped_not_rejected(self):
        e = ev.make_event("tool.failed", "s1", {"tool": "Bash", "signature": "x", "exit_code": 1,
                                                 "command": "c" * 1000, "error": "e" * 5000}, seg=1)
        assert len(e["data"]["command"]) == 300 and len(e["data"]["error"]) == 800
        assert e["data"]["error"].endswith("…")

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

    def test_activity_requires_an_existing_segment(self, store):
        h = opened(store)
        with pytest.raises(StoreError):
            h.append("prompt.submitted", {"prompt_id": None, "chars": 1}, seg=1)

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
        h.append("tool.failed", {"tool": "Bash", "signature": "sig", "exit_code": 1, "command": None,
                                 "error": None}, seg=s2)
        live = load(h.paths.session_json)
        assert live["status"] == "open" and live["segments"] == {"count": 2, "open": 2}

        h.seal_segment(300, "session_end")
        h.link_child("child-1")
        h.link_child("child-1")  # duplicate link is idempotent in the projection
        h.set_private(True)
        h.close_session("clear")
        done = load(h.paths.session_json)
        assert done["status"] == "closed" and done["close_reason"] == "clear"
        assert done["segments"] == {"count": 2, "open": None}
        assert done["children"] == ["child-1"] and done["private"] is True
        assert done["chain_id"] == h.sid  # no parent: its own chain root
        assert load(h.paths.segment(1).segment_json)["counts"] == {"prompts": 1, "skills": 1, "failures": 0,
                                                                   "checkpoints": 0}
        assert load(h.paths.segment(2).segment_json)["counts"]["failures"] == 1

    def test_resume_reopens_a_closed_session(self, store):
        h = opened(store)
        h.close_session("other")
        h.open_session("resume", actor=ACTOR, origin=ORIGIN, transcript_path="/t.jsonl")
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

    def test_session_ids_lists_directories(self, store):
        opened(store, "b")
        opened(store, "a")
        (store.root / "sessions" / ".tmp").mkdir()
        (store.root / "sessions" / "has space").mkdir()
        assert store.session_ids() == ["a", "b"]

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
        h.append("tool.failed", {"tool": "Bash", "signature": "s", "exit_code": 1, "command": None,
                                 "error": None}, seg=s2)
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
        h.append("prompt.submitted", {"prompt_id": None, "chars": 1}, seg=seg)
        # a second writer appended behind the projection's back
        append_jsonl(h.paths.segment(seg).events, ev.make_event("prompt.submitted", h.sid,
                                                                {"prompt_id": None, "chars": 1}, seg=seg))
        h.append("prompt.submitted", {"prompt_id": None, "chars": 1}, seg=seg)
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
            for record in read_jsonl(log).records:
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
            ("segment", lambda d: d.update(index=0)),
            ("segment", lambda d: d["transcript"].update(sha256="nothex")),
            ("segment", lambda d: d["summary"].update(status="maybe")),
        ],
    )
    def test_schemas_reject_malformed_projections(self, name, mutate):
        source = "session.json" if name == "session" else "seg-001.json"
        doc = load(FIXTURE / "expected" / source)
        mutate(doc)
        assert schema.validate(doc, schema.load(name)) != []

    def test_consumers_and_clear_link_schemas(self):
        ok_consumers = {"schema": "claudna.consumers/1", "sid": "s",
                        "consumers": {"claudron": {"through_seg": 2, "acked_at": "2026-09-28T10:00:00.000Z"}}}
        assert schema.validate(ok_consumers, schema.load("consumers")) == []
        ok_consumers["consumers"]["claudron"]["through_seg"] = 0
        assert schema.validate(ok_consumers, schema.load("consumers")) != []
        link = {"schema": "claudna.clear-link/1", "pid": 4242, "sid": "s", "chain_id": "s",
                "ts": "2026-09-28T10:00:00.000Z"}
        assert schema.validate(link, schema.load("clear-link")) == []
        assert schema.validate({**link, "pid": 0}, schema.load("clear-link")) != []

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
        assert check_session(SessionStore(root).session(FIXTURE_SID))

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

    def test_usage_error_exits_2(self):
        assert run_cli("frobnicate").returncode == 2
