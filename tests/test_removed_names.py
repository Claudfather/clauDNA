"""Tests for the removed-names reference gate (epic #165 P2 step 0).

A PR that deletes a skill must not leave references to it anywhere in the
repo — in any form: `claudna:<name>`, `/  <name>`, `skills/<name>/`,
`Skill(<name>)`, or a bare mention. The gate is keyed on
scripts/removed-skills.txt and exempts `Replaces …` breadcrumb lines
(SKILL_CONTRACT §2.1 rule 6 requires those to name removed skills).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import check_removed_name_mentions, load_removed_skills


class TestLoadRemovedSkills:
    def test_parses_names_skipping_comments_and_blanks(self, tmp_path):
        f = tmp_path / "removed-skills.txt"
        f.write_text("# removed in 0.7.0\nghost-deploy\n\nghost-logs  # inline note\n  phantom-query  \n")
        assert load_removed_skills(f) == ["ghost-deploy", "ghost-logs", "phantom-query"]

    def test_malformed_entry_raises(self, tmp_path):
        f = tmp_path / "removed-skills.txt"
        f.write_text("ghost deploy\n")
        try:
            load_removed_skills(f)
        except ValueError as e:
            assert "not a valid skill name" in str(e)
        else:
            raise AssertionError("expected ValueError for malformed entry")

    def test_missing_file_returns_empty(self):
        assert load_removed_skills(Path("/nonexistent/removed-skills.txt")) == []


class TestCheckRemovedNameMentions:
    NAMES = ["ghost-deploy", "phantom-query"]

    def test_all_reference_forms_detected(self):
        text = (
            "See claudna:ghost-deploy for details.\n"
            "Or invoke /ghost-deploy directly.\n"
            "The file lives at skills/ghost-deploy/SKILL.md.\n"
            "Permission rule: Skill(ghost-deploy)\n"
            "The ghost-deploy skill handles this.\n"
        )
        errors = check_removed_name_mentions(text, self.NAMES)
        assert len(errors) == 5
        assert all("ghost-deploy" in msg for _n, msg in errors)

    def test_word_boundary_no_false_positives(self):
        text = "The ghost-deployment pipeline uses ghost-deploy-v2 conventions."
        assert check_removed_name_mentions(text, self.NAMES) == []

    def test_replaces_breadcrumb_line_exempt(self):
        text = "Replaces /ghost-deploy, /ghost-logs, /ghost-status."
        assert check_removed_name_mentions(text, self.NAMES) == []

    def test_clean_text_empty(self):
        text = "Use for Modal serverless operations — deploying and logs."
        assert check_removed_name_mentions(text, self.NAMES) == []

    def test_line_numbers_reported(self):
        text = "line one is fine\nrun /phantom-query here\n"
        errors = check_removed_name_mentions(text, self.NAMES)
        assert len(errors) == 1
        name, msg = errors[0]
        assert name == "phantom-query"
        assert "line 2" in msg

    def test_multiple_names_one_line(self):
        text = "both /ghost-deploy and /phantom-query appear here"
        errors = check_removed_name_mentions(text, self.NAMES)
        assert {n for n, _ in errors} == {"ghost-deploy", "phantom-query"}


class TestRepoIsCleanOfRemovedNames:
    """The gate must bind FUTURE changes, not just the deleting PR.

    validate-skills.py treats gate hits as always-blocking, but even if that
    ever regressed toward touched-set demotion (a deleted skill can never be
    touched again), this test runs in the unpartitioned pytest CI job — so a
    post-merge PR resurrecting a retired name in prose fails 'Run tests' on
    every future PR regardless of the validator's scoping.
    """

    def test_no_repo_surface_mentions_a_removed_name(self):
        # Hyphenated module: import via spec (same pattern as test_validate_promotion.py)
        spec = importlib.util.spec_from_file_location(
            "validate_skills", REPO_ROOT / "scripts" / "validate-skills.py"
        )
        validate_skills = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validate_skills)
        removed = validate_skills.load_removed_skills(validate_skills.REMOVED_SKILLS_FILE)
        assert removed, "removed-skills.txt should list the P2 removals"
        hits = validate_skills.scan_removed_names(removed)
        assert hits == [], "\n".join(f"{rel}: {msg}" for rel, msg in hits)
