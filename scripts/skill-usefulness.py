#!/usr/bin/env python3
"""Read-only local skill inventory. Stdlib only; never reads transcripts or calls a host."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Historical attribution only, not executable aliases. Bare names remain ambiguous.
ALIASES = {
    "review-changes": "review-work", "review-pr": "review-work",
    "skill-health": "using-claudna", "session-handoff": "session", "session-resume": "session",
    "name-session": "session", "remember": "recall", "learn": "capture", "reflect": "capture",
    "implement-plan": "build", "commit-push-pr": "ship", "quick-commit": "ship", "visual-crawl": "qa",
    "product-brainstorm": "product-vision",
}
for old in ("security-audit", "tech-debt", "docs-review", "design-review", "access-path-audit",
            "data-model-audit", "frontend-performance-audit", "repo-health"):
    ALIASES[old] = "audit"
for old in ("first-principles", "align-to-mission", "extension-check", "precedent-check",
            "plan-health-audit", "cost-benefit"):
    ALIASES[old] = "ironclad"
for engine, modes in {"modal": ("deploy", "logs", "status"), "railway": ("deploy", "logs", "status"),
                      "vercel": ("deploy", "logs", "status"), "neon": ("branch", "info", "query")}.items():
    ALIASES.update({f"{engine}-{mode}": engine for mode in modes})


def read_json(path, errors):
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError("not an object")
        return value
    except (OSError, ValueError):
        errors.append(str(path))
        return {}


def lines(path, errors):
    try:
        with path.open() as stream:
            for n, line in enumerate(stream, 1):
                try:
                    obj = json.loads(line)
                    if not isinstance(obj, dict):
                        raise ValueError("not an object")
                    yield n, obj
                except ValueError:
                    errors.append(f"{path}:{n}")
    except OSError:
        errors.append(str(path))


def catalog(repo):
    skills = {}
    for path in sorted((repo / "skills").glob("*/SKILL.md")):
        body = path.read_text()
        front = body.split("---", 2)[1]
        desc = re.search(r"^description:\s*(.+)$", front, re.M)
        skills[path.parent.name] = {
            "trigger": desc[1].strip().strip('"') if desc else "unknown",
            "context": "source checkout required" if "requires-context: repo-clone" in front else "",
            "content_ref": str(path.relative_to(repo)),
        }
    manifests = {}
    for host, folder in (("Claude", ".claude-plugin"), ("Codex", ".codex-plugin"), ("Cursor", ".cursor-plugin")):
        manifest = json.loads((repo / folder / "plugin.json").read_text())
        selected = manifest.get("skills")
        names = sorted(skills) if selected is None else sorted(Path(p).name for p in selected)
        manifests[host] = {"version": manifest["version"], "skills": names, "path": f"{folder}/plugin.json"}
    return skills, manifests


def canonical(name, skills):
    if not isinstance(name, str) or not name.startswith("claudna:"):
        return None
    slug = name.split(":", 1)[1]
    slug = ALIASES.get(slug, slug)
    return slug if slug in skills else None


def scan(state, telemetry, skills, excluded):
    errors, sessions, events, synthetic, duplicates = [], {}, [], [], []
    hosts, kinds, statuses, retired, excluded_hosts = Counter(), Counter(), Counter(), Counter(), Counter()
    seen, all_dates, opened = set(), [], []
    dirs = sorted(p for p in (state / "sessions").glob("*") if p.is_dir())
    private = 0
    private_sids = set()
    for directory in dirs:
        meta = read_json(directory / "session.json", errors)
        if not meta:
            continue
        sid = directory.name
        host = meta.get("agent_cli", "unknown")
        hosts[host] += 1
        statuses[f"{host}:{meta.get('status', 'unknown')}"] += 1
        retired[host] += meta.get("segments", {}).get("retired", 0)
        if meta.get("opened_at"):
            opened.append(meta["opened_at"])
        if meta.get("private"):
            private += 1
            private_sids.add(sid)
            continue
        origin = meta.get("origin") or {}
        cwd = origin.get("cwd") or ""
        reason = excluded.get(sid)
        if not reason and re.search(r"canary|pytest|fixture|smoke", cwd + "/" + sid, re.I):
            reason = "test-like path/id heuristic; review before treating as organic"
        if reason:
            synthetic.append({"sid": sid, "reason": reason})
            excluded_hosts[host] += 1
        sessions[sid] = {"host": host, "project": origin.get("repo"), "cwd": cwd,
                         "meta_ref": str(directory / "session.json"), "excluded": bool(reason)}
        for path in sorted(directory.glob("seg-*/events.jsonl")):
            for n, event in lines(path, errors):
                data = event.get("data")
                ts = event.get("ts")
                if (event.get("sid") != sid or not isinstance(data, dict) or not isinstance(ts, str)
                        or not isinstance(event.get("kind"), str)):
                    errors.append(f"{path}:{n}: invalid envelope")
                    continue
                try:
                    dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    errors.append(f"{path}:{n}: invalid timestamp")
                    continue
                kinds[f"{host}:{event['kind']}"] += 1
                all_dates.append(ts)
                if reason:
                    continue
                ident = data.get("tool_use_id") or data.get("invocation_id")
                key = (sid, event["kind"], ident) if ident else (sid, json.dumps(event, sort_keys=True))
                if key in seen:
                    duplicates.append(f"{path}:{n}")
                    continue
                seen.add(key)
                events.append({**event, "ref": f"{path}:{n}", **sessions[sid]})
    projection, suppressed, telemetry_seen = [], [], set()
    store_pairs = {(e["sid"], canonical(e["data"].get("skill"), skills)) for e in events
                   if e["kind"] in ("skill.invoked", "tool.failed")}
    if telemetry.is_file():
        for n, event in lines(telemetry, errors):
            data = event.get("data", {})
            if event.get("type") != "skill_invocation" or not isinstance(data, dict):
                continue
            sid = data.get("session_id")
            slug = canonical("claudna:" + str(data.get("skill_slug", "")), skills)
            if not slug or sid in excluded or sid in private_sids or sessions.get(sid, {}).get("excluded"):
                continue
            # Legacy projection has no tool-use ID. Never add it to session-store counts.
            key = json.dumps(event, sort_keys=True)
            if key in telemetry_seen:
                duplicates.append(f"{telemetry}:{n}")
                continue
            telemetry_seen.add(key)
            record = {"slug": slug, "sid": sid, "ts": event.get("ts"), "ref": f"{telemetry}:{n}"}
            if (sid, slug) in store_pairs:
                suppressed.append(record)
            else:
                projection.append(record)
    coverage = {
        "state_dir": str(state), "telemetry_path": str(telemetry), "telemetry_present": telemetry.is_file(),
        "session_directories": len(dirs), "hosts": dict(hosts), "statuses": dict(statuses),
        "private_sessions_excluded": private, "retired_segments": dict(retired),
        "session_open_period": [min(opened), max(opened)] if opened else [],
        "activity_period": [min(all_dates), max(all_dates)] if all_dates else [],
        "activity_by_host": dict(kinds), "synthetic_or_test_sessions": synthetic,
        "excluded_hosts": dict(excluded_hosts), "malformed_or_unreadable": errors, "duplicates": duplicates,
        "telemetry_suppressed": suppressed, "telemetry_only": projection,
    }
    return sessions, events, coverage


def assessment(repo, state, telemetry, notes):
    skills, manifests = catalog(repo)
    sessions, events, coverage = scan(state, telemetry, skills, notes.get("exclude_sessions", {}))
    grouped, ambiguous = defaultdict(list), defaultdict(list)
    unrelated = Counter()
    for event in events:
        if event["kind"] not in ("skill.invoked", "tool.failed", "tool.interrupted"):
            continue
        name = event["data"].get("skill")
        if not isinstance(name, str) or not name:
            continue
        slug = canonical(name, skills)
        if slug:
            grouped[slug].append(event)
        elif ":" not in name and ALIASES.get(name, name) in skills:
            ambiguous[ALIASES.get(name, name)].append(event)
        else:
            unrelated[name] += 1
    coverage["unattributed_or_other_skills"] = dict(unrelated)
    rows = []
    for slug, info in skills.items():
        uses = grouped[slug]
        native = [e for e in uses if e["kind"] == "skill.invoked" and not e["data"].get("observation")]
        starts = [e for e in uses if e["data"].get("observation") == "agent_procedure_start"]
        failures = [e for e in uses if e["kind"] == "tool.failed"]
        observed = native + starts
        use_sids = {e["sid"] for e in observed}
        projects = {sessions[s]["project"] for s in use_sids if sessions[s]["project"]}
        workdirs = {sessions[s]["cwd"] for s in use_sids if sessions[s]["cwd"]}
        note = notes.get("skills", {}).get(slug, {})
        hosts = [h for h, m in manifests.items() if slug in m["skills"]]
        refs = [info["content_ref"], *[e["ref"] for e in uses], *note.get("references", [])]
        rows.append({
            "skill": slug, "availability": ", ".join(hosts) + ("; " + info["context"] if info["context"] else ""),
            "coverage": "Claude native Skill results; Codex prior gap/new agent entry only; Cursor unsupported",
            "native_invocations": len(native), "agent_procedure_starts": len(starts),
            "failed_attempts": len(failures), "ambiguous_bare_calls": len(ambiguous[slug]),
            "telemetry_only_unadded": sum(e["slug"] == slug for e in coverage["telemetry_only"]),
            "sessions": len(use_sids), "projects": len(projects), "project_names": "; ".join(sorted(projects)),
            "distinct_workdirs": len(workdirs),
            "sessions_without_project": sum(not sessions[s]["project"] for s in use_sids),
            "last_use": max((e["ts"] for e in observed), default="unobserved"),
            "tool_ok_true": sum(e["data"].get("ok") is True for e in native),
            "observed_outcome": note.get("outcome", "No reviewed task outcome; tool result is not task success."),
            "trigger": info["trigger"],
            "content_judgment": note.get("content", "Trigger visible; usefulness unmeasured."),
            "recommendation": note.get("recommendation", "insufficient evidence"),
            "confidence": note.get("confidence", "low usefulness confidence; counts describe retained events only"),
            "evidence": "; ".join(refs),
            "ambiguous_evidence": "; ".join(e["ref"] for e in ambiguous[slug]),
        })
    return rows, coverage, manifests


def write_report(output, rows, coverage, manifests, notes):
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (output / "assessment.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    snapshot = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "manifests": manifests,
                "coverage": coverage, "historical_aliases": ALIASES,
                "notes_as_of": notes.get("as_of"), "notes_are_not_refreshed_by_this_command": True}
    (output / "coverage.json").write_text(json.dumps(snapshot, indent=2) + "\n")
    text = [
        "---", "title: Local skill usefulness assessment", "type: audit", "status: completed",
        "owner: clauDNA maintainers", "created: " + dt.date.today().isoformat(), "---", "",
        "# Local skill usefulness assessment", "",
        "Local, unpublished report. Counts are retained evidence, not total lifetime use. "
        "Missing events do not prove non-use. No skill should be retired on these counts alone.", "",
        "Native = successful-return Skill invocation observations, not completed procedures. "
        "Agent entry = explicitly labeled procedure-start attestation; completion and task outcome unknown. "
        "Failed attempts, ambiguous bare names and legacy telemetry-only records are separate, "
        "never added to native counts.",
        "Claude coverage depends on installed/enabled hooks and an open segment. Codex's declared Skill matcher "
        "does not observe the measured read-and-execute path. Cursor is intentionally hook-free. "
        "Unavailable skills have no coverage on that host.", "",
        "Manual outcome/content notes are dated " + str(notes.get("as_of", "unreviewed")) +
        "; refreshing metadata does not re-verify those judgments.", "",
        "## Coverage", "",
        f"Session directories: {coverage['session_directories']}; hosts: {coverage['hosts']}.",
        f"Session opening period: {coverage['session_open_period']}. Activity period: {coverage['activity_period']}.",
        f"Excluded test/canary sessions: {len(coverage['synthetic_or_test_sessions'])}; "
        f"private: {coverage['private_sessions_excluded']}; malformed/unreadable: "
        f"{len(coverage['malformed_or_unreadable'])}; duplicate representations: {len(coverage['duplicates'])}.",
        f"Telemetry present: {coverage['telemetry_present']}. Same-session/skill telemetry representations "
        f"suppressed: {len(coverage['telemetry_suppressed'])}; telemetry-only records remain separate: "
        f"{len(coverage['telemetry_only'])}.", "",
        "The legacy telemetry format has no tool-use ID; suppression is conservative per session/skill, "
        "not an invented exact match. Historical aliases normalize only namespaced clauDNA calls. "
        "Bare names may be local or another plugin; they remain unattributed.",
        "Retained final segments normally expire at 30 days or 7 days after registered consumer ack. "
        "Open sessions are not age-pruned; no lifetime coverage is implied.", "",
        "Manifest selections and versions, source paths, malformed entries, exclusions and alias mappings "
        "are in coverage.json. Full columns and evidence locators are in assessment.csv.", "",
        "## Every canonical skill", "",
        "| Skill | Availability / coverage | Native / agent entry / failed / ambiguous | Sessions / projects / last | "
        "Observed outcomes | Content judgment: overlap and trigger | Recommendation / confidence | Evidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    for row in rows:
        values = [row["skill"], row["availability"] + "; coverage as above",
                  f"{row['native_invocations']} / {row['agent_procedure_starts']} / "
                  f"{row['failed_attempts']} / {row['ambiguous_bare_calls']}",
                  f"{row['sessions']} / {row['projects']} / {row['last_use']}", row["observed_outcome"],
                  row["content_judgment"], row["recommendation"] + "; " + row["confidence"], row["evidence"]]
        text.append("| " + " | ".join(cell(v) for v in values) + " |")
    (output / "assessment.md").write_text("\n".join(text) + "\n")
    for name in ("assessment.csv", "assessment.md", "coverage.json"):
        (output / name).chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path,
                        default=Path(os.environ.get("CLAUDNA_STATE_DIR") or Path.home() / ".claudna"))
    parser.add_argument("--telemetry", type=Path,
                        default=Path(os.environ.get("CLAUDNA_TELEMETRY_PATH") or
                                     Path.home() / ".claude/telemetry/skill-events.jsonl"))
    parser.add_argument("--notes", type=Path, help="reviewed local annotations and explicit session exclusions")
    args = parser.parse_args()
    if not args.state_dir.is_absolute():
        parser.error("--state-dir must be absolute")
    if not (args.state_dir / "sessions").is_dir():
        parser.error("session store missing; no zero-use report can be inferred")
    notes = json.loads(args.notes.read_text()) if args.notes else {}
    rows, coverage, manifests = assessment(ROOT, args.state_dir, args.telemetry, notes)
    write_report(args.output, rows, coverage, manifests, notes)
    print(f"Wrote {len(rows)} skill rows to {args.output}; local only.")


if __name__ == "__main__":
    main()
