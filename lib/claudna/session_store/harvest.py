"""Harvest, thin slice (spec §7.2): summarized segments' knowledge blocks → draft vault notes.

``session_store harvest`` walks every session, and for each segment with a
completed summary that this harvest hasn't taken yet, writes the segment's
blocks through Claudron's write door — ``claudron capture --stdin --json`` —
where each lands as ``maturity: draft``. Claudron never reads the store;
clauDNA never writes the vault except through ``claudron``.

This is the loop-closing slice, not the full librarian: no subject
resolution, no plan model, no risk tiers yet (they wait on Claudron#200's
pipes). What it does hold to:

* **Drafts only, and never person facts.** ``person`` blocks are held back:
  an other-person fact is high-risk (§7.2) and waits for the human digest.
* **Claudron's dedup routes, never rejects.** A ``suggest_update`` /
  ``suggest_supersede`` answer writes nothing; it counts as already known.
* **The cursor moves only after success.** Each session's
  ``consumers.json`` → ``harvest.through_seg`` advances past a segment only
  when every capture for it returned; a failure leaves it to the next run.
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
from .fsio import atomic_write_json, ensure_dir, exclusive_lock, read_json
from .paths import validate_sid
from .project import load_lifecycle
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


class CaptureError(RuntimeError):
    """``claudron capture`` failed outright (not a dedup answer)."""


#: ``capture(finding, cwd, env) -> action`` — Claudron's ``data.action``.
Capture = Callable[[dict, "str | None", Mapping[str, str]], str]


def run_claudron_capture(finding: dict, cwd: str | None, env: Mapping[str, str]) -> str:
    """One ``claudron capture --stdin --json``; returns ``data.action``.

    Content goes on stdin as JSON — never as a shell argument (Claudron's
    contract for programmatic writers).
    """
    import subprocess  # imported here: the hook imports this module for is_due alone

    cmd = [claudron_bin(env), "capture", "--stdin", "--json"]
    try:
        proc = subprocess.run(cmd, input=json.dumps(finding), capture_output=True, text=True,
                              timeout=TIMEOUT_S, env=dict(env), cwd=cwd if cwd and os.path.isdir(cwd) else None)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CaptureError(f"claudron capture: {exc}") from exc
    try:
        data = json.loads(proc.stdout).get("data") or {}
    except ValueError as exc:
        raise CaptureError(f"claudron capture exited {proc.returncode}: {proc.stderr.strip()[:150]}") from exc
    if data.get("action") not in ("created", "updated", "suggest_update", "suggest_supersede", "rejected"):
        raise CaptureError(f"claudron capture: unexpected answer {data!r:.150}")
    return data["action"]


def claudron_bin(env: Mapping[str, str]) -> str:
    return env.get(CLAUDRON_ENV) or "claudron"


def is_due(root: Path, env: Mapping[str, str], now: float | None = None) -> bool:
    """Should a harvest start? Enabled, ``claudron`` installed, and the last run older than the interval."""
    if env.get(ENABLE_ENV) == "0" or shutil.which(claudron_bin(env), path=env.get("PATH")) is None:
        return False
    return _due(read_json(root / "harvest" / "last_run.json"), env, time.time() if now is None else now)


def finding_of(block: dict, *, project: str | None) -> dict | None:
    """The ``claudron capture`` JSON for one block, or ``None`` when it is held back."""
    note_type = NOTE_TYPES.get(block["home"])
    if note_type is None:
        return None
    subject = block["subject_hint"]["name"]
    finding = {
        "type": note_type,
        "title": _title(f"{subject}: {block['claim']}"),
        "body": block["claim"] + ("" if not block.get("section_hint") else f"\n\nSection: {block['section_hint']}"),
        "tags": sorted({*block.get("tags", []), f"home:{block['home']}", f"asserted-by:{block['asserted_by']}",
                        "origin:session-harvest"}),
        "source_type": "inline",
    }
    if project:
        finding["project"] = project
    return finding


def _title(text: str, limit: int = 100) -> str:
    """``text`` cut at a word boundary to ``limit`` characters, with an ellipsis when cut."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


@dataclass
class RunReport:
    """What one harvest run did; persisted as ``last_run.json``."""

    started_at: str
    status: str = "ok"  # ok · skipped · error
    reason: str | None = None
    segments: int = 0
    created: int = 0
    known: int = 0
    held_back: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)


def _project_of(lifecycle: list[dict]) -> tuple[str | None, str | None]:
    """``(project, cwd)`` from the latest ``session.opened``: the repo's root name, when there is one."""
    opened = [e for e in lifecycle if e["kind"] == "session.opened"]
    origin = (opened[-1]["data"].get("origin") or {}) if opened else {}
    return origin.get("repo"), origin.get("cwd")


def _cursor(consumers_path: Path) -> int:
    doc = read_json(consumers_path)
    try:
        return int(doc["consumers"][CONSUMER]["through_seg"])
    except (TypeError, KeyError, ValueError):
        return 0


def _advance(consumers_path: Path, sid: str, through: int) -> None:
    doc = read_json(consumers_path)
    if not isinstance(doc, dict) or doc.get("schema") != "claudna.consumers/1":
        doc = {"schema": "claudna.consumers/1", "sid": sid, "consumers": {}}
    doc["consumers"][CONSUMER] = {"through_seg": through, "acked_at": ev.now_ts()}
    atomic_write_json(consumers_path, doc)


def _harvest_session(store: SessionStore, sid: str, report: RunReport, capture: Capture,
                     env: Mapping[str, str], budget: list[int]) -> None:
    handle = store.session(sid)
    lifecycle = load_lifecycle(handle.paths).events
    project, cwd = _project_of(lifecycle)
    consumers = handle.paths.dir / "consumers.json"
    through = _cursor(consumers)
    for index in handle.paths.segment_indices():
        if index <= through:
            continue
        if handle.boundary(index, lifecycle).summary["status"] != "done":
            break  # harvest in order: a segment still pending holds the cursor
        summary = read_json(handle.paths.segment(index).dir / "summary.json")
        if not isinstance(summary, dict) or schema.validate(summary, schema.load("segment-summary")):
            report.errors.append(f"{sid}: seg-{index:03d}/summary.json is missing or invalid; not harvested")
            return  # never step past a segment whose blocks can't be read: the cursor holds
        blocks = summary["blocks"]
        findings = [finding_of(b, project=project) for b in blocks]
        wanted = [f for f in findings if f is not None]
        if len(wanted) > budget[0]:
            return  # out of budget for this run: the whole segment waits, the cursor stays
        report.held_back += len(findings) - len(wanted)
        for finding in wanted:
            action = capture(finding, cwd, env)
            budget[0] -= 1
            if action in ("created", "updated"):
                report.created += 1
            elif action == "rejected":
                report.rejected += 1
            else:
                report.known += 1
        report.segments += 1
        through = index
        _advance(consumers, sid, through)


def _due(state: dict | None, env: Mapping[str, str], now: float) -> bool:
    try:
        interval_h = float(env.get(INTERVAL_ENV) or DEFAULT_INTERVAL_H)
    except ValueError:
        interval_h = DEFAULT_INTERVAL_H
    last = (state or {}).get("started_epoch")
    return not isinstance(last, (int, float)) or now - last >= interval_h * 3600


def harvest(store: SessionStore, *, env: Mapping[str, str] | None = None, capture: Capture = run_claudron_capture,
            force: bool = False) -> RunReport:
    """One harvest run over every session in ``store``; see the module doc."""
    env = dict(os.environ) if env is None else env
    report = RunReport(started_at=ev.now_ts())
    if env.get(ENABLE_ENV) == "0":
        report.status, report.reason = "skipped", "disabled"
        return report
    home = ensure_dir(store.root / "harvest")
    last_run = home / "last_run.json"
    now = time.time()
    with exclusive_lock(home / "lock", blocking=False) as taken:
        if not taken:
            report.status, report.reason = "skipped", "another harvest is running"
            return report
        if not force and not _due(read_json(last_run), env, now):
            report.status, report.reason = "skipped", "not due"
            return report
        budget = [MAX_CAPTURES]
        sessions = store.root / "sessions"
        for sid_dir in sorted(sessions.iterdir()) if sessions.is_dir() else []:
            try:
                sid = validate_sid(sid_dir.name)
            except ValueError:
                continue
            try:
                _harvest_session(store, sid, report, capture, env, budget)
            except CaptureError as exc:
                report.status = "error"
                report.errors.append(f"{sid}: {exc}")
                break  # claudron is unhappy: stop, keep every cursor where it is
            if budget[0] <= 0:
                break
        atomic_write_json(last_run, {**report.__dict__, "started_epoch": now})
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
        parts.append(f"{report.held_back} person fact(s) held back")
    if report.rejected:
        parts.append(f"{report.rejected} rejected")
    line = f"{head}: {', '.join(parts)} from {report.segments} segment(s)"
    return line + (f"; problem: {report.errors[0][:160]}" if report.errors else "")

