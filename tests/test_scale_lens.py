"""Checks for the /audit scale lens (routing, contract, detection patterns).

Five concerns, each deterministic in CI:

1. Lens registration — the engine table row, argument-hint token, and depth
   files exist and agree; the engine stays a thin router (deep method tokens
   live only in the lens directory).
2. Routing — positive anchors resolve against the routing surface, negative
   rows name their alternative lens, ambiguous rows fall to the engine's
   stop-on-ambiguity rule (fixtures/scale/routing-cases.yaml; the
   richer manual protocol is documented in that file's header).
3. Report contract — report-template.md carries the stable section order,
   verdict values, scorecard dimensions, per-finding fields, and the severity
   mapping that keeps `--output github` labels compatible with other lenses.
4. Method — evidence classes, the read-only hard gate, scan-category coverage
   of the scorecard, and failure-window coverage of the required traces.
5. Detection patterns — the machine-checked regexes in scan-categories.md
   against the golden fixtures: the fail-open fixture trips every fail-open
   pattern, the queue/worker hazard fixture trips every queue pattern, and
   the two correct implementations (the fail-closed repository and the
   fenced queue/worker) trip none of either set — every heuristic must tell
   the bug from its fix, not merely find code of the same shape.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import parse_frontmatter

ENGINE_MD = REPO_ROOT / "skills" / "audit" / "SKILL.md"
LENS_DIR = REPO_ROOT / "skills" / "audit" / "scale"
LENS_MD = LENS_DIR / "scale.md"
SCAN_MD = LENS_DIR / "scan-categories.md"
WINDOWS_MD = LENS_DIR / "failure-windows.md"
TEMPLATE_MD = LENS_DIR / "report-template.md"
PROMPTS_MD = LENS_DIR / "subagent-prompts.md"

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "scale"
ROUTING_CASES = FIXTURE_DIR / "routing-cases.yaml"
FAIL_OPEN_FIXTURE = FIXTURE_DIR / "tenant_fail_open.py"
FAIL_CLOSED_FIXTURE = FIXTURE_DIR / "tenant_fail_closed.py"
QUEUE_FIXTURE = FIXTURE_DIR / "queue_worker.py"
FENCED_QUEUE_FIXTURE = FIXTURE_DIR / "queue_worker_fenced.py"

# The lens's declared positive triggers (scale.md § Positive triggers),
# flattened to matchable terms. Ambiguous fixture rows are screened against
# this full vocabulary — not just the curated per-row anchors — so an
# "ambiguous" utterance cannot smuggle in a declared trigger word.
POSITIVE_TRIGGER_TERMS = [
    "multi-tenan",
    "tenant",
    "organization",
    "workspace",
    "account",
    "isolation",
    "replica",
    "scaling",
    "queue",
    "worker",
    "job",
    "lease",
    "outbox",
    "scheduler",
    "rate limit",
    "fairness",
    "throughput",
    "growth",
    "scale",
    "capacity",
    "rls",
    "row-level security",
    "migration",
    "backfill",
    "credential",
]


def engine_frontmatter_and_body() -> tuple[dict, str]:
    parsed = parse_frontmatter(ENGINE_MD)
    assert parsed is not None, "audit SKILL.md has unparseable frontmatter"
    return parsed


def engine_lens_row() -> str:
    """The scale row of the engine's lens table."""
    _, body = engine_frontmatter_and_body()
    rows = [ln for ln in body.splitlines() if ln.startswith("| `scale`")]
    assert len(rows) == 1, f"expected exactly one scale table row, found {len(rows)}"
    return rows[0]


def markdown_section(text: str, heading: str) -> str:
    """A `## <heading>` section (including nested ### subsections)."""
    m = re.search(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.DOTALL | re.MULTILINE
    )
    assert m, f"missing section '## {heading}'"
    return m.group(0)


def routing_surface() -> str:
    """What routing decisions read: the engine's table row + the lens's Routing section."""
    return engine_lens_row() + "\n" + markdown_section(LENS_MD.read_text(), "Routing")


def load_routing_cases() -> dict:
    data = yaml.safe_load(ROUTING_CASES.read_text())
    assert isinstance(data, dict)
    for key in ("positive", "negative", "ambiguous"):
        assert isinstance(data.get(key), list) and data[key], f"routing-cases.yaml missing {key} rows"
    return data


def extract_patterns(anchor: str) -> list[str]:
    """Regex lines from the fenced block following a `<!-- test-anchor: ... -->` marker."""
    text = SCAN_MD.read_text()
    marker = f"<!-- test-anchor: {anchor} -->"
    assert marker in text, f"scan-categories.md missing marker {marker!r}"
    after = text.split(marker, 1)[1]
    block = re.search(r"```regex\n(.*?)```", after, re.DOTALL)
    assert block, f"no ```regex block after marker {marker!r}"
    lines = [ln.strip() for ln in block.group(1).splitlines()]
    patterns = [ln for ln in lines if ln and not ln.startswith("#")]
    assert patterns, f"empty pattern block for {anchor!r}"
    return patterns


# --- 1. Lens registration -------------------------------------------------


def test_lens_files_exist():
    for path in (LENS_MD, SCAN_MD, WINDOWS_MD, TEMPLATE_MD, PROMPTS_MD):
        assert path.is_file(), f"missing lens file: {path.relative_to(REPO_ROOT)}"


def test_engine_table_row_registers_the_lens():
    row = engine_lens_row()
    assert "`scale/scale.md`" in row, "row must point at the lens depth file"
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[2] == "yes", f"scale is a read-only scan lens — Auto column should be 'yes', got {cells[2]!r}"


def test_argument_hint_carries_the_lens_token():
    fm, _ = engine_frontmatter_and_body()
    assert "scale" in str(fm.get("argument-hint", "")), (
        "engine argument-hint must list the scale lens token"
    )


def test_description_carries_routing_vocabulary():
    # The skill picker routes on the engine description (see routing-matrix.yaml);
    # these anchors are what the matrix rows for this lens key on.
    fm, _ = engine_frontmatter_and_body()
    desc = str(fm.get("description", "")).lower()
    for anchor in ("scale", "throughput", "multi-tenant", "isolation"):
        assert anchor in desc, f"engine description lost routing anchor {anchor!r}"


def test_engine_stays_thin():
    # Deep methodology belongs in the lens directory (thin-router rule,
    # audit-lens-contract §1) — these tokens appearing in the engine body
    # would mean lens depth leaked into the router.
    _, body = engine_frontmatter_and_body()
    for token in ("BYPASSRLS", "fencing", "idempotency", "fail-open"):
        assert token.lower() not in body.lower(), (
            f"engine body contains lens-depth token {token!r} — keep the router thin"
        )


# --- 2. Routing -----------------------------------------------------------


def test_routing_case_schema():
    cases = load_routing_cases()
    for row in cases["positive"]:
        assert isinstance(row.get("utterance"), str) and row["utterance"]
        assert isinstance(row.get("anchors"), list) and row["anchors"]
    for row in cases["negative"]:
        assert isinstance(row.get("utterance"), str) and row["utterance"]
        assert isinstance(row.get("route_to"), str) and row["route_to"]
    for row in cases["ambiguous"]:
        assert isinstance(row.get("utterance"), str) and row["utterance"]


def test_positive_anchors_resolve_in_routing_surface():
    surface = routing_surface().lower()
    failures = []
    for row in load_routing_cases()["positive"]:
        for anchor in row["anchors"]:
            if str(anchor).lower() not in surface:
                failures.append(
                    f"anchor {anchor!r} (utterance: {row['utterance']!r}) not in routing surface"
                )
    assert not failures, "\n".join(failures)


def test_negative_rows_route_to_existing_alternatives():
    for row in load_routing_cases()["negative"]:
        target = row["route_to"]
        if target.startswith("audit "):
            lens = target.split(" ", 1)[1]
            lens_file = REPO_ROOT / "skills" / "audit" / lens / f"{lens}.md"
            assert lens_file.is_file(), f"route_to {target!r}: no such lens depth file"
        else:
            skill_md = REPO_ROOT / "skills" / target / "SKILL.md"
            assert skill_md.is_file(), f"route_to {target!r}: no such skill"


def test_negative_triggers_name_the_alternatives():
    negative = markdown_section(LENS_MD.read_text(), "Routing")
    for row in load_routing_cases()["negative"]:
        target = row["route_to"]
        ref = f"/claudna:{target}"  # "audit <lens>" → /claudna:audit <lens>; bare skill → /claudna:<skill>
        assert ref in negative, (
            f"lens negative triggers must name the alternative {ref!r} "
            f"(for utterances like {row['utterance']!r})"
        )


def test_tenant_id_alone_is_declared_a_non_trigger():
    # The one confusion this lens must not create: routing ordinary
    # code-quality audits here just because a tenant_id field exists.
    row = engine_lens_row()
    assert "tenant_id" in row and "NOT a trigger" in row, (
        "engine row must declare a bare tenant_id column a non-trigger"
    )
    negative = markdown_section(LENS_MD.read_text(), "Routing")
    assert "tenant_id" in negative and "NOT a trigger" in negative, (
        "lens negative triggers must declare a bare tenant_id column a non-trigger"
    )


def test_ambiguous_utterances_carry_no_positive_trigger():
    # Fixture hygiene: an "ambiguous" utterance containing a declared positive
    # trigger would not be ambiguous — it would legitimately route to this
    # lens. Screen against the full trigger vocabulary, not just the curated
    # per-row anchors (which are a subset and can miss a smuggled trigger).
    cases = load_routing_cases()
    anchors = {str(a).lower() for row in cases["positive"] for a in row["anchors"]}
    screen = anchors | set(POSITIVE_TRIGGER_TERMS)
    for row in cases["ambiguous"]:
        utterance = row["utterance"].lower()
        hits = [term for term in sorted(screen) if term in utterance]
        assert not hits, f"ambiguous utterance {row['utterance']!r} contains positive trigger(s) {hits}"


def test_engine_retains_stop_on_ambiguity_contract():
    _, body = engine_frontmatter_and_body()
    assert "unambiguous" in body, "engine dispatch must retain the unambiguous-wording rule"
    assert "print this table and stop" in body, (
        "engine dispatch must retain the print-the-table-and-stop ambiguity behavior"
    )


def test_lens_defers_the_ambiguous_case_to_the_engine():
    routing = markdown_section(LENS_MD.read_text(), "Routing")
    assert "never claims the ambiguous case" in routing, (
        "lens routing must defer mixed-evidence requests to the engine's ambiguity rule"
    )


# --- 3. Report contract ---------------------------------------------------

REPORT_SECTIONS = [
    "## 1. Executive verdict",
    "## 2. Scorecard",
    "## 3. Boundary and capacity map",
    "## 4. Evidence audit",
    "## 5. Failure sequences",
    "## 6. Findings (P0–P3)",
    "## 7. Required invariants",
    "## 8. Acceptance-test matrix",
    "## 9. Open decisions",
    "## 10. Unverified claims",
]

SCORECARD_DIMENSIONS = [
    "Identity and authorization",
    "Data isolation",
    "Distributed coordination",
    "Provider isolation",
    "Fairness and capacity",
    "Observability",
    "Migration safety",
    "Testability",
]

FINDING_FIELDS = [
    "**Severity:**",
    "**Confidence:**",
    "**Concern area:**",
    "**Evidence:**",
    "**Consequence:**",
    "**Exploit / failure sequence:**",
    "**Remediation direction:**",
]


def test_report_sections_present_and_ordered():
    text = TEMPLATE_MD.read_text()
    positions = []
    for heading in REPORT_SECTIONS:
        assert heading in text, f"report-template.md missing section {heading!r}"
        positions.append(text.index(heading))
    assert positions == sorted(positions), "report sections out of order — the report is a stable contract"


def test_report_verdict_values():
    text = TEMPLATE_MD.read_text()
    for verdict in ("approve", "approve with required changes", "reject"):
        assert verdict in text, f"report-template.md missing verdict {verdict!r}"


def test_report_scorecard_dimensions():
    scorecard = markdown_section(TEMPLATE_MD.read_text(), "2. Scorecard")
    for dim in SCORECARD_DIMENSIONS:
        assert dim in scorecard, f"scorecard missing dimension {dim!r}"


def test_report_finding_fields():
    findings = markdown_section(TEMPLATE_MD.read_text(), "6. Findings (P0–P3)")
    for field in FINDING_FIELDS:
        assert field in findings, f"finding block missing field {field!r}"


def test_severity_ladder_maps_to_shared_labels():
    # Compatibility with the shared `--output github` label scheme used by
    # every other lens (output-guide §4): P0..P3 map onto priority labels.
    text = TEMPLATE_MD.read_text()
    for severity, label in [
        ("P0", "priority:critical"),
        ("P1", "priority:high"),
        ("P2", "priority:medium"),
        ("P3", "priority:low"),
    ]:
        assert re.search(rf"\*\*{severity}\*\*.*{re.escape(label)}", text), (
            f"severity ladder missing {severity} → {label} mapping"
        )


def test_lens_preserves_shared_audit_surfaces():
    # The lens must ride the shared contracts, not fork them: lens contract
    # (arguments/plan-mode/auto), output guide (github/session routing),
    # canonical concern vocabulary, and §10.C structured-result emission.
    text = LENS_MD.read_text()
    for ref in (
        "skills/_shared/audit-lens-contract.md",
        "skills/_shared/output-guide.md",
        "lens-result-contract.md",
        "§10.C",
    ):
        assert ref in text, f"lens must reference shared surface {ref!r}"


# --- 4. Method ------------------------------------------------------------

EVIDENCE_CLASSES = [
    "repository-proven",
    "documentation-only",
    "external-assumption",
    "proposed",
    "unverified",
]


def test_evidence_classes_defined_everywhere_claims_flow():
    lens_text = LENS_MD.read_text()
    template_text = TEMPLATE_MD.read_text()
    for cls in EVIDENCE_CLASSES:
        assert cls in lens_text, f"lens evidence discipline missing class {cls!r}"
        assert cls in template_text, f"report evidence audit missing class {cls!r}"


def test_read_only_hard_gate():
    text = LENS_MD.read_text()
    assert "<HARD-GATE>" in text and "</HARD-GATE>" in text, "read-only rule must be a hard gate"
    gate = text.split("<HARD-GATE>")[1].split("</HARD-GATE>")[0]
    assert "read-only" in gate.lower(), "the hard gate must state the audited target is read-only"


def test_scan_categories_cover_the_scorecard():
    text = SCAN_MD.read_text()
    for letter in "ABCDEFGH":
        assert re.search(rf"^## {letter}\. ", text, re.MULTILINE), (
            f"scan-categories.md missing category {letter} — one per scorecard dimension"
        )


def test_failure_windows_cover_required_traces():
    text = WINDOWS_MD.read_text().lower()
    for keyword in (
        "replay",
        "lease expiry",
        "stale",
        "cancellation",
        "ambiguous",
        "broker loss",
        "pooled connection",
        "poison",
        "flood",
        "degraded admission",
        "herd",
    ):
        assert keyword in text, f"failure-windows.md missing required window keyword {keyword!r}"


def test_capacity_envelope_is_demanded():
    # The pressure-tester bar: claims are graded against a stated numeric
    # target, and the absence of one is itself a finding.
    lens = LENS_MD.read_text()
    assert "capacity envelope" in lens.lower(), "Phase 0 must demand the capacity envelope"
    assert "No declared envelope is itself a finding" in lens, (
        "an unstated capacity target must be a finding, not a blank"
    )
    boundary = markdown_section(TEMPLATE_MD.read_text(), "3. Boundary and capacity map")
    assert "capacity envelope" in boundary.lower(), (
        "the report's boundary map must carry the envelope the audit graded against"
    )


def test_slo_measurement_point_rule():
    # Every claimed SLO needs an unambiguous measurement point in shipped
    # telemetry; an unmeasurable SLO is documentation-only by construction.
    scan = SCAN_MD.read_text().lower()
    assert "measurement point" in scan, "scan category F must carry the SLO measurement-point rule"


def test_saturation_and_recovery_behavior_is_audited():
    scan = SCAN_MD.read_text().lower()
    for token in ("backpressure", "jitter", "degraded-mode", "autoscaling", "all-or-none"):
        assert token in scan, f"scan categories missing pressure-behavior token {token!r}"


def test_acceptance_matrix_requires_pressure_rows():
    matrix = markdown_section(TEMPLATE_MD.read_text(), "8. Acceptance-test matrix").lower()
    for token in ("saturation", "storm", "herd", "fast reject"):
        assert token in matrix, f"acceptance-test matrix missing pressure scenario token {token!r}"
    assert "one saturation row per shared budget" in matrix, (
        "the matrix must require a saturation row for every shared budget"
    )


# --- 5. Detection patterns vs. golden fixtures -----------------------------


def test_patterns_compile():
    for anchor in ("fail-open-patterns", "queue-worker-patterns"):
        for pattern in extract_patterns(anchor):
            re.compile(pattern)  # raises on an invalid pattern


def test_fail_open_fixture_trips_every_fail_open_pattern():
    text = FAIL_OPEN_FIXTURE.read_text()
    misses = [p for p in extract_patterns("fail-open-patterns") if not re.search(p, text)]
    assert not misses, (
        "fail-open golden fixture no longer exercises these patterns "
        f"(fixture and scan-categories.md must move together): {misses}"
    )


def test_queue_fixture_trips_every_queue_pattern():
    text = QUEUE_FIXTURE.read_text()
    misses = [p for p in extract_patterns("queue-worker-patterns") if not re.search(p, text)]
    assert not misses, (
        "queue/worker golden fixture no longer exercises these patterns "
        f"(fixture and scan-categories.md must move together): {misses}"
    )


def test_correct_implementations_trip_no_pattern():
    # The discriminating half of the golden set: the correct implementations
    # must not match any heuristic — otherwise the lens flags healthy code.
    # tenant_fail_closed.py mirrors the fail-open hazards (mandatory tenant
    # context, tenant-scoped keys and prefix lookups, audited maintenance
    # path); queue_worker_fenced.py mirrors the queue/worker hazards (fenced
    # finalization, tenant-scoped idempotency key, reconcile-not-retry,
    # injected shared limiter, jittered polls) — so every pattern is proven
    # to tell its bug from that bug's fix.
    for fixture in (FAIL_CLOSED_FIXTURE, FENCED_QUEUE_FIXTURE):
        text = fixture.read_text()
        false_positives = [
            p
            for anchor in ("fail-open-patterns", "queue-worker-patterns")
            for p in extract_patterns(anchor)
            if re.search(p, text)
        ]
        assert not false_positives, (
            f"patterns match the correct implementation {fixture.name} "
            f"(false positives): {false_positives}"
        )
