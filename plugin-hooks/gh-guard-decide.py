#!/usr/bin/env python3
"""Decision half of the `gh` read-guard in the PreToolUse permissions hook.

A pre-approved `gh` READ verb can still move a value off the machine, or reach a host
other than github.com, through its own arguments — no write verb needed:

  - a ``--jq`` / ``-q`` / ``--template`` / ``-t`` expression that reads the process
    environment (jq's ``env`` builtin or ``$ENV``) prints a secret into the output;
  - ``-R`` / ``--repo`` / ``--hostname`` naming a host other than github.com, a
    positional URL that names one, or a ``HOST/OWNER/REPO`` positional of a verb that
    takes a repository (``gh repo view|clone|fork ...``), sends the request (and any
    ``--search`` text) there;
  - ``--web`` / ``-w`` opens a URL at that host.

Two calls of one granted read verb thus suffice to carry an environment-resident token
off the box. This module answers ``allow`` or ``deny <reason>`` for a whole command
line so the bash hook stays a thin caller and the rule is unit-testable.

Standalone stdlib (the ``vault-git-decide.py`` / ``mention-rewrite.py`` precedent). It
refuses only the shapes above; every other ``gh`` call — including the fleet's own
``--json`` / ``--jq '.field'`` reads — is allowed. It reads the *unexpanded* command
text, so a value the shell assembles at run time (a variable, a ``$'...'`` form) is
invisible to it; those are the hook's approver's to gate, not the decider's (the approver
does not approve a gh command in which an expansion can form or change an option word).
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


# The verbs whose first positional argument is a repository, ``[HOST/]OWNER/REPO``
# (`gh help reference`, gh 2.92), with the options of each that take a value, so the
# positional is found where pflag finds it: ``gh repo view -b a/b/c OWNER/REPO`` names
# its repository last, and ``gh repo clone OWNER/REPO a/b/c`` clones into a directory.
_REPO_CREATE = {"-d", "--description", "-g", "--gitignore", "-h", "--homepage", "-l",
                "--license", "-r", "--remote", "-s", "--source", "-t", "--team", "-p",
                "--template"}
_SKILL_INSTALL = {"--agent", "--dir", "--pin", "--scope"}
_REPO_POSITIONAL: dict[tuple[str, str], set[str]] = {
    ("repo", "view"): {"-b", "--branch", "-q", "--jq", "--json", "-t", "--template"},
    ("repo", "clone"): {"-u", "--upstream-remote-name"},
    ("repo", "fork"): {"--fork-name", "--org", "--remote-name"},
    ("repo", "create"): _REPO_CREATE,
    ("repo", "new"): _REPO_CREATE,
    ("repo", "edit"): {"--add-topic", "--default-branch", "-d", "--description", "-h",
                       "--homepage", "--remove-topic", "--squash-merge-commit-message",
                       "--visibility"},
    ("repo", "delete"): set(),
    ("repo", "archive"): set(),
    ("repo", "unarchive"): set(),
    ("repo", "set-default"): set(),
    ("repo", "sync"): {"-b", "--branch", "-s", "--source"},
    ("label", "clone"): set(),
    **{(g, "install"): {"--pin"} for g in ("extension", "extensions", "ext")},
    **{(g, v): _SKILL_INSTALL for g in ("skill", "skills") for v in ("install", "add")},
    **{(g, v): set() for g in ("skill", "skills") for v in ("preview", "show")},
}


def _takes_next(opt: str, value_opts: set[str]) -> bool:
    """Whether ``opt`` takes the next argument as its value (pflag: in a single-dash
    cluster, the first shorthand that takes a value takes the rest of the token)."""
    if opt.startswith("--"):
        return "=" not in opt and opt in value_opts
    for k, ch in enumerate(opt[1:], start=1):
        if "-" + ch in value_opts:
            return k == len(opt) - 1
    return False


# A word that is only parameter expansions (``$X``, ``"${X}"``, ``$1``): unquoted and empty,
# it is no word at all, so the words after it move up a place.
_ONLY_PARAMS = re.compile(r"(?:\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?!$-]))+")


def _repo_positional(args: list[str]) -> tuple[str, bool] | None:
    """The repository positional of a verb that takes one, and whether a parameter-only
    word sat in front of it; ``None`` when there is none. Options and their values are
    skipped; after ``--`` every word is positional (``gh repo clone -- HOST/O/R``)."""
    pos: list[str] = []
    value_opts: set[str] = set()
    after_param = dashdash = False
    i = 0
    while i < len(args):
        a = args[i]
        if not dashdash and a == "--":
            dashdash = True
        elif not dashdash and a.startswith("-") and len(a) > 1:
            i += 2 if _takes_next(a, value_opts) else 1
            continue
        elif _ONLY_PARAMS.fullmatch(a):
            after_param = True
        else:
            pos.append(a)
            if len(pos) == 2:
                if (pos[0], pos[1]) not in _REPO_POSITIONAL:
                    return None
                value_opts = _REPO_POSITIONAL[(pos[0], pos[1])]
            elif len(pos) == 3:
                return a, after_param
        i += 1
    return None


def _host_shaped(host: str) -> bool:
    """A name that can only be a host: dotted, with a port, bracketed, or localhost."""
    return "." in host or ":" in host or host.startswith("[") or host.lower() == "localhost"


def _strip_comment(line: str) -> str:
    """Drop a ``#`` comment the way bash does: only where a word starts, outside quotes.

    shlex starts a comment in the middle of a word and swallows the newline that ends it; with
    its comments switched off, an apostrophe inside a comment opens a quote that pairs up with
    one on a later line and hides the lines between them.
    """
    quote = None
    esc = False
    prev = " "
    for i, ch in enumerate(line):
        if esc:
            esc = False
        elif ch == "\\" and quote != "'":
            esc = True
        elif quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and prev in " \t;&|()<>`":
            return line[:i]
        prev = ch
    return line


def _lex(text: str) -> list[str]:
    try:
        lx = shlex.shlex(text, posix=True, punctuation_chars=_PUNCT)
        lx.whitespace_split = True
        lx.whitespace = " \t\r"
        lx.commenters = ""  # comments are removed by _strip_comment, at a word start only
        return list(lx)
    except ValueError:
        # Quoting we cannot follow: a lenient split that still sees the flags, so a
        # doubt is inspected, not skipped.
        return [t.strip("'\"") for t in re.findall(r"[;()&|`\n]|[^\s;()&|`]+", text)]


def _readings(command: str) -> list[list[str]]:
    """The token streams to inspect: the whole text, then every physical line on its own.

    A quote that pairs up across lines (an apostrophe in a comment or in a heredoc body) hides
    the lines between in the whole-text reading only; each line read alone still shows them.
    A heredoc body is not skipped: deciding where one starts from the text alone is a second
    shell parser. Every reading only adds denials, so a doubt is inspected, not skipped.

    The trade: prose in a heredoc body that holds a gh call with a denied flag is denied. In
    recorded traffic that is a markdown code span, since a backtick starts a command for this
    reading, and not a line that starts with the call (which is denied too). Write such prose
    with the file tools and pass it with --body-file.
    """
    # bash removes a backslash-newline continuation before it splits words
    command = re.sub(r"\\\r?\n", "", command)
    lines = [_strip_comment(ln) for ln in command.split("\n")]
    out = [_lex("\n".join(lines))]
    if len(lines) > 1:
        out.extend(_lex(ln) for ln in lines)
    return out


def _tokens(command: str) -> list[str]:
    return _readings(command)[0]


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


def _expand_clusters(args: list[str]) -> list[str]:
    """pflag lets one dash carry several shorthands (``-dq EXPR``, ``-dR HOST/o/r``, ``-iqEXPR``).
    The four the guard reads (-q -t -R -w) are found wherever they sit in a cluster, and the rest
    of the token is their value. A superset reading: a shorthand in front of them is dropped."""
    out: list[str] = []
    for a in args:
        m = re.match(r"-([A-Za-z]+)", a) if len(a) > 2 and a[1] != "-" else None
        k = next((i for i, ch in enumerate(m.group(1)) if ch in "qtRw"), None) if m else None
        if k is None:
            out.append(a)
            continue
        out.append("-" + m.group(1)[k])
        rest = a[k + 2 :]
        if rest:
            out.append(rest)
    return out


def _inspect_gh_args(args: list[str], allowed: set[str]) -> str | None:
    """Return a deny reason for one gh invocation's argument list, or ``None``."""
    # a HOST/OWNER/REPO positional names its host the way -R does (a URL or an scp form
    # is read below, for every verb; a local path, and --from-local, name no host)
    # A parameter-only word in front of it may be the repository itself (its value comes
    # from the environment), so a word after one counts only when it names a host outright.
    found = _repo_positional(args)
    if found and "--from-local" not in args:
        repo, after_param = found
        host = None if repo.startswith((".", "/", "~")) or _looks_like_repo_url(repo) else _host_of(repo)
        if _foreign(host, allowed) and (not after_param or _host_shaped(host)):
            return "gh names a repository on a host other than github.com"
    args = _expand_clusters(args)
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
    for tokens in _readings(command):
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
