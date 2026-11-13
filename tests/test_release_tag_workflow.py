"""`.github/workflows/release-tag.yml`: the baseline pin and the non-bump skip.

The workflow qualifies and publishes the commit a push to main brings. Its `bump` step decides which
commit the changelog gate compares that commit with (`origin/main`, read by
`release_candidate.qualify`) and whether the push is a release at all. Nothing else tests the file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-tag.yml"
PUBLISH_STEP = "Qualify and publish this exact candidate"
ZERO_SHA = "0" * 40


def steps():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["tag-and-release"]["steps"]


def bump_step():
    return next(step for step in steps() if step.get("id") == "bump")


def publish_step():
    return next(step for step in steps() if step.get("name") == PUBLISH_STEP)


class TestStructure:
    def test_the_bump_step_precedes_publishing_and_reads_the_replaced_tip_from_the_push_event(self):
        assert steps().index(bump_step()) < steps().index(publish_step())
        assert bump_step()["env"]["BEFORE"] == "${{ github.event.before }}"
        assert "${{" not in bump_step()["run"], "the script is run as written by TestScript"

    def test_publishing_runs_only_when_the_version_changed(self):
        assert publish_step()["if"] == "steps.bump.outputs.changed == 'true'"


# ─── the step's script, run for real against a throwaway history ──────

# jq is on ubuntu-latest; where CI is set a missing jq fails these tests instead of skipping them.
needs_jq = pytest.mark.skipif(shutil.which("jq") is None and not os.environ.get("CI"),
                              reason="the step reads versions with jq")

CHANGELOG_PRERELEASE = "# Changelog\n\n## [Unreleased]\n\n## [1.0.0]\n- Existing release.\n"
CHANGELOG_RELEASED = "# Changelog\n\n## [Unreleased]\n\n## [1.0.1]\n- New release.\n\n## [1.0.0]\n- Existing release.\n"
CHANGELOG_MOVED_ON = "# Changelog\n\n## [Unreleased]\n- A later merge.\n\n## [1.0.1]\n- New release.\n\n## [1.0.0]\n- Existing release.\n"


def git(cwd, *args):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return subprocess.check_output(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                                    *args], cwd=cwd, env=env, text=True, stderr=subprocess.PIPE).strip()


def commit_state(root, message, version, changelog, description="a plugin"):
    for host in ("claude", "cursor", "codex"):
        path = root / f".{host}-plugin"
        path.mkdir(exist_ok=True)
        (path / "plugin.json").write_text(json.dumps({"version": version, "description": description}))
    (root / "CHANGELOG.md").write_text(changelog)
    git(root, "add", ".")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def history(tmp_path):
    """before (1.0.0) -> release (1.0.1) -> a description-only edit -> a later merge on main."""
    root = tmp_path / "checkout"
    root.mkdir()
    git(root, "init", "-q")
    return root, {
        "before": commit_state(root, "before", "1.0.0", CHANGELOG_PRERELEASE),
        "release": commit_state(root, "release", "1.0.1", CHANGELOG_RELEASED),
        "reword": commit_state(root, "reword plugin.json", "1.0.1", CHANGELOG_RELEASED, description="reworded"),
        "later": commit_state(root, "a later merge", "1.0.1", CHANGELOG_MOVED_ON, description="reworded"),
    }


def at_push(root, sha, moving_tip):
    """The runner's starting state: the pushed commit checked out, origin/main at the moving tip of main."""
    git(root, "checkout", "-q", "--detach", sha)
    git(root, "update-ref", "refs/remotes/origin/main", moving_tip)


def run_bump(root, tmp_path, *, sha, before, moving_tip):
    """Run the workflow's script the way a runner does: `bash -e` and a GITHUB_OUTPUT file."""
    at_push(root, sha, moving_tip)
    output = tmp_path / "github_output"
    output.write_text("")
    env = dict(os.environ, BEFORE=before, GITHUB_SHA=sha, GITHUB_OUTPUT=str(output))
    proc = subprocess.run(["bash", "-e", "-c", bump_step()["run"]], cwd=root, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return output.read_text().strip(), proc.stdout, git(root, "rev-parse", "refs/remotes/origin/main")


@needs_jq
class TestScript:
    def test_a_version_bump_pins_the_baseline_to_the_tip_the_push_replaced(self, history, tmp_path):
        root, shas = history
        output, _, baseline = run_bump(root, tmp_path, sha=shas["release"], before=shas["before"],
                                       moving_tip=shas["later"])
        assert (output, baseline) == ("changed=true", shas["before"])

    def test_a_push_of_several_commits_compares_against_the_tip_it_replaced(self, history, tmp_path):
        """[release, reword] arrive together: the pushed tip's parent is the bump itself, not the baseline."""
        root, shas = history
        output, _, baseline = run_bump(root, tmp_path, sha=shas["reword"], before=shas["before"],
                                       moving_tip=shas["later"])
        assert (output, baseline) == ("changed=true", shas["before"])

    @pytest.mark.parametrize("before", [ZERO_SHA, "1" * 40, ""], ids=["all-zero", "not-in-history", "empty"])
    def test_an_unusable_before_falls_back_to_the_pushed_commits_parent_and_says_so(self, history, tmp_path, before):
        root, shas = history
        output, stdout, baseline = run_bump(root, tmp_path, sha=shas["release"], before=before,
                                            moving_tip=shas["later"])
        assert (output, baseline) == ("changed=true", shas["before"])
        assert "::warning::github.event.before is not in the fetched history" in stdout

    def test_a_plugin_json_edit_without_a_version_change_releases_nothing(self, history, tmp_path):
        root, shas = history
        output, stdout, _ = run_bump(root, tmp_path, sha=shas["reword"], before=shas["release"],
                                     moving_tip=shas["later"])
        assert output == "changed=false"
        assert "nothing to release" in stdout

    def test_the_pin_is_what_lets_the_changelog_gate_pass_once_main_has_moved(self, history, tmp_path):
        """Left at the moving tip the gate rejects the release commit; pinned, it passes (release_candidate)."""
        root, shas = history
        gate = [sys.executable, str(REPO_ROOT / "scripts" / "release_candidate.py"), "--check-changelog"]
        at_push(root, shas["release"], shas["later"])
        unpinned = subprocess.run(gate, cwd=root, capture_output=True, text=True)
        assert unpinned.returncode != 0
        assert "needs new meaningful [Unreleased] content" in unpinned.stdout + unpinned.stderr
        run_bump(root, tmp_path, sha=shas["release"], before=shas["before"], moving_tip=shas["later"])
        pinned = subprocess.run(gate, cwd=root, capture_output=True, text=True)
        assert pinned.returncode == 0, pinned.stderr
        assert "new meaningful release notes for 1.0.1" in pinned.stdout
