"""One foreground native worker, durable session payloads, and a global coordination pointer."""
from __future__ import annotations

import json
import math
import os
import selectors
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from claudna.redact import redact_strings, redact_text
from claudna.session_store.events import AGENT_CLIS
from claudna.session_store.fsio import atomic_write_json, ensure_dir, exclusive_lock, read_json
from claudna.session_store.paths import CHILD_ENV, validate_sid
from claudna.session_store.project import load_lifecycle, session_facts
from claudna.session_store.store import SessionHandle, SessionStore, StoreError, record_delegation

RECORD_LIMIT, RESPONSE_LIMIT, TAIL_LIMIT = 1048576, 65536, 16384
PAYLOAD_LIMIT = 32768
COORDINATION_VERSION = 1


class DelegationError(ValueError):
    """A request cannot be performed without guessing or widening authority."""


@dataclass
class Request:
    parent_sid: str
    parent_provider: str
    provider: str
    cwd: str
    owned_paths: list[str]
    task: str
    model: str | None = None
    deadline_seconds: float = 300
    workspace_owned: bool = False
    read_only: bool = False


@dataclass
class Result:
    job_id: str = ""
    outcome: str = "incomplete"
    child_sid: str | None = None
    exit_code: int | None = None
    summary: str = ""
    cleanup: str = "pending"
    permission_denials: list[dict] = field(default_factory=list)


def native_command(request: Request) -> list[str]:
    if request.provider not in ("codex", "claude"):
        raise DelegationError("unsupported native provider")
    binary = shutil.which(request.provider)
    if not binary:
        raise DelegationError(f"{request.provider} CLI is not installed")
    if request.provider == "codex":
        command = [binary, "exec", "--sandbox", "read-only" if request.read_only else "workspace-write", "--json"]
    else:
        command = [binary, "--print", "--output-format", "json", "--permission-prompts", "none"]
        if request.read_only:
            command += ["--tools", "Read,Glob,Grep"]
    if request.model:
        command += ["--model", request.model]
    return command + (["-"] if request.provider == "codex" else [])


class NativeObservation:
    """Only explicit native evidence; final model prose is not an acceptance verdict."""

    def __init__(self, provider: str):
        self.provider, self.sid, self.response = provider, None, ""
        self.completed = self.failed = self.invalid = False
        self.cancelled = False
        self.permission_denials = []

    def read(self, line: bytes) -> None:
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("protocol record must be an object")
            kind = record.get("type")
            sid = record.get("thread_id") if kind == "thread.started" else None
            if self.provider == "claude" and kind == "result":
                sid = record.get("session_id")
                self.completed = record.get("subtype") == "success" and record.get("is_error") is False
                self.failed = not self.completed
                self.response = record.get("result", "")
                denials = record.get("permission_denials")
                if (not isinstance(denials, list) or any(not isinstance(d, dict) for d in denials)
                        or len(json.dumps(denials).encode()) > RESPONSE_LIMIT):
                    raise ValueError("invalid or oversized permission-denial metadata")
                self.permission_denials = redact_strings(denials)
            if self.provider == "codex":
                if kind == "turn.completed":
                    self.completed = True
                elif kind in ("error", "turn.failed"):
                    self.failed = True
                elif kind == "item.completed" and isinstance(record.get("item"), dict):
                    item = record["item"]
                    if item.get("type") == "agent_message":
                        self.response = item.get("text", "")
                    elif item.get("type") == "refusal":
                        self.failed = True
            if sid is not None:
                validate_sid(sid)
                if self.sid and self.sid != sid:
                    raise ValueError("native identity changed")
                self.sid = sid
            if not isinstance(self.response, str) or len(self.response.encode()) > RESPONSE_LIMIT:
                raise ValueError("native result exceeds response limit")
        except (ValueError, TypeError):
            self.invalid, self.response = True, ""


def _git(cwd: str, *args: str) -> str:
    result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=", *args], cwd=cwd,
                            capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise DelegationError("workspace must be an existing Git checkout with a committed baseline")
    return result.stdout.strip()


def _parent(store: SessionStore, sid: str, provider: str):
    parent = store.session(sid)
    if not parent.exists() or parent.capture_state() != "captured":
        raise DelegationError("parent session is not recorded")
    facts = session_facts(load_lifecycle(parent.paths).events)
    if facts.status == "unknown" or facts.agent_cli != provider:
        raise DelegationError("parent provider does not match recorded session")
    return parent


def _validate(request: Request, store: SessionStore) -> tuple[SessionHandle, str]:
    if os.environ.get("CLAUDNA_SESSION_STORE") == "0":
        raise DelegationError("session logging is disabled")
    if request.provider not in AGENT_CLIS or request.parent_provider not in AGENT_CLIS:
        raise DelegationError("unsupported provider")
    if request.provider == request.parent_provider:
        raise DelegationError("use native subagents for same-provider work")
    parent = _parent(store, request.parent_sid, request.parent_provider)
    if (request.workspace_owned is not True or not isinstance(request.read_only, bool)
            or not isinstance(request.cwd, str) or not Path(request.cwd).is_absolute()
            or not Path(request.cwd).is_dir()):
        raise DelegationError("explicit absolute owned-workspace handoff is required")
    if request.model is not None and (not isinstance(request.model, str) or not request.model.strip()):
        raise DelegationError("model must be an explicit name or null for the native default")
    if (isinstance(request.deadline_seconds, bool) or not isinstance(request.deadline_seconds, (int, float))
            or not math.isfinite(request.deadline_seconds) or not 1 <= request.deadline_seconds <= 3600):
        raise DelegationError("deadline must be between 1 and 3600 seconds")
    if not isinstance(request.task, str) or not request.task or len(request.task.encode()) > RESPONSE_LIMIT:
        raise DelegationError("task must be nonempty and at most 64 KiB")
    if (not isinstance(request.owned_paths, list) or not request.owned_paths
            or any(not isinstance(p, str) or not p or Path(p).is_absolute() or ".." in Path(p).parts
                   for p in request.owned_paths)):
        raise DelegationError("explicit workspace-relative owned paths are required")
    if not request.read_only and _git(request.cwd, "status", "--porcelain", "--untracked-files=all"):
        raise DelegationError("editing requires a clean owned workspace")
    return parent, _git(request.cwd, "rev-parse", "HEAD")


def _data(state: dict, *, cleanup: str = "pending", summary: str = "") -> dict:
    return {"provider": state["provider"], "child_sid": state.get("child_sid"),
            "exit_code": state.get("exit_code"), "outcome": state["outcome"],
            "cleanup": cleanup, "summary": summary,
            **({"permission_denials": state["permission_denials"]} if "permission_denials" in state else {})}


def _save_payload(path: Path, state: dict) -> None:
    if len(json.dumps(state).encode()) > PAYLOAD_LIMIT:
        raise DelegationError("operational record exceeds 32 KiB")
    atomic_write_json(path, state, durable=True)


def _pointer(state: dict) -> dict:
    return {"version": COORDINATION_VERSION, "job_id": state["job_id"],
            "parent_sid": state["parent_sid"], "parent_provider": state["parent_provider"]}


def _matches_pointer(pointer: object, state: dict) -> bool:
    if not isinstance(pointer, dict) or not isinstance(state, dict):
        return False
    try:
        return pointer == _pointer(state)
    except (KeyError, TypeError, ValueError):
        return False


def _clear_pointer(path: Path, expected: dict) -> bool:
    current = read_json(path)
    if current != expected:
        return False
    path.unlink(missing_ok=True)
    return True


def _save_pointer(path: Path, state: dict) -> None:
    atomic_write_json(path, _pointer(state), durable=True)


def _terminal(state: dict) -> bool:
    if not isinstance(state, dict):
        return False
    outcome = state.get("outcome")
    return (state.get("phase") == "finished" and isinstance(outcome, str) and
            outcome in {"completed", "failed", "timeout", "cancelled", "protocol_error"})


def _valid_payload(store: SessionStore, state: dict) -> bool:
    if not isinstance(state, dict):
        return False
    required = {"version", "job_id", "parent_sid", "parent_provider", "provider", "cwd", "base",
                "phase", "outcome", "child_sid", "exit_code", "coordination_cleared"}
    if not required <= state.keys():
        return False
    if (type(state["version"]) is not int or state["version"] != 1
            or not isinstance(state["job_id"], str) or not isinstance(state["parent_sid"], str)
            or not isinstance(state["parent_provider"], str) or state["parent_provider"] not in AGENT_CLIS
            or not isinstance(state["provider"], str) or state["provider"] not in AGENT_CLIS
            or state["parent_provider"] == state["provider"]
            or not isinstance(state["cwd"], str) or not isinstance(state["base"], str)
            or not isinstance(state["phase"], str) or not isinstance(state["outcome"], str)
            or (state["child_sid"] is not None and not isinstance(state["child_sid"], str))
            or (state["exit_code"] is not None and type(state["exit_code"]) is not int)
            or type(state["coordination_cleared"]) is not bool):
        return False
    try:
        validate_sid(state["parent_sid"])
        if state["child_sid"] is not None:
            validate_sid(state["child_sid"])
        store.session(state["parent_sid"]).paths.delegation_record(state["job_id"])
    except (ValueError, TypeError):
        return False
    return True


def _valid_legacy_record(state: dict) -> bool:
    """Validate the exact full-record schema written before v1 pointers."""
    if not isinstance(state, dict):
        return False
    required = {"job_id", "parent_sid", "parent_provider", "provider", "cwd", "base", "phase",
                "outcome", "child_sid", "exit_code"}
    if set(state) not in (required, required | {"permission_denials"}):
        return False
    if (not isinstance(state["job_id"], str) or len(state["job_id"]) > 64
            or not isinstance(state["parent_sid"], str)
            or not isinstance(state["parent_provider"], str) or state["parent_provider"] not in AGENT_CLIS
            or not isinstance(state["provider"], str) or state["provider"] not in AGENT_CLIS
            or state["parent_provider"] == state["provider"]
            or not isinstance(state["cwd"], str) or len(state["cwd"]) > 4096
            or not isinstance(state["base"], str) or len(state["base"]) != 40
            or any(char not in "0123456789abcdef" for char in state["base"])
            or not isinstance(state["phase"], str) or not isinstance(state["outcome"], str)
            or (state["child_sid"] is not None and not isinstance(state["child_sid"], str))
            or (state["exit_code"] is not None and type(state["exit_code"]) is not int)
            or ("permission_denials" in state and
                (type(state["permission_denials"]) is not int or state["permission_denials"] < 0))):
        return False
    try:
        uuid.UUID(state["job_id"])
        validate_sid(state["parent_sid"])
        if state["child_sid"] is not None:
            validate_sid(state["child_sid"])
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _finalize(store: SessionStore, pointer_path: Path, payload_path: Path, state: dict) -> str:
    if not _terminal(state):
        raise DelegationError("worker exit was not observed; do not clean or relaunch")
    parent_handle = store.session(state["parent_sid"])
    parent_state = parent_handle.capture_state()
    if parent_state == "absent" or parent_state == "artifact-only":
        state["coordination_cleared"] = True
        _save_payload(payload_path, state)
        if not _clear_pointer(pointer_path, _pointer(state)):
            raise DelegationError("active delegation pointer changed during cleanup")
        return "Parent history is absent; removed known-terminal bookkeeping without recreating it."
    if parent_state != "captured":
        raise DelegationError("parent lifecycle is incomplete or corrupt; preserve delegation evidence")
    parent = _parent(store, state["parent_sid"], state["parent_provider"])
    if state.get("child_sid"):
        parent.link_child(state["child_sid"], relation="delegation", child_agent_cli=state["provider"],
                          job_id=state["job_id"])
    record_delegation(parent, state["job_id"], "finished", _data(state))
    state["coordination_cleared"] = True
    _save_payload(payload_path, state)
    if not _clear_pointer(pointer_path, _pointer(state)):
        raise DelegationError("active delegation pointer changed during cleanup")
    record_delegation(parent, state["job_id"], "cleaned", _data(state, cleanup="complete"))
    return ""


def _finalize_legacy(store: SessionStore, active_path: Path, state: dict) -> str:
    """Clear only an observed terminal record, retaining it until history is durable."""
    if read_json(active_path) != state:
        raise DelegationError("legacy active record changed before cleanup")
    parent_handle = store.session(state["parent_sid"])
    parent_state = parent_handle.capture_state()
    if parent_state in ("absent", "artifact-only"):
        if not _clear_pointer(active_path, state):
            raise DelegationError("legacy active record changed during cleanup")
        return "Parent history is absent; removed known-terminal bookkeeping without recreating it."
    if parent_state != "captured":
        raise DelegationError("parent lifecycle is incomplete or corrupt; preserve delegation evidence")
    parent = _parent(store, state["parent_sid"], state["parent_provider"])
    if state.get("child_sid"):
        parent.link_child(state["child_sid"], relation="delegation", child_agent_cli=state["provider"],
                          job_id=state["job_id"])
    record_delegation(parent, state["job_id"], "finished", _data(state))
    # The legacy record remains the retry authority until both lifecycle events
    # are durable. A failed unlink is safe: the exact terminal state is retried
    # idempotently under the same global slot lock.
    record_delegation(parent, state["job_id"], "cleaned", _data(state, cleanup="complete"))
    if not _clear_pointer(active_path, state):
        raise DelegationError("legacy active record changed during cleanup")
    return ""


def _recover_cleared_payloads(store: SessionStore, *, allow_recovery: bool = True) -> dict | None:
    """Recover terminal lifecycle cleanup after a durable pointer was removed."""
    recovered = []
    for sid in store.session_ids():
        directory = store.session(sid).paths.delegation
        if not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            try:
                oversized = path.stat().st_size > PAYLOAD_LIMIT
            except OSError:
                return {"outcome": "needs_attention", "reason": "durable delegation payload is unreadable"}
            if path.is_symlink() or oversized:
                return {"outcome": "needs_attention", "reason": "durable delegation payload is unsafe"}
            state = read_json(path)
            if (not _valid_payload(store, state) or not _terminal(state)
                    or state["coordination_cleared"] is not True
                    or path != store.session(state["parent_sid"]).paths.delegation_record(state["job_id"])):
                return {"outcome": "needs_attention", "reason": "orphaned or malformed delegation payload"}
            parent_handle = store.session(state["parent_sid"])
            parent_state = parent_handle.capture_state()
            if parent_state in ("absent", "artifact-only"):
                continue
            if parent_state != "captured":
                return {"outcome": "needs_attention", "reason": "parent lifecycle is incomplete or corrupt"}
            try:
                parent = _parent(store, state["parent_sid"], state["parent_provider"])
            except (ValueError, KeyError, StoreError) as exc:
                return {"outcome": "needs_attention", "reason": redact_text(str(exc))[:1000]}
            lifecycle = load_lifecycle(parent.paths).events
            job_events = [event for event in lifecycle if event["kind"] == "delegation.updated"
                          and event["data"].get("job_id") == state["job_id"]]
            expected_finished = {**_data(state), "job_id": state["job_id"], "phase": "finished"}
            expected_cleaned = {**_data(state, cleanup="complete"),
                                "job_id": state["job_id"], "phase": "cleaned"}
            for phase, expected in (("finished", expected_finished), ("cleaned", expected_cleaned)):
                phase_events = [event["data"] for event in job_events if event["data"].get("phase") == phase]
                if len(phase_events) > 1 or any(any(data.get(key) != value for key, value in expected.items())
                                                for data in phase_events):
                    return {"outcome": "needs_attention", "reason": "parent delegation history disagrees with payload"}
            finished = any(event["data"].get("phase") == "finished" for event in job_events)
            cleaned = any(event["data"].get("phase") == "cleaned" for event in job_events)
            if not finished:
                return {"outcome": "needs_attention", "reason": "cleared payload has no matching finished history"}
            if not cleaned:
                if not allow_recovery:
                    return {"outcome": "needs_attention",
                            "reason": "coordination lock is unavailable for cleanup recovery"}
                try:
                    record_delegation(parent, state["job_id"], "cleaned", _data(state, cleanup="complete"))
                except OSError as exc:
                    return {"outcome": "cleanup_pending", "reason": redact_text(str(exc))[:1000]}
                except (ValueError, KeyError, StoreError) as exc:
                    return {"outcome": "needs_attention", "reason": redact_text(str(exc))[:1000]}
                recovered.append(state["job_id"])
    if recovered:
        return {"outcome": "recovered", "job_ids": recovered}
    return None


def _reconcile_locked(store: SessionStore, pointer_path: Path) -> dict:
    if not pointer_path.exists() and not pointer_path.is_symlink():
        return _recover_cleared_payloads(store) or {"outcome": "idle"}
    if pointer_path.is_symlink():
        return {"outcome": "needs_attention", "reason": "operational record is a symlink"}
    try:
        if pointer_path.stat().st_size > PAYLOAD_LIMIT:
            return {"outcome": "needs_attention", "reason": "coordination pointer exceeds the record limit"}
    except OSError:
        return {"outcome": "needs_attention", "reason": "coordination pointer is unreadable"}
    pointer = read_json(pointer_path)
    if not isinstance(pointer, dict):
        return {"outcome": "needs_attention", "reason": "coordination pointer is unreadable"}
    if set(pointer) != {"version", "job_id", "parent_sid", "parent_provider"}:
        if not _valid_legacy_record(pointer):
            return {"outcome": "needs_attention", "reason": "legacy or unknown delegation state; do not relaunch"}
        if not _terminal(pointer):
            return {"outcome": "needs_attention", "reason": "worker exit was not observed; do not relaunch"}
        try:
            warning = _finalize_legacy(store, pointer_path, pointer)
        except OSError as exc:
            return {"outcome": "cleanup_pending", "reason": redact_text(str(exc))[:1000]}
        except (ValueError, KeyError, StoreError) as exc:
            return {"outcome": "needs_attention", "reason": redact_text(str(exc))[:1000]}
        return {"outcome": "cleaned", "job_id": pointer["job_id"],
                **({"warning": warning} if warning else {})}
    pointer_provider = pointer.get("parent_provider")
    if (type(pointer.get("version")) is not int or pointer.get("version") != COORDINATION_VERSION or
            not isinstance(pointer_provider, str) or pointer_provider not in AGENT_CLIS):
        return {"outcome": "needs_attention", "reason": "unknown coordination pointer version or provider"}
    try:
        payload_path = store.session(pointer["parent_sid"]).paths.delegation_record(pointer["job_id"])
    except (ValueError, TypeError):
        return {"outcome": "needs_attention", "reason": "invalid coordination pointer identity"}
    if payload_path.is_symlink():
        return {"outcome": "needs_attention", "reason": "durable delegation payload is a symlink"}
    try:
        if payload_path.stat().st_size > PAYLOAD_LIMIT:
            return {"outcome": "needs_attention", "reason": "durable delegation payload exceeds the record limit"}
    except OSError:
        return {"outcome": "needs_attention", "reason": "durable delegation payload is missing or unreadable"}
    state = read_json(payload_path)
    if not isinstance(state, dict):
        return {"outcome": "needs_attention", "reason": "durable delegation payload is missing or unreadable"}
    if not _valid_payload(store, state) or not _matches_pointer(pointer, state):
        return {"outcome": "needs_attention", "reason": "coordination pointer and durable payload disagree"}
    if not _terminal(state):
        return {"outcome": "needs_attention", "reason": "worker exit was not observed; do not relaunch"}
    try:
        warning = _finalize(store, pointer_path, payload_path, state)
    except OSError as exc:
        return {"outcome": "cleanup_pending", "reason": redact_text(str(exc))[:1000]}
    except (ValueError, KeyError, StoreError) as exc:
        return {"outcome": "needs_attention", "reason": redact_text(str(exc))[:1000]}
    return {"outcome": "cleaned", "job_id": state["job_id"], **({"warning": warning} if warning else {})}


def reconcile(store: SessionStore) -> dict:
    root = store.root / "delegation"
    if not root.exists():
        return _recover_cleared_payloads(store, allow_recovery=False) or {"outcome": "idle"}
    with exclusive_lock(root / ".lock", blocking=False) as taken:
        return _reconcile_locked(store, root / "active.json") if taken else {"outcome": "busy"}


def _observe(command: list[str], request: Request) -> tuple[int | None, NativeObservation, bool, str]:
    observation = NativeObservation(request.provider)
    timed_out, tail, buffer, dropping = False, b"", b"", False
    deadline = time.monotonic() + request.deadline_seconds
    try:
        prompt = (f"Bounded task. Own only: {', '.join(request.owned_paths)}. No subagents, commits, pushes, "
                  "deployments, external messages, detached processes or dependency installs. Preserve project "
                  "policy and others' work. Report actual results; do not self-certify acceptance.\n"
                  + request.task).encode()
        process = subprocess.Popen(command, cwd=request.cwd, env={**os.environ, CHILD_ENV: "1"},
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
    except (OSError, ValueError) as exc:
        return None, observation, False, redact_text(str(exc))
    with process:
        try:
            with selectors.DefaultSelector() as selector:
                for stream, events in ((process.stdin, selectors.EVENT_WRITE),
                                       (process.stdout, selectors.EVENT_READ), (process.stderr, selectors.EVENT_READ)):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, events)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                    for key, _ in selector.select(min(remaining, 1)):
                        stream = key.fileobj
                        if stream is process.stdin:
                            try:
                                count = os.write(stream.fileno(), prompt[:65536])
                                prompt = prompt[count:]
                            except BrokenPipeError:
                                prompt = b""
                            if not prompt:
                                selector.unregister(stream)
                                stream.close()
                            continue
                        chunk = os.read(stream.fileno(), 65536)
                        if not chunk:
                            selector.unregister(stream)
                            continue
                        if stream is process.stderr:
                            tail = (tail + chunk)[-TAIL_LIMIT:]
                            continue
                        for part in chunk.splitlines(keepends=True):
                            ended = part.endswith(b"\n")
                            if not dropping:
                                buffer += part
                                if len(buffer) > RECORD_LIMIT:
                                    observation.invalid, dropping, buffer = True, True, b""
                            if ended:
                                if not dropping and buffer.strip():
                                    observation.read(buffer)
                                buffer, dropping = b"", False
                if buffer.strip() and not timed_out:
                    observation.read(buffer)
            if timed_out:
                os.killpg(process.pid, signal.SIGKILL)
            try:
                exit_code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                exit_code = process.wait()
        except BaseException as exc:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            exit_code = process.wait()
            if isinstance(exc, KeyboardInterrupt):
                observation.cancelled = True
            elif isinstance(exc, Exception):
                observation.failed, observation.response = True, ""
                tail = ("Observation failed: " + str(exc)).encode()[-TAIL_LIMIT:]
            else:
                raise
    return exit_code, observation, timed_out, redact_text(tail.decode(errors="replace"))


def run_job(request: Request, store: SessionStore) -> Result:
    root = ensure_dir(store.root / "delegation")
    path = root / "active.json"
    with exclusive_lock(root / ".lock", blocking=False) as taken:
        if not taken:
            return Result(outcome="busy")
        prior = _reconcile_locked(store, path)
        if prior["outcome"] not in ("idle", "cleaned"):
            return Result(outcome=prior["outcome"], summary=prior.get("reason", ""))
        parent, base = _validate(request, store)
        command = native_command(request)
        job_id = str(uuid.uuid4())
        state = {"version": 1, "job_id": job_id, "parent_sid": request.parent_sid,
                 "parent_provider": request.parent_provider,
                 "provider": request.provider, "cwd": request.cwd, "base": base,
                 "phase": "running", "outcome": "incomplete", "child_sid": None, "exit_code": None,
                 "coordination_cleared": False}
        payload_path = parent.paths.delegation_record(job_id)
        ensure_dir(payload_path.parent)
        _save_payload(payload_path, state)
        record_delegation(parent, job_id, "started", _data(state))
        _save_pointer(path, state)
        exit_code, observed, timed_out, diagnostic = _observe(command, request)
        state.update(exit_code=exit_code, child_sid=observed.sid, phase="finished",
                     permission_denials=len(observed.permission_denials))
        state["outcome"] = ("cancelled" if observed.cancelled else "timeout" if timed_out else
                            "protocol_error" if observed.invalid else
                            "completed" if exit_code == 0 and observed.sid and observed.completed
                            and not observed.failed else "failed")
        _save_payload(payload_path, state)
        result = Result(job_id, state["outcome"], observed.sid, exit_code,
                        redact_text(observed.response or diagnostic)[:RESPONSE_LIMIT],
                        permission_denials=observed.permission_denials)
        try:
            warning = _finalize(store, path, payload_path, state)
            result.cleanup = "complete"
            if warning:
                result.summary = (warning + "\n" + result.summary)[:RESPONSE_LIMIT]
        except OSError:
            _save_payload(payload_path, state)
            try:
                record_delegation(parent, job_id, "cleanup_pending", _data(state))
            except (OSError, ValueError, StoreError):
                pass  # The durable operational record is the retry authority, not a success claim.
            result.cleanup = "pending"
        except (ValueError, StoreError) as exc:
            _save_payload(payload_path, state)
            result.cleanup = "needs_attention"
            result.summary = (redact_text(str(exc)) + "\n" + result.summary)[:RESPONSE_LIMIT]
        return result


def settle(store: SessionStore, parent_sid: str, job_id: str, decision: str, evidence: str) -> dict:
    if decision not in ("accepted", "rejected") or not isinstance(evidence, str) or not evidence.strip():
        raise DelegationError("settlement requires an explicit decision and check evidence")
    parent = store.session(parent_sid)
    events = [e["data"] for e in load_lifecycle(parent.paths).events
              if e["kind"] == "delegation.updated" and e["data"]["job_id"] == job_id]
    finished = next((e for e in events if e["phase"] == "finished"), None)
    if not finished:
        raise DelegationError("job has no observed finish")
    return record_delegation(parent, job_id, decision, {
        **{k: v for k, v in finished.items() if k not in ("job_id", "phase")},
        "cleanup": "complete" if any(e["phase"] == "cleaned" for e in events) else "pending",
        "summary": evidence,
    })


def main(argv: list[str] | None = None) -> int:
    import argparse
    from claudna.session_store import readers

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb", choices=("run", "settle", "status", "reconcile"))
    parser.add_argument("--root")
    parser.add_argument("--request", choices=("-",))
    parser.add_argument("--parent")
    args = parser.parse_args(argv)
    import sys

    try:
        store = SessionStore(Path(args.root)) if args.root else SessionStore()
        payload = None
        if args.request == "-":
            if args.verb not in ("run", "settle"):
                raise DelegationError("JSON input is supported only by run and settle")
            raw = sys.stdin.buffer.read(RECORD_LIMIT + 1)
            if len(raw) > RECORD_LIMIT:
                raise DelegationError("request exceeds 1 MiB")
            payload = json.loads(raw)
        if args.verb == "run":
            if args.request != "-":
                raise DelegationError("run requires --request -")
            handlers = {sig: signal.signal(sig, signal.default_int_handler) for sig in (signal.SIGTERM, signal.SIGHUP)}
            try:
                output = asdict(run_job(Request(**payload), store))
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
        elif args.verb == "settle":
            if args.request != "-":
                raise DelegationError("settle requires --request -")
            output = settle(store, **payload)
        elif args.verb == "status":
            if not args.parent:
                raise DelegationError("status requires --parent")
            output = {"delegations": readers.show(store, args.parent)["delegations"],
                      "active": read_json(store.root / "delegation" / "active.json")}
        else:
            output = reconcile(store)
        print(json.dumps(output))
        return 0 if args.verb != "run" or (output["outcome"] == "completed" and output["cleanup"] == "complete") else 1
    except (OSError, ValueError, TypeError, KeyError, StoreError) as exc:
        print(json.dumps({"outcome": "blocked", "error": redact_text(str(exc))[:1000]}))
        return 1
