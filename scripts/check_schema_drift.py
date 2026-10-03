#!/usr/bin/env python3
"""Schema-drift gate: output-guide §3 must be an honest rendered copy of Claudron's contract.

clauDNA's frontmatter vocabulary (note types, per-type status enums, default
status and legacy mappings, the maturity axis) is a *rendered copy* of
Claudron's: the ``statuses`` and ``maturity`` of ``contracts/claudron.json``,
the vendored ``claudron contract --json`` (CONTRIBUTING § The Claudron
contract). §3 carries a stamp naming the Claudron release it was rendered
from, which must be the release ``contracts/claudron.ref`` names.

Every check is offline (the copy is in the repo):
  1. The stamp parses and names the release ``contracts/claudron.ref`` names.
  2. The table behind the ``schema-drift: STATUS_TABLE`` marker, and the
     maturity axis, are exactly the contract's: every type, canonical and
     terminal statuses, default, legacy mappings.
  3. Single-table invariant: §3 is the ONLY status enum table; publish Step
     1a and index Step 2 point at §3 and never restate per-type enums.

``--write`` re-renders the table and the stamp from the contract, so a
Claudron release reaches §3 without a hand edit
(``scripts/sync_claudron_contract.py`` refreshes the contract first).

Run standalone: ``python3 scripts/check_schema_drift.py [--write]``. Wired into
scripts/validate-skills.py, where errors always block (never demoted by CI
touched-set scoping): the copy and the contract both live in this repo, so
any failure was introduced by the change under test.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CONTRACT_REL = "contracts/claudron.json"
REF_REL = "contracts/claudron.ref"
OUTPUT_GUIDE_REL = "skills/_shared/output-guide.md"
# The consumers that must point at §3 instead of restating the vocabulary.
POINTER_FILES_REL = ("skills/publish/SKILL.md", "skills/index/SKILL.md")

TABLE_MARKER = "<!-- schema-drift: STATUS_TABLE"
TABLE_HEADER = ("| type | canonical | terminal | default | accepted legacy → mapping |", "|---|---|---|---|---|")

#: The §3 stamp: ``rendered from Claudron's `claudron contract --json` @ `vX.Y.Z` ``.
STAMP_RE = re.compile(r"`claudron contract --json`\s+@\s+`(v\d+\.\d+\.\d+)`")

# "output-guide … §3" (or "Section 3") within a line = a pointer to the SSOT table.
POINTER_RE = re.compile(r"output-guide[^\n]{0,160}(?:§\s*3|Section\s+3)")

# Captures a pipe-separated enum after the word "maturity", tolerating both the
# escaped table-cell form (`draft \| verified \| canonical`) and plain prose
# (`draft | verified | canonical`). The gap between "maturity" and the enum may
# not contain letters, so prose like "maturity vocabularies" never matches.
MATURITY_RE = re.compile(r"maturity[^A-Za-z\n]{0,24}?((?:[a-z]+[ \t]*\\?\|[ \t]*){1,8}[a-z]+)")

# Detection-heuristic vocabulary for restated enum tables (never used to validate the copy).
TYPE_NAMES = {"knowledge", "decision", "runbook", "plan", "audit", "review",
              "entity", "concept", "person", "project", "practice"}
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


# --- the contract and its rendering ---


def load_contract(repo_root: Path) -> tuple[dict | None, str | None, list[str]]:
    """``(contract, ref, errors)`` from ``contracts/``."""
    errors: list[str] = []
    try:
        contract = json.loads((repo_root / CONTRACT_REL).read_text(encoding="utf-8"))
        if not (isinstance(contract.get("statuses"), dict) and isinstance(contract.get("maturity"), list)):
            errors.append(f"{CONTRACT_REL}: no `statuses`/`maturity` (a contract from before Claudron 0.9?)")
            contract = None
    except (OSError, ValueError) as exc:
        errors.append(f"{CONTRACT_REL}: unreadable: {exc}")
        contract = None
    try:
        ref = (repo_root / REF_REL).read_text(encoding="utf-8").strip()
    except OSError as exc:
        errors.append(f"{REF_REL}: unreadable: {exc}")
        ref = None
    return contract, ref, errors


def _legacy_cell(legacy: dict) -> str:
    """``{"active": "current", "draft": "use maturity: draft"}`` → the table's mapping cell."""
    def target(value: str) -> str:
        return f"use `{value[4:]}`" if value.startswith("use ") else f"`{value}`"

    return "; ".join(f"`{alias}` → {target(value)}" for alias, value in legacy.items()) or "—"


def render_rows(statuses: dict) -> list[str]:
    """The STATUS_TABLE rows (header included) for the contract's ``statuses``."""
    rows = list(TABLE_HEADER)
    for name, vocab in statuses.items():
        cells = (name, ", ".join(f"`{s}`" for s in vocab["canonical"]),
                 ", ".join(f"`{s}`" for s in vocab["terminal"]), f"`{vocab['default']}`",
                 _legacy_cell(vocab["legacy"]))
        rows.append("| " + " | ".join(cells) + " |")
    return rows


def _row_key(row: str) -> list[str]:
    return [_norm(c) for c in _split_cells(row)]


def diff_table(rendered: list[str], expected: list[str]) -> list[str]:
    """Differences between the table in §3 and the one the contract renders (empty = equal)."""
    if [_row_key(r) for r in rendered] == [_row_key(r) for r in expected]:
        return []
    ours = {_row_key(r)[0]: _row_key(r) for r in rendered[2:] if _split_cells(r)}
    theirs = {_row_key(r)[0]: _row_key(r) for r in expected[2:]}
    diffs = [f"type '{t}': in the contract, missing from §3" for t in theirs if t not in ours]
    diffs += [f"type '{t}': in §3, not in the contract" for t in ours if t not in theirs]
    diffs += [f"type '{t}': §3 has {ours[t][1:]!r}, the contract renders {theirs[t][1:]!r}"
              for t in theirs if t in ours and ours[t] != theirs[t]]
    if not diffs:
        diffs.append("the header or the row order differs from the rendering")
    return diffs


def parse_stamp(text: str) -> str | None:
    """The release §3's stamp names, or None."""
    m = STAMP_RE.search(text)
    return m.group(1) if m else None


def parse_maturity(text: str) -> list[str] | None:
    """Return the maturity enum values, or None if not found."""
    m = MATURITY_RE.search(text)
    if not m:
        return None
    return [v.strip() for v in re.split(r"\s*\\?\|\s*", m.group(1)) if v.strip()]


def _section3(text: str) -> str:
    """§3 onward, so a pre-§3 pipe-shaped phrase can't shadow the maturity axis."""
    sec3 = re.search(r"^## 3\..*$", text, re.M)
    return text[sec3.start():] if sec3 else text


def find_inline_enum_rows(text: str, *, exclude_marked: bool = False) -> list[str]:
    """Flag table rows that restate a per-type status enum.

    Heuristic: a table row whose first cell is exactly one or more note-type
    names — or a field name (`status`/`type`, the shape of a Field/Rule row
    restating the vocabulary) — and whose remaining cells mention >=3
    distinct status tokens. Rows like the vault destination map
    (`| plan | shared/planning/active/ … |`) stay clean (<3 tokens); a
    restated enum table trips on its 3+-value rows (an audit/review-only
    2-value row alone would slip through — accepted: real enum tables carry
    the richer sibling rows).
    """
    lines = text.splitlines()
    excluded: set[int] = set()
    if exclude_marked:
        m_idx = _find_marker(lines, TABLE_MARKER)
        ext = _extract_table(lines, m_idx + 1) if m_idx is not None else None
        if ext:
            excluded = set(range(m_idx, ext[2] + 1))
    msgs: list[str] = []
    for i, line in enumerate(lines):
        if i in excluded or not line.lstrip().startswith("|"):
            continue
        cells = _split_cells(line)
        if len(cells) < 2:
            continue
        first_types = {t.strip() for t in _norm(cells[0]).lower().split(",") if t.strip()}
        if not first_types or not (first_types <= TYPE_NAMES or first_types <= {"status", "type"}):
            continue
        rest = _norm(" ".join(cells[1:])).lower()
        hits = {tok for tok in STATUS_TOKENS if re.search(rf"\b{tok}\b", rest)}
        if len(hits) >= 3:
            msgs.append(
                f"line {i + 1}: inline status-enum table row keyed {sorted(first_types)} -- "
                f"the vocabulary lives only in {OUTPUT_GUIDE_REL} §3; point there instead of restating"
            )
    return msgs


# --- the gate ---


def run_check(repo_root: Path = REPO_ROOT, **_legacy: object) -> tuple[list[str], list[str], list[str]]:
    """Run the schema-drift gate. Returns (errors, warnings, notes); the gate is offline, so no warnings."""
    errors: list[str] = []
    guide_path = repo_root / OUTPUT_GUIDE_REL
    if not guide_path.is_file():
        return [f"{OUTPUT_GUIDE_REL}: file missing"], [], []
    guide_text = guide_path.read_text(encoding="utf-8")
    contract, ref, load_errors = load_contract(repo_root)
    errors.extend(load_errors)

    stamp = parse_stamp(guide_text)
    if stamp is None:
        errors.append(f"{OUTPUT_GUIDE_REL}: §3 stamp missing or unparseable -- expected "
                      "'`claudron contract --json` @ `vX.Y.Z`' in the banner")
    elif ref and stamp != ref:
        errors.append(f"{OUTPUT_GUIDE_REL}: §3 is stamped {stamp} but {REF_REL} names {ref} -- "
                      "re-render: python3 scripts/check_schema_drift.py --write")

    lines = guide_text.splitlines()
    m_idx = _find_marker(lines, TABLE_MARKER)
    ext = _extract_table(lines, m_idx + 1) if m_idx is not None else None
    if ext is None:
        errors.append(f"{OUTPUT_GUIDE_REL}: no table follows a {TABLE_MARKER!r} marker")
    elif contract:
        diffs = diff_table(ext[0], render_rows(contract["statuses"]))
        if diffs:
            errors.append(f"{OUTPUT_GUIDE_REL}: §3's table is not {CONTRACT_REL}'s statuses -- re-render: "
                          "python3 scripts/check_schema_drift.py --write")
            errors.extend(f"  {d}" for d in diffs)

    maturity = parse_maturity(_section3(guide_text))
    if maturity is None:
        errors.append(f"{OUTPUT_GUIDE_REL}: maturity axis (draft | verified | canonical form) not found in §3")
    elif contract and maturity != contract["maturity"]:
        errors.append(f"{OUTPUT_GUIDE_REL}: maturity axis {maturity!r} != the contract's {contract['maturity']!r}")

    # Single-table invariant: no enum rows outside the marked table…
    errors.extend(f"{OUTPUT_GUIDE_REL}: {m}" for m in find_inline_enum_rows(guide_text, exclude_marked=True))
    # …and the consumers point at §3 instead of restating it.
    for rel in POINTER_FILES_REL:
        path = repo_root / rel
        if not path.is_file():
            errors.append(f"{rel}: file missing")
            continue
        text = path.read_text(encoding="utf-8")
        if not POINTER_RE.search(text):
            errors.append(f"{rel}: no pointer to the output-guide §3 vocabulary table (expected 'output-guide … §3')")
        errors.extend(f"{rel}: {m}" for m in find_inline_enum_rows(text))
    return errors, [], []


def write(repo_root: Path = REPO_ROOT) -> list[str]:
    """Re-render §3's table and stamp from the contract, in place. Returns errors (nothing written on one)."""
    contract, ref, errors = load_contract(repo_root)
    path = repo_root / OUTPUT_GUIDE_REL
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    m_idx = _find_marker([ln.rstrip("\n") for ln in lines], TABLE_MARKER)
    ext = _extract_table([ln.rstrip("\n") for ln in lines], m_idx + 1) if m_idx is not None else None
    if ext is None:
        errors.append(f"{OUTPUT_GUIDE_REL}: no table follows a {TABLE_MARKER!r} marker")
    if not STAMP_RE.search(text):
        errors.append(f"{OUTPUT_GUIDE_REL}: no stamp to update")
    if errors:
        return errors
    table = [row + "\n" for row in render_rows(contract["statuses"])]
    text = "".join(lines[:ext[1]] + table + lines[ext[2] + 1:])
    path.write_text(STAMP_RE.sub(f"`claudron contract --json` @ `{ref}`", text, count=1), encoding="utf-8")
    return []


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check output-guide §3 against Claudron's vendored contract.")
    parser.add_argument("--write", action="store_true", help="re-render §3's table and stamp from the contract")
    parser.add_argument("--offline", action="store_true", help=argparse.SUPPRESS)  # always offline now
    args = parser.parse_args(argv)
    if args.write:
        errors = write()
        for e in errors:
            print(f"  {e}")
        if errors:
            return 1
        print(f"wrote {OUTPUT_GUIDE_REL} §3 from {CONTRACT_REL}")
    errors, _, _ = run_check()
    if errors:
        print(f"FAIL: schema-drift gate -- {len(errors)} error line(s)")
        for e in errors:
            print(f"  {e}")
        return 1
    print("OK: schema-drift gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
