#!/usr/bin/env python3
"""Vault-address conformance gate: the ladder is Claudron's, and we point at it.

The vault address is **Claudron's** contract — the canonical env name, its
precedence, and the migration record live once in that repo's
``docs/CLI_CONTRACT.md`` §Environment. clauDNA holds *conformance*: it points at
the owner's text and never forks it (boundary phase D1).

Two things go wrong without a gate, and both already happened:

1. **Reading a name the engine ignores.** ``CLAUDRON_VAULT`` (no ``_PATH``) was
   removed in Claudron 0.3.0. While clauDNA still honored it, a host exporting
   only that name had the skill layer resolve one vault and the engine resolve
   another. ``skills/claudron/status.md`` went further and *told users to export
   it* — the same bug Claudron had to fix in its own ``init`` output.
2. **Restating the ladder.** Seven files independently described the resolution
   order; when the engine changed, all seven became wrong at once and nothing
   noticed. Prose an LLM executes is still an implementation.

Each shape has a rule. Shape 1 is ``ASSIGNS_REMOVED_NAME`` /
``INSTRUCTS_REMOVED_NAME`` plus the per-line "say it is removed" requirement;
shape 2 is ``RESTATES_LADDER``. Shape 2 went unenforced in the first cut of this
gate, and ``skills/index/SKILL.md`` promptly demonstrated why — it forked the
order while citing the section that owns it, in the same sentence.

Scope note: this gate is **textual and offline**, unlike ``check_schema_drift``
which fetches the SSOT at a stamped commit. That is deliberate rather than lazy
— §10 now holds a *pointer*, not a rendered copy, so there is no local copy to
diff. What can be pinned is that the dead name is gone, that nobody re-derives
the order, and that the owner is cited — which is what fails first when this
drifts.

Run standalone::

    python3 scripts/check_vault_address.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

#: The name Claudron removed. Word-boundary matched, so ``CLAUDRON_VAULT_PATH``
#: does not trip it (``_`` is a word character).
REMOVED_NAME = re.compile(r"\bCLAUDRON_VAULT\b")

#: Telling a user to set the dead variable — the sharpest failure shape. Two
#: forms, because the first cut only caught one and an allowlisted file could
#: re-teach the name through the other:
#:
#: * **assignment** — ``CLAUDRON_VAULT=/p``, with or without a leading verb, and
#:   tolerant of the backticks docs wrap it in. The original required a literal
#:   ``export``/``printenv``/``setenv``, so a bare ``CLAUDRON_VAULT=/p claudron
#:   status`` in a command sample sailed through.
#: * **imperative** — "Set ``CLAUDRON_VAULT`` to your vault". Prose instructs
#:   without an ``=`` at all; ``set`` is the verb the original list omitted.
#: ``[ \t]`` rather than ``\s`` throughout: these run against whole file text, and
#: ``\s`` would let a match straddle a newline and invent an instruction that no
#: single line actually gives.
ASSIGNS_REMOVED_NAME = re.compile(r"`?\bCLAUDRON_VAULT\b`?[ \t]*=")
INSTRUCTS_REMOVED_NAME = re.compile(
    r"\b(?:export|printenv|setenv|unset|set|point)[ \t]+`?\bCLAUDRON_VAULT\b", re.I
)

#: A line that names the removed variable must also say it is removed. Matched
#: **per line**, not per file: a whole-file search passes on any doc that
#: happens to use "removed" elsewhere, which silently exempted SETUP_GUIDE.md.
SAYS_REMOVED = re.compile(r"\b(removed|gone|no longer|dead)\b", re.I)

#: …and the disclaimer has to be *near* the mention, not merely somewhere on the
#: same line. A long narrative line can carry one "removed" at the end and use
#: the name freely before it. Window is generous enough for real prose
#: ("``CLAUDRON_VAULT`` (no ``_PATH``) was removed") and tight enough that an
#: unrelated clause does not launder an unqualified use.
SAYS_REMOVED_LOOKBEHIND = 40
SAYS_REMOVED_LOOKAHEAD = 80

CANONICAL_NAME = "CLAUDRON_VAULT_PATH"

#: Files permitted to name the removed variable, because they narrate the
#: removal. Keep this short — a growing allowlist means the migration is
#: leaking. Each is still required to *say* the name is removed, on the line
#: that mentions it.
ALLOWED_MENTIONS = {
    "skills/_shared/documentation-standard.md",  # §10, the ladder SSOT
    "SETUP_GUIDE.md",                            # humans configuring a machine
}

#: The gate and its test necessarily spell the name they forbid — the same
#: self-reference ``scripts/removed-skills.txt`` has in the removed-names gate.
SELF = {
    "scripts/check_vault_address.py",
    "tests/test_vault_address_conformance.py",
}

#: The one file that states the clauDNA-side ladder must cite the owner.
#: Deliberately one entry: every other file single-hops to §10 instead, so a
#: renamed anchor upstream is one edit here, not N.
LADDER_OWNER_DOC = "skills/_shared/documentation-standard.md"
CONTRACT_URL_FRAGMENT = "Claudron/blob/main/docs/CLI_CONTRACT.md#environment"

#: Failure shape 2, made checkable. Naming **both** env vars on one line is what
#: a restatement of the ladder looks like — the file is enumerating the options
#: rather than single-hopping to §10. Requiring a §10 *citation* is not enough:
#: the live regression this rule was written for (``skills/index/SKILL.md``)
#: cited §10 by name in the same sentence that contradicted it, saying "in that
#: order" where §10 says the two names are mode-selected and explicitly "not a
#: precedence chain". So the enumeration itself is the violation, and the remedy
#: is always the same: cite §10, name neither.
RESTATES_LADDER = re.compile(
    r"(?=.*\bCLAUDRON_VAULT_PATH\b)(?=.*\bSHARED_DOCS_PATH\b)"
)

#: Files permitted to enumerate both names. The owner doc states the ladder by
#: definition; SETUP_GUIDE is the human-facing configuration page, where naming
#: the variable you must export is the entire point.
ALLOWED_RESTATEMENTS = {
    LADDER_OWNER_DOC,
    "SETUP_GUIDE.md",
}

#: **Gate-local** exclusions — deliberately not ``validate-skills``'s, which is
#: tuned for retired *skill names*. That list exempts
#: ``skills/cleanup-legacy-install/`` because enumerating retired skill names is
#: that skill's job; nothing about the rationale transfers to an env var, and the
#: skill is live prose an LLM executes. It is therefore **in scope here**.
#:
#: What remains excluded is only the point-in-time record: plan, spec, decision
#: and archive documents describe the ladder as it stood when written, and
#: rewriting them to match today's ladder would falsify the record rather than
#: fix a bug. ``CHANGELOG.md`` is excluded for the same reason — it is the
#: migration's own narration, append-only by construction.
GATE_EXCLUDE_PREFIXES = (
    "documentation/archive/",
    "documentation/decisions/",
    "documentation/planning/",
    "documentation/specs/",
)
GATE_EXCLUDE_FILES = {"CHANGELOG.md", "scripts/removed-skills.txt"}


def _candidates(repo_root: Path) -> list[Path]:
    """Living surfaces that could carry or execute the variable.

    Borrows ``validate-skills.py``'s *file-type* scope — ``GATE_EXTENSIONS`` and
    ``GATE_PRUNE_DIRS``. That matters beyond tidiness: it brings in ``.sh`` files
    and the templates shipped into user projects, which are the only surfaces
    that could *actually read* an env var, and which a ``skills/**/*.md`` walk
    misses.

    It does **not** borrow that module's exclusions — see
    ``GATE_EXCLUDE_PREFIXES`` above. Inheriting them silently exempted a live
    skill directory from an env-var gate on the strength of a rationale about
    retired skill names.
    """
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "_validate_skills", repo_root / "scripts" / "validate-skills.py"
    )
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    out: list[Path] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix not in mod.GATE_EXTENSIONS:
            continue
        rel = path.relative_to(repo_root).as_posix()
        if any(part in mod.GATE_PRUNE_DIRS for part in path.relative_to(repo_root).parts):
            continue
        if rel in GATE_EXCLUDE_FILES or rel.startswith(GATE_EXCLUDE_PREFIXES):
            continue
        if rel in SELF:
            continue
        out.append(path)
    return out


def _explains_removal(line: str) -> bool:
    """True when every bare-name mention on the line sits near a removal note.

    Proximity, not mere co-occurrence: a long narrative line can carry a single
    "removed" at its tail and use the name unqualified everywhere before it.
    """
    for m in REMOVED_NAME.finditer(line):
        window = line[
            max(0, m.start() - SAYS_REMOVED_LOOKBEHIND) : m.end() + SAYS_REMOVED_LOOKAHEAD
        ]
        if not SAYS_REMOVED.search(window):
            return False
    return True


def run_check(repo_root: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (errors, warnings, notes) — the shape validate-skills.py expects."""
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    candidates = _candidates(repo_root)
    if not candidates:
        errors.append("vault-address gate scanned zero files — the walk is broken")
        return errors, warnings, notes

    seen_allowed: set[str] = set()
    for path in candidates:
        rel = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue

        # Failure shape 2 — restating the ladder. Checked before, and
        # independently of, the dead-name rules: a fork can be perfectly current
        # on the name and still contradict §10 on the order, which is exactly how
        # this shipped.
        if rel not in ALLOWED_RESTATEMENTS:
            for lineno, line in enumerate(text.splitlines(), 1):
                if RESTATES_LADDER.search(line):
                    errors.append(
                        f"{rel}:{lineno}: enumerates both vault env names — a "
                        f"restatement of the ladder that `{LADDER_OWNER_DOC}` §10 "
                        "owns. Cite §10 and name neither: §10 selects the name by "
                        "mode and is explicitly not a precedence chain, so an "
                        "enumeration here can only agree with it by accident."
                    )
                    break

        # Record the exemption as *used* before any early exit below, or a file
        # that trips a dead-name rule also draws a "stale exemption" error saying
        # it no longer mentions the name — one problem reported as two, the
        # second one false.
        if rel in ALLOWED_MENTIONS and REMOVED_NAME.search(text):
            seen_allowed.add(rel)

        if m := (ASSIGNS_REMOVED_NAME.search(text) or INSTRUCTS_REMOVED_NAME.search(text)):
            errors.append(
                f"{rel}: instructs a user to set the removed variable "
                f"({m.group(0).strip()!r}) — the engine does not read it since "
                "Claudron 0.3.0; use CLAUDRON_VAULT_PATH"
            )
            continue

        offending = [ln for ln in text.splitlines() if REMOVED_NAME.search(ln)]
        if not offending:
            continue
        if rel not in ALLOWED_MENTIONS:
            errors.append(
                f"{rel}: names the removed CLAUDRON_VAULT. The engine does not "
                "read it (Claudron 0.3.0); honoring it here resolves a "
                "different vault than the engine does."
            )
            continue

        seen_allowed.add(rel)
        unexplained = [ln for ln in offending if not _explains_removal(ln)]
        if unexplained:
            errors.append(
                f"{rel}: names CLAUDRON_VAULT without saying it is removed — "
                f"{unexplained[0].strip()[:90]!r}"
            )

    for rel in sorted(ALLOWED_MENTIONS - seen_allowed):
        errors.append(
            f"{rel}: allowlisted to narrate the CLAUDRON_VAULT removal but no "
            "longer mentions it — drop the stale exemption"
        )

    owner_doc = repo_root / LADDER_OWNER_DOC
    if not owner_doc.is_file():
        errors.append(f"{LADDER_OWNER_DOC} is missing — it owns the clauDNA-side ladder")
    else:
        text = owner_doc.read_text()
        if CONTRACT_URL_FRAGMENT not in text:
            errors.append(
                f"{LADDER_OWNER_DOC}: states vault resolution without citing "
                "Claudron's CLI_CONTRACT §Environment, which owns it"
            )
        if CANONICAL_NAME not in text:
            errors.append(f"{LADDER_OWNER_DOC}: does not name {CANONICAL_NAME}")

    notes.append(f"vault-address gate: {len(candidates)} living surfaces scanned")
    return errors, warnings, notes


def main() -> int:
    errors, warnings, notes = run_check(REPO_ROOT)
    for n in notes:
        print(f"  {n}")
    for w in warnings:
        print(f"  [WARN] {w}")
    for e in errors:
        print(f"  [ERROR] {e}")
    if errors:
        print(f"\nFAILED — {len(errors)} vault-address conformance error(s).")
        return 1
    print("\nPASSED — vault-address conformance OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
