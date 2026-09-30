"""Tests for the ops log (ops.py, and the worker verbs that write it) — phase 7.

What these guard: every background run (summarize, harvest, sweep) leaves one
record with its kind, timing, outcome and the sessions it touched; the log
reads back newest first and filters by kind and time; an unwritable log never
fails a run; and the hook's hot path never imports it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ACTOR, ORIGIN

from claudna.session_store import harvest, ops
from claudna.session_store.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestRecord:
    def test_a_record_has_the_documented_shape(self, tmp_path):
        rec = ops.record(tmp_path, "summarize", started=0.0, outcome="summarized: 2 block(s)", sessions=["b", "a", "a"],
                         detail={"seg": 1})
        assert set(rec) == {"run_id", "kind", "started_at", "duration_ms", "outcome", "sessions", "detail"}
        assert rec["sessions"] == ["a", "b"] and rec["started_at"] == "1970-01-01T00:00:00Z"
        assert json.loads(ops.log_path(tmp_path).read_text()) == rec
        assert ops.log_path(tmp_path).stat().st_mode & 0o077 == 0

    def test_runs_read_newest_first_and_filter(self, tmp_path):
        ops.record(tmp_path, "harvest", started=100.0, outcome="done")
        ops.record(tmp_path, "sweep", started=200.0, outcome="done")
        ops.record(tmp_path, "harvest", started=300.0, outcome="error")
        assert [r["started_at"][-9:] for r in ops.runs(tmp_path)] == ["00:05:00Z", "00:03:20Z", "00:01:40Z"]
        assert [r["outcome"] for r in ops.runs(tmp_path, kind="harvest")] == ["error", "done"]
        assert len(ops.runs(tmp_path, since="1970-01-01T00:03:00Z")) == 2

    def test_an_unwritable_log_never_fails_the_run(self, tmp_path):
        (tmp_path / "runs").write_text("not a directory")
        assert ops.record(tmp_path, "sweep", started=0.0, outcome="done") is None

    def test_an_unknown_kind_is_a_programming_error(self, tmp_path):
        with pytest.raises(ValueError):
            ops.record(tmp_path, "rebuild", started=0.0, outcome="x")


class TestWorkersRecord:
    def test_summarize_harvest_and_sweep_each_leave_a_record(self, store, monkeypatch, capsys):
        h = store.session("s1")
        h.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path="/nope.jsonl")
        h.open_segment("session_open", 0)
        h.seal_segment(0, "precompact")
        root = ["--root", str(store.root)]
        monkeypatch.setattr(harvest, "run_claudron_capture", lambda *a, **k: pytest.fail("no capture expected"))
        assert main(["summarize", "s1", "1", *root]) == 0
        assert main(["harvest", "--force", *root]) == 0
        assert main(["sweep", *root]) == 0
        capsys.readouterr()
        kinds = [r["kind"] for r in ops.runs(store.root)]
        assert sorted(kinds) == ["harvest", "summarize", "sweep"]
        (summ,) = ops.runs(store.root, kind="summarize")
        assert summ["sessions"] == ["s1"] and summ["detail"] == {"seg": 1} and summ["outcome"].startswith("skipped")
        assert main(["runs", "--kind", "sweep", *root]) == 0 and "sweep" in capsys.readouterr().out


def test_the_hook_path_never_imports_the_ops_log():
    code = "import sys; sys.path.insert(0, 'lib'); import claudna.session_store.cli; " \
           "print('claudna.session_store.ops' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO_ROOT).stdout
    assert out.strip() == "False"
