"""Harvest, thin slice (spec §7.2): summarized segments' knowledge blocks → draft vault notes.

``session_store harvest`` walks every session, and for each segment with a
completed summary that this harvest hasn't taken yet, writes the segment's
blocks through Claudron's write door — ``claudron capture --stdin --json`` —
where each lands as ``maturity: draft``. Claudron never reads the store;
clauDNA never writes the vault except through ``claudron``.

This is the loop-closing slice, not the full librarian: no subject
resolution, no plan model, no risk tiers yet (they wait on Claudron#200's
pipes). What it does hold to:

* **Drafts only, and never person facts.** ``person`` blocks are held back
  in ``<root>/harvest/held.jsonl``: an other-person fact is high-risk (§7.2)
  and waits for the human digest. Private sessions are never harvested.
* **Claudron's dedup routes, never rejects.** A ``suggest_update`` /
  ``suggest_supersede`` answer writes nothing; it counts as already known.
* **The cursor moves only after success.** Each session's harvest cursor
  (``consumers.json``, written only through :meth:`SessionHandle.ack`)
  advances past a segment only when every capture for it returned; a failure
  leaves it to the next run.
* **Single-flight and bounded.** A non-blocking lock on
  ``<root>/harvest/lock``, a debounce (:data:`INTERVAL_ENV`, hours), and at
  most :data:`MAX_CAPTURES` writes per run.
* **Liveness.** Every run writes ``<root>/harvest/last_run.json`` and a
  one-line ``<root>/harvest/liveness.txt`` that SessionStart shows.

The ``claudron`` call is behind ``capture`` so tests never touch a vault.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from . import events as ev
from . import schema
from .fsio import append_jsonl, atomic_write_json, ensure_dir, exclusive_lock, read_json
from .project import by_segment, load_lifecycle, session_facts
from .store import SessionStore

ENABLE_ENV = "CLAUDNA_HARVEST"
INTERVAL_ENV = "CLAUDNA_HARVEST_INTERVAL_H"
CLAUDRON_ENV = "CLAUDNA_CLAUDRON_BIN"
DEFAULT_INTERVAL_H = 6.0
MAX_CAPTURES = 10
CONSUMER = "harvest"
#: Block homes → Claudron note types. ``person`` is held back (see module doc).
NOTE_TYPES = {"entity": "knowledge", "concept": "knowledge", "project": "knowledge",
              "practice": "knowledge", "decision": "decision"}
TIMEOUT_S = 30
#: A summary still ``pending`` this long after its request lost its worker (killed, machine asleep).
STALE_PENDING_S = 15 * 60
#: Summarizer attempts per segment before harvest gives up on it and moves on.
MAX_ATTEMPTS = 3
#: Stranded summaries harvest re-runs per run (each is one model call, in this detached process).
MAX_RETRIES_PER_RUN = 2
LAST_RUN = "harvest/last_run.json"


class CaptureError(RuntimeError):
    """``claudron capture`` failed outright (not a dedup answer)."""


_ACTIONS = ("created", "updated", "suggest_update", "suggest_supersede", "rejected")


def run_claudron_capture(finding: dict, cwd: str | None, env: Mapping[str, str]) -> str:
    """One ``claudron capture --stdin --json``; returns ``data.action``.

    Content goes on stdin as JSON — never as a shell argument — and the
    envelope is validated per ``skills/_shared/claudron-engine.md`` §2: exit 0,
    ``ok``, ``command == "capture"``, a known ``data.action``. A ``rejected``
    write exits 1 with a well-formed envelope; that is an answer, not a failure.
    """
    import subprocess  # imported here: the hook imports this module for is_due alone

    cmd = [claudron_bin(env), "capture", "--stdin", "--json"]
    try:
        proc = subprocess.run(cmd, input=json.dumps(finding), capture_output=True, text=True,
                              timeout=TIMEOUT_S, env=dict(env), cwd=cwd if cwd and os.path.isdir(cwd) else None)
        envelope = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise CaptureError(f"claudron capture: {str(exc)[:150]}") from exc
    if not isinstance(envelope, dict):
        raise CaptureError(f"claudron capture exited {proc.returncode}: the output is not a JSON object")
    data = envelope.get("data")
    action = data.get("action") if isinstance(data, dict) else None
    if envelope.get("command") != "capture" or action not in _ACTIONS or \
            (proc.returncode != 0 and action != "rejected") or (not envelope.get("ok") and action != "rejected"):
        errors = envelope.get("errors")
        raise CaptureError(f"claudron capture exited {proc.returncode}: {str(errors or data)[:150]}")
    return action


def claudron_bin(env: Mapping[str, str]) -> str:
    return env.get(CLAUDRON_ENV) or "claudron"


def _skip_reason(root: Path, env: Mapping[str, str], now: float) -> str | None:
    """Why a harvest shouldn't run now, or ``None``: the switch, then the debounce."""
    if env.get(ENABLE_ENV) == "0":
        return "disabled"
    try:
        interval_h = float(env.get(INTERVAL_ENV) or DEFAULT_INTERVAL_H)
    except ValueError:
        interval_h = DEFAULT_INTERVAL_H
    last = (read_json(root / LAST_RUN) or {}).get("started_epoch")
    if isinstance(last, (int, float)) and now - last < interval_h * 3600:
        return "not due"
    return None


def is_due(root: Path, env: Mapping[str, str], now: float | None = None) -> bool:
    """Should SessionStart start a harvest? Not skipped, and ``claudron`` is installed."""
    now = time.time() if now is None else now
    return _skip_reason(root, env, now) is None and shutil.which(claudron_bin(env), path=env.get("PATH")) is not None


def _title(text: str, limit: int = 100) -> str:
    """``text`` cut at a word boundary to ``limit`` characters, with an ellipsis when cut."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def finding_of(block: dict, *, sid: str, index: int, project: str | None) -> dict | None:
    """The ``claudron capture`` JSON for one block, or ``None`` when it is held back.

    The tag namespaces (``home:``, ``asserted-by:``, ``origin:``) are
    provisional until Claudron's tag registry lands (Claudron#200). Provenance
    goes after the claim, never before it: the first body line is the summary
    recall shows.
    """
    note_type = NOTE_TYPES.get(block["home"])
    if note_type is None:
        return None
    body = block["claim"]
    if block.get("section_hint"):
        body += f"\n\nSection: {block['section_hint']}"
    body += f"\n\nHarvested from session {sid}, segment {index} (asserted by the {block['asserted_by']})."
    finding = {
        "type": note_type,
        "title": _title(f"{block['subject_hint']['name']}: {block['claim']}"),
        "body": body,
        "tags": sorted({*block.get("tags", []), f"home:{block['home']}", f"asserted-by:{block['asserted_by']}",
                        "origin:session-harvest"}),
        "source_type": "inline",
    }
    if project:
        finding["project"] = project
    return finding


@dataclass
class RunReport:
    """What one harvest run did; persisted as ``last_run.json``."""

    started_epoch: float
    status: str = "ok"  # ok · skipped · error
    reason: str | None = None
    segments: int = 0
    created: int = 0
    known: int = 0
    held_back: int = 0
    rejected: int = 0
    retried: int = 0
    gave_up: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def captures(self) -> int:
        return self.created + self.known + self.rejected

    @property
    def started_at(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started_epoch))

    def as_dict(self) -> dict:
        return {**self.__dict__, "started_at": self.started_at}


def _stranded(events: list[dict], now: float) -> str | None:
    """Why a segment's summary needs another attempt — or ``"give up"`` — from its summary events.

    ``pending`` long past its request (the worker died) and a retryable
    failure get another attempt, up to :data:`MAX_ATTEMPTS`; after that, or
    after a permanent failure, harvest gives up so the session isn't stuck.
    """
    summary = [e for e in events if e["kind"].startswith("summary.")]
    if not summary or summary[-1]["kind"] not in ("summary.requested", "summary.failed"):
        return None
    attempts = sum(e["kind"] == "summary.requested" for e in summary)
    last = summary[-1]
    if last["kind"] == "summary.failed" and not last["data"]["retryable"]:
        return "give up"
    if last["kind"] == "summary.requested":
        requested = time.mktime(time.strptime(last["ts"][:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
        if now - requested < STALE_PENDING_S:
            return None  # a worker may still be on it
    return "give up" if attempts >= MAX_ATTEMPTS else "retry"


def _harvest_session(store: SessionStore, sid: str, report: RunReport, capture: Callable[..., str],
                     env: Mapping[str, str], held_log: Path, resummarize: Callable[..., str]) -> None:
    handle = store.session(sid)
    through = handle.cursor(CONSUMER)
    if through >= max(handle.paths.segment_indices(), default=0):
        return  # nothing new: skip the lifecycle read (most sessions, most runs)
    lifecycle = load_lifecycle(handle.paths).events
    if session_facts(lifecycle).private:
        return  # a private session is never harvested (and never summarized)
    origin = _latest_origin(lifecycle)
    indices = handle.paths.segment_indices()
    closed = session_facts(lifecycle).status == "closed"
    for index in indices:
        if index <= through:
            continue
        if index == indices[-1] and not closed:
            return  # the current segment can still be re-sealed and re-summarized: only final ones are taken
        status = handle.boundary(index, lifecycle).summary["status"]
        if status in ("pending", "failed"):
            verdict = _stranded(by_segment(lifecycle)[index], report.started_epoch)
            if verdict == "retry" and report.retried < MAX_RETRIES_PER_RUN:
                report.retried += 1
                resummarize(handle, index)
                lifecycle = load_lifecycle(handle.paths).events
                status = handle.boundary(index, lifecycle).summary["status"]
            elif verdict == "give up":
                report.gave_up += 1
                report.errors.append(f"{sid}: seg-{index:03d} was never summarized; skipped by harvest")
                handle.ack(CONSUMER, index)
                continue
        if status == "skipped":  # final: trivial, gated off, or its transcript is gone — nothing to take
            handle.ack(CONSUMER, index)
            continue
        if status != "done":
            return  # harvest in order: a segment still pending holds the cursor
        summary = read_json(handle.paths.segment(index).summary)
        if not isinstance(summary, dict) or schema.validate(summary, schema.load("segment-summary")):
            report.errors.append(f"{sid}: seg-{index:03d}/summary.json is missing or invalid; not harvested")
            return  # never step past a segment whose blocks can't be read: the cursor holds
        findings = [(b, finding_of(b, sid=sid, index=index, project=origin.get("repo"))) for b in summary["blocks"]]
        wanted = [f for _, f in findings if f is not None]
        if report.captures and report.captures + len(wanted) > MAX_CAPTURES:
            return  # out of budget: the whole segment waits for the next run (a first one always fits)
        for finding in wanted:
            action = capture(finding, origin.get("cwd"), env)
            if action in ("created", "updated"):
                report.created += 1
            elif action == "rejected":
                report.rejected += 1
            else:
                report.known += 1
        for block, _ in (pair for pair in findings if pair[1] is None):
            append_jsonl(held_log, {"ts": ev.now_ts(), "sid": sid, "seg": index, "reason": "person",
                                    "block": block}, durable=False)
            report.held_back += 1
        report.segments += 1
        handle.ack(CONSUMER, index)


def _latest_origin(lifecycle: list[dict]) -> dict:
    opened = [e for e in lifecycle if e["kind"] == "session.opened"]
    return opened[-1]["data"].get("origin") or {} if opened else {}


def _resummarize(handle, index: int) -> str:
    from . import summarize  # only a run with a stranded summary needs it

    return summarize.summarize(handle, index)


def harvest(store: SessionStore, *, env: Mapping[str, str] = os.environ,
            capture: Callable[..., str] = run_claudron_capture, force: bool = False,
            resummarize: Callable[..., str] = _resummarize) -> RunReport:
    """One harvest run over every session in ``store``; see the module doc."""
    report = RunReport(started_epoch=time.time())
    if env.get(ENABLE_ENV) == "0":
        report.status, report.reason = "skipped", "disabled"
        return report
    home = ensure_dir(store.root / "harvest")
    with exclusive_lock(home / "lock", blocking=False) as taken:
        if not taken:
            report.status, report.reason = "skipped", "another harvest is running"
            return report
        reason = None if force else _skip_reason(store.root, env, report.started_epoch)
        if reason:
            report.status, report.reason = "skipped", reason
            return report
        for sid in store.session_ids():
            try:
                _harvest_session(store, sid, report, capture, env, home / "held.jsonl", resummarize)
            except CaptureError as exc:
                report.status = "error"
                report.errors.append(f"{sid}: {exc}")
                break  # claudron is unhappy: stop, keep every cursor where it is
            if report.captures >= MAX_CAPTURES:
                break
        atomic_write_json(store.root / LAST_RUN, report.as_dict())
        (home / "liveness.txt").write_text(liveness_line(report) + "\n")
    return report


def liveness_line(report: RunReport) -> str:
    """The one line SessionStart shows about the last harvest run."""
    head = f"clauDNA harvest {report.started_at[:16].replace('T', ' ')}Z"
    if report.status == "error":
        return f"{head}: FAILED — {report.errors[0][:160]} (drafts written before it: {report.created})"
    parts = [f"{report.created} new draft(s)"]
    if report.known:
        parts.append(f"{report.known} already known")
    if report.held_back:
        parts.append(f"{report.held_back} person fact(s) held for review")
    if report.rejected:
        parts.append(f"{report.rejected} rejected")
    if report.retried:
        parts.append(f"{report.retried} summary retried")
    if report.gave_up:
        parts.append(f"{report.gave_up} segment(s) never summarized")
    line = f"{head}: {', '.join(parts)} from {report.segments} segment(s)"
    return line + (f"; problem: {report.errors[0][:160]}" if report.errors else "")
