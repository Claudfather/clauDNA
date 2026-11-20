"""The permissions hook denies the git output flags it reads, under any grant.

Under any grant, it denies ``--output`` (or a leading part of that name, or ``--output-directory``) on
any verb and ``-o`` on ``diff``, ``log``, ``show``, ``format-patch``, ``archive`` and ``bundle``, in the
forms these tests name. The decider (``plugin-hooks/gh-guard-decide.py``) finds the git call past
wrappers, assignments, redirections and git's own options; the shipped settings deny ``--output`` on the
git reads they grant, and the skills grant git reads only in the forms their steps run.
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
def test_a_git_call_is_read_in_each_position_listed(cmd):
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


EXPANSION_FORMS = [
    "git log --out${Z}put=x",
    "git log $'--output=x'",
    "git log --out$'put'=x",
    "git log --o$'utput'=x",
    'git log --o$"utput"=x',
    "git diff {--output=x,HEAD}",
    "git log --o${Z:-utput}=x",
    "git log --outpu?=x",
    "git format-patch -1 -$'o' outdir",
]
GRANTS = ["Bash(git log *)", "Bash(git diff *)", "Bash(git format-patch *)"]


@pytest.mark.parametrize("cmd", EXPANSION_FORMS)
def test_each_expansion_form_listed_is_refused(tmp_path, cmd):
    # The shell hands git the expanded word; the decider reads each form listed here as git gets it.
    assert verdict(cmd) == "deny", cmd
    assert _hook(tmp_path, cmd, GRANTS) == "deny", cmd


@pytest.mark.parametrize(
    "cmd", ["git log --format=$'%H\\t%s' -1", "git log --oneline $BASE..HEAD", "git log --author=$USER -1"]
)
def test_an_ordinary_expansion_in_a_git_read_is_still_approved(tmp_path, cmd):
    assert verdict(cmd) == "allow", cmd
    assert _hook(tmp_path, cmd, GRANTS) == "allow", cmd


def test_each_refused_form_listed_reaches_the_decider_through_the_hook(tmp_path):
    # The hook's prefilter spawns the decider only for some text; each refused form must pass it.
    forms = [f"{OUTPUT_VERBS[v]} --output=x" for v in OUTPUT_VERBS] + [
        "git format-patch -ko outdir -1", "git archive -vo out.tar HEAD", "git log --outp=x", 'git log --out"put"=x',
        "git -C /tmp log --output=x", "timeout -s KILL 5 git log --output=x", "echo ok\ngit log --output=x",
    ]
    for cmd in forms:
        assert _hook(tmp_path, cmd, ["Bash"]) == "deny", cmd


# Each makes git read an output flag once the shell has read its words: an ANSI-C quote, $IFS, a brace
# list or sequence, a command substitution, a string that eval, a shell or env -S runs, a -c alias, and a
# glob that a file named like an output option matches.
SHELL_FORMED = [
    "git log -1 $'\\x2d\\x2doutput=x'",
    "git log -1 --$'\\x6f'utput=x",
    "git log -1 $'\\055\\055output=x'",
    "git log -1 --$'\\157'utput=x",
    "git log -1 $'\\x2d'$'\\x2d'output=x",
    "git log -1 $'-\\x2d'output=x",
    "git log -1 --output$'\\x3d'x",
    "$'\\x67it' log -1 --output=x",
    "g$'i't log -1 --output=x",
    "git log -1 --output${IFS}x",
    "git log -1 --out${Z}put${IFS}x",
    "git log -1 --{out,x}{put,y}=x",
    "git log -1 --{o..o}utput=x",
    "git log -1 --out{p..p}ut=x",
    "git log -1 --{o{u,x}tput,z}=x",
    "git log -1 $(echo --output=x)",
    "git log -1 `echo --output=x`",
    "git log -1 --$(echo output)=x",
    'git log -1 "$(echo --output=x)"',
    'git log -1 "--$(echo output)=x"',
    "env -S 'git log -1 --output=x'",
    "bash -c 'git log -1 --output=x'",
    "sh -c 'git log -1 --output=x'",
    "eval 'git log -1 --output=x'",
    "eval git log -1 --output=x",
    "git -c alias.l='log -1 --output=x' l",
    "git -c 'alias.l=log -1 --output=x' l",
    "git log *",
    "git diff *",
    "git show *",
    "git log -1 *.txt",
    "git l *",
    "git -C $(echo . log --output=x) commit",
    "git $(echo log) --output=x",
]
SHELL_GRANTS = GRANTS + ["Bash(git show *)", "Bash(git -c *)", "Bash(env *)", "Bash(bash *)", "Bash(sh *)", "Bash(eval *)"]


@pytest.mark.parametrize("cmd", SHELL_FORMED)
def test_each_shell_formed_word_listed_is_refused(tmp_path, cmd):
    assert verdict(cmd) == "deny", cmd
    for allow in (SHELL_GRANTS, ["Bash"]):
        assert _hook(tmp_path, cmd, allow) == "deny", (allow, cmd)


@pytest.mark.parametrize("cmd", [
    "git ls-files '*.py'",
    "git log -- '*.py'",
    "git show HEAD^{commit}",
    'git log --author="$(whoami)" -1',
    "git diff src/*.c",
    "git log --grep='fix*'",
    'git -C "$(pwd)" log -1',
    "git -c core.pager=cat log -1",
    "git add *.md",
    'git commit -m "$(cat msg)"',
    "git commit -m \"$(cat <<'EOF'\nfix: a message\nEOF\n)\"",
])
def test_each_ordinary_read_listed_with_a_quote_glob_or_substitution_is_not_refused(tmp_path, cmd):
    assert verdict(cmd) == "allow", cmd
    assert _hook(tmp_path, cmd, SHELL_GRANTS + ["Bash(git ls-files *)"]) != "deny", cmd


def _deny_reason(tmp_path: Path, cmd: str) -> str:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"allow": ["Bash"]}}))
    p = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True, text=True, cwd=tmp_path, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}, timeout=60,
    )
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    return out.get("permissionDecisionReason", "") if out.get("permissionDecision") == "deny" else ""


def test_a_long_command_gets_a_decision_and_one_over_the_cap_is_refused(tmp_path):
    # Mixed content: quotes, backslashes, expansions, substitutions, braces and globs, over many lines.
    line = "echo 'a \"b\" \\\\c' $X `date` {e,f} *g? ; printf '%s\\n' \"$(id -u)\"\n"
    under = line * (120_000 // len(line)) + "git log -1 --output=x"
    over = line * (140_000 // len(line)) + "git log -1 --oneline"
    assert len(under) < 131_072 < len(over)
    assert _deny_reason(tmp_path, under) == "git log --output writes its output to a file; run it without --output and read the output"
    assert _deny_reason(tmp_path, under.replace("--output=x", "--oneline")) == ""
    assert _deny_reason(tmp_path, over) == (
        "the output-flag guard does not read a command over 131072 characters; split it into shorter commands"
    )
    assert _deny_reason(tmp_path, over.replace("git log -1 --oneline", "echo done")) == ""
    many = "git log " + " ".join(["{a,b}{c,d}{e,f}{g,h}{i,j}{k,l}{m,n}{o,p}"] * 300)
    assert mod.decide(many) == ("deny", "git: this command gives the guard more than 65536 words to read; split it into shorter commands")


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
