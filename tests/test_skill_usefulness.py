"""Reporting regressions: zero-use catalog, attribution, privacy and duplicate observations."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skill_usefulness", ROOT / "scripts/skill-usefulness.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def session(root, sid="s1", private=False, cwd="/work"):
    directory = root / "sessions" / sid
    (directory / "seg-001").mkdir(parents=True)
    (directory / "session.json").write_text(json.dumps({
        "sid": sid, "agent_cli": "claude", "status": "open", "private": private,
        "opened_at": "2026-11-01T00:00:00Z", "origin": {"cwd": cwd, "repo": "work"},
    }))
    return directory / "seg-001/events.jsonl"


def event(skill="claudna:audit", sid="s1", tool="t1", **extra):
    return {"sid": sid, "seg": 1, "kind": "skill.invoked", "v": 1, "ts": "2026-11-01T00:00:01Z",
            "data": {"skill": skill, "tool_use_id": tool, "ok": True}, **extra}


def test_complete_catalog_includes_unobserved_and_host_excluded(tmp_path):
    (tmp_path / "sessions").mkdir()
    rows, _, manifests = report.assessment(ROOT, tmp_path, tmp_path / "none", {})
    assert {r["skill"] for r in rows} == {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
    assert all(r["native_invocations"] == 0 and r["recommendation"] == "insufficient evidence" for r in rows)
    for slug in ("cleanup-legacy-install", "promotion-intake", "skill-scaffold"):
        assert slug not in manifests["Codex"]["skills"]


def test_duplicates_projection_bare_names_and_malformed_are_not_usage(tmp_path):
    path = session(tmp_path)
    first = event()
    second = event("audit", tool="t2")
    path.write_text("\n".join(map(json.dumps, [first, first, second])) + "\n{broken\n")
    telemetry = tmp_path / "telemetry.jsonl"
    telemetry.write_text(json.dumps({"type": "skill_invocation", "ts": "2026-11-01T00:00:01Z",
                                     "data": {"skill_slug": "audit", "session_id": "s1"}}) + "\n")
    rows, coverage, _ = report.assessment(ROOT, tmp_path, telemetry, {})
    row = next(r for r in rows if r["skill"] == "audit")
    assert row["native_invocations"] == 1 and row["ambiguous_bare_calls"] == 1
    assert row["sessions"] == row["projects"] == 1
    assert len(coverage["duplicates"]) == len(coverage["malformed_or_unreadable"]) == 1
    assert len(coverage["telemetry_suppressed"]) == 1 and row["telemetry_only_unadded"] == 0


def test_private_and_synthetic_sessions_excluded_in_both_representations(tmp_path):
    session(tmp_path, "private", private=True).write_text(json.dumps(event(sid="private")) + "\n")
    session(tmp_path, "test", cwd="/work/canary").write_text(json.dumps(event(sid="test")) + "\n")
    session(tmp_path, "explicit").write_text(json.dumps(event(sid="explicit")) + "\n")
    telemetry = tmp_path / "telemetry.jsonl"
    telemetry.write_text("\n".join(json.dumps({
        "type": "skill_invocation", "data": {"skill_slug": "audit", "session_id": sid}
    }) for sid in ("private", "test", "explicit")) + "\n")
    rows, coverage, _ = report.assessment(ROOT, tmp_path, telemetry,
                                         {"exclude_sessions": {"explicit": "validation"}})
    assert sum(r["native_invocations"] + r["telemetry_only_unadded"] for r in rows) == 0
    assert coverage["private_sessions_excluded"] == 1
    assert len(coverage["synthetic_or_test_sessions"]) == 2


def test_procedure_attestation_and_failure_do_not_become_success(tmp_path):
    path = session(tmp_path)
    start = event()
    start["data"].update(observation="agent_procedure_start", ok=None, invocation_id="entry1", tool_use_id=None)
    failed = event(tool="failed", kind="tool.failed")
    failed["data"]["ok"] = False
    path.write_text("\n".join(map(json.dumps, [start, failed])) + "\n")
    rows, _, _ = report.assessment(ROOT, tmp_path, tmp_path / "none", {})
    row = next(r for r in rows if r["skill"] == "audit")
    assert row["agent_procedure_starts"] == row["failed_attempts"] == 1
    assert row["native_invocations"] == row["tool_ok_true"] == 0


def test_report_default_uses_writer_root_and_legacy_input_is_explicit(tmp_path, monkeypatch):
    import sys

    state = tmp_path / "relocated"
    session(state).write_text(json.dumps(event()) + "\n")
    canonical = state / "telemetry/skill-events.jsonl"
    canonical.parent.mkdir()
    canonical.write_text("")
    legacy = tmp_path / "host-owned/old-feed.jsonl"
    legacy.parent.mkdir()
    legacy.write_text("legacy sentinel\n")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDNA_STATE_DIR", str(state))
    monkeypatch.delenv("CLAUDNA_TELEMETRY_PATH", raising=False)
    before = {p: p.read_bytes() for p in state.rglob("*") if p.is_file()}
    for name, args, expected in (("canonical", [], canonical), ("legacy", ["--telemetry", str(legacy)], legacy)):
        output = tmp_path / name
        monkeypatch.setattr(sys, "argv", ["skill-usefulness.py", "--output", str(output), *args])
        report.main()
        coverage = json.loads((output / "coverage.json").read_text())["coverage"]
        assert coverage["telemetry_path"] == str(expected)
    assert legacy.read_text() == "legacy sentinel\n"
    assert {p: p.read_bytes() for p in state.rglob("*") if p.is_file()} == before
