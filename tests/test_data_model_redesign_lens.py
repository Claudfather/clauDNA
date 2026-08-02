"""Checks for the /audit data-model-redesign lens (registration, protocol, closure).

Five concerns, each deterministic in CI:

1. Lens registration — the engine table row, argument-hint token, and depth
   files exist and agree; the sibling rows cross-reference each other (the
   fit/rebuild intent partition); the engine stays a thin router (deep method
   tokens live only in the lens directory).
2. Protocol structure — the seven parts appear, in order, in both the lens's
   protocol table and the evaluation prompt; the two ordering rules the
   protocol exists to enforce (reconstruct-before-critique as a hard gate,
   recommendation-last) are stated where they bind; the lens stays
   interactive-only.
3. Template closure — every {{variable}} used in the dispatched prompt is
   declared in the template's variable table and vice versa (an undeclared
   variable ships unfilled; a declared-but-unused one is dead weight the
   leakage scan still has to reason about); the leakage-scan rule carries
   its five categories and the lens applies it to every dispatch.
4. Playbook contract — the six stages in order, the four backfill
   requirements, the per-stage rollback triple, and the load-bearing safety
   rules (expand and contract never share a deploy; contract — not cutover —
   is the point of no return; per-consumer coverage with no silent omissions).
5. Verification-checklist contract — the five checks, the tracker-
   reconciliation buckets with `--state all`, runs-in-every-output-mode, and
   the internal-consistency check that keeps incremental repair mandatory.

A live `claude --plugin-dir` dogfood run is the richer manual protocol these
mechanical checks proxy for; it cannot run in CI.
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
LENS_DIR = REPO_ROOT / "skills" / "audit" / "data-model-redesign"
LENS_MD = LENS_DIR / "data-model-redesign.md"
TEMPLATE_MD = LENS_DIR / "evaluation-prompt-template.md"
PLAYBOOK_MD = LENS_DIR / "migration-playbook.md"
CHECKLIST_MD = LENS_DIR / "verification-checklist.md"
SIBLING_MD = REPO_ROOT / "skills" / "audit" / "data-model" / "data-model.md"
DOC_STANDARD_MD = REPO_ROOT / "skills" / "_shared" / "documentation-standard.md"
ROUTING_MATRIX = Path(__file__).parent / "fixtures" / "routing-matrix.yaml"


def engine_frontmatter_and_body() -> tuple[dict, str]:
    parsed = parse_frontmatter(ENGINE_MD)
    assert parsed is not None, "audit SKILL.md has unparseable frontmatter"
    return parsed


def engine_lens_row(lens: str) -> str:
    """A single lens's row of the engine's dispatch table."""
    _, body = engine_frontmatter_and_body()
    rows = [ln for ln in body.splitlines() if ln.startswith(f"| `{lens}`")]
    assert len(rows) == 1, f"expected exactly one {lens} table row, found {len(rows)}"
    return rows[0]


# --- 1. Lens registration -------------------------------------------------


def test_lens_files_exist():
    for path in (LENS_MD, TEMPLATE_MD, PLAYBOOK_MD, CHECKLIST_MD):
        assert path.is_file(), f"missing lens file: {path.relative_to(REPO_ROOT)}"


def test_engine_table_row_registers_the_lens():
    row = engine_lens_row("data-model-redesign")
    assert "`data-model-redesign/data-model-redesign.md`" in row, "row must point at the lens depth file"
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[2] == "no", (
        f"data-model-redesign is interactive-only — Auto column must be 'no', got {cells[2]!r}"
    )


def test_argument_hint_carries_the_lens_token():
    fm, _ = engine_frontmatter_and_body()
    assert "data-model-redesign" in str(fm.get("argument-hint", "")), (
        "engine argument-hint must list the data-model-redesign lens token"
    )


def test_description_carries_routing_vocabulary():
    # The skill picker routes on the engine description (see routing-matrix.yaml);
    # these anchors are what the matrix row for this lens keys on.
    fm, _ = engine_frontmatter_and_body()
    desc = str(fm.get("description", "")).lower()
    for anchor in ("data model", "redesign"):
        assert anchor in desc, f"engine description lost routing anchor {anchor!r}"


def test_sibling_rows_partition_the_intent_space():
    # The one confusion this lens must not create: fit-audit requests landing
    # on the redesign lens or vice versa. Each row names the other.
    redesign_row = engine_lens_row("data-model-redesign")
    fit_row = engine_lens_row("data-model")
    assert "`data-model`" in redesign_row.split("|")[2], (
        "redesign row must route the fit-audit case to `data-model`"
    )
    assert "data-model-redesign" in fit_row, (
        "data-model row must route the rebuild question to `data-model-redesign`"
    )
    assert "/claudna:audit data-model-redesign" in SIBLING_MD.read_text(), (
        "the fit lens's opening must name the redesign sibling"
    )
    assert "/claudna:audit data-model" in LENS_MD.read_text(), (
        "the redesign lens must name the fit sibling in When NOT to use"
    )


def test_engine_stays_thin():
    # Deep methodology belongs in the lens directory (thin-router rule,
    # audit-lens-contract §1) — these tokens appearing in the engine body
    # would mean lens depth leaked into the router.
    _, body = engine_frontmatter_and_body()
    for token in ("leakage", "dual-write", "shadow-read", "backfill", "source-of-truth"):
        assert token.lower() not in body.lower(), (
            f"engine body contains lens-depth token {token!r} — keep the router thin"
        )


def test_routing_matrix_carries_the_redesign_row():
    data = yaml.safe_load(ROUTING_MATRIX.read_text())
    rows = [r for r in data["rows"] if r.get("mode") == "data-model-redesign"]
    assert rows, "routing-matrix.yaml must carry a data-model-redesign row"
    for row in rows:
        assert row["expect"] == "audit"
        assert "redesign" in [str(k).lower() for k in row["keywords"]], (
            "the redesign row must anchor on 'redesign' — the keyword that "
            "disambiguates it from the fit sibling's rows"
        )


# --- 2. Protocol structure --------------------------------------------------

PART_HEADINGS = [
    "## Part 1 — Reconstruct the system as built",
    "## Part 2 — Source-of-truth inventory",
    "## Part 3 — Path traces with transaction boundaries",
    "## Part 4 — Evaluation",
    "## Part 5 — Candidate approaches (three or more)",
    "## Part 6 — Recommendation (last)",
    "## Part 7 — Migration plan",
]


def test_lens_protocol_table_lists_all_seven_parts():
    text = LENS_MD.read_text()
    for n in range(1, 8):
        assert re.search(rf"^\| {n} \|", text, re.MULTILINE), (
            f"lens protocol table missing Part {n}"
        )


def test_prompt_carries_all_seven_parts_in_order():
    text = TEMPLATE_MD.read_text()
    positions = []
    for heading in PART_HEADINGS:
        assert heading in text, f"evaluation prompt missing {heading!r}"
        positions.append(text.index(heading))
    assert positions == sorted(positions), (
        "protocol parts out of order — the ordering is load-bearing "
        "(reconstruct before critique; recommendation last)"
    )


def test_reconstruction_gate_is_hard():
    text = LENS_MD.read_text()
    assert "<HARD-GATE>" in text and "</HARD-GATE>" in text, (
        "reconstruct-before-critique must be a hard gate"
    )
    gate = text.split("<HARD-GATE>")[1].split("</HARD-GATE>")[0]
    assert "No critique" in gate, "the hard gate must forbid critique before confirmation"


def test_recommendation_last_binds_the_presentation_too():
    assert "recommendation-last governs the presentation" in LENS_MD.read_text(), (
        "the direction gate must present findings and the comparison matrix "
        "before the recommendation — not just order the document that way"
    )


def test_incremental_repair_is_mandatory():
    assert "MUST be incremental repair" in TEMPLATE_MD.read_text(), (
        "Part 5 must make incremental repair a mandatory candidate — "
        "the null-redesign baseline every rebuild must beat"
    )


def test_lens_is_interactive_only():
    assert "no `--auto` variant" in LENS_MD.read_text(), (
        "the lens must declare itself interactive-only; the engine owns the "
        "--auto blocked-result path (lens contract §4)"
    )


def test_lens_preserves_shared_audit_surfaces():
    # The lens must ride the shared contracts, not fork them.
    text = LENS_MD.read_text()
    for ref in (
        "skills/_shared/audit-lens-contract.md",
        "skills/_shared/output-guide.md",
        "skills/_shared/orchestration-guide.md",
        "skills/_shared/planning-standard.md",
        "never the literal `scripts/redact.py`",  # §7-resolved redactor, not a hardcoded path
    ):
        assert ref in text, f"lens must reference shared surface {ref!r}"


def test_docs_routing_is_registered_and_shared_with_the_sibling():
    assert "documentation/planning/data-model/" in LENS_MD.read_text(), (
        "lens --output docs must route to the data-model planning convention"
    )
    registry = DOC_STANDARD_MD.read_text()
    assert re.search(
        r"^\| `/claudna:audit data-model-redesign` \| `documentation/planning/data-model/`",
        registry,
        re.MULTILINE,
    ), "documentation-standard §2 must carry the redesign lens's --dir registry row"


# --- 3. Template closure ----------------------------------------------------


def template_prompt_block() -> str:
    m = re.search(r"^````markdown\n(.*?)^````", TEMPLATE_MD.read_text(), re.DOTALL | re.MULTILINE)
    assert m, "evaluation-prompt-template.md missing the fenced prompt block"
    return m.group(1)


def test_template_variables_are_closed():
    text = TEMPLATE_MD.read_text()
    declared = set(re.findall(r"^\| `\{\{(\w+)\}\}` \|", text, re.MULTILINE))
    assert declared, "template variable table is empty or unparseable"
    used = set(re.findall(r"\{\{(\w+)\}\}", template_prompt_block()))
    assert used - declared == set(), (
        f"prompt uses undeclared variables (would ship unfilled): {sorted(used - declared)}"
    )
    assert declared - used == set(), (
        f"declared variables never used in the prompt (dead weight): {sorted(declared - used)}"
    )


def test_leakage_scan_rule_carries_its_five_categories():
    m = re.search(
        r"^## The leakage-scan rule\n(.*?)(?=^## |\Z)",
        TEMPLATE_MD.read_text(),
        re.DOTALL | re.MULTILINE,
    )
    assert m, "template missing the leakage-scan rule section"
    section = m.group(1)
    numbered = re.findall(r"^\d+\. \*\*(.+?)\*\*", section, re.MULTILINE)
    assert len(numbered) == 5, f"leakage scan must name its 5 categories, found {len(numbered)}"
    assert "re-scan after every edit" in section.lower(), (
        "the scan must repeat after every edit until a pass returns clean"
    )


def test_lens_applies_the_scan_to_every_dispatch():
    text = LENS_MD.read_text()
    assert "leakage" in text.lower(), "lens procedure must invoke the leakage scan"
    assert re.search(r"applies to \*\*every\*\* dispatch", text), (
        "the scan must cover every dispatch wave, not just the first"
    )


# --- 4. Playbook contract ---------------------------------------------------

STAGE_HEADINGS = [
    "### 1. Expand",
    "### 2. Backfill",
    "### 3. Dual-write",
    "### 4. Shadow-read",
    "### 5. Cutover",
    "### 6. Contract",
]


def test_playbook_six_stages_in_order():
    text = PLAYBOOK_MD.read_text()
    positions = []
    for heading in STAGE_HEADINGS:
        assert heading in text, f"migration playbook missing stage {heading!r}"
        positions.append(text.index(heading))
    assert positions == sorted(positions), "playbook stages out of order"


def test_backfill_carries_all_four_requirements():
    text = PLAYBOOK_MD.read_text()
    for req in ("**Idempotent**", "**Resumable**", "**Rate-limited**", "**Verified**"):
        assert req in text, f"backfill stage missing requirement {req!r}"


def test_rollback_triple_is_defined():
    text = PLAYBOOK_MD.read_text()
    for field in ("**Trigger**", "**Mechanism**", "**Blast radius**"):
        assert field in text, f"rollback section missing {field!r}"


def test_expand_and_contract_never_share_a_deploy():
    assert "Never combine expand and contract in one deploy" in PLAYBOOK_MD.read_text()


def test_contract_is_the_point_of_no_return():
    text = PLAYBOOK_MD.read_text()
    assert "the point of no return is here, not at cutover" in text, (
        "the playbook must place irreversibility at contract, not cutover"
    )


def test_per_consumer_coverage_has_no_silent_omissions():
    text = PLAYBOOK_MD.read_text()
    assert "consumer × stage matrix" in text, "coverage must be a consumer × stage matrix"
    assert "never an omission" in text, (
        "'unaffected' must be a recorded disposition, never an omission"
    )


# --- 5. Verification-checklist contract --------------------------------------

CHECK_HEADINGS = [
    "## 1. Referenced files exist",
    "## 2. Referenced issues exist",
    "## 3. Placeholder scan",
    "## 4. Tracker reconciliation",
    "## 5. Internal consistency",
]


def test_checklist_carries_all_five_checks():
    text = CHECKLIST_MD.read_text()
    positions = []
    for heading in CHECK_HEADINGS:
        assert heading in text, f"verification checklist missing {heading!r}"
        positions.append(text.index(heading))
    assert positions == sorted(positions), "checklist checks out of order"


def test_tracker_reconciliation_searches_closed_issues_too():
    text = CHECKLIST_MD.read_text()
    assert "--state all" in text, (
        "reconciliation must search closed issues — a closed match means "
        "landed-or-regressed, which open-only search cannot see"
    )
    for bucket in ("net-new", "extends #N", "regressed #N", "duplicate of #N", "already landed"):
        assert bucket in text, f"reconciliation missing bucket {bucket!r}"


def test_checklist_runs_in_every_output_mode():
    assert "every output mode" in CHECKLIST_MD.read_text(), (
        "verification is a pre-handoff gate in session/github/docs alike, "
        "not a filing courtesy"
    )


def test_checklist_enforces_the_candidate_floor():
    text = CHECKLIST_MD.read_text()
    assert "three or more" in text and "incremental repair" in text, (
        "internal consistency must re-check ≥3 candidates with repair among them"
    )
