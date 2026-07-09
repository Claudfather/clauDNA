"""Tests for the schema-drift gate (#199, epic #197 P2).

output-guide §3 is a stamped rendered copy of Claudron SCHEMA.md and the
repo's only type/status enum table; publish/index point at it. The gate:
offline it verifies the stamp + the three-way single-table invariant; online
it diffs the rendered copy against the SSOT at the stamped ref (mismatch =
failure: the copy was hand-edited) and against upstream HEAD (mismatch =
warning: update available). Network failure always degrades to a note.

All network here is faked via injected fetchers — no test touches the wire.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_schema_drift as csd

# --- fixtures ---

STATUS_ROWS = """\
| knowledge | `current`, `stale`, `superseded`, `archived` | `superseded`, `archived` | `active` → `current`; `draft` → use `maturity: draft` |
| decision | `draft`, `ratified`, `superseded`, `archived` | `ratified`, `superseded`, `archived` | — |
| runbook | `current`, `stale`, `superseded`, `archived` | `superseded`, `archived` | `active` → `current`; `draft` → use `maturity: draft` |
| plan | `draft`, `active`, `completed`, `superseded`, `archived` | `completed`, `superseded`, `archived` | — |
| audit | `draft`, `completed`, `archived` | `completed`, `archived` | — |
| review | `draft`, `completed`, `archived` | `completed`, `archived` | — |"""

# Structurally mirrors the real SCHEMA.md: prose axis line whose enum the
# maturity regex must NOT pick up from (letters in the gap), the optional-
# fields table row with escaped pipes (which it must), doc-parity marker.
def upstream_text(rows: str = STATUS_ROWS, maturity: str = r"`draft \| verified \| canonical`") -> str:
    return f"""# Claudron Note Schema — v1

- **`maturity`** — the **trust axis**. Describes curation; absent means unrated.

## Frontmatter fields

| Field | Type | Meaning |
|---|---|---|
| `aliases` | list | Alternate titles |
| `maturity` | {maturity} | Trust axis (see above) |

## Status vocabulary (per type)

<!-- doc-parity: STATUS_TABLE -->
| type | canonical | terminal | accepted legacy → mapping |
|---|---|---|---|
{rows}

Notes on the vocabulary follow.
"""


def guide_text(sha: str = "abc1234", rows: str = STATUS_ROWS, stamp_line: str | None = None) -> str:
    stamp = stamp_line if stamp_line is not None else (
        f"> **SSOT: [Claudron `SCHEMA.md`](https://github.com/Claudfather/Claudron/blob/main/SCHEMA.md).** "
        f"Rendered from [Claudfather/Claudron `SCHEMA.md`](https://github.com/Claudfather/Claudron/blob/{sha}/SCHEMA.md) "
        f"@ `{sha}` (2026-07-08) — adds an optional `maturity: draft | verified | canonical` trust axis."
    )
    return f"""# Output Guide

## 3. The Publishable Doc — Frontmatter

{stamp}

| Field | Rule |
|-------|------|
| `type` | One of the note types in the vocabulary table below. |
| `status` | Valid for the `type` per the vocabulary table below. |

<!-- schema-drift: STATUS_TABLE — rendered copy; do not hand-edit -->
| type | canonical | terminal | accepted legacy → mapping |
|---|---|---|---|
{rows}

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


def make_repo(tmp_path, *, guide: str | None = None, publish: str | None = None, index: str | None = None) -> Path:
    (tmp_path / "skills/_shared").mkdir(parents=True)
    (tmp_path / "skills/publish").mkdir(parents=True)
    (tmp_path / "skills/index").mkdir(parents=True)
    (tmp_path / "skills/_shared/output-guide.md").write_text(guide if guide is not None else guide_text())
    (tmp_path / "skills/publish/SKILL.md").write_text(publish if publish is not None else PUBLISH_STUB)
    (tmp_path / "skills/index/SKILL.md").write_text(index if index is not None else INDEX_STUB)
    return tmp_path


def fetch_from(mapping: dict):
    """Fake fetcher: mapping of ref -> SCHEMA.md text (missing ref = network failure)."""
    return lambda ref: mapping.get(ref)


# --- stamp parsing ---


class TestStampParsing:
    def test_linked_form(self):
        text = guide_text(sha="bb84ee3")
        assert csd.parse_stamp(text) == ("bb84ee3", "2026-07-08")

    def test_plain_form(self):
        text = "Rendered from Claudfather/Claudron SCHEMA.md @ bb84ee3ab9325c3a49c4f0274069c29eb2270768 (2026-07-08)"
        sha, date = csd.parse_stamp(text)
        assert sha == "bb84ee3ab9325c3a49c4f0274069c29eb2270768"
        assert date == "2026-07-08"

    def test_missing_date_rejected(self):
        assert csd.parse_stamp("Rendered from Claudfather/Claudron SCHEMA.md @ bb84ee3") is None

    def test_no_stamp(self):
        assert csd.parse_stamp("no stamp here") is None


# --- maturity parsing ---


class TestMaturityParsing:
    def test_prose_form(self):
        assert csd.parse_maturity("an optional `maturity: draft | verified | canonical` trust axis") == [
            "draft",
            "verified",
            "canonical",
        ]

    def test_escaped_table_cell_form(self):
        assert csd.parse_maturity(r"| `maturity` | `draft \| verified \| canonical` | Trust axis |") == [
            "draft",
            "verified",
            "canonical",
        ]

    def test_prose_without_enum_not_matched(self):
        # "maturity vocabularies" / "maturity: draft`," must not produce an enum.
        assert csd.parse_maturity("status and maturity vocabularies, wikilink resolution") is None
        assert csd.parse_maturity("enter as `maturity: draft`, humans promote") is None

    def test_upstream_fixture_picks_table_row(self):
        assert csd.parse_maturity(upstream_text()) == ["draft", "verified", "canonical"]


# --- vocab parsing ---


class TestVocabParsing:
    def test_rendered_parses_all_types_in_order(self):
        vocab, errors = csd.parse_rendered_vocab(guide_text())
        assert errors == []
        assert list(vocab["types"]) == ["knowledge", "decision", "runbook", "plan", "audit", "review"]
        assert vocab["types"]["plan"]["canonical"] == ["draft", "active", "completed", "superseded", "archived"]
        assert vocab["types"]["decision"]["terminal"] == ["ratified", "superseded", "archived"]
        assert vocab["types"]["knowledge"]["legacy"] == "active → current; draft → use maturity: draft"
        assert vocab["types"]["plan"]["legacy"] == ""
        assert vocab["maturity"] == ["draft", "verified", "canonical"]

    def test_missing_marker_errors(self):
        text = guide_text().replace("schema-drift: STATUS_TABLE", "no-marker-here")
        vocab, errors = csd.parse_rendered_vocab(text)
        assert vocab is None
        assert any("STATUS_TABLE marker not found" in e for e in errors)

    def test_marker_without_table_errors(self):
        text = "<!-- schema-drift: STATUS_TABLE -->\n\nno table follows\n"
        vocab, errors = csd.parse_rendered_vocab(text)
        assert vocab is None
        assert any("no table follows" in e for e in errors)

    def test_upstream_via_marker(self):
        vocab = csd.parse_upstream_vocab(upstream_text())
        assert vocab is not None
        assert set(vocab["types"]) == {"knowledge", "decision", "runbook", "plan", "audit", "review"}

    def test_upstream_fallback_header_when_marker_absent(self):
        text = upstream_text().replace("<!-- doc-parity: STATUS_TABLE -->\n", "")
        vocab = csd.parse_upstream_vocab(text)
        assert vocab is not None
        assert vocab["types"]["runbook"]["canonical"] == ["current", "stale", "superseded", "archived"]

    def test_upstream_unlocatable_returns_none(self):
        assert csd.parse_upstream_vocab("# A doc with no vocabulary table at all\n") is None


# --- diffing ---


class TestDiffVocab:
    def test_equal_vocab_no_diffs(self):
        rendered, errors = csd.parse_rendered_vocab(guide_text())
        assert errors == []
        upstream = csd.parse_upstream_vocab(upstream_text())
        assert csd.diff_vocab(rendered, upstream) == []

    def test_edited_canonical_detected(self):
        edited = STATUS_ROWS.replace(
            "| decision | `draft`, `ratified`, `superseded`, `archived` |",
            "| decision | `draft`, `ratified`, `superseded` |",
        )
        rendered, _ = csd.parse_rendered_vocab(guide_text(rows=edited))
        upstream = csd.parse_upstream_vocab(upstream_text())
        diffs = csd.diff_vocab(rendered, upstream)
        assert len(diffs) == 1
        assert "decision" in diffs[0] and "canonical" in diffs[0]

    def test_missing_type_detected(self):
        five_rows = "\n".join(STATUS_ROWS.splitlines()[:-1])  # drop review
        rendered, _ = csd.parse_rendered_vocab(guide_text(rows=five_rows))
        upstream = csd.parse_upstream_vocab(upstream_text())
        diffs = csd.diff_vocab(rendered, upstream)
        assert diffs == ["type 'review': present upstream, missing from the rendered copy"]

    def test_legacy_mapping_diff_detected(self):
        edited = STATUS_ROWS.replace("`active` → `current`; `draft` → use `maturity: draft` |\n| decision", "— |\n| decision")
        rendered, _ = csd.parse_rendered_vocab(guide_text(rows=edited))
        upstream = csd.parse_upstream_vocab(upstream_text())
        assert any("'knowledge' legacy" in d for d in csd.diff_vocab(rendered, upstream))

    def test_maturity_diff_detected(self):
        rendered, _ = csd.parse_rendered_vocab(guide_text())
        upstream = csd.parse_upstream_vocab(upstream_text(maturity=r"`draft \| verified \| canonical \| contested`"))
        assert any("maturity axis" in d for d in csd.diff_vocab(rendered, upstream))


# --- inline-enum heuristic ---


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

    def test_vault_destination_map_not_flagged(self):
        # The real publish Step 2 routing table: type names in the first cell,
        # but fewer than 3 status tokens — must stay clean.
        assert csd.find_inline_enum_rows(PUBLISH_STUB) == []

    def test_sort_prose_line_not_flagged(self):
        # index Step 3's sort heuristic is a list item, not a table row.
        assert csd.find_inline_enum_rows(INDEX_STUB) == []

    def test_two_token_audit_row_alone_is_a_documented_miss(self):
        text = "| audit, review | draft, completed |\n"
        assert csd.find_inline_enum_rows(text) == []

    def test_exclude_marked_skips_the_rendered_table(self):
        text = guide_text()
        assert csd.find_inline_enum_rows(text, exclude_marked=True) == []
        # …and without the exclusion the rendered table's own rows trip it.
        assert csd.find_inline_enum_rows(text, exclude_marked=False) != []


# --- run_check: offline ---


class TestRunCheckOffline:
    def test_conformant_repo_passes(self, tmp_path):
        root = make_repo(tmp_path)
        errors, warnings, notes = csd.run_check(root, offline=True)
        assert errors == []
        assert warnings == []
        assert any("offline mode" in n for n in notes)

    def test_missing_stamp_errors(self, tmp_path):
        root = make_repo(tmp_path, guide=guide_text(stamp_line="> **SSOT:** SCHEMA.md, unstamped."))
        errors, _, _ = csd.run_check(root, offline=True)
        assert any("source stamp missing" in e for e in errors)

    def test_publish_restating_enums_errors(self, tmp_path):
        restated = PUBLISH_STUB + "\n| plan | draft, active, completed, superseded |\n"
        root = make_repo(tmp_path, publish=restated)
        errors, _, _ = csd.run_check(root, offline=True)
        assert any("skills/publish/SKILL.md" in e and "inline status-enum" in e for e in errors)

    def test_missing_pointer_errors(self, tmp_path):
        root = make_repo(tmp_path, index="# Index\n\nNo pointer anywhere.\n")
        errors, _, _ = csd.run_check(root, offline=True)
        assert any("skills/index/SKILL.md" in e and "no pointer" in e for e in errors)

    def test_env_var_forces_offline(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SCHEMA_DRIFT_OFFLINE", "1")
        root = make_repo(tmp_path)

        def explode(ref):
            raise AssertionError("network must not be attempted with SCHEMA_DRIFT_OFFLINE=1")

        errors, _, notes = csd.run_check(root, fetch=explode)
        assert errors == []
        assert any("offline mode" in n for n in notes)


# --- run_check: online (faked network) ---


class TestRunCheckOnline:
    def test_matching_copy_passes_with_note(self, tmp_path):
        root = make_repo(tmp_path, guide=guide_text(sha="abc1234"))
        fetch = fetch_from({"abc1234": upstream_text(), "main": upstream_text()})
        errors, warnings, notes = csd.run_check(root, offline=False, fetch=fetch)
        assert errors == []
        assert warnings == []
        assert any("online check passed" in n for n in notes)

    def test_hand_edited_copy_fails_at_stamped_ref(self, tmp_path):
        edited = STATUS_ROWS.replace("`draft`, `ratified`, `superseded`, `archived`", "`draft`, `ratified`, `superseded`")
        root = make_repo(tmp_path, guide=guide_text(sha="abc1234", rows=edited))
        fetch = fetch_from({"abc1234": upstream_text(), "main": upstream_text()})
        errors, _, _ = csd.run_check(root, offline=False, fetch=fetch)
        assert any("does not match" in e and "stamped ref abc1234" in e for e in errors)
        assert any("decision" in e for e in errors)

    def test_honest_stamp_bump_passes(self, tmp_path):
        # The issue's test plan: hand-edit fails (above); re-rendering the new
        # vocabulary WITH a fresh stamp pointing at the commit that contains it
        # passes — no checker edits needed.
        new_rows = STATUS_ROWS.replace("`draft`, `ratified`, `superseded`, `archived`", "`draft`, `proposed`, `ratified`, `superseded`, `archived`")
        root = make_repo(tmp_path, guide=guide_text(sha="def5678", rows=new_rows))
        fetch = fetch_from({"def5678": upstream_text(rows=new_rows), "main": upstream_text(rows=new_rows)})
        errors, warnings, notes = csd.run_check(root, offline=False, fetch=fetch)
        assert errors == []
        assert warnings == []
        assert any("online check passed" in n for n in notes)

    def test_upstream_head_moved_warns_only(self, tmp_path):
        root = make_repo(tmp_path, guide=guide_text(sha="abc1234"))
        newer = upstream_text(rows=STATUS_ROWS.replace("`draft`, `completed`, `archived` | `completed`, `archived` | — |", "`draft`, `completed`, `archived`, `parked` | `completed`, `archived` | — |"))
        fetch = fetch_from({"abc1234": upstream_text(), "main": newer})
        errors, warnings, _ = csd.run_check(root, offline=False, fetch=fetch)
        assert errors == []
        assert any("update available" in w for w in warnings)

    def test_network_failure_degrades_to_note(self, tmp_path):
        root = make_repo(tmp_path, guide=guide_text(sha="abc1234"))
        errors, warnings, notes = csd.run_check(root, offline=False, fetch=fetch_from({}))
        assert errors == []
        assert warnings == []
        assert any("network unavailable" in n for n in notes)

    def test_head_fetch_failure_after_stamp_match_is_silent(self, tmp_path):
        root = make_repo(tmp_path, guide=guide_text(sha="abc1234"))
        fetch = fetch_from({"abc1234": upstream_text()})  # no "main"
        errors, warnings, notes = csd.run_check(root, offline=False, fetch=fetch)
        assert errors == []
        assert warnings == []
        assert any("online check passed" in n for n in notes)

    def test_structural_errors_skip_online(self, tmp_path):
        root = make_repo(tmp_path, index="# Index\n\nNo pointer.\n")

        def explode(ref):
            raise AssertionError("online comparison must not run when structural checks fail")

        errors, _, _ = csd.run_check(root, offline=False, fetch=explode)
        assert errors != []


# --- the real repo (hermetic backstop, mirrors TestRepoIsCleanOfRemovedNames) ---


class TestRealRepoIsClean:
    def test_offline_gate_passes_on_the_real_repo(self):
        errors, warnings, notes = csd.run_check(REPO_ROOT, offline=True)
        assert errors == [], "\n".join(errors)

    def test_real_stamp_parses(self):
        # Deliberately no assertion on the real table's VALUES: pinning the
        # vocabulary here would make an honest re-render (new stamp, new
        # values) fail pytest — the property the gate is designed to preserve.
        # Online drift protection runs in the validate-skills CI job instead.
        text = (REPO_ROOT / csd.OUTPUT_GUIDE_REL).read_text()
        stamp = csd.parse_stamp(text)
        assert stamp is not None
        sha, date = stamp
        assert 7 <= len(sha) <= 40
