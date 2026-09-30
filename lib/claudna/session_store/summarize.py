"""The segment summarizer (spec §7.1): a sealed segment's transcript slice → ``seg-NNN/summary.json``.

Runs out of band, as its own process (``session_store summarize <sid> <seg>``),
spawned detached by the hook that sealed the segment. One run:

1. **Gates.** Records ``summary.skipped`` and stops when the session is
   private, summaries are switched off (``CLAUDNA_SESSION_SUMMARY=0``), the
   session isn't interactive and summaries weren't switched on for it
   (``CLAUDNA_SESSION_SUMMARY=1`` — headless ``claude -p`` and Claudlobby bots
   are off by default), the transcript is gone, or the slice holds no prose.
2. **Idempotence.** Stops without an event when a ``done`` summary already
   covers the same transcript range with the same prompt version — checked
   before anything is read, since the transcript is append-only. One runner
   per segment: a second one finds the segment's lock taken and leaves.
3. **One model call.** ``claude -p`` with its own fresh ``--session-id``, no
   tools, no MCP servers, no settings (``--setting-sources ""``, so neither
   clauDNA's nor any other plugin's hooks fire in the child), the instructions
   in the system prompt, the transcript on stdin as untrusted data, and the
   output held to the schema's ``model_output`` by ``--json-schema``.
4. **Validation, then the write.** The result is checked against
   ``segment-summary.schema.json`` before it is written atomically; then
   ``summary.completed`` makes it visible. Any failure records ``summary.failed``.

The hook applies the same gate before it spawns a worker (so a gated-off
session never starts one); the worker re-checks it for direct CLI calls. The
model call is behind ``runner`` so tests never spawn ``claude``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Callable, Mapping

from claudna.redact import redact_text

from . import schema
from .fsio import atomic_write_json, exclusive_lock, read_json
from .paths import CHILD_ENV
from .project import load_lifecycle, segment_transcript_paths, session_facts, summary_gate
from .store import SessionHandle
from .transcript import read_range, render

SCHEMA_ID = "claudna.segment-summary/1"
PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "segment-summary.md"
PROMPT_VERSION = "segment-summary/1"
MODEL_ENV = "CLAUDNA_SUMMARY_MODEL"
CLAUDE_ENV = "CLAUDNA_CLAUDE_BIN"
DEFAULT_MODEL = "haiku"
TIMEOUT_S = 180
#: Most recent characters of the slice the model sees; older turns are cut first.
INPUT_LIMIT = 120_000


class SummarizerError(RuntimeError):
    """The model call failed or returned something that isn't a valid summary."""

    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def run_claude(system_prompt: str, dialogue: str, output_schema: dict, model: str,
               env: Mapping[str, str]) -> tuple[dict, float | None]:
    """One isolated, tool-less ``claude -p`` call returning schema-shaped JSON and its cost."""
    cmd = [
        env.get(CLAUDE_ENV) or "claude", "-p",
        "--session-id", str(uuid.uuid4()), "--no-session-persistence",
        "--setting-sources", "", "--tools", "", "--strict-mcp-config",
        "--model", model, "--output-format", "json",
        "--system-prompt", system_prompt, "--json-schema", json.dumps(output_schema),
    ]
    child_env = {**env, CHILD_ENV: "1"}
    child_env.pop("CLAUDE_CODE_SESSION_ID", None)  # never let the child inherit this session's id
    try:
        proc = subprocess.run(cmd, input=dialogue, capture_output=True, text=True,
                              timeout=TIMEOUT_S, env=child_env)
    except FileNotFoundError as exc:
        raise SummarizerError(f"claude not found: {exc}", retryable=False) from exc
    except subprocess.TimeoutExpired as exc:
        raise SummarizerError(f"claude timed out after {TIMEOUT_S}s", retryable=True) from exc
    try:
        envelope = json.loads(proc.stdout)
    except ValueError as exc:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
        raise SummarizerError(f"claude exited {proc.returncode}: {tail[0][:150]}", retryable=True) from exc
    if envelope.get("is_error") or not isinstance(envelope.get("structured_output"), dict):
        raise SummarizerError(f"claude returned no structured output ({envelope.get('subtype')})", retryable=True)
    return envelope["structured_output"], envelope.get("total_cost_usd")


def summarize(handle: SessionHandle, index: int, *, env: Mapping[str, str] = os.environ,
              runner: Callable[..., tuple[dict, float | None]] = run_claude) -> str:
    """Summarize sealed segment ``index``; return what happened (see the module doc)."""
    seg = handle.paths.segment(index)
    if not seg.dir.is_dir():
        return f"ignored: no segment {index}"
    with exclusive_lock(seg.dir / ".summarize.lock", blocking=False) as taken:
        if not taken:
            return "ignored: another summarizer holds the segment"
        lifecycle = load_lifecycle(handle.paths).events
        boundary = handle.boundary(index, lifecycle)
        if not boundary.sealed:
            return f"ignored: segment {index} is not sealed"
        reason = summary_gate(session_facts(lifecycle), env)
        if reason:
            return _skip(handle, index, reason)
        path = segment_transcript_paths(lifecycle)[index]
        start, end = boundary.start or 0, boundary.last_seal["data"]["end"]
        wanted = {"transcript_path": path, "range": {"start": start, "end": end}}
        previous = read_json(seg.dir / "summary.json")
        if boundary.summary["status"] == "done" and isinstance(previous, dict) and \
                previous.get("producer", {}).get("prompt_version") == PROMPT_VERSION and \
                {k: previous.get("input", {}).get(k) for k in wanted} == wanted:
            return "ignored: already summarized"  # the transcript is append-only: same range, same input
        if not path:
            return _skip(handle, index, "no_transcript")
        try:
            turns = read_range(Path(path), start, end)
        except OSError:
            return _skip(handle, index, "no_transcript")
        if not any(t.role == "user" for t in turns):
            return _skip(handle, index, "trivial")

        dialogue = redact_text(render(turns, limit=INPUT_LIMIT))  # credentials never reach the model
        sha = hashlib.sha256(f"{PROMPT_VERSION}\n{dialogue}".encode()).hexdigest()
        job_id = str(uuid.uuid4())
        handle.append("summary.requested", {"job_id": job_id}, seg=index)
        model = env.get(MODEL_ENV) or DEFAULT_MODEL
        full = schema.load("segment-summary")
        began = time.monotonic()
        try:
            output, cost = runner(PROMPT_FILE.read_text(), dialogue, full["$defs"]["model_output"], model, env)
            duration_ms = int((time.monotonic() - began) * 1000)
            artifact = {
                "schema": SCHEMA_ID, "sid": handle.sid, "index": index,
                "input": {**wanted, "sha256": sha, "turns": len(turns)},
                "producer": {"model": model, "prompt_version": PROMPT_VERSION, "duration_ms": duration_ms,
                             "cost_usd": cost},
                **(output if isinstance(output, dict) else {}),
            }
            problems = schema.validate(artifact, full)
            if problems:
                raise SummarizerError("invalid summary: " + "; ".join(problems[:3]), retryable=True)
        except SummarizerError as exc:
            handle.append("summary.failed", {"job_id": job_id, "error": str(exc), "retryable": exc.retryable},
                          seg=index)
            return f"failed: {exc}"
        atomic_write_json(seg.dir / "summary.json", artifact)
        handle.append("summary.completed", {"job_id": job_id, "artifact": f"{seg.dir.name}/summary.json",
                                            "input_sha256": sha, "duration_ms": duration_ms}, seg=index)
        return f"summarized: {len(artifact['blocks'])} block(s)"


def _skip(handle: SessionHandle, index: int, reason: str) -> str:
    handle.append("summary.skipped", {"reason": reason}, seg=index)
    return f"skipped: {reason}"
