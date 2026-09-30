#!/usr/bin/env python3
"""Decision half of the `gh` read-guard in the PreToolUse permissions hook.

A pre-approved `gh` READ verb can still move a value off the machine, or reach a
host other than github.com, through its own arguments — no write verb needed:

  - a ``--jq`` / ``-q`` / ``--template`` / ``-t`` expression that reads the process
    environment (jq's ``env`` builtin or ``$ENV``) prints a secret straight into the
    command's output, which for a bot may land in a report or a channel message;
  - ``-R`` / ``--repo`` naming a host other than github.com — or a positional URL that
    names one — sends the request, and any ``--search`` text with it, to that host;
  - ``--web`` / ``-w`` opens a URL at that host.

Two calls of one granted read verb therefore suffice to carry an environment-resident
token off the box. This module answers ``allow`` or ``deny <reason>`` for a whole
command line so the bash hook stays a thin caller and the rule is unit-testable.

Standalone stdlib (the ``vault-git-decide.py`` / ``mention-rewrite.py`` precedent). It
refuses only the three shapes above; every other ``gh`` call — including the fleet's
own ``--json`` / ``--jq '.field'`` reads — is allowed, so nothing legitimate breaks.
The guard is verb-agnostic: these shapes are never legitimate on any verb, read or
write, and matching the verb would only add a way to miss one.
"""

from __future__ import annotations

import re
import shlex
import sys

# jq reads the environment through the ``env`` builtin (``env``, ``env.FOO``,
# ``env["FOO"]``, ``env|keys``) or the ``$ENV`` predefined variable. Match the
# builtin only: a field literally named ``.env`` on the JSON input is preceded by a
# dot and is NOT the builtin, so it stays allowed. gh's Go templates have no ``env``
# function at all (an ``env`` template cannot read anything), so applying the same
# test to ``--template`` values denies a suspicious-but-inert expression while every
# real template — ``{{.title}}`` and the like — carries no ``env`` token and passes.
_ENV_REF = re.compile(r"(?<![\w.])env(?![\w])|\$ENV\b")

# Flags whose value is a jq or Go-template expression.
_EXPR_LONG = ("--jq", "--template")
_EXPR_SHORT = ("-q", "-t")
# Flags whose value is a repository, which may carry a [HOST/]OWNER/REPO host.
_REPO_LONG = ("--repo",)
_REPO_SHORT = ("-R",)

_ALLOWED_HOSTS = {"github.com"}
# Leading words that may sit in front of the real command; used to find a `gh`
# invocation that is wrapped rather than bare. Conservative and best-effort — the
# hook's own matcher never auto-approves a wrapped form, so the load-bearing case is
# the bare `gh …`, which needs none of this.
_WRAPPERS = {"command", "builtin", "exec", "nohup", "nice", "stdbuf", "time", "env", "xargs", "timeout"}


def _host_of(value: str) -> str | None:
    """The host a ``-R``/``--repo`` value or a positional URL names, or ``None``.

    ``owner/repo`` (two segments) names no host. ``host/owner/repo`` (three or more)
    names its first segment. A ``scheme://host/…`` URL names the URL host.
    """
    v = value.strip()
    if not v:
        return None
    m = re.match(r"[a-zA-Z][a-zA-Z0-9+.\-]*://([^/]+)", v)
    if m:
        host = m.group(1)
        return host.split("@")[-1]  # drop any user-info
    parts = v.split("/")
    if len(parts) >= 3 and parts[0]:
        return parts[0]
    return None


def _looks_like_repo_url(token: str) -> bool:
    return bool(re.match(r"[a-zA-Z][a-zA-Z0-9+.\-]*://", token))


def _foreign(host: str | None, allowed: set[str]) -> bool:
    if host is None:
        return False
    return host.split(":")[0].lower() not in allowed


def _gh_command_words(tokens: list[str]) -> list[list[str]]:
    """Split a token stream on shell operators into segments, and return the argument
    lists of the segments whose command word is ``gh`` (bare, ``\\gh``, or wrapped)."""
    segments: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok in (";", "&", "&&", "|", "||", "(", ")", "\n", "|&"):
            segments.append(current)
            current = []
        else:
            current.append(tok)
    segments.append(current)

    out: list[list[str]] = []
    for seg in segments:
        i = 0
        # Skip leading NAME=VALUE assignments and simple wrappers with their options.
        while i < len(seg):
            t = seg[i]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t):
                i += 1
                continue
            base = t.lstrip("\\")
            if base in _WRAPPERS:
                i += 1
                # consume a wrapper's own leading options / one duration-like arg
                while i < len(seg) and (seg[i].startswith("-") or re.fullmatch(r"[0-9]+[smhd]?", seg[i])):
                    i += 1
                continue
            break
        if i < len(seg) and seg[i].lstrip("\\") == "gh":
            out.append(seg[i + 1 :])
    return out


def _inspect_gh_args(args: list[str], allowed: set[str]) -> str | None:
    """Return a deny reason for one gh invocation's argument list, or ``None``."""
    i = 0
    n = len(args)
    while i < n:
        a = args[i]

        # --web / -w
        if a in ("--web", "-w"):
            return "gh --web opens a URL in a browser at the named host"

        # expression flags: --jq/--template EXPR, --jq=EXPR, -q EXPR, -qEXPR, -t …
        expr = None
        if a in _EXPR_LONG:
            expr = args[i + 1] if i + 1 < n else ""
            i += 1
        elif a.startswith("--jq=") or a.startswith("--template="):
            expr = a.split("=", 1)[1]
        elif a in _EXPR_SHORT:
            expr = args[i + 1] if i + 1 < n else ""
            i += 1
        elif len(a) > 2 and a[:2] in _EXPR_SHORT:
            expr = a[2:]
        if expr is not None:
            if _ENV_REF.search(expr):
                return "gh --jq/--template reads the process environment"
            i += 1
            continue

        # repo flags: --repo/-R VALUE, --repo=VALUE, -RVALUE
        repo = None
        if a in _REPO_LONG or a in _REPO_SHORT:
            repo = args[i + 1] if i + 1 < n else ""
            i += 1
        elif a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        elif len(a) > 2 and a.startswith("-R"):
            repo = a[2:]
        if repo is not None:
            if _foreign(_host_of(repo), allowed):
                return "gh -R/--repo names a host other than github.com"
            i += 1
            continue

        # positional argument that is a repository URL naming a foreign host
        if not a.startswith("-") and _looks_like_repo_url(a):
            if _foreign(_host_of(a), allowed):
                return "gh is pointed at a URL on a host other than github.com"

        i += 1
    return None


def decide(command: str, *, gh_host: str = "") -> tuple[str, str]:
    """``("allow", "")`` or ``("deny", reason)`` for a whole command line.

    ``gh_host`` is the fleet's configured GitHub host (``$GH_HOST``) if any; a repo on
    that host is allowed alongside github.com, so a GitHub Enterprise fleet is not
    blocked from its own host. On its own the empty string means github.com only.
    """
    allowed = set(_ALLOWED_HOSTS)
    if gh_host.strip():
        allowed.add(gh_host.strip().split(":")[0].lower())

    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        # Unbalanced quotes: the bash hook already prompts on these, but be explicit.
        return ("allow", "")

    for args in _gh_command_words(tokens):
        reason = _inspect_gh_args(args, allowed)
        if reason:
            return ("deny", reason)
    return ("allow", "")


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else sys.stdin.read()
    import os

    verdict, reason = decide(command, gh_host=os.environ.get("GH_HOST", ""))
    if verdict == "deny":
        print(reason)
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
