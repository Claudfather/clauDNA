"""Deterministic subprocess and loss boundaries; no provider calls or user state."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from conftest import ACTOR, ORIGIN

from claudna import delegation as d
from claudna.session_store import readers
from claudna.session_store.fsio import exclusive_lock


@pytest.fixture
def job(store, tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDNA_SESSION_STORE", raising=False)
    parent = store.session("parent")
    parent.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path=None, agent_cli="claude")
    work = tmp_path / "work"
    work.mkdir()
    (work / "code.txt").write_text("before")
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "add", "code.txt"], cwd=work, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "baseline"], cwd=work, check=True)
    req = d.Request(parent_sid="parent", parent_provider="claude", provider="codex", cwd=str(work),
                    owned_paths=["code.txt"], task="bounded task", model=None, deadline_seconds=10,
                    workspace_owned=True)
    return req, work


def worker(monkeypatch, code="", *, final=None, exit_code=0):
    records = [{"type": "thread.started", "thread_id": "native-child"},
               {"type": "item.completed", "item": {"type": "agent_message", "text": "observed"}},
               {"type": "turn.completed"}] if final is None else final
    script = code + "\nimport json,sys\n"
    script += "\n".join("print(" + repr(json.dumps(r)) + ",flush=True)" for r in records)
    script += f"\nsys.exit({exit_code})\n"
    monkeypatch.setattr(d, "native_command", lambda request: [sys.executable, "-c", script])


def test_run_records_child_cleans_bookkeeping_and_settles(store, job, monkeypatch):
    import io

    req, work = job
    worker(monkeypatch, "from pathlib import Path\nPath('code.txt').write_text('after')")
    result = d.run_job(req, store)
    assert (result.outcome, result.cleanup, result.child_sid) == ("completed", "complete", "native-child")
    assert (work / "code.txt").read_text() == "after"
    assert {p.name for p in (store.root / "delegation").iterdir()} == {".lock"}
    payload = {"parent_sid": "parent", "job_id": result.job_id,
               "decision": "accepted", "evidence": "behavior check passed"}
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode())))
    assert d.main(["settle", "--root", str(store.root), "--request", "-"]) == 0
    d.settle(store, "parent", result.job_id, "accepted", "behavior check passed")
    shown = readers.show(store, "parent")
    assert shown["session"]["children"] == []
    assert shown["delegations"][0]["decision"] == "accepted"
    with pytest.raises(d.StoreError):
        d.settle(store, "parent", result.job_id, "rejected", "changed my mind")
    payload["evidence"] = 5
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode())))
    assert d.main(["settle", "--root", str(store.root), "--request", "-"]) == 1


def test_nonzero_exit_keeps_all_worker_edits(store, job, monkeypatch):
    req, work = job
    worker(monkeypatch, "from pathlib import Path\nPath('code.txt').write_text('partial')\n"
                       "Path('untracked.bin').write_bytes(b'\\x00partial')", exit_code=2)
    result = d.run_job(req, store)
    assert result.outcome == "failed" and result.cleanup == "complete"
    assert (work / "code.txt").read_text() == "partial"
    assert (work / "untracked.bin").read_bytes() == b"\x00partial"


@pytest.mark.parametrize("records", [
    [{"type": "turn.completed"}],
    [{"type": "thread.started", "thread_id": "native-child"}, {"type": "turn.failed"}],
    [{"type": "thread.started", "thread_id": "../escape"}, {"type": "turn.completed"}],
    [{"type": "thread.started", "thread_id": "native-child"}, {"type": "error", "message": "denied"},
     {"type": "turn.completed"}],
])
def test_incomplete_protocol_is_not_success(store, job, monkeypatch, records):
    worker(monkeypatch, final=records)
    result = d.run_job(job[0], store)
    assert result.outcome != "completed" and result.cleanup == "complete"


def test_oversized_record_is_drained_without_success(store, job, monkeypatch):
    worker(monkeypatch, "print('x' * (1024 * 1024 + 1),flush=True)")
    result = d.run_job(job[0], store)
    assert result.outcome == "protocol_error" and result.cleanup == "complete"
    assert len(result.summary.encode()) <= 65536


def test_busy_and_unknown_slots_never_launch(store, job, monkeypatch):
    req, _ = job
    monkeypatch.setattr(d, "native_command", lambda req: pytest.fail("must not launch"))
    root = store.root / "delegation"
    root.mkdir()
    with exclusive_lock(root / ".lock"):
        assert d.reconcile(store)["outcome"] == "busy"
        assert d.run_job(req, store).outcome == "busy"
    (root / "active.json").write_text(json.dumps({"job_id": "unknown", "phase": "running"}))
    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert d.run_job(req, store).outcome == "needs_attention"
    assert (root / "active.json").exists()


@pytest.mark.parametrize("entry", ["reconcile", "disabled_run"])
def test_terminal_cleanup_retry_is_idempotent(store, job, monkeypatch, entry):
    from pathlib import Path

    worker(monkeypatch)
    original = Path.unlink
    def fail_active(path, *args, **kwargs):
        if path.name == "active.json":
            raise OSError("injected unlink failure")
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_active)
        result = d.run_job(job[0], store)
    assert result.cleanup == "pending"
    assert readers.show(store, "parent")["delegations"][0]["cleanup"] == "pending"
    d.settle(store, "parent", result.job_id, "accepted", "behavior check passed")
    if entry == "disabled_run":
        with monkeypatch.context() as patch:
            patch.setenv("CLAUDNA_SESSION_STORE", "0")
            patch.setattr(d, "native_command", lambda req: pytest.fail("blocked request must not launch"))
            with pytest.raises(d.DelegationError, match="logging"):
                d.run_job(job[0], store)
    else:
        assert d.reconcile(store)["outcome"] == "cleaned"
    d.settle(store, "parent", result.job_id, "accepted", "behavior check passed")
    shown = readers.show(store, "parent")["delegations"][0]
    assert (shown["decision"], shown["evidence"], shown["cleanup"]) == (
        "accepted", "behavior check passed", "complete")
    assert d.reconcile(store)["outcome"] == "idle"
    timeline = readers.timeline(store, "parent")
    assert sum(e["data"].get("phase") == "finished" for e in timeline) == 1
    assert sum(e["data"].get("phase") == "cleaned" for e in timeline) == 1


@pytest.mark.parametrize("retired_parent", [False, True])
def test_terminal_history_failure_preserves_retry_without_rerun(store, job, monkeypatch, retired_parent):
    import shutil

    from claudna.session_store.store import SessionHandle

    worker(monkeypatch)
    original = SessionHandle._append_once
    def fail_finished(handle, kind, data, key):
        if data.get("phase") == "finished":
            raise OSError("injected history failure")
        return original(handle, kind, data, key)
    with monkeypatch.context() as patch:
        patch.setattr(SessionHandle, "_append_once", fail_finished)
        result = d.run_job(job[0], store)
    assert result.cleanup == "pending"
    if retired_parent:
        shutil.rmtree(store.session("parent").paths.dir)
    monkeypatch.setattr(d, "native_command", lambda req: pytest.fail("must not relaunch"))
    recovery = d.reconcile(store)
    assert recovery["outcome"] == "cleaned"
    if retired_parent:
        assert recovery["warning"] and not store.session("parent").exists()
    assert not (store.root / "delegation/active.json").exists()


def test_deadline_is_failure_and_child_cannot_inherit_parent_logging(store, job, monkeypatch):
    worker(monkeypatch, "import os\nassert os.environ['CLAUDNA_SESSION_CHILD'] == '1'")
    ticks = iter([0, 20])
    monkeypatch.setattr(d.time, "monotonic", lambda: next(ticks, 20))
    result = d.run_job(job[0], store)
    assert result.outcome == "timeout" and result.cleanup == "complete"


def test_dirty_workspace_and_logging_opt_out_do_not_launch(store, job, monkeypatch):
    req, work = job
    monkeypatch.setattr(d, "native_command", lambda req: pytest.fail("must not launch"))
    (work / "code.txt").write_text("user edit")
    with pytest.raises(d.DelegationError, match="clean"):
        d.run_job(req, store)
    monkeypatch.setenv("CLAUDNA_SESSION_STORE", "0")
    with pytest.raises(d.DelegationError, match="logging"):
        d.run_job(req, store)


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_native_fixture_and_same_provider_block(store, job, monkeypatch, provider):
    from dataclasses import replace
    from pathlib import Path

    fixture = json.loads((Path(__file__).parent / "fixtures/delegation" / (provider + ".json")).read_text())
    observed = d.NativeObservation(provider)
    for record in fixture["records"]:
        observed.read(json.dumps(record).encode())
    assert observed.sid and observed.completed and not observed.invalid
    monkeypatch.setattr(d, "native_command", lambda req: pytest.fail("unsupported direction must not launch"))
    with pytest.raises(d.DelegationError, match="same-provider"):
        d.run_job(replace(job[0], provider="claude"), store)


@pytest.mark.parametrize("subtype,is_error,exit_code,outcome", [
    ("success", False, 0, "completed"),
    ("error_max_turns", True, 0, "failed"),
    ("success", False, 2, "failed"),
])
def test_claude_denials_are_reported_separately_from_native_completion(
        store, job, monkeypatch, subtype, is_error, exit_code, outcome):
    from dataclasses import replace

    parent = store.session("codex-parent")
    parent.open_session("startup", actor=ACTOR, origin=ORIGIN, transcript_path=None, agent_cli="codex")
    denial = {"tool_name": "Bash", "tool_use_id": "denied-diagnostic",
              "tool_input": {"command": 'echo "exit=$?"'}}
    worker(monkeypatch, final=[{"type": "result", "subtype": subtype, "is_error": is_error,
                               "session_id": "native-claude-child", "result": "observed",
                               "permission_denials": [denial]}], exit_code=exit_code)
    result = d.run_job(replace(job[0], parent_sid="codex-parent", parent_provider="codex", provider="claude"), store)
    assert result.outcome == outcome and result.cleanup == "complete"
    assert result.permission_denials == [denial]
    shown = readers.show(store, "codex-parent")["delegations"][0]
    assert shown["permission_denials"] == 1 and not shown.get("decision")


def test_claude_command_leaves_permission_policy_to_native_settings(job, monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(d.shutil, "which", lambda name: "/native/" + name)
    req = replace(job[0], parent_provider="codex", provider="claude")
    assert d.native_command(req) == ["/native/claude", "--print", "--output-format", "json",
                                     "--permission-prompts", "none"]


def test_opposite_settlements_are_atomic(store, job, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock

    from claudna.session_store.store import StoreError

    worker(monkeypatch)
    result = d.run_job(job[0], store)
    barrier, append_lock = Barrier(2), Lock()
    original_load, original_record = d.load_lifecycle, d.record_delegation

    def synchronized_read(paths):
        history = original_load(paths)
        barrier.wait(timeout=10)  # Both callers observed the same undecided history.
        return history

    def serialized_append(*args, **kwargs):
        with append_lock:
            return original_record(*args, **kwargs)

    monkeypatch.setattr(d, "load_lifecycle", synchronized_read)
    monkeypatch.setattr(d, "record_delegation", serialized_append)

    def decide(decision):
        try:
            d.settle(store, "parent", result.job_id, decision, "checked")
            return True
        except StoreError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decide, ["accepted", "rejected"]))
    assert sorted(outcomes) == [False, True]
    decisions = [e for e in readers.timeline(store, "parent")
                 if e["data"].get("phase") in ("accepted", "rejected")]
    assert len(decisions) == 1


@pytest.mark.parametrize("error,outcome", [(KeyboardInterrupt, "cancelled"), (OSError, "failed")])
def test_handled_observation_failure_reaps_and_cleans(store, job, monkeypatch, error, outcome):
    worker(monkeypatch, "import time\ntime.sleep(60)")
    original = d.subprocess.Popen
    processes = []

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    def interrupt(selector, timeout):
        raise error("controlled interruption")

    monkeypatch.setattr(d.subprocess, "Popen", launch)
    monkeypatch.setattr(d.selectors.DefaultSelector, "select", interrupt)
    result = d.run_job(job[0], store)
    assert result.outcome == outcome and result.cleanup == "complete"
    assert processes and all(p.poll() is not None for p in processes)
    assert d.reconcile(store)["outcome"] == "idle"


@pytest.mark.parametrize("sig", ["SIGTERM", "SIGHUP"])
def test_cli_signals_use_the_owned_worker_cancellation_path(store, job, sig):
    import dataclasses
    from pathlib import Path

    script = f"""
import os, signal, sys
sys.path.insert(0, {str(Path(d.__file__).resolve().parents[1])!r})
from claudna import delegation as d
d.native_command = lambda request: [sys.executable, '-c', 'import time; time.sleep(20)']
d.selectors.DefaultSelector.select = lambda selector, timeout: os.kill(os.getpid(), signal.{sig})
raise SystemExit(d.main())
"""
    result = subprocess.run([sys.executable, "-c", script, "run", "--root", str(store.root), "--request", "-"],
                            input=json.dumps(dataclasses.asdict(job[0])), text=True,
                            capture_output=True, timeout=30)
    output = json.loads(result.stdout)
    assert result.returncode == 1 and output["outcome"] == "cancelled" and output["cleanup"] == "complete"
    assert not (store.root / "delegation/active.json").exists()


@pytest.mark.parametrize("stage", ["argv", "prompt"])
def test_prelaunch_encoding_failure_does_not_protect_a_nonexistent_worker(store, job, monkeypatch, stage):
    from dataclasses import replace

    command = [sys.executable, "-c", "pass"] + (["\0"] if stage == "argv" else [])
    monkeypatch.setattr(d, "native_command", lambda request: command)
    req = replace(job[0], owned_paths=["\ud800"]) if stage == "prompt" else job[0]
    result = d.run_job(req, store)
    assert result.outcome == "failed" and result.cleanup == "complete" and result.exit_code is None
    assert d.reconcile(store)["outcome"] == "idle"
