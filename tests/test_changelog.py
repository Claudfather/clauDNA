"""The contributor gate accepts meaningful additions and exact release notes."""

import json
import subprocess

import pytest

import test_release_candidate as release_cases
from test_release_candidate import commit, git

repo = release_cases.repo


def gate(root):
    return subprocess.run(["bash", "scripts/check-changelog.sh"], cwd=root, text=True, capture_output=True)


def reset_to_contributor(root):
    for host in ("claude", "cursor", "codex"):
        (root / f".{host}-plugin/plugin.json").write_text(json.dumps({"version": "1.0.0"}))


def test_contributor_new_unreleased_entry_passes(repo):
    reset_to_contributor(repo)
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n### Fixed\n- Correct a concrete bug.\n")
    result = gate(repo)
    assert result.returncode == 0, result.stderr
    assert "meaningful unreleased" in result.stdout


@pytest.mark.parametrize("notes", ["", "### Added\n", "<!-- comment only -->\n", "- \n",
                                   "[link]: https://example.invalid\n"])
def test_contributor_empty_heading_comment_or_link_only_fails(repo, notes):
    reset_to_contributor(repo)
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n" + notes)
    assert gate(repo).returncode != 0


def test_missing_unreleased_fails_even_with_new_version_notes(repo):
    (repo / "CHANGELOG.md").write_text("## [1.0.1]\n- A real entry.\n")
    assert "missing [Unreleased]" in gate(repo).stderr


def test_unchanged_changelog_fails_for_contributor(repo):
    reset_to_contributor(repo)
    (repo / "CHANGELOG.md").write_text(git(repo, "show", "origin/main:CHANGELOG.md"))
    assert gate(repo).returncode != 0


def test_deleting_unreleased_content_is_not_a_new_entry(repo):
    reset_to_contributor(repo)
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n- Existing unfinished work.\n")
    git(repo, "update-ref", "refs/remotes/origin/main", commit(repo))
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n")
    commit(repo)
    assert gate(repo).returncode != 0


def test_release_helper_versioned_notes_pass_with_empty_unreleased(repo):
    result = gate(repo)
    assert result.returncode == 0, result.stderr
    assert "release notes for 1.0.1" in result.stdout


@pytest.mark.parametrize("content", ["## [1.0.2]\n- Wrong version.\n", "## [1.0.1]\n### Fixed\n"])
def test_wrong_or_heading_only_release_notes_fail(repo, content):
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n\n" + content)
    assert gate(repo).returncode != 0


def test_notes_for_unchanged_manifest_version_do_not_bypass_contributor_rule(repo):
    reset_to_contributor(repo)
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [1.0.0]\n- Changed shipped notes.\n")
    assert gate(repo).returncode != 0


def test_exact_baseline_has_nothing_to_gate(repo):
    git(repo, "update-ref", "refs/remotes/origin/main", git(repo, "rev-parse", "HEAD"))
    assert gate(repo).returncode == 0


def test_missing_baseline_is_not_silently_accepted(repo):
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    assert "origin/main is required" in gate(repo).stderr
