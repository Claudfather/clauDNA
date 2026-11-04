"""Read-only pipeline health from existing lifecycle, worker and review records.

This is an on-demand inventory, never a hook or a new ledger. Unknown policy,
missing records and intentionally disabled capture are distinct from success.
No transcript, prompt, claim, vault path or private-session identity is returned.
"""

from __future__ import annotations

import os
import time
from collections import Counter
from typing import Mapping

from . import ops, retention
from .fsio import env_number, epoch_of, read_json, read_jsonl, rotated, utc_seconds
from .project import HARVEST_CONSUMER, harvest_skip, load_lifecycle, segment_states, session_facts
from .store import SessionStore


def _reviews(root, public_sids: set[str]) -> dict:
    # A draft can combine several sessions: suppress it if any source is private
    # or absent. Count recorded decisions, not claims and not inferred task wins.
    sources: dict[tuple, set] = {}
    ledger = read_jsonl(root / "harvest" / "ledger.jsonl")
    for rec in ledger.records:
        if isinstance(rec.get("path"), str) and isinstance(rec.get("sid"), str):
            sources.setdefault((rec.get("vault"), rec["path"]), set()).add(rec["sid"])
    reviews = read_jsonl(root / "harvest" / "reviewed.jsonl")
    latest = {}
    for rec in reviews.records:
        if not isinstance(rec.get("item"), str):
            continue
        key = (rec.get("vault"), rec["item"])
        if sources.get(key) and sources[key] <= public_sids and rec.get("outcome") in (
                "promoted", "discarded", "kept"):
            revision = rec.get("revision")
            if revision is None or type(revision) is int:
                latest[(*key, revision)] = rec["outcome"]
    counts = Counter(latest.values())
    decided = counts["promoted"] + counts["discarded"]
    return {"decisions": dict(counts), "decided_revisions": decided,
            "acceptance_fraction": counts["promoted"] / decided if decided else None,
            "skipped_lines": ledger.skipped + reviews.skipped}


def report(store: SessionStore, *, env: Mapping[str, str] | None = None, now: float | None = None) -> dict:
    """Aggregate retained evidence without launching workers, repairing files or probing auth.

    The age-cap calculation uses this process's retention setting, not an
    assertion about another worker's environment. Concurrent writes can make
    this snapshot incomplete; unreadable inputs are reported, never green.
    """
    env, now = os.environ if env is None else env, time.time() if now is None else now
    cap_days = env_number(env, retention.CAP_ENV, retention.CAP_DAYS)
    hosts, summaries, excluded, policies = Counter(), Counter(), Counter(), Counter()
    public_sids: set[str] = set()
    warnings: list[str] = []
    skipped_lines = unreadable = private = ready = unacked = at_risk = 0
    oldest_age = None
    for sid in store.session_ids():
        handle = store.session(sid)
        try:
            log = load_lifecycle(handle.paths)
            facts = session_facts(log.events)
            if facts.private:
                private += 1
                continue
            skipped_lines += log.projected_from["skipped"]
            if not any(e["kind"] == "session.opened" for e in log.events):
                unreadable += 1
                continue
            public_sids.add(sid)
            hosts[facts.agent_cli] += 1
            for name, value in (("summary", facts.summary_enabled), ("prompts", facts.capture_prompts),
                                ("harvest", (facts.harvest or {}).get("enabled"))):
                policies[f"{name}_{'on' if value is True else 'off' if value is False else 'unknown'}"] += 1
            reason = harvest_skip(facts, log.events)
            if reason:
                excluded[reason] += 1
            doc = read_json(handle.paths.consumers)
            consumers = doc.get("consumers", {}) if isinstance(doc, dict) else {}
            cursor = consumers.get(HARVEST_CONSUMER, {}).get("through_seg", 0)
            if type(cursor) is not int or cursor < 0:
                raise ValueError("invalid harvest cursor")
            if handle.paths.consumers.exists() and not isinstance(doc, dict):
                raise ValueError("unreadable consumers")
            for state in segment_states(handle.paths, log.events):
                if not state.final:
                    continue
                summaries[state.summary] += 1
                if reason or state.index <= cursor:
                    continue
                unacked += 1
                ready += state.summary == "done"
                if state.sealed_at:
                    age = max(0, (now - epoch_of(state.sealed_at)) / 86400)
                    oldest_age = max(oldest_age or 0, age)
                    at_risk += bool(cap_days and age >= max(0, cap_days - 3))
        except (OSError, ValueError, TypeError, AttributeError):
            unreadable += 1
    workers = {}
    for kind in ops.KINDS:
        workers[kind] = {"retained_runs": 0, "problem_runs": 0, "latest_at": None, "latest_result": None}
    for path in (rotated(ops.log_path(store.root)), ops.log_path(store.root)):
        try:
            records = read_jsonl(path)
            skipped_lines += records.skipped
            for rec in records.records:
                kind, stamp = rec.get("kind"), rec.get("started_at")
                sids, detail = rec.get("sessions"), rec.get("detail")
                if not isinstance(kind, str) or kind not in workers or not isinstance(stamp, str) \
                        or not isinstance(sids, list) \
                        or any(not isinstance(s, str) for s in sids) or not isinstance(detail, dict):
                    skipped_lines += 1
                    continue
                if set(sids) - public_sids:
                    continue
                outcome = str(rec.get("outcome", ""))
                problem = outcome.startswith(("error", "failed")) or bool(detail.get("errors"))
                row = workers[kind]
                row["retained_runs"] += 1
                row["problem_runs"] += problem
                if stamp >= (row["latest_at"] or ""):
                    row.update(latest_at=stamp, latest_result="problem" if problem else
                               "skipped" if outcome.startswith("skipped") else "recorded")
        except OSError:
            unreadable += 1
    try:
        reviews = _reviews(store.root, public_sids)
        skipped_lines += reviews.pop("skipped_lines")
    except (OSError, TypeError):
        unreadable += 1
        reviews = {"decisions": {}, "decided_revisions": 0, "acceptance_fraction": None}
    if unreadable or skipped_lines:
        warnings.append("Incomplete evidence: unreadable inputs or malformed records; inspect check/runs.")
    if summaries["failed"] or summaries["unreadable"] or summaries["stale"]:
        warnings.append("Some final segments lack a usable summary; inspect lifecycle and summary worker receipts.")
    if at_risk:
        warnings.append("Unacknowledged harvest segments are within 3 days of, or beyond, this process's age cap.")
    if any(r["latest_result"] == "problem" for r in workers.values()):
        warnings.append("A latest retained worker run reported a problem; inspect runs for its recorded cause.")
    return {"schema": "claudna.pipeline-health/1", "observed_at": utc_seconds(now),
            "status": "attention" if warnings else "observed" if public_sids else "no_evidence",
            "sessions_by_host": dict(hosts), "private_sessions_excluded": private,
            "recorded_policies": dict(policies), "final_segment_summaries": dict(summaries),
            "harvest": {"excluded_sessions": dict(excluded), "unacknowledged_segments": unacked,
                        "ready_segments": ready, "oldest_unacknowledged_days": oldest_age,
                        "near_age_cap_segments": at_risk, "age_cap_days": cap_days},
            "workers": workers, "draft_reviews": reviews,
            "unreadable_inputs": unreadable, "skipped_lines": skipped_lines, "warnings": warnings,
            "limits": ["Retained records only; no record is not proof of non-use or healthy workers.",
                       "Recorded policies are historical choices, not installed-default or authentication checks.",
                       "Cursor capture is unsupported; Codex procedure entries are attestations, not task outcomes.",
                       "Review acceptance covers decided draft revisions only; it is not a skill usefulness score."]}
