"""The segment summarizer (spec §7.1): a sealed segment's transcript slice → ``seg-NNN/summary.json``.

Runs out of band, as its own process (``session_store summarize <sid> <seg>``),
spawned detached by the hook that sealed the segment. One run:

1. **Gates.** Records ``summary.skipped`` and stops when the session is
   private, summaries are switched off (``CLAUDNA_SESSION_SUMMARY=0``), the
   session isn't interactive and summaries weren't switched on for it
   (``CLAUDNA_SESSION_SUMMARY=1`` — headless ``claude -p`` and Claudlobby bots
   are off by default), the transcript is gone, or the slice holds no prose.
2. **Idempotence.** Stops without an event when a ``done`` summary already
   covers the same input (same ``input.sha256``). One runner per segment: a
   second one finds the segment's lock taken and leaves.
3. **One model call.** ``claude -p`` with its own fresh ``--session-id``, no
   tools, no MCP servers, no settings (``--setting-sources ""``, so neither
   clauDNA's nor any other plugin's hooks fire in the child), the instructions
   in the system prompt, the transcript on stdin as untrusted data, and the
   output held to the schema's ``model_output`` by ``--json-schema``.
4. **Validation, then the write.** The result is checked against
   ``segment-summary.schema.json`` before it is written atomically; then
   ``summary.completed`` makes it visible. Any failure records ``summary.failed``.

The model call is behind ``runner`` so tests never spawn ``claude``.
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

from . import schema
from .fsio import atomic_write_json, read_json, try_exclusive_lock
from .project import SessionFacts, load_lifecycle, segment_transcript_paths, session_facts
from .store import SessionHandle
from .transcript import read_range, render

SCHEMA_ID = "claudna.segment-summary/1"
PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "segment-summary.md"
PROMPT_VERSION = "segment-summary/1"
ENABLE_ENV = "CLAUDNA_SESSION_SUMMARY"
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


#: ``runner(system_prompt, dialogue, output_schema, model, env) -> (output, cost_usd)``
Runner = Callable[[str, str, dict, str, Mapping[str, str]], "tuple[dict, float | None]"]


def run_claude(system_prompt: str, dialogue: str, output_schema: dict, model: str,
               env: Mapping[str, str]) -> tuple[dict, float | None]:
    """One isolated, tool-less ``claude -p`` call returning schema-shaped JSON."""
    cmd = [
        env.get(CLAUDE_ENV) or "claude", "-p",
        "--session-id", str(uuid.uuid4()), "--no-session-persistence",
        "--setting-sources", "", "--tools", "", "--strict-mcp-config",
        "--model", model, "--output-format", "json",
        "--system-prompt", system_prompt, "--json-schema", json.dumps(output_schema),
    ]
    child_env = {**env, "CLAUDNA_SESSION_CHILD": "1"}
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


def _gate(facts: SessionFacts, env: Mapping[str, str]) -> str | None:
    """The ``summary.skipped`` reason for this session, or ``None`` to summarize."""
    if facts.private:
        return "private"
    switch = env.get(ENABLE_ENV)
    if switch == "0":
        return "disabled"
    if switch != "1" and (facts.actor or {}).get("kind") in ("headless", "bot"):
        return "headless"
    return None


def summarize(handle: SessionHandle, index: int, *, env: Mapping[str, str] | None = None,
              runner: Runner = run_claude) -> str:
    """Summarize sealed segment ``index``; return what happened."""
    env = dict(os.environ) if env is None else env
    seg = handle.paths.segment(index)
    if not seg.dir.is_dir():
        return f"ignored: no segment {index}"
    with try_exclusive_lock(seg.dir / ".summarize.lock") as taken:
        if not taken:
            return "ignored: another summarizer holds the segment"
        return _summarize_locked(handle, index, env, runner)


def _summarize_locked(handle: SessionHandle, index: int, env: Mapping[str, str], runner: Runner) -> str:
    lifecycle = load_lifecycle(handle.paths).events
    boundary = handle.boundary(index, lifecycle)
    if not boundary.sealed:
        return f"ignored: segment {index} is not sealed"
    reason = _gate(session_facts(lifecycle), env)
    if reason:
        return _skip(handle, index, reason)
    path = segment_transcript_paths(lifecycle)[index]
    start, end = boundary.start or 0, boundary.last_seal["data"]["end"]
    try:
        turns = read_range(Path(path), start, end) if path else None
    except OSError:
        turns = None
    if turns is None:
        return _skip(handle, index, "no_transcript")
    if not any(t.role == "user" for t in turns):
        return _skip(handle, index, "trivial")

    dialogue = render(turns, limit=INPUT_LIMIT)
    sha = hashlib.sha256(f"{PROMPT_VERSION}\n{dialogue}".encode()).hexdigest()
    seg = handle.paths.segment(index)
    previous = read_json(seg.dir / "summary.json")
    if isinstance(previous, dict) and previous.get("input", {}).get("sha256") == sha and \
            boundary.summary["status"] == "done":
        return "ignored: already summarized"

    job_id = str(uuid.uuid4())
    handle.append("summary.requested", {"job_id": job_id}, seg=index)
    model = env.get(MODEL_ENV) or DEFAULT_MODEL
    full = schema.load("segment-summary")
    began = time.monotonic()
    try:
        output, cost = runner(PROMPT_FILE.read_text(), dialogue, full["$defs"]["model_output"], model, env)
        artifact = {
            "schema": SCHEMA_ID, "sid": handle.sid, "index": index,
            "input": {"transcript_path": path, "range": {"start": start, "end": end}, "sha256": sha,
                      "turns": len(turns)},
            "producer": {"model": model, "prompt_version": PROMPT_VERSION,
                         "duration_ms": int((time.monotonic() - began) * 1000), "cost_usd": cost},
            "summary": output,
        }
        problems = schema.validate(artifact, full)
        if problems:
            raise SummarizerError("invalid summary: " + "; ".join(problems[:3]), retryable=True)
    except SummarizerError as exc:
        handle.append("summary.failed", {"job_id": job_id, "error": str(exc), "retryable": exc.retryable},
                      seg=index)
        return f"failed: {exc}"
    atomic_write_json(seg.dir / "summary.json", artifact)
    handle.append("summary.completed", {
        "job_id": job_id, "artifact": f"{seg.dir.name}/summary.json",
        "input_sha256": sha, "duration_ms": artifact["producer"]["duration_ms"],
    }, seg=index)
    return f"summarized: {len(output['blocks'])} block(s)"


def _skip(handle: SessionHandle, index: int, reason: str) -> str:
    handle.append("summary.skipped", {"reason": reason}, seg=index)
    return f"skipped: {reason}"

