"""Tests for the grant-scope rule: a skill's allowed-tools may not pre-approve a
whole command family with a wildcard argument.

A wildcard argument defeats prefix matching, so `Bash(python *)` pre-approves
arbitrary code, `Bash(curl *)` pre-approves arbitrary network, and `Bash(git *)`
/ `Bash(gh *)` pre-approve the code-exec and data-egress subcommands (git -c,
git config, gh api, gh auth token, gh gist, ...). The rule rejects the
whole-family wildcards and the named dangerous git/gh subcommands, and accepts
concrete commands, read-only git/gh subcommands, and ordinary build/test tools.

Reached by module attribute (skill_checks.check_grant_scope) so a missing
function fails these tests as assertion errors rather than a collection error
that would silence the whole file.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import skill_checks


def scope(fm):
    return skill_checks.check_grant_scope(fm)


class TestNoGrants:
    def test_no_allowed_tools_is_clean(self):
        assert scope({"name": "x"}) == []

    def test_empty_allowed_tools_is_clean(self):
        assert scope({"allowed-tools": ""}) == []

    def test_non_bash_tools_are_clean(self):
        fm = {"allowed-tools": ["Read", "Write", "Edit", "Glob", "Grep", "Task", "Agent"]}
        assert scope(fm) == []


class TestInterpreterFamilyWildcard:
    def test_python_wildcard_rejected(self):
        errs = scope({"allowed-tools": "Bash(python *)"})
        assert len(errs) == 1
        assert "python" in errs[0]

    def test_python3_node_ruby_bash_sh_rejected(self):
        for fam in ("python3", "node", "ruby", "perl", "bash", "sh", "deno", "bun"):
            errs = scope({"allowed-tools": f"Bash({fam} *)"})
            assert errs, f"{fam} * should be rejected"
            assert fam in errs[0]

    def test_bare_interpreter_rejected(self):
        # `Bash(python)` with no argument still resolves to arbitrary python at
        # the REPL / stdin; a bare family grant is a whole-family grant.
        errs = scope({"allowed-tools": "Bash(python3)"})
        assert errs

    def test_inline_code_flag_rejected(self):
        for flag in ("-c", "-e"):
            errs = scope({"allowed-tools": f"Bash(python3 {flag} *)"})
            assert errs, f"python3 {flag} should be rejected"

    def test_concrete_script_allowed(self):
        # A fixed script path is an exact command, the advisory's accepted form.
        assert scope({"allowed-tools": "Bash(python3 scripts/new-skill.py)"}) == []

    def test_concrete_script_with_trailing_args_allowed(self):
        assert scope({"allowed-tools": "Bash(python3 scripts/new-skill.py *)"}) == []


class TestPackageRunnerWildcard:
    def test_family_wildcards_rejected(self):
        for fam in ("npx", "npm", "pnpm", "yarn"):
            errs = scope({"allowed-tools": f"Bash({fam} *)"})
            assert errs, f"{fam} * should be rejected"

    def test_exec_and_dlx_forms_rejected(self):
        for entry in ("pnpm exec *", "pnpm dlx *", "yarn dlx *", "npm exec *", "npm x *"):
            errs = scope({"allowed-tools": f"Bash({entry})"})
            assert errs, f"{entry} should be rejected (arbitrary-package execution)"

    def test_named_script_allowed(self):
        for entry in ("npm run test", "npm ci", "npm run build *"):
            assert scope({"allowed-tools": f"Bash({entry})"}) == [], entry


class TestNetworkClientPreapproval:
    def test_curl_and_wget_rejected(self):
        for fam in ("curl", "wget"):
            errs = scope({"allowed-tools": f"Bash({fam} *)"})
            assert errs, f"{fam} * should be rejected"

    def test_curl_bare_rejected(self):
        assert scope({"allowed-tools": "Bash(curl)"})


class TestBroadVcs:
    def test_git_family_wildcard_rejected(self):
        errs = scope({"allowed-tools": "Bash(git *)"})
        assert len(errs) == 1
        assert "git" in errs[0]

    def test_gh_family_wildcard_rejected(self):
        errs = scope({"allowed-tools": "Bash(gh *)"})
        assert len(errs) == 1
        assert "gh" in errs[0]

    def test_git_readonly_subcommands_allowed(self):
        for entry in ("git status", "git diff *", "git log *", "git show *", "git add *", "git commit *"):
            assert scope({"allowed-tools": f"Bash({entry})"}) == [], entry

    def test_git_dash_c_rejected(self):
        # git -c <k>=<v> runs an arbitrary command through core.pager / hooks.
        errs = scope({"allowed-tools": "Bash(git -c *)"})
        assert errs

    def test_git_config_rejected(self):
        errs = scope({"allowed-tools": "Bash(git config *)"})
        assert errs

    def test_gh_readonly_subcommands_allowed(self):
        for entry in ("gh pr view *", "gh issue view *", "gh pr list *", "gh pr create *"):
            assert scope({"allowed-tools": f"Bash({entry})"}) == [], entry

    def test_gh_dangerous_subcommands_rejected(self):
        for sub in ("api", "auth", "gist", "extension", "alias"):
            errs = scope({"allowed-tools": f"Bash(gh {sub} *)"})
            assert errs, f"gh {sub} should be rejected"


class TestDestructiveWildcard:
    def test_rm_family_wildcard_rejected(self):
        assert scope({"allowed-tools": "Bash(rm *)"})

    def test_rm_scoped_prefix_allowed(self):
        # rm bounded to a fixed prefix (heist's temp dir) is not a whole-family grant.
        assert scope({"allowed-tools": "Bash(rm -rf /tmp/heist-*)"}) == []


class TestBuildToolsUntouched:
    def test_linters_formatters_test_runners_allowed(self):
        for fam in (
            "ruff",
            "black",
            "isort",
            "mypy",
            "flake8",
            "pytest",
            "eslint",
            "prettier",
            "tsc",
            "make",
            "cargo",
            "go",
            "which",
            "test",
            "ls",
            "mkdir",
            "cat",
            "lsof",
            "stat",
            "wc",
            "date",
        ):
            assert scope({"allowed-tools": f"Bash({fam} *)"}) == [], fam


class TestEscapeHatch:
    def test_disable_model_invocation_exempts(self):
        # A skill only ever run by an explicit user (not model-invoked) may keep
        # broad grants -- the advisory's second remediation path.
        fm = {"allowed-tools": "Bash(git *), Bash(python *)", "disable-model-invocation": True}
        assert scope(fm) == []

    def test_disable_model_invocation_false_does_not_exempt(self):
        fm = {"allowed-tools": "Bash(git *)", "disable-model-invocation": False}
        assert scope(fm)


class TestForms:
    def test_list_form(self):
        fm = {"allowed-tools": ["Bash(git *)", "Read", "Bash(curl *)"]}
        errs = scope(fm)
        assert len(errs) == 2

    def test_string_form_multiple(self):
        fm = {"allowed-tools": "Bash(git *), Read, Bash(python *)"}
        errs = scope(fm)
        assert len(errs) == 2


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
            "allowed-tools: Bash(git status), Bash(git diff *), Read\n"
            "---\n\n" + ("body text with git status and git diff " * 20) + "\n"
        )
        errors = skill_checks.validate_skill_md(d / "SKILL.md", dir_name="demo")
        assert errors == []
