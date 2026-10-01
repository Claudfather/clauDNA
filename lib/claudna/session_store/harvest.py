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

from claudna.redact import redact_strings

from . import schema
from .fsio import atomic_write_json, atomic_write_text, ensure_dir, exclusive_lock, read_json, utc_seconds
from .project import (abandoned_at, by_segment, harvest_skip, latest_origin, load_lifecycle, session_facts,
                      summary_verdict)
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
#: Stranded summaries harvest re-runs per run (each is one model call, in this detached process).
MAX_RETRIES_PER_RUN = 2
LAST_RUN = "harvest/last_run.json"
IDLE_INTERVAL_H = 1.0
#: Prefixed to every draft's title, so any view that lists it — Claudron's own SessionStart brief
#: included — shows it as unreviewed (spec §7.2's banner; #373 review, M4).
DRAFT_BANNER = "(unverified) "


class CaptureError(RuntimeError):
    """``claudron capture`` failed outright (not a dedup answer)."""


_ACTIONS = ("created", "updated", "suggest_update", "suggest_supersede", "rejected")


def run_claudron_capture(finding: dict, cwd: str | None, env: Mapping[str, str], vault: str | None = None) -> dict:
    """One ``claudron capture --stdin --json``; returns ``{"action", "path"}`` from ``data``.

    The vault is the *session's*, never the harvest process's: ``--vault`` when
    the session recorded one, else a walk-up from the session's ``cwd`` — with
    ``$CLAUDRON_VAULT_PATH`` removed from the child's environment either way, so
    whichever session happened to start this run can't redirect another's
    drafts into its vault (#373 review, B2).

    Content goes on stdin as JSON — never as a shell argument — and the
    envelope is validated per ``skills/_shared/claudron-engine.md`` §2: exit 0,
    ``ok``, ``command == "capture"``, a known ``data.action``. A ``rejected``
    write exits 1 with a well-formed envelope; that is an answer, not a failure.
    """
    import subprocess  # imported here: the hook imports this module for is_due alone

    cmd = [claudron_bin(env), *(["--vault", vault] if vault else []), "capture", "--stdin", "--json"]
    child_env = {k: v for k, v in env.items() if k != "CLAUDRON_VAULT_PATH"}
    try:
        proc = subprocess.run(cmd, input=json.dumps(finding), capture_output=True, text=True,
                              timeout=TIMEOUT_S, env=child_env, cwd=cwd if cwd and os.path.isdir(cwd) else None)
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
    path = data.get("path") if isinstance(data.get("path"), str) and data.get("path") else None
    # The root is asked for when the path needs it, or when the session recorded no vault: without one,
    # the digest item would carry vault None and `promote` would resolve against the reviewer's cwd.
    root = _vault_root(cwd, vault, child_env) if path and (os.path.isabs(path) or not vault) else None
    if root and os.path.isabs(path):
        try:  # created/updated answer with an absolute path; promote takes a vault-relative one (contract §2)
            path = Path(os.path.realpath(path)).relative_to(root).as_posix()
        except ValueError:
            pass  # outside the vault claudron reports: keep it as given
    return {"action": action, "path": path, "vault": str(root) if root else vault}


_ROOTS: dict[tuple[str | None, str | None], Path] = {}  #: one ``status`` per vault per run (a short process)


def _vault_root(cwd: str | None, vault: str | None, env: Mapping[str, str]) -> Path | None:
    """The vault root Claudron itself reports (``status --json``'s ``data.root``) for this session, or ``None``.

    Vault resolution is Claudron's contract (claudron-engine.md §2): ask it,
    with the same ``--vault``/``cwd`` the capture used, rather than re-deriving it.
    """
    import subprocess

    key = (cwd, vault)
    if key in _ROOTS:
        return _ROOTS[key]
    cmd = [claudron_bin(env), *(["--vault", vault] if vault else []), "status", "--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, env=dict(env),
                              cwd=cwd if cwd and os.path.isdir(cwd) else None)
        root = (json.loads(proc.stdout).get("data") or {}).get("root") if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        root = None
    if not (isinstance(root, str) and root):
        return None  # not cached: one failed call (a timeout, a busy index) mustn't decide the rest of the run
    _ROOTS[key] = Path(os.path.realpath(root))
    return _ROOTS[key]


class PromoteError(RuntimeError):
    """``claudron promote`` didn't promote: its error, for the person reviewing."""


def run_claudron_promote(item: str, vault: str | None, env: Mapping[str, str]) -> dict:
    """``claudron [--vault V] promote ITEM --to verified --by user --json`` as an argv list; the envelope's data.

    The deterministic half of ``/claudna:capture --review`` (the person chose;
    nothing here is left to a model): no shell, so a vault path with spaces is
    one argument; success is the envelope's own ``ok`` + ``data.action``
    (``promoted``, or ``unchanged`` for a note already verified), never a reading of prose.
    """
    import subprocess

    cmd = [claudron_bin(env), *(["--vault", vault] if vault else []), "promote", item, "--to", "verified",
           "--by", "user", "--json"]
    child_env = {k: v for k, v in env.items() if k != "CLAUDRON_VAULT_PATH"}  # the item's vault, not this shell's
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, env=child_env)
        envelope = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise PromoteError(f"claudron promote: {str(exc)[:150]}") from exc
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if proc.returncode != 0 or not envelope.get("ok") or envelope.get("command") != "promote" or \
            not isinstance(data, dict) or data.get("action") not in ("promoted", "unchanged"):
        errors = envelope.get("errors") if isinstance(envelope, dict) else None
        raise PromoteError(f"claudron promote exited {proc.returncode}: {str(errors or data)[:200]}")
    return data


def claudron_bin(env: Mapping[str, str]) -> str:
    return env.get(CLAUDRON_ENV) or "claudron"


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


def _harvest_session(store: SessionStore, sid: str, report: RunReport, capture: Callable[..., str],
                     env: Mapping[str, str], resummarize: Callable[..., str]) -> None:
    handle = store.session(sid)
    through = handle.cursor(CONSUMER)
    if through >= max(handle.paths.segment_indices(), default=0):
        return  # nothing new: skip the lifecycle read (most sessions, most runs)
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
        if status == "done" and not valid:
            status = "stale"  # summary.json missing or invalid: the summarizer rebuilds it (#387 review S3)
        if status in ("none", "pending", "failed", "stale"):
            verdict = "retry" if status == "stale" else \
                summary_verdict(by_segment(lifecycle)[index], report.started_epoch,
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
        findings = [(b, finding_of(b, sid=sid, index=index, project=origin["repo"])) for b in summary["blocks"]]
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
            digest.record_held(store.root, sid=sid, seg=index, block=block, vault=vault)
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
    if report.rejected:
        parts.append(f"{report.rejected} rejected")
    if report.retried:
        parts.append(f"{report.retried} summary retried")
    if report.gave_up:
        parts.append(f"{report.gave_up} segment(s) never summarized")
    line = f"{head}: {', '.join(parts)} from {report.segments} segment(s)"
    return line + (f"; problem: {report.errors[0][:160]}" if report.errors else "")
