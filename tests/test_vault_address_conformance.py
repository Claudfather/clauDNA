"""Tests for the vault-address conformance gate (boundary phase D1).

The gate itself is ``scripts/check_vault_address.py`` and is wired into
``validate-skills.py`` — the pre-PR command CLAUDE.md names. This file is the
pytest backstop, matching ``test_removed_names.py``'s reasoning: it runs in the
unpartitioned CI job, so it catches what touched-set scoping could demote.

Why the gate exists at all: the vault address is Claudron's contract, and
clauDNA read the wrong end of it. See the module docstring in
``scripts/check_vault_address.py`` for the two failure shapes; that is the one
home for the rationale, not this file.

The fixture cases below are the important part. An earlier revision asserted
against the live repo only, and two of its assertions **passed on the
pre-fix files** — a gate that cannot fail on the regression it was written for.
Each case here is a file state that must be rejected.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "check_vault_address", REPO_ROOT / "scripts" / "check_vault_address.py"
)
check_vault_address = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_vault_address)

run_check = check_vault_address.run_check
ALLOWED_MENTIONS = check_vault_address.ALLOWED_MENTIONS
LADDER_OWNER_DOC = check_vault_address.LADDER_OWNER_DOC
CONTRACT_URL = check_vault_address.CONTRACT_URL_FRAGMENT


def _repo(tmp_path: Path, **files: str) -> Path:
    """A miniature repo that satisfies the gate, plus the given overrides."""
    base = {
        "scripts/validate-skills.py": (
            'GATE_EXTENSIONS = {".md", ".sh"}\n'
            'GATE_PRUNE_DIRS = {".git"}\n'
            'GATE_EXCLUDE_FILES = {"CHANGELOG.md"}\n'
            'GATE_EXCLUDE_PREFIXES = ("documentation/archive/",)\n'
        ),
        LADDER_OWNER_DOC: (
            "# doc\n\nUse `CLAUDRON_VAULT_PATH`, else `SHARED_DOCS_PATH` in "
            "fallback mode.\n`CLAUDRON_VAULT` was removed in Claudron 0.3.0.\n"
            f"Owner: https://github.com/Claudfather/{CONTRACT_URL}\n"
        ),
        "SETUP_GUIDE.md": (
            "# setup\n\nSet `CLAUDRON_VAULT_PATH`. The bare `CLAUDRON_VAULT` "
            "was removed in Claudron 0.3.0 — rename it.\n"
        ),
        "skills/some/SKILL.md": "# a skill\n\nNothing to see.\n",
    }
    base.update(files)
    for rel, text in base.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def _errors(tmp_path: Path, **files: str) -> list[str]:
    errors, _warnings, _notes = run_check(_repo(tmp_path, **files))
    return errors


class TestGateAcceptsConformingRepo:
    def test_clean_repo_passes(self, tmp_path: Path):
        assert _errors(tmp_path) == []

    def test_canonical_name_alone_is_fine(self, tmp_path: Path):
        errs = _errors(
            tmp_path,
            **{"skills/some/SKILL.md": "Read `CLAUDRON_VAULT_PATH` from env.\n"},
        )
        assert errs == [], "the _PATH form must not trip a \\b-matched gate"


class TestGateRejectsTheRegressions:
    """Each case is a state the pre-D1 repo was actually in."""

    def test_skill_naming_the_removed_variable(self, tmp_path: Path):
        errs = _errors(
            tmp_path,
            **{
                "skills/some/SKILL.md":
                    "Root from `CLAUDRON_VAULT`/`CLAUDRON_VAULT_PATH`, in that order.\n"
            },
        )
        assert any("names the removed" in e for e in errs), errs

    def test_instructing_a_user_to_export_it(self, tmp_path: Path):
        errs = _errors(
            tmp_path,
            **{"skills/some/SKILL.md": "    Or point at: export CLAUDRON_VAULT=<path>\n"},
        )
        assert any("instructs a user to set" in e for e in errs), errs

    def test_shell_file_is_in_scope(self, tmp_path: Path):
        """`.sh` is the only surface that could *actually* read the variable.

        A `skills/**/*.md` walk missed these entirely.
        """
        errs = _errors(tmp_path, **{"plugin-hooks/some.sh": 'echo "$CLAUDRON_VAULT"\n'})
        assert any("some.sh" in e for e in errs), errs

    def test_allowlisted_file_mentioning_it_without_saying_removed(self, tmp_path: Path):
        """The bug the first revision shipped: a whole-file search for
        'removed' passed on SETUP_GUIDE.md because the word appears in
        unrelated prose two hundred lines away. Matching must be per line."""
        errs = _errors(
            tmp_path,
            **{
                "SETUP_GUIDE.md":
                    "# setup\n\nA legacy command was removed in 0.2.0.\n\n"
                    "Env: `CLAUDRON_VAULT` or `CLAUDRON_VAULT_PATH` — accept both.\n"
            },
        )
        assert any("without saying it is removed" in e for e in errs), errs

    def test_owner_citation_dropped(self, tmp_path: Path):
        errs = _errors(
            tmp_path,
            **{
                LADDER_OWNER_DOC:
                    "Use `CLAUDRON_VAULT_PATH`. `CLAUDRON_VAULT` was removed.\n"
            },
        )
        assert any("CLI_CONTRACT" in e for e in errs), errs

    def test_stale_exemption_is_reported(self, tmp_path: Path):
        """An allowlisted file that stops narrating the removal should force
        the exemption to be dropped, not linger as dead config."""
        errs = _errors(
            tmp_path,
            **{"SETUP_GUIDE.md": "# setup\n\nNothing about the old variable.\n"},
        )
        assert any("stale exemption" in e for e in errs), errs

    def test_empty_scan_is_an_error_not_a_pass(self, tmp_path: Path):
        """A gate that silently scans nothing is worse than no gate."""
        (tmp_path / "scripts").mkdir(parents=True)
        (tmp_path / "scripts" / "validate-skills.py").write_text(
            "GATE_EXTENSIONS = set()\nGATE_PRUNE_DIRS = set()\n"
            "GATE_EXCLUDE_FILES = set()\nGATE_EXCLUDE_PREFIXES = ()\n"
        )
        errors, _w, _n = run_check(tmp_path)
        assert any("zero files" in e for e in errors), errors


class TestLiveRepo:
    """The real repo must pass its own gate."""

    def test_repo_conforms(self):
        errors, _warnings, _notes = run_check(REPO_ROOT)
        assert errors == [], errors

    def test_gate_is_wired_into_the_validator(self):
        """CLAUDE.md names validate-skills.py as the pre-PR step, and CI runs
        it on push-to-main as well as PRs — pytest runs on PRs only. A gate
        living solely in tests/ is invisible where contributors look."""
        text = (REPO_ROOT / "scripts" / "validate-skills.py").read_text()
        assert "run_vault_address_check" in text

    def test_scan_reaches_the_files_the_gate_reasons_about(self):
        """Guards against a walk that silently narrows."""
        _e, _w, notes = run_check(REPO_ROOT)
        assert notes and "living surfaces scanned" in notes[0]
        count = int(notes[0].split(":")[1].strip().split()[0])
        assert count > 100, f"scan collapsed to {count} files"


class TestSessionMdStableSurface:
    """F6: the handoff artifact is consumed outside clauDNA, so the promise is
    declared and minimal. Asserted against the declaration block only — an
    earlier revision searched the whole file and passed on the pre-fix version,
    because `last_updated` was already in the frontmatter template."""

    def _block(self) -> str:
        text = (REPO_ROOT / "skills/session/templates.md").read_text()
        assert "## Stable surface" in text, "the stable-surface declaration is gone"
        return text.split("## Stable surface", 1)[1].split("\n## ", 1)[0]

    def test_declares_existence_and_timestamp(self):
        block = self._block()
        assert "last_updated" in block
        assert "ISO-8601" in block

    def test_states_what_is_not_promised(self):
        """An unbounded promise is what let a consumer parse whatever it liked."""
        block = self._block()
        assert "informal" in block.lower() or "may change" in block.lower()
