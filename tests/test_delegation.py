"""Deterministic subprocess and loss boundaries; no provider calls or user state."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from conftest import ACTOR, ORIGIN

from claudna import delegation as d
from claudna.session_store import readers
from claudna.session_store.fsio import atomic_write_json, ensure_dir, exclusive_lock
from claudna.session_store.project import load_lifecycle


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
    payload_path = store.session("parent").paths.delegation_record(result.job_id)
    assert json.loads(payload_path.read_text())["coordination_cleared"] is True
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
        session_dir = store.session("parent").paths.dir
        for child in session_dir.iterdir():
            if child.name == "delegation":
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    monkeypatch.setattr(d, "native_command", lambda req: pytest.fail("must not relaunch"))
    recovery = d.reconcile(store)
    assert recovery["outcome"] == "cleaned"
    if retired_parent:
        assert recovery["warning"] and store.session("parent").exists()
        assert not store.session("parent").paths.lifecycle.exists()
        payload = store.session("parent").paths.delegation_record(result.job_id)
        assert payload.exists()
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


def _write_active_payload(store, state, pointer=None):
    payload = store.session(state["parent_sid"]).paths.delegation_record(state["job_id"])
    ensure_dir(payload.parent)
    atomic_write_json(payload, state, durable=True)
    active = ensure_dir(store.root / "delegation") / "active.json"
    atomic_write_json(active, d._pointer(state) if pointer is None else pointer, durable=True)
    return active, payload


def test_payload_written_before_pointer_and_orphan_blocks_relaunch(store, job, monkeypatch):
    req, _ = job
    monkeypatch.setattr(d, "native_command", lambda request: [sys.executable, "-c", "pass"])
    monkeypatch.setattr(d, "_observe", lambda *args: pytest.fail("pointer crash must happen before launch"))
    monkeypatch.setattr(d, "_save_pointer", lambda *args: (_ for _ in ()).throw(OSError("pointer crash")))
    with pytest.raises(OSError, match="pointer crash"):
        d.run_job(req, store)
    payloads = list(store.session("parent").paths.delegation.glob("*.json"))
    assert len(payloads) == 1
    assert not (store.root / "delegation" / "active.json").exists()
    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert d.run_job(req, store).outcome == "needs_attention"


def test_uncleaned_terminal_payload_recovers_cleaned_event_without_relaunch(store, job, monkeypatch):
    worker(monkeypatch)
    record = d.record_delegation

    def fail_cleaned(parent, job_id, phase, data):
        if phase == "cleaned":
            raise OSError("simulated crash after pointer removal")
        return record(parent, job_id, phase, data)

    monkeypatch.setattr(d, "record_delegation", fail_cleaned)
    result = d.run_job(job[0], store)
    assert result.cleanup == "pending"
    active = store.root / "delegation" / "active.json"
    payload = store.session("parent").paths.delegation_record(result.job_id)
    assert not active.exists() and payload.exists()

    monkeypatch.setattr(d, "record_delegation", record)
    assert d.reconcile(store) == {"outcome": "recovered", "job_ids": [result.job_id]}
    events = [event for event in load_lifecycle(store.session("parent").paths).events
              if event["kind"] == "delegation.updated" and event["data"]["job_id"] == result.job_id]
    assert [event["data"]["phase"] for event in events].count("finished") == 1
    assert [event["data"]["phase"] for event in events].count("cleaned") == 1
    assert payload.exists() and json.loads(payload.read_text())["coordination_cleared"] is True
    assert d.reconcile(store)["outcome"] == "idle"


def test_cleared_but_nonterminal_orphan_payload_still_blocks_relaunch(store, job, monkeypatch):
    state = {"version": 1, "job_id": "job-cleared-running", "parent_sid": "parent",
             "parent_provider": "claude", "provider": "codex", "cwd": "/work", "base": "0" * 40,
             "phase": "running", "outcome": "incomplete", "child_sid": None, "exit_code": None,
             "coordination_cleared": True}
    payload = store.session("parent").paths.delegation_record(state["job_id"])
    ensure_dir(payload.parent)
    atomic_write_json(payload, state, durable=True)
    before = payload.read_bytes()
    monkeypatch.setattr(d, "native_command", lambda request: pytest.fail("must not launch"))

    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert d.run_job(job[0], store).outcome == "needs_attention"
    assert payload.read_bytes() == before


def test_no_coordination_or_payload_is_read_only_idle(store):
    root = store.root / "delegation"
    assert not root.exists()

    assert d.reconcile(store)["outcome"] == "idle"
    assert not root.exists()


def test_active_coordination_file_is_a_minimal_pointer_to_durable_payload(store, job, monkeypatch):
    worker(monkeypatch)
    observe = d._observe
    seen = {}

    def inspect_before_launch(command, request):
        active = json.loads((store.root / "delegation" / "active.json").read_text())
        payload = store.session(request.parent_sid).paths.delegation_record(active["job_id"])
        state = json.loads(payload.read_text())
        seen.update(active=active, state=state)
        return observe(command, request)

    monkeypatch.setattr(d, "_observe", inspect_before_launch)
    result = d.run_job(job[0], store)
    assert result.cleanup == "complete"
    assert set(seen["active"]) == {"version", "job_id", "parent_sid", "parent_provider"}
    assert seen["active"] == d._pointer(seen["state"])
    assert seen["state"]["phase"] == "running"


def test_missing_payload_and_pointer_payload_mismatch_are_preserved(store, job):
    req, _ = job
    root = ensure_dir(store.root / "delegation")
    pointer = {"version": 1, "job_id": "job-a", "parent_sid": req.parent_sid,
               "parent_provider": req.parent_provider}
    atomic_write_json(root / "active.json", pointer)
    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert (root / "active.json").exists()

    malformed_payload = store.session(req.parent_sid).paths.delegation_record("job-a")
    ensure_dir(malformed_payload.parent)
    malformed_payload.write_text('{"version": 1}')
    before = malformed_payload.read_bytes()
    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert malformed_payload.read_bytes() == before

    state = {**pointer, "version": 1, "provider": "codex", "cwd": str(job[1]), "base": "0" * 40,
             "phase": "finished", "outcome": "completed", "child_sid": "child", "exit_code": 0,
             "coordination_cleared": False}
    active, payload = _write_active_payload(store, state)
    mismatched = {**pointer, "parent_provider": "codex"}
    atomic_write_json(active, mismatched)
    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert active.exists() and payload.exists()


@pytest.mark.parametrize("field,value", [
    ("parent_provider", []), ("parent_provider", {}), ("parent_provider", None),
    ("provider", []), ("provider", {}), ("provider", None),
    ("phase", []), ("phase", {}), ("phase", None),
    ("outcome", []), ("outcome", {}), ("outcome", None),
])
def test_malformed_payload_values_are_retained_byte_for_byte(store, field, value):
    state = {"version": 1, "job_id": "job-malformed", "parent_sid": "parent",
             "parent_provider": "claude", "provider": "codex", "cwd": "/work", "base": "0" * 40,
             "phase": "finished", "outcome": "completed", "child_sid": None, "exit_code": 0,
             "coordination_cleared": False}
    active, payload = _write_active_payload(store, state)
    malformed = {**state, field: value}
    atomic_write_json(payload, malformed, durable=True)
    before = payload.read_bytes()

    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert active.exists() and payload.read_bytes() == before


@pytest.mark.parametrize("value", [[], {}, None])
def test_malformed_pointer_provider_is_retained_byte_for_byte(store, value):
    state = {"version": 1, "job_id": "job-pointer-malformed", "parent_sid": "parent",
             "parent_provider": "claude", "provider": "codex", "cwd": "/work", "base": "0" * 40,
             "phase": "finished", "outcome": "completed", "child_sid": None, "exit_code": 0,
             "coordination_cleared": False}
    active, payload = _write_active_payload(store, state)
    pointer = {**d._pointer(state), "parent_provider": value}
    atomic_write_json(active, pointer, durable=True)
    before = active.read_bytes()

    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert active.read_bytes() == before and payload.exists()


def test_terminal_payload_with_missing_parent_clears_only_pointer(store):
    state = {"version": 1, "job_id": "job-terminal", "parent_sid": "retired-parent",
             "parent_provider": "claude", "provider": "codex", "cwd": "/work", "base": "0" * 40,
             "phase": "finished", "outcome": "completed", "child_sid": None, "exit_code": 0,
             "coordination_cleared": False}
    active, payload = _write_active_payload(store, state)
    report = d.reconcile(store)
    assert report["outcome"] == "cleaned" and report["warning"]
    assert not active.exists() and payload.exists()
    assert json.loads(payload.read_text())["coordination_cleared"] is True


def test_terminal_provider_mismatch_keeps_pointer_and_payload(store):
    store.session("parent").open_session("startup", actor=ACTOR, origin=ORIGIN,
                                         transcript_path=None, agent_cli="claude")
    state = {"version": 1, "job_id": "job-provider", "parent_sid": "parent",
             "parent_provider": "codex", "provider": "claude", "cwd": "/work", "base": "0" * 40,
             "phase": "finished", "outcome": "completed", "child_sid": None, "exit_code": 0,
             "coordination_cleared": False}
    active, payload = _write_active_payload(store, state)
    report = d.reconcile(store)
    assert report["outcome"] == "needs_attention"
    assert active.exists() and payload.exists()


def test_corrupt_parent_lifecycle_keeps_terminal_evidence(store):
    state = {"version": 1, "job_id": "job-corrupt-parent", "parent_sid": "parent",
             "parent_provider": "claude", "provider": "codex", "cwd": "/work", "base": "0" * 40,
             "phase": "finished", "outcome": "completed", "child_sid": None, "exit_code": 0,
             "coordination_cleared": False}
    active, payload = _write_active_payload(store, state)
    with store.session("parent").paths.lifecycle.open("a") as lifecycle:
        lifecycle.write("torn lifecycle record\n")
    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert active.exists() and payload.exists()


def test_legacy_full_and_unknown_records_are_read_only_and_never_relaunched(store, job, monkeypatch):
    root = ensure_dir(store.root / "delegation")
    legacy = {"job_id": "legacy", "parent_sid": "parent", "parent_provider": "claude",
              "provider": "codex", "phase": "running", "outcome": "incomplete"}
    atomic_write_json(root / "active.json", legacy)
    before = (root / "active.json").read_bytes()
    monkeypatch.setattr(d, "native_command", lambda request: pytest.fail("must not launch"))
    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert (root / "active.json").read_bytes() == before
    assert d.run_job(job[0], store).outcome == "needs_attention"


def test_known_terminal_legacy_record_cleans_against_captured_history_once(store, job):
    legacy = {"job_id": "00000000-0000-4000-8000-000000000001", "parent_sid": "parent",
              "parent_provider": "claude", "provider": "codex", "cwd": str(job[1]), "base": "0" * 40,
              "phase": "finished", "outcome": "completed", "child_sid": None, "exit_code": 0,
              "permission_denials": 0}
    active = ensure_dir(store.root / "delegation") / "active.json"
    atomic_write_json(active, legacy, durable=True)

    assert d.reconcile(store)["outcome"] == "cleaned"
    assert not active.exists()
    events = [event for event in load_lifecycle(store.session("parent").paths).events
              if event["kind"] == "delegation.updated" and event["data"]["job_id"] == legacy["job_id"]]
    assert [event["data"]["phase"] for event in events] == ["finished", "cleaned"]
    assert d.reconcile(store)["outcome"] == "idle"
    assert len([event for event in load_lifecycle(store.session("parent").paths).events
                if event["kind"] == "delegation.updated" and event["data"]["job_id"] == legacy["job_id"]]) == 2


def test_legacy_cleaned_write_failure_retains_terminal_retry_authority(store, job, monkeypatch):
    legacy = {"job_id": "00000000-0000-4000-8000-000000000004", "parent_sid": "parent",
              "parent_provider": "claude", "provider": "codex", "cwd": str(job[1]), "base": "0" * 40,
              "phase": "finished", "outcome": "completed", "child_sid": None, "exit_code": 0,
              "permission_denials": 0}
    active = ensure_dir(store.root / "delegation") / "active.json"
    atomic_write_json(active, legacy, durable=True)
    before = active.read_bytes()
    record = d.record_delegation

    def fail_cleaned(parent, job_id, phase, data):
        if phase == "cleaned":
            raise OSError("injected cleaned write failure")
        return record(parent, job_id, phase, data)

    monkeypatch.setattr(d, "record_delegation", fail_cleaned)
    assert d.reconcile(store)["outcome"] == "cleanup_pending"
    assert active.read_bytes() == before
    events = [event for event in load_lifecycle(store.session("parent").paths).events
              if event["kind"] == "delegation.updated" and event["data"]["job_id"] == legacy["job_id"]]
    assert [event["data"]["phase"] for event in events] == ["finished"]

    monkeypatch.setattr(d, "record_delegation", record)
    assert d.reconcile(store)["outcome"] == "cleaned"
    assert not active.exists()
    events = [event for event in load_lifecycle(store.session("parent").paths).events
              if event["kind"] == "delegation.updated" and event["data"]["job_id"] == legacy["job_id"]]
    assert [event["data"]["phase"] for event in events] == ["finished", "cleaned"]
    assert d.reconcile(store)["outcome"] == "idle"


def test_legacy_unlink_failure_keeps_record_and_does_not_launch(store, job, monkeypatch):
    from pathlib import Path

    legacy = {"job_id": "00000000-0000-4000-8000-000000000005", "parent_sid": "parent",
              "parent_provider": "claude", "provider": "codex", "cwd": str(job[1]), "base": "0" * 40,
              "phase": "finished", "outcome": "completed", "child_sid": None, "exit_code": 0,
              "permission_denials": 0}
    active = ensure_dir(store.root / "delegation") / "active.json"
    atomic_write_json(active, legacy, durable=True)
    before = active.read_bytes()
    original_unlink = Path.unlink

    def fail_active(path, *args, **kwargs):
        if path == active:
            raise OSError("injected active unlink failure")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_active)
        patch.setattr(d, "native_command", lambda request: pytest.fail("must not relaunch"))
        assert d.reconcile(store)["outcome"] == "cleanup_pending"
        assert d.run_job(job[0], store).outcome == "cleanup_pending"
    assert active.read_bytes() == before
    monkeypatch.setattr(d, "native_command", lambda request: pytest.fail("must not relaunch"))
    assert d.reconcile(store)["outcome"] == "cleaned"
    events = [event for event in load_lifecycle(store.session("parent").paths).events
              if event["kind"] == "delegation.updated" and event["data"]["job_id"] == legacy["job_id"]]
    assert [event["data"]["phase"] for event in events] == ["finished", "cleaned"]
    assert d.reconcile(store)["outcome"] == "idle"


def test_known_terminal_legacy_record_with_absent_parent_clears_without_history(store):
    legacy = {"job_id": "00000000-0000-4000-8000-000000000002", "parent_sid": "retired-parent",
              "parent_provider": "claude", "provider": "codex", "cwd": "/work", "base": "0" * 40,
              "phase": "finished", "outcome": "failed", "child_sid": None, "exit_code": 1,
              "permission_denials": 0}
    active = ensure_dir(store.root / "delegation") / "active.json"
    atomic_write_json(active, legacy, durable=True)

    report = d.reconcile(store)
    assert report["outcome"] == "cleaned" and report["warning"]
    assert not active.exists()
    assert not store.session("retired-parent").exists()
    assert d.reconcile(store)["outcome"] == "idle"


def test_known_terminal_legacy_provider_mismatch_is_preserved(store, job):
    legacy = {"job_id": "00000000-0000-4000-8000-000000000003", "parent_sid": "parent",
              "parent_provider": "codex", "provider": "claude", "cwd": str(job[1]), "base": "0" * 40,
              "phase": "finished", "outcome": "completed", "child_sid": None, "exit_code": 0,
              "permission_denials": 0}
    active = ensure_dir(store.root / "delegation") / "active.json"
    atomic_write_json(active, legacy, durable=True)
    before = active.read_bytes()

    assert d.reconcile(store)["outcome"] == "needs_attention"
    assert active.read_bytes() == before
