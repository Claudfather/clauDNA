"""CI touched-set scoping (`skill_checks.get_touched_skills`, `partition_errors`).

In CI pull-request mode a skill's errors block only when the PR touches that skill. A diff that
changes the validator rules, their data files or the contracts they enforce touches no skill, yet
can change the verdict on every skill, so it must run full blocking validation (the same verdict
the merge push gets with FULL_VALIDATE=1). These tests pin that decision without running git.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import get_touched_skills, partition_errors


@pytest.fixture
def ci(monkeypatch):
    """A pull-request run: GITHUB_ACTIONS set, no escape hatch, an overridable `git diff` answer."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("FULL_VALIDATE", raising=False)
    monkeypatch.delenv("PR_LABELS", raising=False)
    calls: list[dict] = []

    def diff(*paths: str, returncode: int = 0, raises: Exception | None = None):
        def fake_run(cmd, **kwargs):
            calls.append({"cmd": cmd, **kwargs})
            if raises is not None:
                raise raises
            return SimpleNamespace(returncode=returncode, stdout="\n".join(paths) + "\n", stderr="boom")

        monkeypatch.setattr(subprocess, "run", fake_run)
        return calls

    return diff


class TestEscapeHatches:
    def test_outside_ci_everything_blocks(self, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        assert get_touched_skills() is None

    def test_full_validate_env_blocks_everything(self, ci, monkeypatch):
        ci("skills/foo/SKILL.md")
        monkeypatch.setenv("FULL_VALIDATE", "1")
        assert get_touched_skills() is None

    def test_full_validate_label_blocks_everything(self, ci, monkeypatch):
        ci("skills/foo/SKILL.md")
        monkeypatch.setenv("PR_LABELS", "docs,full-validate")
        assert get_touched_skills() is None


class TestSkillScoping:
    def test_a_skill_edit_scopes_to_that_skill(self, ci):
        ci("skills/foo/SKILL.md", "skills/bar/notes/x.md", "README.md")
        assert get_touched_skills() == {"foo", "bar"}

    def test_a_change_touching_no_skill_and_no_validator_input_is_empty(self, ci):
        ci("README.md", "tests/test_something.py", "documentation/guides/X.md")
        assert get_touched_skills() == set()

    def test_shared_material_runs_everything(self, ci):
        ci("skills/_shared/x.md")
        assert get_touched_skills() is None


class TestValidatorInputsRunFullValidation:
    @pytest.mark.parametrize(
        "path",
        [
            "scripts/skill_checks.py",
            "scripts/catalog-budget.json",
            "scripts/removed-skills.txt",
            "scripts/validate-skills.py",
            "SKILL_CONTRACT.md",
            "AGENT_CONTRACT.md",
            "contracts/claudron.json",
        ],
    )
    def test_a_validator_or_contract_input_blocks_everything(self, ci, path, capsys):
        ci("README.md", path)
        assert get_touched_skills() is None
        assert "validator or contract input changed" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("skills/scripts/SKILL.md", {"scripts"}),
            ("documentation/scripts/x.md", set()),
            ("NOTSKILL_CONTRACT.md", set()),
            ("contractsX/x.json", set()),
        ],
    )
    def test_lookalike_paths_do_not_trigger_it(self, ci, path, expected):
        ci(path)
        assert get_touched_skills() == expected


class TestUnreadableDiffFallsBackToFullValidation:
    def test_a_failed_git_diff_blocks_everything(self, ci, capsys):
        ci("skills/foo/SKILL.md", returncode=128)
        assert get_touched_skills() is None
        assert "git diff failed" in capsys.readouterr().err

    def test_a_missing_git_blocks_everything(self, ci, capsys):
        ci(raises=FileNotFoundError("git"))
        assert get_touched_skills() is None
        assert "git is not installed" in capsys.readouterr().err

    def test_the_diff_runs_in_the_repository_not_the_callers_cwd(self, ci):
        calls = ci("README.md")
        get_touched_skills()
        assert Path(calls[0]["cwd"]) == REPO_ROOT
        assert calls[0]["cmd"][:3] == ["git", "diff", "--name-only"]


class TestPartitionErrors:
    ALL = {"touched": ["t1"], "untouched": ["u1", "u2"]}

    def test_no_scoping_blocks_everything_and_cross_skill_errors_attach_to_their_target(self):
        cross = [({"touched", "untouched"}, "untouched", "dup")]
        blocking, demoted = partition_errors(self.ALL, cross, None)
        assert blocking == {"touched": ["t1"], "untouched": ["u1", "u2", "dup"]}
        assert demoted == {}

    def test_no_scoping_does_not_mutate_its_input(self):
        original = {name: list(errors) for name, errors in self.ALL.items()}
        partition_errors(self.ALL, [({"touched"}, "touched", "x")], None)
        assert self.ALL == original

    def test_an_untouched_skills_error_is_demoted(self):
        blocking, demoted = partition_errors(self.ALL, [], {"touched"})
        assert blocking == {"touched": ["t1"]}
        assert demoted == {"untouched": ["u1", "u2"]}

    def test_a_cross_skill_error_blocks_when_any_participant_is_touched(self):
        cross = [({"touched", "untouched"}, "untouched", "dup")]
        blocking, demoted = partition_errors(self.ALL, cross, {"touched"})
        assert blocking["untouched"] == ["dup"]
        assert "untouched" in demoted and "dup" not in demoted["untouched"]

    def test_a_cross_skill_error_is_demoted_when_no_participant_is_touched(self):
        cross = [({"a", "b"}, "a", "dup")]
        blocking, demoted = partition_errors({}, cross, {"touched"})
        assert blocking == {}
        assert demoted == {"a": ["dup"]}

    def test_an_empty_touched_set_demotes_everything(self):
        blocking, demoted = partition_errors(self.ALL, [], set())
        assert blocking == {}
        assert set(demoted) == {"touched", "untouched"}
