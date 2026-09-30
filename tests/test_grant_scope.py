"""Tests for the grant-scope rule.

A skill's ``allowed-tools`` pre-approves commands with no prompt backstop, so the
rule must be an ALLOWLIST of accepted grant forms: anything not explicitly
recognised as safe is rejected, however it is spelled. This is the correction to
an earlier command-NAME denylist, which passed any spelling it did not enumerate
(a bare ``Bash`` entry, an absolute-path or version-suffixed interpreter, a
package runner, ``gh --repo x api``, and so on).

Accepted Bash forms:
  * an exact command with no wildcard (author-fixed; cannot be extended at call time);
  * an interpreter running a FIXED script path (optionally with a trailing arg
    wildcard) -- the repo's own script, not a free-form command;
  * a safe read/write git or gh SUBCOMMAND (``git diff *``, ``gh pr view *``);
  * a curated set of read-only shell utilities (``ls *``, ``cat *``, ``grep *``).
Everything else is rejected unless the skill sets
``disable-model-invocation: true``.

Reached by module attribute (``skill_checks.check_grant_scope``) so a missing
function fails as an assertion error, not a collection error that would silence
the file.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import skill_checks  # noqa: E402


def scope(fm):
    return skill_checks.check_grant_scope(fm)


def rejected(entry: str) -> bool:
    return bool(scope({"allowed-tools": entry}))


def accepted(entry: str) -> bool:
    return scope({"allowed-tools": entry}) == []


# --- forms that MUST be rejected (one row each) -----------------------------
# Every spelling below is broader than the allowlist permits (a free-form
# command, an unbounded wildcard, or an unsafe subcommand), yet each passed the
# earlier name-denylist gate.

REJECTED_FORMS = [
    # a grant of the whole shell
    "Bash",
    "Bash(*)",
    "Bash()",
    # interpreters reached by path, wrapper, version suffix, or glob'd script
    "Bash(/usr/bin/python3 *)",
    "Bash(env python3 *)",
    "Bash(./venv/bin/python *)",
    "Bash(python3.11 *)",
    "Bash(pypy3 *)",
    "Bash(python3 scripts/*)",
    "Bash(php *)",
    "Bash(java *)",
    "Bash(pwsh *)",
    "Bash(osascript *)",
    # interpreters with an inline-code flag, even bare
    "Bash(python3 -c *)",
    "Bash(node -e *)",
    "Bash(python3)",
    # package runners / installers (run project-defined code)
    "Bash(npm run *)",
    "Bash(npm install *)",
    "Bash(npm ci)",
    "Bash(pnpm run *)",
    "Bash(yarn run *)",
    "Bash(npx tsc *)",
    "Bash(pip *)",
    "Bash(pip install *)",
    "Bash(uv *)",
    "Bash(uvx *)",
    "Bash(pipx *)",
    # test / lint / build tools that load tree-controlled config or plugins
    "Bash(pytest *)",
    "Bash(eslint *)",
    "Bash(prettier *)",
    "Bash(tsc *)",
    "Bash(make *)",
    "Bash(cargo *)",
    "Bash(go *)",
    "Bash(black *)",
    "Bash(ruff *)",
    "Bash(mypy *)",
    # arbitrary-exec launchers and code-capable text tools
    "Bash(xargs *)",
    "Bash(env *)",
    "Bash(eval *)",
    "Bash(sudo *)",
    "Bash(ssh *)",
    "Bash(docker *)",
    "Bash(awk *)",
    "Bash(sed *)",
    "Bash(find *)",
    "Bash(tar *)",
    # secrets / unbounded deletion
    "Bash(printenv *)",
    "Bash(rm -rf *)",
    "Bash(rm -rf /tmp/heist-*)",
    "Bash(chmod *)",
    # git: config / clone / force / leading global flag / unsafe subcommand
    "Bash(git *)",
    "Bash(git clone *)",
    "Bash(git rebase *)",
    "Bash(git bisect *)",
    "Bash(git ls-remote *)",
    "Bash(git submodule *)",
    "Bash(git remote *)",
    "Bash(git push --force *)",
    "Bash(git -C . config *)",
    "Bash(git --config-env=core.pager=x log)",
    "Bash(git -c core.pager=x log)",
    # gh: api / auth / repo / infra subcommands (not issues or PRs)
    "Bash(gh *)",
    "Bash(gh config *)",
    "Bash(gh api *)",
    "Bash(gh auth *)",
    "Bash(gh secret *)",
    "Bash(gh codespace *)",
    "Bash(gh ssh-key *)",
    "Bash(gh repo *)",
    "Bash(gh release *)",
    "Bash(gh workflow *)",
    "Bash(gh run *)",
    "Bash(gh --repo x api *)",
    # gh whole-verb families and write verbs (vera #360 r3)
    "Bash(gh pr *)",
    "Bash(gh issue *)",
    "Bash(gh label *)",
    "Bash(gh browse *)",
    "Bash(gh pr merge *)",
    "Bash(gh issue create *)",
    "Bash(gh pr create *)",
    # git fetch reaches --upload-pack code exec
    "Bash(git fetch *)",
    # command runs any program; deno/bun run subcommands execute
    "Bash(command *)",
    "Bash(command git status)",
    "Bash(deno run *)",
    "Bash(deno task test)",
    "Bash(bun run *)",
    "Bash(bun x *)",
]


def test_every_rejected_form_is_rejected():
    missed = [e for e in REJECTED_FORMS if not rejected(e)]
    assert missed == [], f"allowlist accepted these over-broad grants: {missed}"


# --- forms that MUST be accepted (legitimate narrow grants) -----------------

ACCEPTED_FORMS = [
    # exact command, no wildcard
    "Bash(python3 scripts/validate-skills.py)",
    "Bash(command -v python3)",
    "Bash(claudron status)",
    # interpreter running a FIXED script, trailing arg wildcard
    "Bash(python3 scripts/validate-skills.py *)",
    # safe git subcommands
    "Bash(git status *)",
    "Bash(git diff *)",
    "Bash(git log *)",
    "Bash(git show *)",
    "Bash(git add *)",
    "Bash(git commit *)",
    "Bash(git checkout *)",
    "Bash(git branch *)",
    "Bash(git rev-parse *)",
    "Bash(git mv *)",
    "Bash(git reset *)",
    "Bash(git tag *)",
    "Bash(git stash *)",
    "Bash(git worktree *)",
    "Bash(git check-ignore *)",
    "Bash(git push *)",
    # safe gh subcommands
    "Bash(gh pr view *)",
    "Bash(gh issue view *)",
    "Bash(gh pr list *)",
    "Bash(gh pr diff *)",
    "Bash(gh issue list *)",
    "Bash(gh search *)",
    "Bash(command -v *)",
    # read-only utilities
    "Bash(ls *)",
    "Bash(cat *)",
    "Bash(grep *)",
    "Bash(diff *)",
    "Bash(wc *)",
    "Bash(stat *)",
    "Bash(which *)",
    "Bash(test *)",
    "Bash(lsof *)",
    "Bash(mkdir *)",
    "Bash(date *)",
    "Bash(mv *)",
    "Bash(cp *)",
    # safe claudron subcommands
    "Bash(claudron status *)",
    "Bash(claudron doctor --json)",
]


def test_every_accepted_form_is_accepted():
    wrongly = [e for e in ACCEPTED_FORMS if not accepted(e)]
    assert wrongly == [], f"allowlist rejected these legitimate grants: {wrongly}"


# --- non-Bash tools are out of this rule's scope (governs Bash only) --------

class TestNonBashOutOfScope:
    def test_plain_tools_clean(self):
        fm = {"allowed-tools": ["Read", "Write", "Edit", "Glob", "Grep", "Task", "Agent"]}
        assert scope(fm) == []

    def test_wildcard_non_bash_clean(self):
        fm = {"allowed-tools": ["Read(*)", "Write(*)", "Edit(*)", "WebFetch"]}
        assert scope(fm) == []


class TestNoGrants:
    def test_no_allowed_tools_is_clean(self):
        assert scope({"name": "x"}) == []

    def test_empty_allowed_tools_is_clean(self):
        assert scope({"allowed-tools": ""}) == []


class TestGitPushForceRejectedButPushAllowed:
    def test_plain_push_allowed(self):
        assert accepted("Bash(git push *)")

    def test_force_variants_rejected(self):
        for f in ("--force", "-f", "--force-with-lease"):
            assert rejected(f"Bash(git push {f} *)"), f


class TestInterpreterFixedScript:
    def test_fixed_script_exact(self):
        assert accepted("Bash(python3 scripts/validate-skills.py)")

    def test_fixed_script_trailing_wildcard(self):
        assert accepted("Bash(python3 scripts/crawl_page.py *)")

    def test_glob_in_script_path_rejected(self):
        assert rejected("Bash(python3 scripts/*)")

    def test_bare_interpreter_rejected(self):
        assert rejected("Bash(python3)")

    def test_inline_flag_rejected(self):
        for flag in ("-c", "-e", "--eval"):
            assert rejected(f"Bash(python3 {flag} *)"), flag


class TestEscapeHatch:
    def test_disable_model_invocation_exempts(self):
        fm = {"allowed-tools": "Bash(git *), Bash(python *)", "disable-model-invocation": True}
        assert scope(fm) == []

    def test_disable_model_invocation_false_does_not_exempt(self):
        fm = {"allowed-tools": "Bash(git *)", "disable-model-invocation": False}
        assert scope(fm)


class TestForms:
    def test_list_form_counts_each(self):
        fm = {"allowed-tools": ["Bash(git *)", "Read", "Bash(curl *)"]}
        assert len(scope(fm)) == 2

    def test_string_form_counts_each(self):
        fm = {"allowed-tools": "Bash(git *), Read, Bash(python *)"}
        assert len(scope(fm)) == 2


class TestWiredIntoValidator:
    def test_validate_skill_md_rejects_broad_grant(self, tmp_path):
        d = tmp_path / "demo"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\n"
            "name: demo\n"
            'description: "Use when demonstrating the grant-scope rule end to end."\n'
            "allowed-tools: Bash(git *)\n"
            "---\n\n" + ("body text " * 40) + "\n"
        )
        errors = skill_checks.validate_skill_md(d / "SKILL.md", dir_name="demo")
        assert any("git" in e for e in errors)

    def test_validate_skill_md_accepts_narrow_grant(self, tmp_path):
        d = tmp_path / "demo"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\n"
            "name: demo\n"
            'description: "Use when demonstrating the grant-scope rule end to end."\n'
            "allowed-tools: Bash(git status *), Bash(git diff *), Read\n"
            "---\n\n" + ("body text with git status and git diff " * 20) + "\n"
        )
        errors = skill_checks.validate_skill_md(d / "SKILL.md", dir_name="demo")
        assert errors == []
