"""The Claudron-release bump: ``scripts/claudron_bump.py`` and the workflow that runs it."""

from __future__ import annotations

import json
import os
import re
import subprocess
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

    def test_it_does_not_say_the_workflow_opened_the_pr(self):
        """Actions may not open PRs here (#432): the fleet opens them, from the workflow's branch."""
        assert "Opened by" not in bump.add_changelog_line(CHANGELOG.format(unreleased=""), "v0.10.0")


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

    def test_it_does_not_say_the_workflow_opened_it(self):
        """The fleet opens these PRs with the same body (#432), so it can't claim the workflow did."""
        assert "before opening this PR" not in bump.pr_body("v0.10.0", "v0.9.0", "pass", "pass")


class TestWorkflow:
    def test_it_parses_and_runs_on_a_schedule_and_by_hand(self):
        doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        triggers = doc.get("on") or doc.get(True)  # YAML 1.1 reads a bare `on` key as True
        assert "schedule" in triggers and "workflow_dispatch" in triggers
        assert doc["permissions"] == {"contents": "write", "pull-requests": "write", "issues": "write"}

    def test_one_run_at_a_time(self):
        """Two overlapping runs (a dispatch during the scheduled one) could each find no issue and each open one."""
        doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        assert doc.get("concurrency") == {"group": "claudron-release", "cancel-in-progress": False}

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

    def test_a_failed_pr_lookup_fails_the_step_rather_than_reading_as_a_pr(self):
        """A failed command substitution inside `[ ]` escapes -e; assigned on its own line, it aborts."""
        step = next(s for s in self._job()["steps"] if s.get("id") == "branch")["run"]
        assert "prs=$(gh pr list" in step and '[ "$prs" -gt 0 ]' in step
        script = "gh() { return 1; }\nGITHUB_OUTPUT=/dev/null\nname=claudron/v9.9.9\n" + step.split(
            'echo "name=$name" >> "$GITHUB_OUTPUT"\n', 1)[1]
        run = subprocess.run(["bash", "-eo", "pipefail", "-c", script], capture_output=True, text=True)
        assert run.returncode != 0 and "already has a PR" not in run.stdout


def issue_page(nodes, total, cursor=None):
    """One page of the issues query, as `gh api graphql` prints it."""
    return json.dumps({"data": {"repository": {"issues": {
        "totalCount": total, "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": nodes}}}})


def issue_row(number, tag=None, title=None, state="OPEN"):
    return {"number": number, "title": title or bump.issue_title(tag), "state": state,
            "url": f"https://github.com/o/r/issues/{number}"}


class FakeGh:
    """`gh` for the issue door: answers the issues query a page at a time and records every call.

    Like GitHub, it leaves out the rows of any state the query's `states:` does not ask for.
    """

    def __init__(self, *pages, created="https://github.com/o/r/issues/99", fail=None):
        self.pages, self.created, self.fail, self.calls = list(pages), created, fail, []

    def __call__(self, args, input=None):
        self.calls.append((list(args), input))
        if self.fail == args[:2]:
            raise subprocess.CalledProcessError(1, ["gh", *args], output="", stderr="HTTP 502: Bad Gateway")
        if args[:2] == ["api", "graphql"]:
            return self.in_states(self.pages.pop(0), next(arg for arg in args if arg.startswith("query=")))
        if args[:2] == ["issue", "create"]:
            return self.created + "\n"
        raise AssertionError(f"unexpected gh call: {args}")

    @staticmethod
    def in_states(page, query):
        """``page`` without the rows of any state ``query`` does not ask for, counted without them."""
        if "states" not in query:
            return page
        asked = re.search(r"\bstates: \[([A-Z, ]*)\]", query)
        assert asked, "this fake reads `states:` only as a list of literals"
        states = re.findall(r"[A-Z]+", asked.group(1))
        try:
            doc = json.loads(page)
            issues = doc["data"]["repository"]["issues"]
        except (ValueError, KeyError, TypeError):
            return page  # an unreadable page goes out as it is
        kept = [node for node in issues["nodes"] if node["state"] in states]
        issues["totalCount"] -= len(issues["nodes"]) - len(kept)
        issues["nodes"] = kept
        return json.dumps(doc)

    def created_issues(self):
        return [call for call in self.calls if call[0][:2] == ["issue", "create"]]


class TestIssue:
    """When the PR can't be opened, one issue per release asks the fleet to open it."""

    def test_only_the_exact_title_is_the_releases_issue(self):
        rows = [issue_row(7, "v0.1.0"), issue_row(8, title=bump.issue_title("v0.10.0") + " (done?)")]
        assert bump.find_issue(rows, "v0.10.0") is None
        assert bump.find_issue(rows, "v0.1.0")["number"] == 7

    def test_a_closed_issue_is_still_the_releases(self):
        assert bump.find_issue([issue_row(5, "v0.10.0", state="CLOSED")], "v0.10.0")["number"] == 5

    def test_of_two_the_first_opened_is_the_one(self):
        assert bump.find_issue([issue_row(12, "v0.10.0"), issue_row(5, "v0.10.0")], "v0.10.0")["number"] == 5

    def test_the_body_says_how_to_land_the_move(self):
        body = bump.issue_body("v0.10.0", "v0.9.0")
        for needed in ("`claudron/v0.10.0`", "`Move to Claudron v0.10.0`",
                       "python3 scripts/claudron_bump.py body v0.10.0 v0.9.0", "Closes"):
            assert needed in body, needed
        assert "`make check` passed" not in body and "**failed**" not in body

    def test_the_body_carries_the_runs_results_when_it_has_them(self):
        body = bump.issue_body("v0.10.0", "v0.9.0", "pass", "fail", "https://github.com/o/r/actions/runs/1")
        assert "`make check` passed" in body and "`make test-contract` **failed**" in body
        assert "https://github.com/o/r/actions/runs/1" in body


class TestIssueListing:
    """The issues are read whole or not at all: a short listing must never read as "no issue"."""

    def test_it_reads_every_page(self):
        gh = FakeGh(issue_page([issue_row(1, "v0.8.0"), issue_row(2, "v0.9.0")], 3, cursor="c1"),
                    issue_page([issue_row(3, "v0.10.0")], 3))
        assert [row["number"] for row in bump.list_issues("o/r", gh=gh)] == [1, 2, 3]
        first, second = (call[0] for call in gh.calls)
        assert "after=c1" in second and not [a for a in first if a.startswith("after=")]

    def test_it_asks_for_closed_issues_too(self):
        """A release's issue closed while its branch still waits is still its issue, so the read must return it."""
        gh = FakeGh(issue_page([issue_row(4, "v0.10.0", state="CLOSED"), issue_row(5, "v0.9.0")], 2))
        assert [row["number"] for row in bump.list_issues("o/r", gh=gh)] == [4, 5]

    @pytest.mark.parametrize("pages", [
        [issue_page([issue_row(1, title="An issue")], 228)],  # no next page, with 227 unread
        [issue_page([], 5)],  # an empty page where there are issues
        [json.dumps({"data": {"repository": {"issues": {
            "totalCount": 2, "pageInfo": {"hasNextPage": True, "endCursor": None}, "nodes": []}}}})],
        [json.dumps({"errors": [{"message": "Something went wrong"}]})],
        [json.dumps({"data": {"repository": None}})],
        ["not json"],
    ], ids=["short", "empty", "no-cursor", "errors", "no-repository", "unparsed"])
    def test_a_listing_that_does_not_add_up_fails(self, pages):
        with pytest.raises(RuntimeError):
            bump.list_issues("o/r", gh=FakeGh(*pages))

    def test_nothing_is_opened_when_the_listing_fails(self):
        gh = FakeGh(issue_page([], 5))
        with pytest.raises(RuntimeError):
            bump.ensure_issue("o/r", "v0.10.0", "v0.9.0", gh=gh)
        assert gh.created_issues() == []


class TestEnsureIssue:
    def test_a_release_with_an_issue_opens_none(self):
        gh = FakeGh(issue_page([issue_row(4, "v0.10.0", state="CLOSED")], 1))
        state, issue = bump.ensure_issue("o/r", "v0.10.0", "v0.9.0", gh=gh)
        assert (state, issue["number"]) == ("found", 4) and gh.created_issues() == []

    def test_a_release_without_one_opens_exactly_one(self):
        gh = FakeGh(issue_page([issue_row(1, "v0.9.0")], 1))
        state, issue = bump.ensure_issue("o/r", "v0.10.0", "v0.9.0", "pass", "pass", gh=gh)
        (args, body), = gh.created_issues()
        assert state == "opened" and issue["url"] == "https://github.com/o/r/issues/99"
        assert args[args.index("--title") + 1] == bump.issue_title("v0.10.0")
        assert args[args.index("--repo") + 1] == "o/r"
        assert body == bump.issue_body("v0.10.0", "v0.9.0", "pass", "pass")


class TestIssueMain:
    def _env(self, monkeypatch, gh):
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
        monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
        monkeypatch.setenv("GITHUB_RUN_ID", "41")
        monkeypatch.setattr(bump, "run_gh", gh)

    def test_it_opens_the_issue_and_prints_where(self, monkeypatch, capsys):
        gh = FakeGh(issue_page([], 0))
        self._env(monkeypatch, gh)
        assert bump.main(["issue", "v0.10.0", "v0.9.0", "pass", "fail"]) == 0
        assert "https://github.com/o/r/issues/99" in capsys.readouterr().out
        (_, body), = gh.created_issues()
        assert "https://github.com/o/r/actions/runs/41" in body and "`make test-contract` **failed**" in body

    def test_a_closed_issue_it_finds_is_named_in_a_warning(self, monkeypatch, capsys):
        gh = FakeGh(issue_page([issue_row(4, "v0.10.0", state="CLOSED")], 1))
        self._env(monkeypatch, gh)
        assert bump.main(["issue", "v0.10.0", "v0.9.0"]) == 0
        out = capsys.readouterr().out
        assert "::warning::" in out and "#4" in out and gh.created_issues() == []

    def test_an_open_issue_it_finds_passes_and_opens_nothing(self, monkeypatch, capsys):
        """Every daily run takes this path while the branch waits: failing here is #432's daily red run again."""
        gh = FakeGh(issue_page([issue_row(4, "v0.10.0")], 1))
        self._env(monkeypatch, gh)
        assert bump.main(["issue", "v0.10.0", "v0.9.0"]) == 0
        out = capsys.readouterr().out
        assert "#4" in out and "::warning::" not in out and gh.created_issues() == []

    def test_a_failed_listing_fails_the_command(self, monkeypatch, capsys):
        gh = FakeGh(fail=["api", "graphql"])
        self._env(monkeypatch, gh)
        assert bump.main(["issue", "v0.10.0", "v0.9.0"]) == 1
        assert "HTTP 502" in capsys.readouterr().err and gh.created_issues() == []

    @pytest.mark.parametrize("args", [["latest", "v0.9.0"], ["v0.10.0", "main"]])
    def test_a_bad_tag_is_refused_before_any_call(self, monkeypatch, args):
        gh = FakeGh()
        self._env(monkeypatch, gh)
        with pytest.raises(ValueError):
            bump.main(["issue", *args])
        assert gh.calls == []

    @pytest.mark.parametrize("args", [["v0.10.0"], ["v0.10.0", "v0.9.0", "pass"],
                                      ["v0.10.0", "v0.9.0", "pass", "maybe"]])
    def test_other_shapes_are_a_usage_error(self, monkeypatch, args):
        gh = FakeGh()
        self._env(monkeypatch, gh)
        assert bump.main(["issue", *args]) == 2 and gh.calls == []

    def test_without_a_repository_it_reads_nothing(self, monkeypatch):
        gh = FakeGh()
        self._env(monkeypatch, gh)
        monkeypatch.delenv("GITHUB_REPOSITORY")
        assert bump.main(["issue", "v0.10.0", "v0.9.0"]) == 2 and gh.calls == []


# Each input a step script reads: the expression the step's `env:` must give it, and a value to run it with.
STEP_ENV = {
    "GH_TOKEN": ("${{ github.token }}", "a-token"),
    "TAG": ("${{ steps.latest.outputs.tag }}", "v9.9.9"),
    "PINNED": ("${{ steps.latest.outputs.pinned }}", "v9.9.8"),
    "BRANCH": ("${{ steps.branch.outputs.name }}", "claudron/v9.9.9"),
    "CHECK": ("${{ steps.move.outputs.check }}", "pass"),
    "CONTRACT": ("${{ steps.move.outputs.contract }}", "pass"),
}

# `gh`, `git` and `python3` as shell functions: each records its call, and the test sets what it returns.
STUBS = """
gh() { echo "gh $*" >> "$CALLS"; case "$1 $2" in "pr list") echo "$PRS" ;; "pr create") return "$PR_CREATE_RC" ;; esac; }
git() { echo "git $*" >> "$CALLS"; case "$1" in ls-remote) return "$LS_REMOTE_RC" ;; push) return "$PUSH_RC" ;; esac; }
python3() { echo "python3 $*" >> "$CALLS"; case "$2" in issue) return "$ISSUE_RC" ;; body) echo "a body" ;; esac; }
"""


class TestWorkflowLeavesTheIssue:
    """The steps' own scripts, run under the job's shell (bash -eo pipefail) with `gh`, `git` and `python3` stubbed."""

    def _run(self, step_id, tmp_path, **knobs):
        steps = [s for s in yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["bump"]["steps"]
                 if s.get("id") == step_id]
        assert len(steps) == 1, f"one step with id {step_id}"
        step = steps[0]
        assert "${{" not in step["run"], "the script takes its inputs from env:, so it runs here as written"
        out, calls = tmp_path / "output", tmp_path / "calls"
        out.touch()
        calls.touch()
        env = {"PATH": os.environ["PATH"], "GITHUB_OUTPUT": str(out), "RUNNER_TEMP": str(tmp_path),
               "CALLS": str(calls), "PRS": "0", "LS_REMOTE_RC": "2", "PR_CREATE_RC": "0", "PUSH_RC": "0",
               "ISSUE_RC": "0"}
        for name, expression in step.get("env", {}).items():
            assert STEP_ENV[name][0] == expression, name
            env[name] = STEP_ENV[name][1]
        env.update({name.upper(): str(value) for name, value in knobs.items()})
        run = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", STUBS + step["run"]],
                             env=env, capture_output=True, text=True)
        return run, out.read_text().splitlines(), calls.read_text().splitlines()

    def test_a_release_with_a_pr_stops_cleanly(self, tmp_path):
        run, out, calls = self._run("branch", tmp_path, prs=1)
        assert run.returncode == 0 and "exists=true" in out and "already has a PR" in run.stdout
        assert not [c for c in calls if c.startswith(("git", "python3"))]

    def test_a_branch_waiting_for_its_pr_leaves_its_issue_and_passes(self, tmp_path):
        run, out, calls = self._run("branch", tmp_path, prs=0, ls_remote_rc=0)
        assert run.returncode == 0, run.stdout + run.stderr
        assert "exists=true" in out and "::error::" not in run.stdout
        assert "python3 scripts/claudron_bump.py issue v9.9.9 v9.9.8" in calls

    def test_a_new_release_moves(self, tmp_path):
        run, out, calls = self._run("branch", tmp_path, prs=0, ls_remote_rc=2)
        assert run.returncode == 0 and "exists=false" in out
        assert not [c for c in calls if c.startswith("python3")]

    def test_a_branch_whose_issue_cannot_be_left_fails(self, tmp_path):
        run, _, _ = self._run("branch", tmp_path, prs=0, ls_remote_rc=0, issue_rc=1)
        assert run.returncode != 0

    def test_an_opened_pr_leaves_no_issue(self, tmp_path):
        run, _, calls = self._run("pr", tmp_path)
        assert run.returncode == 0, run.stdout + run.stderr
        create = next(i for i, c in enumerate(calls) if c.startswith("gh pr create"))
        assert calls.index("git push origin claudron/v9.9.9") < create
        assert "--head claudron/v9.9.9 --title Move to Claudron v9.9.9" in calls[create]
        assert not [c for c in calls if " issue " in c]

    def test_a_pr_that_cannot_be_opened_leaves_the_issue_and_passes(self, tmp_path):
        run, _, calls = self._run("pr", tmp_path, pr_create_rc=1, check="fail")
        assert run.returncode == 0, run.stdout + run.stderr
        assert "python3 scripts/claudron_bump.py issue v9.9.9 v9.9.8 fail pass" in calls

    def test_when_neither_the_pr_nor_the_issue_can_be_left_it_fails(self, tmp_path):
        run, _, _ = self._run("pr", tmp_path, pr_create_rc=1, issue_rc=1)
        assert run.returncode != 0

    def test_a_failed_push_stops_before_the_pr(self, tmp_path):
        run, _, calls = self._run("pr", tmp_path, push_rc=1)
        assert run.returncode != 0 and not [c for c in calls if c.startswith("gh pr create")]

    def test_a_failed_check_still_opens_a_draft(self, tmp_path):
        run, _, calls = self._run("pr", tmp_path, check="fail")
        assert run.returncode == 0 and [c for c in calls if c.startswith("gh pr create --draft ")]


class TestWorkflowWiring:
    def test_every_step_output_it_reads_is_one_that_step_writes(self):
        """A misspelt output reads as an empty string in Actions, and nothing fails."""
        text = WORKFLOW.read_text(encoding="utf-8")
        steps = {s["id"]: s for s in yaml.safe_load(text)["jobs"]["bump"]["steps"] if "id" in s}
        reads = set(re.findall(r"steps\.([\w-]+)\.outputs\.([\w-]+)", text))
        assert {("latest", "tag"), ("branch", "name"), ("move", "check")} <= reads  # the pattern finds them
        for step_id, key in sorted(reads):
            run = steps[step_id]["run"]
            written = set(re.findall(r'echo "([\w-]+)=', run))
            if "claudron_bump.py detect" in run:
                written |= {"tag", "newer"}  # what detect prints (TestMain)
            assert key in written, f"steps.{step_id}.outputs.{key} is read, but that step never writes it"
