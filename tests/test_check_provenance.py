"""Tests for scripts/check_provenance.py — the mechanical author-provenance gate.

The gate reads a GitHub resource's ``author_association`` and answers trusted /
untrusted / unreadable, failing CLOSED (unreadable is never trusted). It reads
the field over the REST API (``gh api ... --jq .author_association``), because
``gh issue view --json authorAssociation`` / ``gh pr view --json
authorAssociation`` are rejected by gh 2.92 (`Unknown JSON field`).

Reached by module attribute so a missing function fails as an assertion error,
not a collection error that silences the file. No network: the gh call is
stubbed via a fake gh on PATH.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_provenance as cp  # noqa: E402

SCRIPT = REPO_ROOT / "scripts" / "check_provenance.py"


class TestClassify:
    def test_trusted_values(self):
        for a in ("OWNER", "MEMBER", "COLLABORATOR"):
            verdict, code = cp.classify(a)
            assert verdict.startswith("TRUSTED"), a
            assert code == 0, a

    def test_untrusted_values(self):
        for a in ("CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "NONE", "FIRST_TIMER", "MANNEQUIN"):
            verdict, code = cp.classify(a)
            assert verdict.startswith("UNTRUSTED"), a
            assert code == 2, a

    def test_none_is_unreadable_not_trusted(self):
        verdict, code = cp.classify(None)
        assert verdict.startswith("UNREADABLE")
        assert code == 3

    def test_empty_is_unreadable(self):
        verdict, code = cp.classify("")
        assert code == 3

    def test_unknown_value_is_untrusted_not_trusted(self):
        # a value gh never returns must not be read as trusted (fail closed)
        verdict, code = cp.classify("SOMETHING_NEW")
        assert code == 2


class TestApiPath:
    def test_issue(self):
        assert cp.api_path("issue", "o", "r", "5") == "repos/o/r/issues/5"

    def test_pr(self):
        assert cp.api_path("pr", "o", "r", "5") == "repos/o/r/pulls/5"

    def test_issue_comment(self):
        assert cp.api_path("issue-comment", "o", "r", "99") == "repos/o/r/issues/comments/99"

    def test_pr_comment(self):
        assert cp.api_path("pr-comment", "o", "r", "99") == "repos/o/r/pulls/comments/99"

    def test_unknown_kind_raises(self):
        import pytest

        with pytest.raises(ValueError):
            cp.api_path("branch", "o", "r", "5")


def _fake_gh(tmp_path, body: str, rc: int = 0) -> str:
    """Write a fake gh onto PATH that prints body and exits rc."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    gh = d / "gh"
    gh.write_text("#!/usr/bin/env bash\n" + body + f"\nexit {rc}\n")
    gh.chmod(0o755)
    return str(gh)


class TestReadAssocFailsClosed:
    def test_missing_gh_is_unreadable(self):
        assoc, reason = cp.read_assoc("repos/o/r/issues/1", gh="/nonexistent/gh-xyz")
        assert assoc is None
        assert reason

    def test_gh_nonzero_is_unreadable(self, tmp_path):
        gh = _fake_gh(tmp_path, 'echo "gh: Not Found" >&2', rc=1)
        assoc, reason = cp.read_assoc("repos/o/r/issues/1", gh=gh)
        assert assoc is None
        assert reason

    def test_gh_empty_output_is_unreadable(self, tmp_path):
        gh = _fake_gh(tmp_path, 'echo ""', rc=0)
        assoc, reason = cp.read_assoc("repos/o/r/issues/1", gh=gh)
        assert assoc is None

    def test_gh_success_returns_value(self, tmp_path):
        gh = _fake_gh(tmp_path, 'echo "MEMBER"', rc=0)
        assoc, reason = cp.read_assoc("repos/o/r/issues/1", gh=gh)
        assert assoc == "MEMBER"
        assert reason is None


class TestMainExit:
    def _run(self, args, gh):
        env = {"PATH": str(Path(gh).parent) + ":/usr/bin:/bin"}
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, env=env,
        )

    def test_trusted_exits_0(self, tmp_path):
        gh = _fake_gh(tmp_path, 'echo "MEMBER"')
        r = self._run(["o", "r", "issue", "1"], gh)
        assert r.returncode == 0, r.stderr
        assert "TRUSTED" in r.stdout

    def test_untrusted_exits_2(self, tmp_path):
        gh = _fake_gh(tmp_path, 'echo "NONE"')
        r = self._run(["o", "r", "issue", "1"], gh)
        assert r.returncode == 2
        assert "UNTRUSTED" in r.stdout

    def test_unreadable_exits_3(self, tmp_path):
        gh = _fake_gh(tmp_path, 'echo "boom" >&2', rc=1)
        r = self._run(["o", "r", "issue", "1"], gh)
        assert r.returncode == 3
        assert "UNREADABLE" in r.stdout


class TestNoArbitraryProgramViaGh:
    """vera #361: the gate must not run a caller-named program. There is no `--gh`
    argument, so an argv (or an injection that controls it) cannot point the gate
    at another binary; `gh` is resolved from PATH. A `--gh <program>` invocation is
    rejected and the named program never runs."""

    def test_gh_flag_is_rejected_and_the_program_never_runs(self, tmp_path):
        marker = tmp_path / "ran.marker"
        evil = tmp_path / "evil"
        evil.write_text(f'#!/usr/bin/env bash\ntouch {marker}\n')
        evil.chmod(0o755)
        # a real gh on PATH too, so a failure would be "ran gh", not "no gh"
        gh = _fake_gh(tmp_path, 'echo "MEMBER"')
        env = {"PATH": str(Path(gh).parent) + ":/usr/bin:/bin"}
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "o", "r", "issue", "1", "--gh", str(evil)],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode != 0, "an unknown --gh argument must be refused"
        assert not marker.exists(), "the caller-named program was run"

    def test_the_cli_has_no_gh_option(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"},
        )
        assert "--gh" not in r.stdout
