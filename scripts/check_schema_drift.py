#!/usr/bin/env python3
"""Schema-drift gate: output-guide §3 must be an honest rendered copy of Claudron SCHEMA.md.

clauDNA's frontmatter vocabulary (note types, per-type status enums + legacy
mappings, the maturity axis) is a *rendered copy* of the SSOT —
Claudfather/Claudron SCHEMA.md — stamped with the source commit it was
rendered from (#199, epic #197 P2). This gate keeps the copy honest.

Offline checks (always run; the default posture — network is never required):
  1. The source stamp exists and parses:
     ``Rendered from Claudfather/Claudron SCHEMA.md @ <sha> (<YYYY-MM-DD>)``.
  2. The rendered vocabulary (the table behind the ``schema-drift:
     STATUS_TABLE`` marker, plus the maturity axis) parses.
  3. Three-way single-table invariant: output-guide §3 is the ONLY status
     enum table — publish Step 1a and index Step 2 must point at §3 and must
     not restate per-type status enums.

Online checks (attempted opportunistically; ANY fetch failure degrades to a
note, never an error — CI must not flake when the network is down):
  4. Fetch SCHEMA.md at the STAMPED ref and diff the vocabulary.
     Mismatch = FAILURE: content at an immutable commit cannot change, so the
     rendered copy was hand-edited. Re-render from the SSOT and restamp.
  5. Fetch SCHEMA.md at the SSOT's default branch and diff against the
     rendered copy. Mismatch = WARNING only: an update is available upstream;
     re-render + restamp when convenient.

The checker deliberately pins NO vocabulary values for validation: an honest
re-render (new stamp, new values) must pass without touching this script.
The only pinned token sets (TYPE_NAMES / STATUS_TOKENS) power the
inline-enum-table *detection heuristic* in publish/index — degrading only
detection, never blocking a re-render.

Env:
  SCHEMA_DRIFT_OFFLINE=1   skip all network attempts (offline checks only).

Run standalone: ``python3 scripts/check_schema_drift.py [--offline]``.
Wired into scripts/validate-skills.py, where errors are ALWAYS-BLOCKING
(never demoted by CI touched-set scoping): main is clean of drift after this
lands, and vocabulary at an immutable stamped ref cannot change on its own,
so any failure was introduced by the change under test. (§3 lives in
skills/_shared/, which already triggers full-repo validation when touched.)
"""

from __future__ import annotations

import os
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SSOT_REPO = "Claudfather/Claudron"
SSOT_FILE = "SCHEMA.md"
SSOT_HEAD_REF = "main"
FETCH_TIMEOUT_SECONDS = 5

OUTPUT_GUIDE_REL = "skills/_shared/output-guide.md"
# The consumers that must point at §3 instead of restating the vocabulary.
POINTER_FILES_REL = ("skills/publish/SKILL.md", "skills/index/SKILL.md")

TABLE_MARKER = "<!-- schema-drift: STATUS_TABLE"  # ours, in output-guide §3
UPSTREAM_MARKER = "<!-- doc-parity: STATUS_TABLE"  # SCHEMA.md's machine-checked anchor

STAMP_RE = re.compile(
    r"Rendered from\s+\[?Claudfather/Claudron\s+`?SCHEMA\.md`?\]?(?:\([^)\s]*\))?"
    r"\s+@\s+`?([0-9a-fA-F]{7,40})`?\s+\((\d{4}-\d{2}-\d{2})\)"
)

# "output-guide … §3" (or "Section 3") within a line = a pointer to the SSOT table.
POINTER_RE = re.compile(r"output-guide[^\n]{0,160}(?:§\s*3|Section\s+3)")

# Captures a pipe-separated enum after the word "maturity", tolerating both the
# escaped table-cell form (`draft \| verified \| canonical`) and plain prose
# (`draft | verified | canonical`). The gap between "maturity" and the enum may
# not contain letters, so prose like "maturity vocabularies" never matches.
MATURITY_RE = re.compile(r"maturity[^A-Za-z\n]{0,24}?((?:[a-z]+[ \t]*\\?\|[ \t]*){1,8}[a-z]+)")

# Detection-heuristic vocabulary (see module docstring — never used to validate docs).
TYPE_NAMES = {"knowledge", "decision", "runbook", "plan", "audit", "review"}
STATUS_TOKENS = {"draft", "active", "completed", "superseded", "archived", "current", "stale", "ratified"}

_DIVIDER_RE = re.compile(r"^[\s|:\-]+$")


# --- markdown-table plumbing ---


def _split_cells(line: str) -> list[str]:
    """Split a markdown table row into cells, honoring escaped pipes."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    s = s.replace("\\|", "\x00")
    return [c.replace("\x00", "|") for c in s.split("|")]


def _norm(cell: str) -> str:
    """Normalize a cell for comparison: strip backticks, collapse whitespace."""
    return re.sub(r"\s+", " ", cell.replace("`", "")).strip()


def _norm_legacy(cell: str) -> str:
    """Normalize a legacy-mapping cell; em/en-dash placeholders mean 'none'."""
    v = _norm(cell)
    return "" if v in {"—", "–", "-"} else v


def _find_marker(lines: list[str], marker: str) -> int | None:
    return next((i for i, line in enumerate(lines) if marker in line), None)


def _extract_table(lines: list[str], start: int) -> tuple[list[str], int, int] | None:
    """First contiguous run of '|' lines at/after `start` (leading blanks allowed).

    Returns (rows, first_line_idx, last_line_idx) or None.
    """
    i = start
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or not lines[i].lstrip().startswith("|"):
        return None
    first = i
    rows: list[str] = []
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        rows.append(lines[i])
        i += 1
    return rows, first, i - 1


def _parse_status_rows(rows: list[str], source: str) -> tuple[dict[str, dict], list[str]]:
    """Parse a per-type status table into {type: {canonical, terminal, legacy}}."""
    errors: list[str] = []
    if len(rows) < 3:
        return {}, [f"{source}: status table too short to hold a header, divider, and rows"]
    header = [_norm(c).lower() for c in _split_cells(rows[0])]
    if len(header) < 4 or "type" not in header[0] or "canonical" not in header[1]:
        errors.append(f"{source}: unexpected status-table header {header!r} (expected type|canonical|terminal|legacy)")
    if not _DIVIDER_RE.match(rows[1].strip()):
        errors.append(f"{source}: status-table divider row missing")
    types: dict[str, dict] = {}
    for row in rows[2:]:
        cells = _split_cells(row)
        if len(cells) < 4:
            errors.append(f"{source}: status-table row has {len(cells)} cells, expected 4: {row.strip()!r}")
            continue
        name = _norm(cells[0]).lower()
        if name in types:
            errors.append(f"{source}: duplicate type row {name!r}")
            continue
        types[name] = {
            "canonical": [v.strip() for v in _norm(cells[1]).split(",") if v.strip()],
            "terminal": [v.strip() for v in _norm(cells[2]).split(",") if v.strip()],
            "legacy": _norm_legacy(cells[3]),
        }
    if not types and not errors:
        errors.append(f"{source}: status table has no data rows")
    return types, errors


def parse_stamp(text: str) -> tuple[str, str] | None:
    """Return (sha, date) from the §3 source stamp, or None."""
    m = STAMP_RE.search(text)
    return (m.group(1), m.group(2)) if m else None


def parse_maturity(text: str) -> list[str] | None:
    """Return the maturity enum values, or None if not found."""
    m = MATURITY_RE.search(text)
    if not m:
        return None
    return [v.strip() for v in re.split(r"\s*\\?\|\s*", m.group(1)) if v.strip()]


def parse_rendered_vocab(text: str) -> tuple[dict | None, list[str]]:
    """Parse output-guide §3's rendered vocabulary. Returns (vocab, errors)."""
    lines = text.splitlines()
    m_idx = _find_marker(lines, TABLE_MARKER)
    if m_idx is None:
        return None, [
            f"{OUTPUT_GUIDE_REL}: STATUS_TABLE marker not found "
            f"(expected an HTML comment starting {TABLE_MARKER!r} heading the rendered table)"
        ]
    ext = _extract_table(lines, m_idx + 1)
    if ext is None:
        return None, [f"{OUTPUT_GUIDE_REL}: no table follows the STATUS_TABLE marker"]
    types, errors = _parse_status_rows(ext[0], source=OUTPUT_GUIDE_REL)
    maturity = parse_maturity(text)
    if maturity is None:
        errors.append(f"{OUTPUT_GUIDE_REL}: maturity axis (draft | verified | canonical form) not found in §3")
    if errors:
        return None, errors
    return {"types": types, "maturity": maturity}, []


def parse_upstream_vocab(text: str) -> dict | None:
    """Parse SCHEMA.md's status vocabulary. Returns vocab or None if unlocatable."""
    lines = text.splitlines()
    m_idx = _find_marker(lines, UPSTREAM_MARKER)
    if m_idx is not None:
        ext = _extract_table(lines, m_idx + 1)
    else:  # fallback: locate the table by its header row
        header_idx = next(
            (i for i, line in enumerate(lines) if re.match(r"^\|\s*type\s*\|\s*canonical\s*\|", line, re.I)),
            None,
        )
        ext = _extract_table(lines, header_idx) if header_idx is not None else None
    if ext is None:
        return None
    types, errors = _parse_status_rows(ext[0], source=SSOT_FILE)
    if errors or not types:
        return None
    return {"types": types, "maturity": parse_maturity(text)}


def diff_vocab(rendered: dict, upstream: dict) -> list[str]:
    """Human-readable differences between two parsed vocabularies (empty = equal)."""
    diffs: list[str] = []
    ours, theirs = rendered["types"], upstream["types"]
    for name in sorted(set(ours) | set(theirs)):
        if name not in ours:
            diffs.append(f"type '{name}': present upstream, missing from the rendered copy")
        elif name not in theirs:
            diffs.append(f"type '{name}': in the rendered copy, absent upstream")
        else:
            for field in ("canonical", "terminal", "legacy"):
                if ours[name][field] != theirs[name][field]:
                    diffs.append(
                        f"type '{name}' {field}: rendered {ours[name][field]!r} != upstream {theirs[name][field]!r}"
                    )
    if rendered.get("maturity") != upstream.get("maturity"):
        diffs.append(f"maturity axis: rendered {rendered.get('maturity')!r} != upstream {upstream.get('maturity')!r}")
    return diffs


def _marked_table_span(lines: list[str], marker: str) -> tuple[int, int] | None:
    m_idx = _find_marker(lines, marker)
    if m_idx is None:
        return None
    ext = _extract_table(lines, m_idx + 1)
    return (m_idx, ext[2]) if ext else None


def find_inline_enum_rows(text: str, *, exclude_marked: bool = False) -> list[str]:
    """Flag table rows that restate a per-type status enum.

    Heuristic: a table row whose first cell is exactly one or more note-type
    names and whose remaining cells mention >=3 distinct status tokens. Rows
    like the vault destination map (`| plan | shared/planning/active/ … |`)
    stay clean (<3 tokens); a restated enum table trips on its 3+-value rows
    (an audit/review-only 2-value row alone would slip through — accepted:
    real enum tables carry the richer sibling rows).
    """
    lines = text.splitlines()
    excluded: set[int] = set()
    if exclude_marked:
        span = _marked_table_span(lines, TABLE_MARKER)
        if span:
            excluded = set(range(span[0], span[1] + 1))
    msgs: list[str] = []
    for i, line in enumerate(lines):
        if i in excluded or not line.lstrip().startswith("|"):
            continue
        cells = _split_cells(line)
        if len(cells) < 2:
            continue
        first_types = {t.strip() for t in _norm(cells[0]).lower().split(",") if t.strip()}
        if not first_types or not first_types <= TYPE_NAMES:
            continue
        rest = _norm(" ".join(cells[1:])).lower()
        hits = {tok for tok in STATUS_TOKENS if re.search(rf"\b{tok}\b", rest)}
        if len(hits) >= 3:
            msgs.append(
                f"line {i + 1}: inline status-enum table row for type(s) {sorted(first_types)} -- "
                f"the vocabulary lives only in {OUTPUT_GUIDE_REL} §3; point there instead of restating"
            )
    return msgs


# --- network ---


def fetch_schema_text(ref: str) -> str | None:
    """Fetch SCHEMA.md at `ref` from the SSOT repo; None on ANY failure (offline posture)."""
    url = f"https://raw.githubusercontent.com/{SSOT_REPO}/{ref}/{SSOT_FILE}"
    req = urllib.request.Request(url, headers={"User-Agent": "claudna-schema-drift-check"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return None


# --- the gate ---


def run_check(
    repo_root: Path = REPO_ROOT,
    *,
    offline: bool | None = None,
    fetch=fetch_schema_text,
) -> tuple[list[str], list[str], list[str]]:
    """Run the schema-drift gate. Returns (errors, warnings, notes).

    offline=None reads SCHEMA_DRIFT_OFFLINE from the environment; the online
    comparison runs only when the offline (structural) checks pass.
    """
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    if offline is None:
        offline = os.environ.get("SCHEMA_DRIFT_OFFLINE") == "1"

    guide_path = repo_root / OUTPUT_GUIDE_REL
    if not guide_path.is_file():
        return [f"{OUTPUT_GUIDE_REL}: file missing"], warnings, notes
    guide_text = guide_path.read_text()

    stamp = parse_stamp(guide_text)
    if stamp is None:
        errors.append(
            f"{OUTPUT_GUIDE_REL}: §3 source stamp missing or unparseable -- expected "
            "'Rendered from Claudfather/Claudron SCHEMA.md @ <sha> (<YYYY-MM-DD>)' in the banner"
        )
    rendered, parse_errors = parse_rendered_vocab(guide_text)
    errors.extend(parse_errors)

    # Single-table invariant: no enum rows outside the marked table…
    errors.extend(f"{OUTPUT_GUIDE_REL}: {m}" for m in find_inline_enum_rows(guide_text, exclude_marked=True))
    # …and the consumers point at §3 instead of restating it.
    for rel in POINTER_FILES_REL:
        path = repo_root / rel
        if not path.is_file():
            errors.append(f"{rel}: file missing")
            continue
        text = path.read_text()
        if not POINTER_RE.search(text):
            errors.append(f"{rel}: no pointer to the output-guide §3 vocabulary table (expected 'output-guide … §3')")
        errors.extend(f"{rel}: {m}" for m in find_inline_enum_rows(text))

    if errors:
        return errors, warnings, notes  # structural breakage; online diff would be noise
    if offline:
        notes.append("offline mode -- online drift comparison skipped")
        return errors, warnings, notes

    sha = stamp[0]
    pinned_text = fetch(sha)
    if pinned_text is None:
        notes.append(f"network unavailable -- online drift comparison at stamped ref {sha} skipped (offline posture)")
        return errors, warnings, notes
    upstream = parse_upstream_vocab(pinned_text)
    if upstream is None:
        errors.append(
            f"{SSOT_FILE}@{sha}: status vocabulary table not found/parseable at the stamped ref -- "
            "if upstream restructured SCHEMA.md, re-render §3 and update this checker together"
        )
        return errors, warnings, notes
    diffs = diff_vocab(rendered, upstream)
    if diffs:
        errors.append(
            f"{OUTPUT_GUIDE_REL}: rendered vocabulary does not match {SSOT_FILE} at the stamped ref {sha} -- "
            "the copy was hand-edited; re-render from the SSOT (and restamp honestly if rendering a newer commit):"
        )
        errors.extend(f"  {d}" for d in diffs)
        return errors, warnings, notes
    notes.append(f"online check passed: rendered copy matches {SSOT_FILE}@{sha}")

    head_text = fetch(SSOT_HEAD_REF)
    if head_text is None:
        return errors, warnings, notes
    head = parse_upstream_vocab(head_text)
    if head is None:
        warnings.append(f"{SSOT_FILE}@{SSOT_HEAD_REF}: vocabulary table not parseable -- upstream restructured?")
        return errors, warnings, notes
    head_diffs = diff_vocab(rendered, head)
    if head_diffs:
        warnings.append(
            f"update available: {SSOT_FILE} vocabulary changed upstream since stamped ref {sha} -- "
            "re-render §3 + restamp when convenient (warning only):"
        )
        warnings.extend(f"  {d}" for d in head_diffs)
    return errors, warnings, notes


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check output-guide §3 against the Claudron SCHEMA.md SSOT.")
    parser.add_argument("--offline", action="store_true", help="skip network; structural checks only")
    args = parser.parse_args(argv)

    errors, warnings, notes = run_check(offline=True if args.offline else None)
    for n in notes:
        print(f"NOTE: {n}")
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        print(f"FAIL: schema-drift gate -- {len(errors)} error line(s)")
        for e in errors:
            print(f"  {e}")
        return 1
    print("OK: schema-drift gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
