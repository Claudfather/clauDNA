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

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from claudna.redact import redact_strings

from . import schema
from .fsio import atomic_write_json, atomic_write_text, ensure_dir, exclusive_lock, read_json, utc_seconds
from . import claudron
from .claudron import _ROOTS, CLAUDRON_ENV, CaptureError, claudron_bin  # noqa: F401 (re-exported)
from .project import (HARVEST_CONSUMER, MAX_ATTEMPTS, abandoned_at, by_segment, harvest_skip, latest_origin,
                      load_lifecycle, session_facts, summary_verdict)
from .store import SessionStore

ENABLE_ENV = "CLAUDNA_HARVEST"
INTERVAL_ENV = "CLAUDNA_HARVEST_INTERVAL_H"
DEFAULT_INTERVAL_H = 6.0
MAX_CAPTURES = 10
CONSUMER = HARVEST_CONSUMER
#: Block homes → Claudron note types. ``person`` is held back (see module doc).
NOTE_TYPES = {"entity": "knowledge", "concept": "knowledge", "project": "knowledge",
              "practice": "knowledge", "decision": "decision"}
#: Stranded summaries harvest re-runs per run (each is one model call, in this detached process).
MAX_RETRIES_PER_RUN = 2
LAST_RUN = "harvest/last_run.json"
IDLE_INTERVAL_H = 1.0
#: Prefixed to every draft's title, so any view that lists it — Claudron's own SessionStart brief
#: included — shows it as unreviewed (spec §7.2's banner; #373 review, M4).
DRAFT_BANNER = "(unverified) "


run_claudron_capture = claudron.capture  #: the default capture (tests replace it)


def _skip_reason(root: Path, env: Mapping[str, str], now: float) -> str | None:
    """Why a harvest shouldn't run now, or ``None``: the opt-in, then the debounce.

    Harvest is opt-in (``CLAUDNA_HARVEST=1``) until Claudron's own recall keeps
    drafts apart (Claudron#200). A run that found nothing to take debounces
    for :data:`IDLE_INTERVAL_H` only, so an early empty run can't hold off the
    first real one for the whole interval.
    """
    if env.get(ENABLE_ENV) != "1":
        return "disabled"
    try:
        interval_h = float(env.get(INTERVAL_ENV) or DEFAULT_INTERVAL_H)
    except ValueError:
        interval_h = DEFAULT_INTERVAL_H
    last = read_json(root / LAST_RUN) or {}
    if last.get("idle"):
        interval_h = min(interval_h, IDLE_INTERVAL_H)
    started = last.get("started_epoch")
    if isinstance(started, (int, float)) and now - started < interval_h * 3600:
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
        "title": DRAFT_BANNER + _title(f"{block['subject_hint']['name']}: {block['claim']}"),
        "body": body,
        "tags": sorted({*block.get("tags", []), f"home:{block['home']}", f"asserted-by:{block['asserted_by']}",
                        "origin:session-harvest"}),
        "source_type": "inline",
    }
    if project:
        finding["project"] = project
    return redact_strings(finding)  # defense in depth: the summary was redacted when written


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
    screened: int = 0  #: blocks the instruction screen kept out (claudna.screen): never captured or held
    rejected: int = 0
    retried: int = 0
    gave_up: int = 0
    idle: bool = False
    errors: list[str] = field(default_factory=list)
    sessions: list[str] = field(default_factory=list)  #: sessions a segment was taken from (the ops log's)

    @property
    def captures(self) -> int:
        return self.created + self.known + self.rejected

    @property
    def started_at(self) -> str:
        return utc_seconds(self.started_epoch)

    def as_dict(self) -> dict:
        return {**self.__dict__, "started_at": self.started_at}


def _since_last_seal(events: list[dict]) -> list[dict]:
    seals = [n for n, e in enumerate(events) if e["kind"] == "segment.sealed"]
    return events[seals[-1]:] if seals else events


def _harvest_session(store: SessionStore, sid: str, report: RunReport, capture: Callable[..., str],
                     env: Mapping[str, str], resummarize: Callable[..., str]) -> None:
    handle = store.session(sid)
    through = handle.cursor(CONSUMER)
    if through >= max(handle.paths.segment_indices(), default=0):
        return  # nothing new: skip the lifecycle read (most sessions, most runs)
    from claudna.screen import tripped

    from . import digest  # here, not at the top: SessionStart imports this module for is_due alone (#387 S5)

    lifecycle = load_lifecycle(handle.paths).events
    facts = session_facts(lifecycle)
    skip = harvest_skip(facts, lifecycle)
    if skip == "no vault":
        report.errors.append(f"{sid}: no vault to route to (none recorded, and its cwd is gone)")
    if skip:
        return
    origin, vault = latest_origin(lifecycle), facts.harvest.get("vault")
    indices = handle.paths.segment_indices()
    for index in indices:
        if index <= through:
            continue
        if index == indices[-1] and facts.status != "closed":
            return  # the current segment can still be re-sealed and re-summarized: only final ones are taken
        boundary = handle.boundary(index, lifecycle)
        status = boundary.summary["status"]
        summary = read_json(handle.paths.segment(index).summary) if status == "done" else None
        valid = isinstance(summary, dict) and not schema.validate(summary, schema.load("segment-summary"))
        if status == "done" and valid and summary["input"]["range"]["end"] != boundary.last_seal["data"]["end"]:
            status = "stale"  # summarized before a later re-seal: its range misses the tail
        unreadable = status == "done" and not valid  # summary.json missing or invalid: rebuild it (#387 review S3)
        if unreadable:
            status = "stale"
        if status in ("none", "pending", "failed", "stale"):
            if unreadable:  # bounded like any retry: a summary that can never be written mustn't cost a call a run
                attempts = sum(e["kind"] == "summary.requested" for e in _since_last_seal(by_segment(lifecycle)[index]))
                verdict = "give up" if attempts >= MAX_ATTEMPTS else "retry"
            elif status == "stale":
                verdict = "retry"
            else:
                verdict = summary_verdict(by_segment(lifecycle)[index], report.started_epoch,
                                          abandoned_at=abandoned_at(lifecycle))
            if verdict == "give up":
                report.gave_up += 1
                report.errors.append(f"{sid}: seg-{index:03d} was never summarized; skipped by harvest")
                handle.ack(CONSUMER, index)
                continue
            if verdict == "retry" and report.retried < MAX_RETRIES_PER_RUN:
                report.retried += 1
                resummarize(handle, index, env)
                lifecycle = load_lifecycle(handle.paths).events
                boundary = handle.boundary(index, lifecycle)
                status = boundary.summary["status"]
                summary = read_json(handle.paths.segment(index).summary) if status == "done" else None
                valid = isinstance(summary, dict) and not schema.validate(summary, schema.load("segment-summary"))
            if status == "done" and valid and summary["input"]["range"]["end"] != boundary.last_seal["data"]["end"]:
                return  # still behind the last seal: never take a summary that misses the tail
        if status == "skipped":  # final: trivial, gated off, or its transcript is gone — nothing to take
            handle.ack(CONSUMER, index)
            continue
        if status != "done":
            return  # harvest in order: a segment still pending holds the cursor
        if not valid:
            report.errors.append(f"{sid}: seg-{index:03d}/summary.json is missing or invalid; not harvested")
            return  # never step past a segment whose blocks can't be read: the cursor holds
        blocks = [b for b in summary["blocks"] if not tripped(b)]  # a summary written before the screen existed
        report.screened += len(summary["blocks"]) - len(blocks)
        findings = [(b, finding_of(b, sid=sid, index=index, project=origin["repo"])) for b in blocks]
        wanted = [f for _, f in findings if f is not None]
        if report.captures and report.captures + len(wanted) > MAX_CAPTURES:
            return  # out of budget: the whole segment waits for the next run (a first one always fits)
        for block, finding in ((b, f) for b, f in findings if f is not None):
            answer = capture(finding, origin.get("cwd"), env, vault)
            action = answer["action"]
            digest.record_capture(store.root, sid=sid, seg=index, block=block, title=finding["title"],
                                  action=action, path=answer["path"], vault=answer.get("vault", vault))
            if action in ("created", "updated"):
                report.created += 1
            elif action == "rejected":
                report.rejected += 1
            else:
                report.known += 1
        for block, _ in (pair for pair in findings if pair[1] is None):
            root = claudron.vault_root(origin.get("cwd"), vault, env)  # the root captures record: one name per vault
            digest.record_held(store.root, sid=sid, seg=index, block=block, vault=str(root) if root else vault)
            report.held_back += 1
        report.segments += 1
        if sid not in report.sessions:
            report.sessions.append(sid)
        handle.ack(CONSUMER, index)


def _resummarize(handle, index: int, env: Mapping[str, str]) -> str:
    from . import summarize  # only a run with a stranded summary needs it

    return summarize.summarize(handle, index, env=env)


def harvest(store: SessionStore, *, env: Mapping[str, str] = os.environ,
            capture: Callable[..., str] | None = None, force: bool = False,
            resummarize: Callable[..., str] | None = None) -> RunReport:
    """One harvest run over every session in ``store``; see the module doc.

    ``capture`` and ``resummarize`` default to the real ``claudron`` and
    summarizer, resolved at call time so tests can stub them module-wide.
    """
    capture = capture or run_claudron_capture
    resummarize = resummarize or _resummarize
    report = RunReport(started_epoch=time.time())
    if env.get(ENABLE_ENV) != "1" and not force:
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
        try:
            for sid in store.session_ids():
                try:
                    _harvest_session(store, sid, report, capture, env, resummarize)
                except CaptureError as exc:
                    report.status = "error"
                    report.errors.append(f"{sid}: {exc}")
                    break  # claudron is unhappy: stop, keep every cursor where it is
                except Exception as exc:  # noqa: BLE001 — one bad session must not stop the run or hide it
                    report.errors.append(f"{sid}: {type(exc).__name__}: {str(exc)[:120]}")
                if report.captures >= MAX_CAPTURES:
                    break
        finally:  # every run leaves its record, so a crash is seen and the debounce still holds
            try:  # the digest's own SessionStart line (phase 5): its failure is this run's error, not every run's
                from . import digest

                digest.write_review_line(store.root)
            except Exception as exc:  # noqa: BLE001 — recorded in last_run.json, which still gets written below
                report.errors.append(f"review line: {type(exc).__name__}: {str(exc)[:120]}")
            report.idle = report.segments == 0 and not report.errors
            atomic_write_json(store.root / LAST_RUN, report.as_dict())
            atomic_write_text(home / "liveness.txt", liveness_line(report) + "\n")
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
    if report.screened:
        parts.append(f"{report.screened} withheld as instruction-like")
    if report.rejected:
        parts.append(f"{report.rejected} rejected")
    if report.retried:
        parts.append(f"{report.retried} summary retried")
    if report.gave_up:
        parts.append(f"{report.gave_up} segment(s) never summarized")
    line = f"{head}: {', '.join(parts)} from {report.segments} segment(s)"
    return line + (f"; problem: {report.errors[0][:160]}" if report.errors else "")
