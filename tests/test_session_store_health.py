"""Pipeline health must preserve unknowns/privacy and use actual cursors and reviews."""

from __future__ import annotations

import json

from conftest import rewrite_log
from test_session_store_harvest import BLOCK, summarized_session

from claudna.session_store import health, ops
from claudna.session_store.cli import main
from claudna.session_store.fsio import append_jsonl, ensure_dir


def test_missing_store_is_unknown_and_read_only(store, capsys):
    assert main(["health", "--root", str(store.root), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "no_evidence"
    assert report["draft_reviews"]["acceptance_fraction"] is None
    assert not store.root.exists()


def test_health_enumerates_artifact_only_separately_from_partial_capture(store):
    from claudna.session_store.fsio import ensure_dir

    artifact = store.session("artifact-owner")
    ensure_dir(artifact.paths.dir / "artifacts")
    (artifact.paths.dir / "artifacts" / "manual.md").write_text("manual artifact")
    partial = store.session("partial")
    ensure_dir(partial.paths.dir)
    partial.paths.lifecycle.write_text("")

    report = health.report(store, env={})
    assert report["artifact_only_sessions"] == 1
    assert report["status"] == "attention"
    assert report["unreadable_inputs"] == 1
    assert report["sessions_by_host"] == {}


def test_backlog_uses_final_segments_ack_and_recorded_policy(store):
    h = summarized_session(store, "ready", [[BLOCK], [BLOCK]])
    h.ack("harvest", 1)
    summarized_session(store, "disabled", [[BLOCK]], opted_in=False)
    summarized_session(store, "still-open", [[BLOCK]], closed=False)
    before = {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    report = health.report(store, env={})
    assert report["harvest"]["ready_segments"] == report["harvest"]["unacknowledged_segments"] == 1
    assert report["harvest"]["excluded_sessions"] == {"off": 1}
    assert report["final_segment_summaries"] == {"done": 3}
    assert report["recorded_policies"]["summary_unknown"] == 3
    assert {p: p.read_bytes() for p in store.root.rglob("*") if p.is_file()} == before


def test_private_inputs_never_enter_counts_workers_or_reviews(store):
    h = summarized_session(store, "private-secret", [[BLOCK]])
    h.set_private(True)
    summarized_session(store, "public", [[BLOCK]], agent_cli="codex")
    ensure_dir(store.root / "harvest")
    ops.record(store.root, "summarize", started=100, outcome="failed: secret", sessions=["private-secret"])
    for sid in ("public", "private-secret"):
        append_jsonl(store.root / "harvest" / "ledger.jsonl",
                     {"sid": sid, "vault": "/secret-vault", "path": "mixed.md"})
    append_jsonl(store.root / "harvest" / "reviewed.jsonl",
                 {"item": "mixed.md", "vault": "/secret-vault", "revision": 1, "outcome": "promoted"})
    report = health.report(store, env={})
    assert report["sessions_by_host"] == {"codex": 1}
    assert report["private_sessions_excluded"] == 1
    assert report["workers"]["summarize"]["retained_runs"] == 0
    assert report["draft_reviews"]["acceptance_fraction"] is None
    assert "secret" not in json.dumps(report)


def test_failed_summary_near_retention_and_partial_worker_error_are_visible(store):
    h = summarized_session(store, "failing", [[BLOCK]], done=False)
    h.append("summary.failed", {"job_id": "j1", "error": "runner_error", "retryable": True}, seg=1)
    rewrite_log(h.paths.lifecycle, lambda es: [{**e, "ts": "2026-01-01T00:00:00.000Z"} for e in es])
    ops.record(store.root, "harvest", started=100, outcome="done", detail={"errors": ["partial failure"]})
    from claudna.session_store.fsio import epoch_of

    report = health.report(store, env={}, now=epoch_of("2026-01-29T00:00:00.000Z"))
    assert report["status"] == "attention"
    assert report["final_segment_summaries"] == {"failed": 1}
    assert report["harvest"]["near_age_cap_segments"] == 1
    assert report["workers"]["harvest"]["latest_result"] == "problem"
    uncapped = health.report(store, env={"CLAUDNA_RETAIN_DAYS": "0"}, now=epoch_of("2026-01-29T00:00:00.000Z"))
    assert uncapped["harvest"]["near_age_cap_segments"] == 0


def test_reviews_are_unique_decisions_per_revision_not_all_harvested_claims(store):
    summarized_session(store, "public", [[BLOCK]])
    ensure_dir(store.root / "harvest")
    for name in ("accepted.md", "rejected.md", "kept.md", "undecided.md"):
        append_jsonl(store.root / "harvest" / "ledger.jsonl", {"sid": "public", "path": name})
    for name, outcome in (("accepted.md", "promoted"), ("accepted.md", "promoted"),
                          ("rejected.md", "discarded"), ("kept.md", "kept")):
        append_jsonl(store.root / "harvest" / "reviewed.jsonl", {"item": name, "revision": 1, "outcome": outcome})
    reviews = health.report(store, env={})["draft_reviews"]
    assert reviews == {"decisions": {"promoted": 1, "discarded": 1, "kept": 1},
                       "decided_revisions": 2, "acceptance_fraction": 0.5}


def test_malformed_records_are_attention_not_healthy_or_a_crash(store):
    h = summarized_session(store, "s1", [[BLOCK]])
    with h.paths.lifecycle.open("a") as f:
        f.write('not json\n')
    ensure_dir(ops.log_path(store.root).parent)
    append_jsonl(ops.log_path(store.root), {"kind": [], "sessions": []})
    report = health.report(store, env={})
    assert report["status"] == "attention"
    assert report["skipped_lines"] == 2


def test_completed_summary_with_missing_artifact_is_not_ready(store):
    h = summarized_session(store, "s1", [[BLOCK]])
    h.paths.segment(1).summary.unlink()
    report = health.report(store, env={})
    assert report["final_segment_summaries"] == {"unreadable": 1}
    assert report["harvest"]["ready_segments"] == 0
    assert report["status"] == "attention"
