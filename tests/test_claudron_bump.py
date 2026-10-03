"""The Claudron-release bump: ``scripts/claudron_bump.py`` and the workflow that runs it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import claudron_bump as bump  # noqa: E402

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "claudron-release.yml"


class TestDetect:
    @pytest.mark.parametrize("latest,newer", [("v0.10.0", True), ("v0.9.1", True), ("v1.0.0", True),
                                              ("v0.9.0", False), ("v0.8.9", False)])
    def test_versions_compare_as_numbers_not_strings(self, latest, newer):
        assert bump.detect("v0.9.0", latest) == {"tag": latest, "newer": newer}

    @pytest.mark.parametrize("tag", ["0.9.0", "v0.9", "v0.9.0-rc1", "latest"])
    def test_anything_but_a_release_tag_is_refused(self, tag):
        with pytest.raises(ValueError):
            bump.version(tag)


CHANGELOG = """# Changelog

## [Unreleased]
{unreleased}
## [0.25.0] - 2026-10-03
### Added
- An older entry.
"""


class TestChangelog:
    def test_an_empty_unreleased_gets_a_changed_subsection(self):
        out = bump.add_changelog_line(CHANGELOG.format(unreleased=""), "v0.10.0")
        unreleased = out.split("## [Unreleased]\n")[1].split("## [0.25.0]")[0]
        assert unreleased.startswith("### Changed\n- **Moves to Claudron v0.10.0.**")
        assert out.count("## [0.25.0]") == 1 and out.endswith("- An older entry.\n")

    def test_it_lands_after_an_added_block(self):
        out = bump.add_changelog_line(CHANGELOG.format(unreleased="### Added\n- New thing.\n\n"), "v0.10.0")
        unreleased = out.split("## [Unreleased]\n")[1].split("## [0.25.0]")[0]
        assert unreleased.index("### Added") < unreleased.index("### Changed") < unreleased.index("Moves to")

    def test_an_existing_changed_subsection_takes_the_line_first(self):
        out = bump.add_changelog_line(CHANGELOG.format(unreleased="### Changed\n- Other change.\n\n"), "v0.10.0")
        unreleased = out.split("## [Unreleased]\n")[1].split("## [0.25.0]")[0]
        assert unreleased.count("### Changed") == 1
        assert unreleased.index("Moves to") < unreleased.index("Other change.")

    def test_it_never_writes_into_a_released_section(self):
        out = bump.add_changelog_line(CHANGELOG.format(unreleased=""), "v0.10.0")
        assert "Moves to" not in out.split("## [0.25.0]")[1]


class TestBody:
    def test_all_passing_says_so_and_asks_nothing(self):
        body = bump.pr_body("v0.10.0", "v0.9.0", "pass", "pass")
        assert "from Claudron v0.9.0 to v0.10.0" in body
        assert body.count("passed") == 2 and "needs a person" not in body

    def test_a_failure_is_named_and_asks_for_a_person(self):
        body = bump.pr_body("v0.10.0", "v0.9.0", "pass", "fail")
        assert "`make test-contract` (the live suite, exact mode): **failed**" in body
        assert "needs a person" in body

    def test_it_says_ci_does_not_start_on_its_own(self):
        assert "doesn't start CI" in bump.pr_body("v0.10.0", "v0.9.0", "pass", "pass")


class TestWorkflow:
    def test_it_parses_and_runs_on_a_schedule_and_by_hand(self):
        doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        triggers = doc.get("on") or doc.get(True)  # YAML 1.1 reads a bare `on` key as True
        assert "schedule" in triggers and "workflow_dispatch" in triggers
        assert doc["permissions"] == {"contents": "write", "pull-requests": "write"}

    def test_it_moves_with_the_repo_tools_and_checks_with_the_makefile(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for needed in ("claudron_bump.py detect", "sync_claudron_contract.py --ref", "claudron_bump.py changelog",
                       "make deps-contract", "make check", "make test-contract", "gh pr create"):
            assert needed in text, needed

    def test_the_scripts_it_names_exist(self):
        for script in ("claudron_bump.py", "sync_claudron_contract.py"):
            assert (REPO_ROOT / "scripts" / script).is_file()


class TestKeepAChangelogOrder:
    def test_a_new_changed_goes_ahead_of_fixed(self):
        out = bump.add_changelog_line(CHANGELOG.format(unreleased="### Added\n- A.\n\n### Fixed\n- F.\n\n"), "v0.10.0")
        unreleased = out.split("## [Unreleased]\n")[1].split("## [0.25.0]")[0]
        assert unreleased.index("### Added") < unreleased.index("### Changed") < unreleased.index("### Fixed")


class TestMain:
    def test_detect_prints_exactly_what_the_workflow_matches(self, monkeypatch, tmp_path, capsys):
        ref = tmp_path / "claudron.ref"
        ref.write_text("v0.9.0\n")
        monkeypatch.setattr(bump, "REF", ref)
        monkeypatch.setattr(bump, "latest_release", lambda token=None: "v0.10.0")
        assert bump.main(["detect"]) == 0
        assert capsys.readouterr().out == "tag=v0.10.0\nnewer=true\n"
        monkeypatch.setattr(bump, "latest_release", lambda token=None: "v0.9.0")
        bump.main(["detect"])
        assert capsys.readouterr().out == "tag=v0.9.0\nnewer=false\n"

    def test_detect_fails_on_a_latest_tag_it_cannot_read(self, monkeypatch, tmp_path):
        ref = tmp_path / "claudron.ref"
        ref.write_text("v0.9.0\n")
        monkeypatch.setattr(bump, "REF", ref)
        monkeypatch.setattr(bump, "latest_release", lambda token=None: "v1.0.0-rc1")
        with pytest.raises(ValueError):
            bump.main(["detect"])

    def test_changelog_refuses_a_bad_tag_before_writing(self, monkeypatch, tmp_path):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(CHANGELOG.format(unreleased=""))
        monkeypatch.setattr(bump, "CHANGELOG", changelog)
        with pytest.raises(ValueError):
            bump.main(["changelog", "latest"])
        assert changelog.read_text() == CHANGELOG.format(unreleased="")


class TestWorkflowFailsLoudly:
    def _job(self):
        return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["bump"]

    def test_steps_run_with_pipefail(self):
        """`detect | tee` must fail the step when detect fails: bash -eo pipefail, not the default sh."""
        assert self._job()["defaults"]["run"]["shell"] == "bash"

    def test_it_looks_for_a_pr_not_just_a_branch(self):
        step = next(s for s in self._job()["steps"] if s.get("id") == "branch")
        assert "gh pr list --head" in step["run"]
        assert "exit 1" in step["run"]  # a branch without a PR fails the run

    def test_a_failed_pr_lookup_fails_the_step_rather_than_reading_as_a_pr(self):
        """A failed command substitution inside `[ ]` escapes -e; assigned on its own line, it aborts."""
        import subprocess

        step = next(s for s in self._job()["steps"] if s.get("id") == "branch")["run"]
        assert "prs=$(gh pr list" in step and '[ "$prs" -gt 0 ]' in step
        script = "gh() { return 1; }\nGITHUB_OUTPUT=/dev/null\nname=claudron/v9.9.9\n" + step.split(
            'echo "name=$name" >> "$GITHUB_OUTPUT"\n', 1)[1]
        run = subprocess.run(["bash", "-eo", "pipefail", "-c", script], capture_output=True, text=True)
        assert run.returncode != 0 and "already has a PR" not in run.stdout
