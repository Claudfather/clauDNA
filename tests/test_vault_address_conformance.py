"""Conformance gate for the vault-address contract (boundary phase D1).

The vault address is **Claudron's** contract, not clauDNA's: the canonical env
name, its precedence, and the migration record live once in that repo's
``docs/CLI_CONTRACT.md`` §Environment. clauDNA holds *conformance* — it points
at the owner's text and never forks it (register rule R3).

Two things go wrong without a gate, and both have happened:

1. **Reading a name the engine ignores.** ``CLAUDRON_VAULT`` (no ``_PATH``) was
   removed in Claudron 0.3.0. While clauDNA still honored it, a host exporting
   only that name had the skill layer resolve one vault and the engine resolve
   another — the two-vaults hazard, pointing the other way.
2. **Restating the ladder.** Seven files independently described the resolution
   order; when the engine changed, they all became wrong at once and nothing
   noticed. Prose that an LLM executes is still an implementation.

This gate is deliberately textual. The ladder is prompt text, so "both layers
resolve the same vault" cannot be asserted mechanically — that is a manual eval
check. What *can* be pinned is that the dead name is gone and the owner is
cited, which is what fails first when this drifts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The name Claudron removed. Word-boundary matched, so ``CLAUDRON_VAULT_PATH``
#: does not trip it (``_`` is a word character).
REMOVED_NAME = re.compile(r"\bCLAUDRON_VAULT\b")

CANONICAL_NAME = "CLAUDRON_VAULT_PATH"
FALLBACK_NAME = "SHARED_DOCS_PATH"

#: Files permitted to name the removed variable, and why. Anything else naming
#: it is either an instruction to set it or an unmigrated ladder — both bugs.
#: Keep this list short; a growing allowlist means the migration is leaking.
ALLOWED_MENTIONS = {
    "skills/_shared/documentation-standard.md": "states the removal (the ladder SSOT)",
    "SETUP_GUIDE.md": "states the removal for humans configuring a machine",
}

#: Files that state the env ladder and must therefore cite the owner.
LADDER_FILES = [
    "skills/_shared/documentation-standard.md",
    "skills/_shared/claudron-engine.md",
]

CONTRACT_URL_FRAGMENT = "Claudron/blob/main/docs/CLI_CONTRACT.md#environment"


def _scanned_files() -> list[Path]:
    """Every doc a consumer could read the ladder out of."""
    files = sorted((REPO_ROOT / "skills").rglob("*.md"))
    setup = REPO_ROOT / "SETUP_GUIDE.md"
    if setup.is_file():
        files.append(setup)
    return files


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


class TestRemovedNameIsGone:
    def test_scan_covers_something(self):
        """Guard against the gate silently scanning nothing."""
        assert len(_scanned_files()) > 20

    def test_no_unexpected_file_names_the_removed_variable(self):
        offenders = {
            _rel(p)
            for p in _scanned_files()
            if REMOVED_NAME.search(p.read_text())
        }
        assert offenders <= set(ALLOWED_MENTIONS), (
            "these files still name the removed CLAUDRON_VAULT: "
            f"{sorted(offenders - set(ALLOWED_MENTIONS))}. The engine does not "
            "read it (Claudron 0.3.0); honoring it here resolves a different "
            "vault than the engine does."
        )

    def test_nothing_instructs_a_user_to_set_it(self):
        """The sharpest failure: telling someone to export a dead variable.

        Claudron's own `init` output had this exact bug before its C1 fix.
        """
        pattern = re.compile(r"(export|printenv|setenv)\s+CLAUDRON_VAULT\b")
        offenders = [
            f"{_rel(p)}: {m.group(0)}"
            for p in _scanned_files()
            for m in [pattern.search(p.read_text())]
            if m
        ]
        assert not offenders, offenders

    @pytest.mark.parametrize("relpath", sorted(ALLOWED_MENTIONS))
    def test_allowlisted_mentions_are_migration_notes(self, relpath: str):
        """An allowlisted file must be *explaining the removal*, not using it."""
        text = (REPO_ROOT / relpath).read_text()
        assert REMOVED_NAME.search(text), (
            f"{relpath} no longer mentions the removed name — drop it from "
            "ALLOWED_MENTIONS rather than leaving a stale exemption."
        )
        assert re.search(r"\b(removed|gone|no longer)\b", text, re.I), (
            f"{relpath} names the removed variable without saying it is removed"
        )


class TestLadderCitesTheOwner:
    """R3: consumers point at the owner's text, never fork it."""

    @pytest.mark.parametrize("relpath", LADDER_FILES)
    def test_ladder_file_cites_the_contract(self, relpath: str):
        text = (REPO_ROOT / relpath).read_text()
        assert CONTRACT_URL_FRAGMENT in text, (
            f"{relpath} describes vault resolution without citing Claudron's "
            "CLI_CONTRACT §Environment, which owns it."
        )

    def test_canonical_name_precedes_the_fallback(self):
        """`SHARED_DOCS_PATH` is fallback-mode only; it must never be read
        ahead of the engine's address."""
        text = (REPO_ROOT / "skills/_shared/documentation-standard.md").read_text()
        assert CANONICAL_NAME in text and FALLBACK_NAME in text
        assert text.index(CANONICAL_NAME) < text.index(FALLBACK_NAME)


class TestSessionMdStableSurface:
    """F6: Claudlobby parses this artifact; the promise is declared, minimal."""

    def test_templates_declare_the_stable_subset(self):
        text = (REPO_ROOT / "skills/session/templates.md").read_text()
        assert "Stable surface" in text
        assert "last_updated" in text
        assert re.search(r"informal|may change", text, re.I), (
            "the stable-surface block must say what is NOT promised — an "
            "unbounded promise is what let Claudlobby parse whatever it liked"
        )
