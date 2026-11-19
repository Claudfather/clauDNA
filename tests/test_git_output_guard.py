"""The permissions hook refuses a git command that writes a file through an output flag.

git reads ``--output`` in its diff and revision options, so every git command that takes them, a
granted read such as ``git log``, ``git diff`` or ``git show`` included, writes the file that option
names, and ``format-patch`` and ``archive`` also take ``-o``. The hook's redirection guard looks for
``>`` only, and a shipped ``Bash(git log:*)`` grant is a native rule the hook's own matching never
reaches, so the hook denies these shapes under any grant: a hook deny is the one decision that
overrides an allow. The decider (``plugin-hooks/gh-guard-decide.py``) finds the git call the way the
shell will.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "gh_guard_decide_git_output", _ROOT / "plugin-hooks" / "gh-guard-decide.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
HOOK = _ROOT / "plugin-hooks" / "pretooluse-permissions.sh"
sys.path.insert(0, str(_ROOT / "scripts"))

import skill_checks  # noqa: E402
from skill_frontmatter import parse_frontmatter  # noqa: E402


def verdict(cmd: str) -> str:
    return mod.decide(cmd)[0]


# Each git command measured to write the file --output names (git 2.39.5), with the arguments it was
# measured with. rev-list, blame and range-diff create or empty the file even when they print nothing.
OUTPUT_VERBS = {
    "diff": "git diff HEAD~1 HEAD",
    "log": "git log -1",
    "show": "git show HEAD",
    "format-patch": "git format-patch -1",
    "archive": "git archive HEAD",
    "bundle": "git bundle create b.bundle HEAD",
    "whatchanged": "git whatchanged -1",
    "diff-tree": "git diff-tree -p HEAD~1 HEAD",
    "diff-index": "git diff-index -p HEAD~1",
    "diff-files": "git diff-files -p",
    "stash show": "git stash show -p",
    "stash list": "git stash list",
    "reflog": "git reflog",
    "shortlog": "git shortlog -1 HEAD",
    "rev-list": "git rev-list -1 HEAD",
    "blame": "git blame f",
    "range-diff": "git range-diff A..B C..D",
}
# -o is format-patch's --output-directory and archive's --output; git refuses it on the other four.
DASH_O_VERBS = ["diff", "log", "show", "format-patch", "archive", "bundle"]


# -- the decider ------------------------------------------------------------------------------------
@pytest.mark.parametrize("verb", sorted(OUTPUT_VERBS))
@pytest.mark.parametrize("flag", ["--output=out.txt", "--output out.txt"])
def test_an_output_flag_is_refused_on_each_verb(verb, flag):
    assert verdict(f"{OUTPUT_VERBS[verb]} {flag}") == "deny"


@pytest.mark.parametrize("verb", DASH_O_VERBS)
@pytest.mark.parametrize("flag", ["-o out", "-oout"])
def test_dash_o_is_refused_on_each_verb_that_names_it(verb, flag):
    assert verdict(f"{OUTPUT_VERBS[verb]} {flag}") == "deny"


@pytest.mark.parametrize(
    "cmd",
    [
        "git format-patch -1 --output-directory=outdir",
        "git format-patch -1 --output-directory outdir",
        "git format-patch -ko outdir -1",  # -k, then -o and its value
        "git format-patch -koutdir -1",
        "git archive -vo out.tar HEAD",
        "git log --outp=out.txt",  # git takes no abbreviation, but no other option starts like this
    ],
)
def test_the_directory_cluster_and_prefix_forms_are_refused(cmd):
    assert verdict(cmd) == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "git -C /tmp log --output=x",
        "git --no-pager log --output=x",
        "git -c core.pager=cat log --output=x",
        "git --git-dir=.git show --output=x HEAD",
        "/usr/bin/git log --output=x",
        "\\git log --output=x",
        "A=1 git log --output=x",
        "2>/dev/null git log --output=x",
        "env A=1 git log --output=x",
        "timeout -s KILL 5 git log --output=x",
        "sudo -u u git log --output=x",
        "xargs -I {} git log --output={}",
        "echo ok && git show --output x HEAD",
        "echo ok; git log --output=x",
        "echo ok | git log --output=x",
        "echo $(git log --output=x)",
        "echo `git log --output=x`",
        "echo ok\ngit log --output=x",
        'git log --out"put"=x',
        "git log '--output=x'",
        "git log --output=x # a comment",
        "git lg --output=x",  # an alias: git reads --output wherever its options reach
    ],
)
def test_a_git_call_is_read_where_the_shell_runs_it(cmd):
    assert verdict(cmd) == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "git log --oneline -5",
        "git diff --stat main...HEAD",
        "git show HEAD:f",
        "git log -Sfoo",
        "git log --format=%ad -1",
        "git log --oneline origin/main..HEAD",
        "git log -- --output=x",  # after --, a path
        "git log --end-of-options --output=x",  # after --end-of-options, a revision
        "git diff --output-indicator-new=+",
        "git diff --output=/dev/null --exit-code",
        "git log --output /dev/null",
        "git grep -o pattern",  # -o is --only-matching here
        "git ls-files -o",  # and --others here
        "git format-patch -1 --stdout",
        "git archive --format=tar HEAD",
        'git commit -m "document the --output flag"',
        "echo git log --output=x",
        "git status",
    ],
)
def test_an_ordinary_git_read_is_allowed(cmd):
    assert verdict(cmd) == "allow", cmd


# -- the hook, end to end ---------------------------------------------------------------------------
def _hook(tmp_path: Path, cmd: str, allow: list[str], *, path: str = "/usr/bin:/bin") -> str:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"allow": allow}}))
    p = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True, text=True, cwd=tmp_path, env={"HOME": str(tmp_path), "PATH": path}, timeout=20,
    )
    return (
        "deny" if '"permissionDecision":"deny"' in p.stdout
        else "allow" if '"permissionDecision":"allow"' in p.stdout
        else "prompt"
    )


def _narrow(verb: str) -> str:
    return f"Bash({' '.join(OUTPUT_VERBS[verb].split()[:2])} *)"


@pytest.mark.parametrize("verb", DASH_O_VERBS)
def test_the_hook_denies_an_output_flag_under_a_narrow_and_a_bare_grant(tmp_path, verb):
    for cmd in (f"{OUTPUT_VERBS[verb]} --output=out.txt", f"{OUTPUT_VERBS[verb]} -o out"):
        for allow in ([_narrow(verb)], ["Bash"]):
            assert _hook(tmp_path, cmd, allow) == "deny", (allow, cmd)


@pytest.mark.parametrize("verb", DASH_O_VERBS)
def test_the_hook_still_approves_the_read_without_the_flag(tmp_path, verb):
    assert _hook(tmp_path, OUTPUT_VERBS[verb], [_narrow(verb)]) == "allow"


@pytest.mark.parametrize(
    "cmd", ["git log --out${Z}put=x", "git log $'--output=x'", "git log --out$'put'=x", "git diff {--output=x,HEAD}"]
)
def test_the_hook_leaves_a_git_option_an_expansion_can_form_to_claude_code(tmp_path, cmd):
    # The decider reads the text as written; the shell would hand git --output. The hook does not
    # approve such a command, so Claude Code's own permission check decides it.
    assert _hook(tmp_path, cmd, ["Bash(git log *)", "Bash(git diff *)"]) == "prompt", cmd


def test_every_form_the_decider_refuses_reaches_it_through_the_hook(tmp_path):
    # The hook's prefilter spawns the decider only for some text; each refused form must pass it.
    forms = [f"{OUTPUT_VERBS[v]} --output=x" for v in OUTPUT_VERBS] + [
        "git format-patch -ko outdir -1", "git archive -vo out.tar HEAD", "git log --outp=x", 'git log --out"put"=x',
        "git -C /tmp log --output=x", "timeout -s KILL 5 git log --output=x", "echo ok\ngit log --output=x",
    ]
    for cmd in forms:
        assert _hook(tmp_path, cmd, ["Bash"]) == "deny", cmd


def _bin_without_python3(tmp_path: Path) -> str:
    """A PATH with the tools the hook needs but no python3, so `command -v python3` fails."""
    bin_dir = tmp_path / "nopy"
    bin_dir.mkdir(exist_ok=True)
    for tool in ("bash", "jq", "cat", "mkdir", "mv", "wc", "date", "sed", "dirname", "env"):
        src = shutil.which(tool)
        if src:
            (bin_dir / tool).symlink_to(src)
    assert shutil.which("python3", path=str(bin_dir)) is None
    return str(bin_dir)


def test_no_python3_refuses_a_git_command_with_an_output_flag(tmp_path):
    path = _bin_without_python3(tmp_path)
    assert _hook(tmp_path, "git log --output=x", ["Bash(git log *)"], path=path) == "deny"
    # a git read with no output flag never reaches the guard, so it needs no python3
    assert _hook(tmp_path, "git log --oneline -5", ["Bash(git log *)"], path=path) == "allow"


def test_a_guard_error_refuses_a_git_command_with_an_output_flag(tmp_path):
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "python3").write_text("#!/bin/sh\ncat >/dev/null\nexit 3\n")  # reads its input, then fails
    (shim / "python3").chmod(0o755)
    assert _hook(tmp_path, "git log --output=x", ["Bash(git log *)"], path=f"{shim}:/usr/bin:/bin") == "deny"


def _wrapper_arm(function: str) -> str:
    """The wrapper words of one of the hook's command-word readers: its one `word|word...) ;;` arm."""
    body = HOOK.read_text().split(f"{function}() {{", 1)[1].split("\n}\n", 1)[0]
    arms = re.findall(r"^\s*([A-Za-z|]+)\) ;;$", body, re.M)
    assert len(arms) == 1, arms
    return arms[0]


def test_the_hook_reads_git_behind_the_same_wrappers_as_gh():
    assert _wrapper_arm("is_git_command") == _wrapper_arm("is_gh_command")


# -- the shipped grants ------------------------------------------------------------------------------
SETTINGS = [_ROOT / "project-template" / ".claude" / "settings.json", _ROOT / ".claude" / "settings.json"]


@pytest.mark.parametrize("path", SETTINGS, ids=["template", "repo"])
def test_the_shipped_settings_deny_the_output_flag_on_each_git_read_they_grant(path):
    perms = json.loads(path.read_text())["permissions"]
    granted = {m.group(1) for e in perms["allow"] if (m := re.fullmatch(r"Bash\(git (diff|log|show):\*\)", e))}
    assert granted == {"diff", "log", "show"}
    assert {f"Bash(git {verb} *--output*)" for verb in granted} <= set(perms["deny"])


def _skill_grants(skill: str) -> list[str]:
    parsed = parse_frontmatter(_ROOT / "skills" / skill / "SKILL.md")
    assert parsed is not None, skill
    return skill_checks._parse_allowed_tools_entries(parsed[0].get("allowed-tools"))


@pytest.mark.parametrize("skill", ["heist", "development-retro", "qa", "init-project"])
def test_a_skill_grants_git_log_and_diff_only_in_a_form_its_steps_run(skill):
    """None of these skills' steps runs git log or git diff with arguments of its own choosing."""
    loose = [g for g in _skill_grants(skill) if re.fullmatch(r"Bash\(git (diff|log|show) \*\)", g)]
    assert loose == [], (skill, loose)


def test_init_project_grants_the_git_log_its_steps_name():
    assert "Bash(git log --oneline)" in _skill_grants("init-project")
    assert "git log --oneline" in (_ROOT / "skills" / "init-project" / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]
