#!/usr/bin/env python3
"""Decision half of the `gh` read-guard in the PreToolUse permissions hook.

A pre-approved `gh` READ verb can still move a value off the machine, or reach a host
other than github.com, through its own arguments — no write verb needed:

  - a ``--jq`` / ``-q`` / ``--template`` / ``-t`` expression that reads the process
    environment (jq's ``env`` builtin or ``$ENV``) prints a secret into the output;
  - ``-R`` / ``--repo`` / ``--hostname`` naming a host other than github.com, or a
    positional URL that names one, sends the request (and any ``--search`` text) there;
  - ``--web`` / ``-w`` opens a URL at that host.

Two calls of one granted read verb thus suffice to carry an environment-resident token
off the box. This module answers ``allow`` or ``deny <reason>`` for a whole command
line so the bash hook stays a thin caller and the rule is unit-testable.

Standalone stdlib (the ``vault-git-decide.py`` / ``mention-rewrite.py`` precedent). It
refuses only the shapes above; every other ``gh`` call — including the fleet's own
``--json`` / ``--jq '.field'`` reads — is allowed. It reads the *unexpanded* command
text, so a value the shell assembles at run time (a variable, a ``$'...'`` form) is
invisible to it; those are the hook's approver's to gate, not the decider's.
"""

from __future__ import annotations

import re
import shlex
import sys

# jq reads the environment through the ``env`` builtin or ``$ENV``. ``.env`` (a field)
# is preceded by a dot; ``env:`` is an object key. Text inside a jq STRING LITERAL is
# data (see _code_only), so a label such as "env=" is not a read.
_ENV_REF = re.compile(r"(?<![\w.])env(?![\w])(?!\s*:)|\$ENV\b")

# GitHub's own hosts. A repo or URL naming any of these is github.com, not a foreign host.
_ALLOWED_HOSTS = {
    "github.com",
    "api.github.com",
    "uploads.github.com",
    "gist.github.com",
    "www.github.com",
}
# Leading words that may sit in front of the real command word, plus shell keywords a
# segment can open with; used to find a `gh` invocation that is wrapped rather than bare.
_WRAPPERS = {
    "command",
    "builtin",
    "exec",
    "nohup",
    "nice",
    "stdbuf",
    "time",
    "env",
    "xargs",
    "timeout",
    "do",
    "then",
    "else",
    "elif",
    "if",
    "while",
    "until",
    "!",
    "{",
}
_SEPARATOR_CHARS = set(";&|()`\n")
_PUNCT = ";()<>|&`\n"


def _code_only(expr: str) -> str | None:
    """The jq text with string-literal DATA blanked out and ``\\( ... )`` interpolations
    kept as code. ``None`` when the scanner cannot be sure (an unterminated string or
    interpolation): the caller then uses the raw text, so a doubt denies, not allows."""
    out: list[str] = []
    in_str = False
    depth: list[int] = []  # open interpolations: paren depth inside each
    i, n = 0, len(expr)
    while i < n:
        c = expr[i]
        if not in_str:
            if c == '"':
                in_str = True
                out.append(" ")
            else:
                out.append(c)
                if depth:
                    if c == "(":
                        depth[-1] += 1
                    elif c == ")":
                        if depth[-1] == 0:
                            depth.pop()
                            in_str = True
                        else:
                            depth[-1] -= 1
            i += 1
        else:
            if c == "\\" and i + 1 < n:
                if expr[i + 1] == "(":
                    in_str = False
                    depth.append(0)
                    out.append(" ")
                    i += 2
                    continue
                i += 2
                continue
            if c == '"':
                in_str = False
                out.append(" ")
            i += 1
    if in_str or depth:
        return None
    return "".join(out)


def _reads_env(expr: str, *, jq: bool) -> bool:
    if not jq or "#" in expr:  # templates and commented jq: use the raw text, as before
        return bool(_ENV_REF.search(expr))
    code = _code_only(expr)
    return bool(_ENV_REF.search(expr if code is None else code))


def _host_of(value: str) -> str | None:
    """The host a ``-R``/``--repo`` value or a positional URL names, or ``None``.

    ``owner/repo`` (two segments) names no host; ``host/owner/repo`` (three) names its
    first. A ``scheme://host/…`` URL names the URL host. A trailing slash is not a
    segment (``owner/repo/`` names no host — gh rejects the form, but the deny reason
    would wrongly say "names a host"), so trailing empty segments are dropped first.
    """
    v = value.strip()
    if not v:
        return None
    m = re.match(r"[a-zA-Z][a-zA-Z0-9+.\-]*://([^/]+)", v)
    if m:
        return m.group(1).split("@")[-1]  # drop any user-info
    m = re.match(r"[^@/\s]+@([^:/\s]+):", v)  # scp-style: git@HOST:owner/repo
    if m:
        return m.group(1)
    parts = v.split("/")
    while parts and parts[-1] == "":
        parts.pop()
    if len(parts) >= 3 and parts[0]:
        return parts[0]
    return None


def _looks_like_repo_url(token: str) -> bool:
    return bool(re.match(r"[a-zA-Z][a-zA-Z0-9+.\-]*://|[^@/\s]+@[^:/\s]+:", token))


def _foreign(host: str | None, allowed: set[str]) -> bool:
    if host is None:
        return False
    return host.split(":")[0].lower() not in allowed


def _tokens(command: str) -> list[str]:
    # bash removes a backslash-newline continuation before it splits words
    command = re.sub(r"\\\r?\n", "", command)
    # A heredoc body is NOT skipped. Deciding where a body starts from the text alone is a
    # second shell parser: a `<<WORD` inside a comment, after a backslash, in a quoted string
    # or in `$((a << b))` is not a heredoc, and dropping the lines after it hides a real `gh`
    # call. Measured on 11,222 recorded gh lines (1,863 with a heredoc marker): no denial
    # without it. The cost is one shape: prose in a real heredoc body that starts a line with
    # a gh call and a denied flag is denied (use --body-file).
    try:
        lx = shlex.shlex(command, posix=True, punctuation_chars=_PUNCT)
        lx.whitespace_split = True
        lx.whitespace = " \t\r"
        # shlex treats `#` as a comment and swallows the newline that ends it, which would
        # join the next line onto this command and hide its `gh`.
        lx.commenters = ""
        return list(lx)
    except ValueError:
        # Quoting we cannot follow: a lenient split that still sees the flags, so a
        # doubt is inspected, not skipped.
        return [t.strip("'\"") for t in re.findall(r"[;()&|`\n]|[^\s;()&|`]+", command)]


def _is_separator(tok: str) -> bool:
    return bool(tok) and all(ch in _SEPARATOR_CHARS for ch in tok)


def _gh_command_words(tokens: list[str]) -> list[list[str]]:
    """Split a token stream on shell operators into segments, and return the argument
    lists of the segments whose command word is ``gh`` (bare, ``\\gh``, wrapped, or a
    path ending in ``gh``)."""
    segments: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if _is_separator(tok):
            segments.append(current)
            current = []
        else:
            current.append(tok)
    segments.append(current)

    out: list[list[str]] = []
    for seg in segments:
        i = 0
        host_env = None  # a GH_HOST=<host> prefix names the host this gh call talks to
        while i < len(seg):
            t = seg[i]
            m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", t)
            if m:
                if m.group(1) == "GH_HOST":
                    host_env = m.group(2)
                i += 1
                continue
            base = t.lstrip("\\")
            if base in _WRAPPERS:
                i += 1
                while i < len(seg) and (
                    seg[i].startswith("-") or re.fullmatch(r"[0-9]+[smhd]?", seg[i])
                ):
                    i += 1
                continue
            break
        if i < len(seg) and seg[i].lstrip("\\").rsplit("/", 1)[-1] == "gh":
            args = seg[i + 1 :]
            out.append(args + ["--hostname", host_env] if host_env else args)
    return out


def _inspect_gh_args(args: list[str], allowed: set[str]) -> str | None:
    """Return a deny reason for one gh invocation's argument list, or ``None``."""
    words: list[str] = []
    for a in args:
        if a.startswith("-"):
            break
        words.append(a)
    words = words[:2]
    has_json = words[:1] == ["api"] or any(
        a == "--json" or a.startswith("--json=") for a in args
    )
    i, n = 0, len(args)
    while i < n:
        a = args[i]
        # --web / -w (but -w is --workflow on `gh run list`)
        if a == "--web" or (a == "-w" and words != ["run", "list"]):
            return "gh --web opens a URL in a browser at the named host"

        # expression flags: --jq/-q always; --template/-t only where a template applies
        expr, is_jq = None, False
        if a in ("--jq", "-q"):
            expr, is_jq = (args[i + 1] if i + 1 < n else ""), True
            i += 1
        elif a == "--template" or (a == "-t" and has_json):
            expr = args[i + 1] if i + 1 < n else ""
            i += 1
        elif a.startswith("--jq="):
            expr, is_jq = a.split("=", 1)[1], True
        elif a.startswith("--template="):
            expr = a.split("=", 1)[1]
        elif len(a) > 2 and a[:2] == "-q":
            expr, is_jq = a[2:], True
        elif len(a) > 2 and a[:2] == "-t" and has_json:
            expr = a[2:]
        if expr is not None:
            if _reads_env(expr, jq=is_jq):
                return "gh --jq/--template reads the process environment"
            i += 1
            continue

        # repo / host flags: --repo/-R VALUE, --repo=VALUE, -RVALUE, --hostname HOST
        repo = None
        if a in ("--repo", "-R", "--hostname"):
            repo = args[i + 1] if i + 1 < n else ""
            i += 1
        elif a.startswith("--repo=") or a.startswith("--hostname="):
            repo = a.split("=", 1)[1]
        elif len(a) > 2 and a.startswith("-R"):
            repo = a[2:]
        if repo is not None:
            host = (
                repo
                if a == "--hostname" or a.startswith("--hostname=")
                else _host_of(repo)
            )
            if _foreign(host, allowed):
                return "gh -R/--repo/--hostname names a host other than github.com"
            i += 1
            continue

        # a positional argument that is a repository URL naming a foreign host
        if not a.startswith("-") and _looks_like_repo_url(a):
            if _foreign(_host_of(a), allowed):
                return "gh is pointed at a URL on a host other than github.com"
        i += 1
    return None


def decide(command: str, *, gh_host: str = "") -> tuple[str, str]:
    """``("allow", "")`` or ``("deny", reason)`` for a whole command line.

    ``gh_host`` is the fleet's configured GitHub host (``$GH_HOST``) if any; a repo on
    that host is allowed alongside github.com, so a GitHub Enterprise fleet is not
    blocked from its own host.
    """
    allowed = set(_ALLOWED_HOSTS)
    if gh_host.strip():
        allowed.add(gh_host.strip().split(":")[0].lower())
    for args in _gh_command_words(_tokens(command)):
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
