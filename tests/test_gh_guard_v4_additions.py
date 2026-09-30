"""Round-4 additions on clauDNA #369: two ways the round-3 guard still read a command differently from the shell.

1. Comments. With shlex comments off, an apostrophe or a double quote inside a comment (or a heredoc body) opens a
   quote for the tokenizer that the shell never sees; two of them on different lines pair up and hide the gh call
   between them, and a single one sends the whole command down the lenient fallback, which splits a quoted --jq value
   at a pipe or a paren. Each physical line is now read on its own too, and `#` starts a comment only where bash starts
   one (at a word start, outside quotes).
2. Shorthand clusters. pflag reads `-dq EXPR` as `-d -q EXPR` and `-dR HOST/o/r` as `-d -R HOST/o/r` (real gh 2.92:
   `-dz` fails with "unknown shorthand flag", `-dq` and `-dR` parse). Neither the decider nor the pre-filter read them.
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
