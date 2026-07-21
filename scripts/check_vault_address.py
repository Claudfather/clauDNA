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

Scope note: this gate is **textual and offline**, unlike ``check_schema_drift``
which fetches the SSOT at a stamped commit. That is deliberate rather than lazy
— §10 now holds a *pointer*, not a rendered copy, so there is no local copy to
diff. What can be pinned is that the dead name is gone and the owner is cited,
which is what fails first when this drifts.

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

#: Telling a user to set the dead variable — the sharpest failure shape.
SETS_REMOVED_NAME = re.compile(r"(export|printenv|setenv)\s+CLAUDRON_VAULT\b")

#: A line that names the removed variable must also say it is removed. Matched
#: **per line**, not per file: a whole-file search passes on any doc that
#: happens to use "removed" elsewhere, which silently exempted SETUP_GUIDE.md.
SAYS_REMOVED = re.compile(r"\b(removed|gone|no longer|dead)\b", re.I)

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


def _candidates(repo_root: Path) -> list[Path]:
    """Living surfaces that could carry or execute the variable.

    Reuses ``validate-skills.py``'s gate scope — the same living-surface vs
    point-in-time-record split the removed-*names* gate already tuned. That
    matters here beyond tidiness: it brings in ``.sh`` files and the templates
    shipped into user projects, which are the only surfaces that could
    *actually read* an env var, and which a ``skills/**/*.md`` walk misses.
    """
    from importlib import import_module
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "_validate_skills", repo_root / "scripts" / "validate-skills.py"
    )
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    del import_module

    out: list[Path] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix not in mod.GATE_EXTENSIONS:
            continue
        rel = path.relative_to(repo_root).as_posix()
        if any(part in mod.GATE_PRUNE_DIRS for part in path.relative_to(repo_root).parts):
            continue
        if rel in mod.GATE_EXCLUDE_FILES or rel.startswith(mod.GATE_EXCLUDE_PREFIXES):
            continue
        if rel in SELF:
            continue
        out.append(path)
    return out


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

        if m := SETS_REMOVED_NAME.search(text):
            errors.append(
                f"{rel}: instructs a user to set the removed variable "
                f"({m.group(0)!r}) — the engine does not read it since "
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
        unexplained = [ln for ln in offending if not SAYS_REMOVED.search(ln)]
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
