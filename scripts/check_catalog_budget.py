#!/usr/bin/env python3
"""Catalog budget: the always-loaded skill and agent listings have a ceiling.

Every skill the model can invoke lists its name and description in every
session, whether or not it is used, and so does every agent (CLAUDE.md, Design
Philosophy: "each one must earn its context cost"). The per-skill length rule
(SKILL_CONTRACT §2, 20–500 characters) bounds one description; nothing bounded
the sum, so the catalog could only grow. This gate holds each sum to a ceiling
in ``scripts/catalog-budget.json``:

* **Over the ceiling** is an error. Adding a skill, or lengthening a
  description, means raising the number in the same PR, so the cost is a
  reviewed one-line diff rather than a side effect.
* **Under it at all** is a warning naming the number to lower it to, so a
  trim's PR is told to take the freed room back. It doesn't block: two trims
  that each pass alone could put ``main`` under together, and a trim should
  never be what fails a build. Until someone lowers it, the gap is room a
  later PR can spend unreviewed; the warning is what keeps that gap visible.

A skill with ``disable-model-invocation: true`` isn't in the model's listing,
so it isn't counted. Size is the characters of the entry, ``claudna:<name>:
<description>``, plus `` (Tools: …)`` for an agent, whose listing names its
tools (``*`` when it declares none): a deterministic proxy for what the listing
costs (about four characters a token), good for comparing change against change.

Wired into ``validate-skills.py`` as an always-blocking gate; standalone it
also prints the bill of materials, largest first::

    python3 scripts/check_catalog_budget.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import SKIP_DIRS, parse_frontmatter  # noqa: E402

BUDGET_FILE = Path("scripts") / "catalog-budget.json"
#: Entries named in an over-budget error: where to look first.
TOP = 5


def entry_size(name: str, description: str, tools: str | None = None) -> int:
    """Characters of one listing entry; ``tools`` only for an agent."""
    return len(f"claudna:{name}: {description}" + ("" if tools is None else f" (Tools: {tools})"))


def _tools(value) -> str:
    """An agent's ``tools`` frontmatter as its listing shows it: ``*`` when it declares none."""
    if isinstance(value, list):
        return ", ".join(str(t) for t in value) or "*"
    return value.strip() if isinstance(value, str) and value.strip() else "*"


def ranked(sizes: dict[str, int]) -> list[tuple[str, int]]:
    """``(name, size)`` pairs, largest first."""
    return sorted(sizes.items(), key=lambda item: -item[1])


def _entries(paths: list[Path], *, agents: bool) -> dict[str, int]:
    """``{name: size}`` for each listed file (a malformed one is its validator's to report)."""
    sizes: dict[str, int] = {}
    for path in paths:
        try:
            parsed = parse_frontmatter(path)
        except (OSError, ValueError):
            continue
        fm = parsed[0] if parsed else {}
        name, desc = fm.get("name"), fm.get("description")
        if not isinstance(name, str) or not isinstance(desc, str):
            continue
        if agents:
            sizes[name] = entry_size(name, desc, _tools(fm.get("tools")))
        elif fm.get("disable-model-invocation") is not True:  # a skill-only field: hidden from the listing
            sizes[name] = entry_size(name, desc)
    return sizes


def catalogs(repo_root: Path) -> dict[str, dict[str, int]]:
    """The two always-loaded catalogs, ``{"skills": {...}, "agents": {...}}``, with sizes per entry."""
    skills_dir = repo_root / "skills"
    skills = sorted(p / "SKILL.md" for p in (skills_dir.iterdir() if skills_dir.is_dir() else [])
                    if p.is_dir() and p.name not in SKIP_DIRS and (p / "SKILL.md").is_file())
    agents = sorted((repo_root / "agents").glob("*.md"))
    return {"skills": _entries(skills, agents=False), "agents": _entries(agents, agents=True)}


def run_check(repo_root: Path, cats: dict[str, dict[str, int]] | None = None,
              ) -> tuple[list[str], list[str], list[str]]:
    """Return (errors, warnings, notes), the shape the repo's other gates return."""
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    try:
        budget = json.loads((repo_root / BUDGET_FILE).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{BUDGET_FILE.as_posix()} unreadable ({exc})"], [], []
    if not isinstance(budget, dict):
        return [f"{BUDGET_FILE.as_posix()} must be a JSON object of ceilings"], [], []

    for kind, sizes in (catalogs(repo_root) if cats is None else cats).items():
        ceiling = budget.get(kind)
        if not isinstance(ceiling, int) or isinstance(ceiling, bool) or ceiling <= 0:
            errors.append(f"{BUDGET_FILE.as_posix()}: '{kind}' must be a positive integer ceiling")
            continue
        if not sizes:
            errors.append(f"catalog budget found no {kind}: the walk is broken")
            continue
        total = sum(sizes.values())
        if total > ceiling:
            largest = ", ".join(f"{n} ({s})" for n, s in ranked(sizes)[:TOP])
            errors.append(
                f"{kind} catalog is {total} chars, over its {ceiling}-char ceiling by {total - ceiling}. "
                f"Every {kind[:-1]} listing loads into every session: trim a description, or raise "
                f"'{kind}' in {BUDGET_FILE.as_posix()} to {total} in this PR so the cost is reviewed. "
                f"Largest: {largest}."
            )
        elif total < ceiling:
            warnings.append(
                f"{kind} catalog is {total} chars, {ceiling - total} under its {ceiling}-char ceiling: "
                f"lower '{kind}' in {BUDGET_FILE.as_posix()} to {total} so the freed room isn't spent silently."
            )
        notes.append(f"{kind}: {total}/{ceiling} chars across {len(sizes)} entries")
    return errors, warnings, notes


def main() -> int:
    cats = catalogs(REPO_ROOT)
    errors, warnings, notes = run_check(REPO_ROOT, cats)
    for kind, sizes in cats.items():
        for name, size in ranked(sizes):
            print(f"  {size:5d}  {kind}/{name}")
    for prefix, lines in (("NOTE", notes), ("WARN", warnings), ("ERROR", errors)):
        for line in lines:
            print(f"{prefix}: {line}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
