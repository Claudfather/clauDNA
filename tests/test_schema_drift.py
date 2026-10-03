"""Tests for the schema-drift gate: output-guide §3 against Claudron's vendored contract.

§3's status table is rendered from ``contracts/claudron.json`` (``statuses``
and ``maturity``) and stamped with the release ``contracts/claudron.ref``
names. The gate is offline: everything it compares lives in the repo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_schema_drift as csd  # noqa: E402

# --- fixtures ---

CONTRACT = {
    "contract_version": 1,
    "statuses": {
        "knowledge": {"canonical": ["current", "stale", "superseded", "archived"],
                      "terminal": ["superseded", "archived"],
                      "legacy": {"active": "current", "draft": "use maturity: draft"}, "default": "current"},
        "plan": {"canonical": ["draft", "active", "completed", "superseded", "archived"],
                 "terminal": ["completed", "superseded", "archived"], "legacy": {}, "default": "draft"},
    },
    "maturity": ["draft", "verified", "canonical"],
}
REF = "v0.9.0"


def guide_text(*, rows: list[str] | None = None, ref: str = REF, stamp: bool = True,
               maturity: str = "draft | verified | canonical") -> str:
    table = "\n".join(rows if rows is not None else csd.render_rows(CONTRACT["statuses"]))
    banner = f"Rendered from Claudron's `claudron contract --json` @ `{ref}`." if stamp else "Unstamped."
    return f"""# Output Guide

## 3. The Publishable Doc — Frontmatter

> {banner} Adds an optional `maturity: {maturity}` trust axis.

| Field | Rule |
|-------|------|
| `type` | One of the note types in the vocabulary table below. |
| `status` | Valid for the `type` per the vocabulary table below. |

{csd.TABLE_MARKER} — rendered; do not hand-edit -->
{table}

## 4. House Style
"""


PUBLISH_STUB = """# Publish

### 1a. Frontmatter schema

| Field | Rule |
|-------|------|
| `type` | a valid note type — vocabulary table in `skills/_shared/output-guide.md` §3 |
| `status` | valid for the `type` per the §3 vocabulary table |

| Type | Destination |
|------|-------------|
| plan | shared/planning/active/ (or completed/ if status is completed) |
| audit, review | shared/planning/active/ |
"""

INDEX_STUB = """# Index

## Step 2

Validate against the schema (vocabulary SSOT: `skills/_shared/output-guide.md` §3).

1. **Primary:** active/current/ratified/draft first, then completed/stale/superseded/archived
"""


def make_repo(tmp_path, *, guide: str | None = None, publish: str | None = None, index: str | None = None,
              contract: dict | None = None, ref: str = REF) -> Path:
    for d in ("skills/_shared", "skills/publish", "skills/index", "contracts"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "skills/_shared/output-guide.md").write_text(guide if guide is not None else guide_text())
    (tmp_path / "skills/publish/SKILL.md").write_text(publish if publish is not None else PUBLISH_STUB)
    (tmp_path / "skills/index/SKILL.md").write_text(index if index is not None else INDEX_STUB)
    (tmp_path / csd.CONTRACT_REL).write_text(json.dumps(contract if contract is not None else CONTRACT))
    (tmp_path / csd.REF_REL).write_text(ref + "\n")
    return tmp_path


def errors_of(root: Path) -> list[str]:
    return csd.run_check(root)[0]


# --- rendering ---


class TestRendering:
    def test_rows_carry_every_column_in_the_contracts_order(self):
        rows = csd.render_rows(CONTRACT["statuses"])
        assert rows[:2] == list(csd.TABLE_HEADER)
        assert rows[2] == ("| knowledge | `current`, `stale`, `superseded`, `archived` | `superseded`, `archived` "
                           "| `current` | `active` → `current`; `draft` → use `maturity: draft` |")
        assert rows[3].endswith("| `draft` | — |")

    def test_legacy_cells_keep_the_house_format(self):
        """Mappings render as §3 always wrote them: a status in backticks, a hint as `use <code>`."""
        legacy = csd._legacy_cell({"active": "current", "draft": "use maturity: draft"})
        assert legacy == "`active` → `current`; `draft` → use `maturity: draft`"
        assert csd._legacy_cell({}) == "—"


# --- the gate ---


class TestRunCheck:
    def test_a_rendered_copy_passes(self, tmp_path):
        assert csd.run_check(make_repo(tmp_path)) == ([], [], [])

    def test_a_hand_edited_status_fails_naming_the_type(self, tmp_path):
        rows = csd.render_rows(CONTRACT["statuses"])
        rows[3] = rows[3].replace("`active`, ", "")
        errors = errors_of(make_repo(tmp_path, guide=guide_text(rows=rows)))
        assert any("not contracts/claudron.json's statuses" in e for e in errors)
        assert any("type 'plan'" in e for e in errors)

    def test_a_type_the_contract_adds_fails_until_re_rendered(self, tmp_path):
        bigger = json.loads(json.dumps(CONTRACT))
        bigger["statuses"]["entity"] = {**CONTRACT["statuses"]["knowledge"]}
        errors = errors_of(make_repo(tmp_path, contract=bigger))
        assert any("type 'entity': in the contract, missing from §3" in e for e in errors)

    def test_a_type_only_in_the_copy_fails(self, tmp_path):
        rows = csd.render_rows(CONTRACT["statuses"]) + ["| audit | `draft` | `completed` | `draft` | — |"]
        errors = errors_of(make_repo(tmp_path, guide=guide_text(rows=rows)))
        assert any("type 'audit': in §3, not in the contract" in e for e in errors)

    def test_reordered_rows_fail(self, tmp_path):
        rows = csd.render_rows(CONTRACT["statuses"])
        rows[2], rows[3] = rows[3], rows[2]
        errors = errors_of(make_repo(tmp_path, guide=guide_text(rows=rows)))
        assert any("row order" in e for e in errors)

    def test_formatting_alone_does_not_fail(self, tmp_path):
        """Backticks and spacing are presentation: the comparison is on normalized cells."""
        rows = [r.replace("`", "") for r in csd.render_rows(CONTRACT["statuses"])]
        assert errors_of(make_repo(tmp_path, guide=guide_text(rows=rows))) == []

    def test_a_stamp_for_another_release_fails(self, tmp_path):
        errors = errors_of(make_repo(tmp_path, guide=guide_text(ref="v0.8.0")))
        assert any("stamped v0.8.0" in e and "names v0.9.0" in e for e in errors)

    def test_a_missing_stamp_fails(self, tmp_path):
        errors = errors_of(make_repo(tmp_path, guide=guide_text(stamp=False)))
        assert any("stamp missing" in e for e in errors)

    def test_a_maturity_axis_unlike_the_contracts_fails(self, tmp_path):
        errors = errors_of(make_repo(tmp_path, guide=guide_text(maturity="draft | reviewed | canonical")))
        assert any("maturity axis" in e and "reviewed" in e for e in errors)

    def test_a_contract_without_statuses_fails(self, tmp_path):
        errors = errors_of(make_repo(tmp_path, contract={"contract_version": 1}))
        assert any("no `statuses`/`maturity`" in e for e in errors)

    def test_publish_restating_enums_fails(self, tmp_path):
        restated = PUBLISH_STUB + "\n| plan | draft, active, completed, superseded |\n"
        errors = errors_of(make_repo(tmp_path, publish=restated))
        assert any("skills/publish/SKILL.md" in e and "inline status-enum" in e for e in errors)

    def test_a_missing_pointer_fails(self, tmp_path):
        errors = errors_of(make_repo(tmp_path, index="# Index\n\nNo pointer anywhere.\n"))
        assert any("skills/index/SKILL.md" in e and "no pointer" in e for e in errors)


class TestWrite:
    def test_it_re_renders_a_stale_table_and_stamp(self, tmp_path):
        bigger = json.loads(json.dumps(CONTRACT))
        bigger["statuses"]["entity"] = {**CONTRACT["statuses"]["knowledge"]}
        root = make_repo(tmp_path, guide=guide_text(ref="v0.8.0"), contract=bigger, ref="v0.10.0")
        assert errors_of(root) != []
        assert csd.write(root) == []
        assert errors_of(root) == []
        text = (root / csd.OUTPUT_GUIDE_REL).read_text()
        assert "@ `v0.10.0`" in text and "| entity |" in text
        assert text.endswith("## 4. House Style\n")  # the rest of the guide is untouched

    def test_it_is_a_no_op_on_a_rendered_copy(self, tmp_path):
        root = make_repo(tmp_path)
        before = (root / csd.OUTPUT_GUIDE_REL).read_text()
        assert csd.write(root) == []
        assert (root / csd.OUTPUT_GUIDE_REL).read_text() == before

    def test_it_writes_nothing_without_a_marked_table(self, tmp_path):
        guide = guide_text().replace(csd.TABLE_MARKER, "<!-- something else")
        root = make_repo(tmp_path, guide=guide)
        assert any("no table follows" in e for e in csd.write(root))
        assert (root / csd.OUTPUT_GUIDE_REL).read_text() == guide


class TestInlineEnumHeuristic:
    def test_old_style_enum_table_flagged(self):
        text = (
            "| Type | Valid statuses |\n"
            "|------|----------------|\n"
            "| `plan` | draft, active, completed, superseded |\n"
            "| `knowledge` | current, stale, superseded |\n"
        )
        msgs = csd.find_inline_enum_rows(text)
        assert len(msgs) == 2
        assert "['plan']" in msgs[0]

    def test_a_home_type_row_is_flagged_too(self):
        assert csd.find_inline_enum_rows("| entity | current, stale, superseded |\n") != []

    def test_vault_destination_map_not_flagged(self):
        assert csd.find_inline_enum_rows(PUBLISH_STUB) == []

    def test_sort_prose_line_not_flagged(self):
        assert csd.find_inline_enum_rows(INDEX_STUB) == []

    def test_two_token_audit_row_alone_is_a_documented_miss(self):
        assert csd.find_inline_enum_rows("| audit, review | draft, completed |\n") == []

    def test_field_keyed_enum_row_is_flagged(self):
        text = "| `status` | audit/review: `draft`\\|`completed`; plan: `draft`\\|`active`\\|`superseded` |\n"
        msgs = csd.find_inline_enum_rows(text)
        assert msgs and "status" in msgs[0]

    def test_exclude_marked_skips_the_rendered_table(self):
        text = guide_text()
        assert csd.find_inline_enum_rows(text, exclude_marked=True) == []
        assert csd.find_inline_enum_rows(text, exclude_marked=False) != []


class TestMaturityParsing:
    def test_prose_form(self):
        assert csd.parse_maturity("an optional `maturity: draft | verified | canonical` axis") == \
            ["draft", "verified", "canonical"]

    def test_escaped_table_cell_form(self):
        assert csd.parse_maturity("| `maturity` | `draft \\| verified \\| canonical` |") == \
            ["draft", "verified", "canonical"]

    def test_prose_without_enum_not_matched(self):
        assert csd.parse_maturity("maturity vocabularies are described elsewhere") is None


# --- the real repo ---


class TestRealRepoIsClean:
    def test_the_gate_passes_on_the_real_repo(self):
        assert csd.run_check(REPO_ROOT)[0] == []

    def test_the_real_stamp_is_the_pinned_release(self):
        text = (REPO_ROOT / csd.OUTPUT_GUIDE_REL).read_text(encoding="utf-8")
        assert csd.parse_stamp(text) == (REPO_ROOT / csd.REF_REL).read_text().strip()

    def test_the_real_pointer_files_stay_clean(self):
        for rel in csd.POINTER_FILES_REL + (csd.OUTPUT_GUIDE_REL,):
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            assert csd.find_inline_enum_rows(text, exclude_marked=rel == csd.OUTPUT_GUIDE_REL) == []


class TestValidatorWiring:
    def test_validate_skills_wires_the_gate(self):
        src = (REPO_ROOT / "scripts" / "validate-skills.py").read_text(encoding="utf-8")
        assert "from check_schema_drift import run_check" in src
        assert "run_schema_drift_check(" in src
        assert '"schema-drift"' in src

    def test_validate_skills_executes_the_gate(self):
        import subprocess

        proc = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "validate-skills.py")],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stdout + proc.stderr
