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
import re
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

    def test_bare_assignment_without_an_export_keyword(self, tmp_path: Path):
        """A command sample is an instruction too.

        The first cut required a literal `export`/`printenv`/`setenv`, so an
        inline `CLAUDRON_VAULT=/p claudron status` re-taught the dead name from
        inside an allowlisted file and passed clean.
        """
        errs = _errors(
            tmp_path,
            **{
                "SETUP_GUIDE.md": "# setup\n\nRun `CLAUDRON_VAULT=/p claudron "
                "status` if the walk-up no longer works.\n"
            },
        )
        assert any("instructs a user to set" in e for e in errs), errs

    def test_imperative_prose_without_an_equals_sign(self, tmp_path: Path):
        """"Set `CLAUDRON_VAULT` to ..." — no `=`, no `export`, still an order."""
        errs = _errors(
            tmp_path,
            **{
                "SETUP_GUIDE.md": "# setup\n\nSet `CLAUDRON_VAULT` to your vault "
                "(the old auto-detect was removed).\n"
            },
        )
        assert any("instructs a user to set" in e for e in errs), errs

    def test_removal_note_must_sit_near_the_mention(self, tmp_path: Path):
        """Per-line was an improvement on per-file; it is still launderable.

        One "removed" at the tail of a long line qualifies every unrelated use
        before it, so proximity is what actually gets checked.
        """
        filler = "and a great deal of unrelated narrative prose besides, " * 3
        errs = _errors(
            tmp_path,
            **{
                "SETUP_GUIDE.md": "# setup\n\nEnv: `CLAUDRON_VAULT` is read here "
                f"{filler}— a legacy command was removed in 0.2.0.\n"
            },
        )
        assert any("without saying it is removed" in e for e in errs), errs


class TestGateRejectsARestatedLadder:
    """Failure shape 2 from the module docstring, which the first cut declared
    and never implemented. `skills/index/SKILL.md` then shipped the exact shape:
    it enumerated the two env names "(in that order)" while citing the section
    that says they are mode-selected and explicitly "not a precedence chain".
    """

    def test_enumerating_both_names_is_a_restatement(self, tmp_path: Path):
        errs = _errors(
            tmp_path,
            **{
                "skills/some/SKILL.md": "Defaults to `CLAUDRON_VAULT_PATH`/"
                "`SHARED_DOCS_PATH` env vars (in that order).\n"
            },
        )
        assert any("enumerates both vault env names" in e for e in errs), errs

    def test_an_inverted_order_is_caught_without_the_dead_name(self, tmp_path: Path):
        """The dead-name rules are blind to this: every name here is current."""
        errs = _errors(
            tmp_path,
            **{
                "skills/some/SKILL.md": "Resolve from `SHARED_DOCS_PATH`, then "
                "`CLAUDRON_VAULT_PATH` — in that order.\n"
            },
        )
        assert any("enumerates both vault env names" in e for e in errs), errs

    def test_citing_section_10_does_not_license_a_fork(self, tmp_path: Path):
        """The live regression cited §10 *in the sentence that contradicted it*.

        So a citation cannot be the test — the enumeration itself has to be.
        """
        errs = _errors(
            tmp_path,
            **{
                "skills/some/SKILL.md": "Root from `CLAUDRON_VAULT_PATH`/"
                "`SHARED_DOCS_PATH` (in that order) — contract: "
                f"`{LADDER_OWNER_DOC}` §10, which owns the ladder.\n"
            },
        )
        assert any("enumerates both vault env names" in e for e in errs), errs

    def test_single_hopping_to_section_10_is_the_conforming_form(self, tmp_path: Path):
        errs = _errors(
            tmp_path,
            **{
                "skills/some/SKILL.md": "Resolve the docs root per "
                f"`{LADDER_OWNER_DOC}` §10 (\"locating the root\").\n"
            },
        )
        assert errs == [], errs

    def test_the_owner_doc_may_enumerate(self, tmp_path: Path):
        """§10 states the ladder — that is the whole point of a single home.

        The precondition is asserted so this cannot decay into a restatement of
        `test_clean_repo_passes`: the fixture's owner doc really does put both
        names on one line, which is precisely what the rule rejects elsewhere.
        """
        owner = _repo(tmp_path).joinpath(LADDER_OWNER_DOC).read_text()
        assert any(
            "CLAUDRON_VAULT_PATH" in ln and "SHARED_DOCS_PATH" in ln
            for ln in owner.splitlines()
        ), "fixture no longer enumerates; this test would prove nothing"
        assert _errors(tmp_path) == []

    def test_names_on_separate_lines_are_not_a_restatement(self, tmp_path: Path):
        """`init-project` checks each var in its own operational step. Naming
        both across a file is normal; enumerating them as an order is not."""
        errs = _errors(
            tmp_path,
            **{
                "skills/some/SKILL.md": "If `SHARED_DOCS_PATH` is set, the raw "
                "tree exists.\n\nIf `CLAUDRON_VAULT_PATH` is set, a vault does.\n"
            },
        )
        assert errs == [], errs


class TestGateScopeIsLocal:
    def test_a_live_skill_directory_is_not_exempt(self, tmp_path: Path):
        """`skills/cleanup-legacy-install/` is exempt from the removed-*names*
        gate because enumerating retired skill names is that skill's job. None
        of that rationale transfers to an env var, and the skill is live prose
        an LLM executes — so this gate must reach it even though the fake
        validate-skills.py below still lists it as excluded.
        """
        errs = _errors(
            tmp_path,
            **{
                "scripts/validate-skills.py": (
                    'GATE_EXTENSIONS = {".md", ".sh"}\n'
                    'GATE_PRUNE_DIRS = {".git"}\n'
                    'GATE_EXCLUDE_FILES = {"CHANGELOG.md"}\n'
                    'GATE_EXCLUDE_PREFIXES = ("skills/cleanup-legacy-install/",)\n'
                ),
                "skills/cleanup-legacy-install/SKILL.md":
                    "Point at your vault: export CLAUDRON_VAULT=/srv/vault\n",
            },
        )
        assert any("cleanup-legacy-install" in e for e in errs), errs

    def test_point_in_time_records_stay_exempt(self, tmp_path: Path):
        """Plan and archive documents describe the ladder as it stood when they
        were written. Rewriting them to match today's ladder would falsify the
        record rather than fix a bug — the same reasoning validate-skills.py
        already applies to retired skill names.
        """
        errs = _errors(
            tmp_path,
            **{
                "documentation/planning/old-plan.md":
                    "**Precedence:** `CLAUDRON_VAULT`/`CLAUDRON_VAULT_PATH` env "
                    "> section.\n"
            },
        )
        assert errs == [], errs


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

    #: A write site is any file instructing a write to the artifact. Detected by
    #: the *instruction*, never by the atomicity phrasing — a detector keyed on
    #: "files that mention tmp+mv" would be circular and would wave through a
    #: newly added write path, which is the regression that actually matters.
    #: Rewording "atomically" is not; the promise survives a synonym.
    WRITE_INSTRUCTION = re.compile(r"(?=.*\bwrit)(?=.*\.claude/session\.md)", re.I)

    def _write_sites(self) -> dict[str, str]:
        sites = {}
        for path in sorted((REPO_ROOT / "skills" / "session").glob("*.md")):
            text = path.read_text()
            if any(self.WRITE_INSTRUCTION.search(ln) for ln in text.splitlines()):
                sites[path.name] = text
        return sites

    def test_every_write_site_mandates_the_atomic_write(self):
        """"A reader sees a complete file or none" is the promise; `.tmp` + `mv`
        (→ `rename(2)`) is the only thing implementing it. Nothing pinned the
        two together, so a fourth write path could ship non-atomic and keep the
        declaration honest-looking.
        """
        sites = self._write_sites()
        assert sites, "no write sites detected — the detector has drifted"
        missing = sorted(
            name
            for name, text in sites.items()
            if "session.md.tmp" not in text and not ("tmp" in text and "mv" in text)
        )
        assert not missing, (
            f"{missing} instruct writing session.md without the tmp+mv atomic "
            "write. Claudlobby age-gates bot resume on this file, so a torn "
            "read is a consumer-visible break of a declared promise "
            "(templates.md, '## Stable surface')."
        )

    def test_the_timestamp_stays_iso_8601(self):
        """Epoch seconds would keep the field name and the word 'timestamp'
        while silently breaking every consumer that parses it as a date."""
        text = (REPO_ROOT / "skills" / "session" / "templates.md").read_text()
        m = re.search(r"^last_updated:\s*(.+)$", text, re.M)
        assert m, "the templates' `last_updated:` line is gone"
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", m.group(1)), (
            f"`last_updated:` example is no longer ISO-8601 shaped: {m.group(1)!r}"
        )
