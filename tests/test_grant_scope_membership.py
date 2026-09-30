"""Pin the MEMBERSHIP of the grant-scope allowlist, not only its structure.

vera's #360 round-3 finding (D): 96 of 97 "never-granted" names could be removed
from `_GRANT_REJECT_ALWAYS` and every existing test still passed, because the
star fallback masks the wildcard rows and the exact form is not pinned. The same
held for risky git/gh subcommands added to the safe sets. So these lists are the
names copied as LITERALS: removing a name from the module's set (or adding a
risky subcommand to a safe set) turns a row here red.

Each dangerous command is checked as an EXACT grant (a non-star argument), the
form the star fallback does not catch.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import skill_checks  # noqa: E402


def refused(entry: str) -> bool:
    return bool(skill_checks.check_grant_scope({"allowed-tools": entry}))


def accepted(entry: str) -> bool:
    return skill_checks.check_grant_scope({"allowed-tools": entry}) == []


# Commands that must be refused even as an exact grant (they run code, reach the
# network, dump secrets, or delete). Interpreters (python3, node, ...) are NOT
# here: they may run a fixed script. deno/bun ARE here (they run via subcommands).
NEVER_GRANTED = [
    "npm", "pnpm", "yarn", "npx", "pip", "pip3", "uv", "uvx", "pipx", "poetry",
    "bundle", "gem", "make", "cmake", "ninja", "cargo", "go", "gradle", "mvn",
    "gcc", "cc", "clang", "rustc", "javac", "pytest", "tox", "nox", "jest",
    "vitest", "mocha", "ava", "cypress", "playwright", "eslint", "prettier",
    "tsc", "black", "flake8", "isort", "mypy", "ruff", "pylint", "bandit",
    "curl", "wget", "nc", "ncat", "socat", "ssh", "scp", "sftp", "rsync",
    "telnet", "ftp", "env", "eval", "exec", "source", "xargs", "sudo", "doas",
    "nice", "nohup", "timeout", "watch", "script", "docker", "podman",
    "kubectl", "terraform", "ansible", "aws", "gcloud", "az", "sed", "awk",
    "find", "printenv", "chmod", "chown", "dd", "rm", "tar", "unzip", "zip",
    "chattr", "deno", "bun", "php", "java", "pwsh", "powershell", "osascript",
    "groovy", "scala", "elixir", "lua", "tclsh", "expect",
]

REFUSE_GIT_SUB = [
    "config", "clone", "rebase", "remote", "ls-remote", "submodule", "bisect",
    "pull", "merge", "cherry-pick", "apply", "am", "grep", "gc", "filter-branch",
    "update-ref", "replace", "archive", "bundle", "daemon", "instaweb",
    "send-email", "fetch", "difftool", "mergetool",
]

REFUSE_GH_SUB = [
    "api", "auth", "repo", "config", "secret", "codespace", "ssh-key",
    "release", "workflow", "run", "gist", "extension", "alias", "cache",
    "variable", "ruleset", "project", "label", "browse", "attestation",
]

# Every WRITE/action verb of an otherwise-allowed subcommand must be refused
# (the read-verb set must not be wideable to include one). vera #360 round-3.
REFUSE_GH_VERBS = [
    # gh pr <write>
    "gh pr create *", "gh pr edit *", "gh pr merge *", "gh pr close *",
    "gh pr comment *", "gh pr review *", "gh pr ready *", "gh pr reopen *",
    "gh pr lock *", "gh pr unlock *", "gh pr checkout *",
    # gh issue <write>
    "gh issue create *", "gh issue edit *", "gh issue close *",
    "gh issue comment *", "gh issue delete *", "gh issue reopen *",
    "gh issue lock *", "gh issue unlock *", "gh issue pin *",
    "gh issue unpin *", "gh issue transfer *", "gh issue develop *",
]

# Every READ verb a skill needs must stay allowed (the set must not be narrowed).
ALLOW_GH_VERBS = [
    "gh pr view *", "gh pr list *", "gh pr diff *", "gh pr status *",
    "gh pr checks *",
    "gh issue view *", "gh issue list *", "gh issue status *",
]


def test_every_never_granted_name_is_refused_even_exact():
    missed = [c for c in NEVER_GRANTED if not refused(f"Bash({c} x)")]
    assert missed == [], f"accepted as an exact grant: {missed}"


def test_risky_git_subcommands_refused():
    missed = [s for s in REFUSE_GIT_SUB if not refused(f"Bash(git {s} *)")]
    assert missed == [], f"git subcommand accepted: {missed}"


def test_risky_gh_subcommands_refused():
    missed = [s for s in REFUSE_GH_SUB if not refused(f"Bash(gh {s} *)")]
    assert missed == [], f"gh subcommand accepted: {missed}"


def test_gh_write_verbs_refused():
    missed = [e for e in REFUSE_GH_VERBS if not refused(f"Bash({e})")]
    assert missed == [], f"gh write verb accepted: {missed}"


def test_gh_read_verbs_allowed():
    wrong = [e for e in ALLOW_GH_VERBS if not accepted(f"Bash({e})")]
    assert wrong == [], f"gh read verb refused: {wrong}"


def test_command_refused_except_lookup():
    assert refused("Bash(command git status)")
    assert refused("Bash(command *)")
    assert accepted("Bash(command -v python3)")
    assert accepted("Bash(command -v *)")


def test_read_only_positive_controls_still_pass():
    for ok in (
        "Bash(git status *)", "Bash(git diff *)", "Bash(git log *)",
        "Bash(git checkout *)",
        "Bash(gh pr view *)", "Bash(gh pr list *)", "Bash(gh pr diff *)",
        "Bash(gh issue view *)", "Bash(gh issue list *)", "Bash(gh search *)",
        "Bash(python3 scripts/validate-skills.py)", "Bash(ls *)", "Bash(cat *)",
    ):
        assert accepted(ok), ok
