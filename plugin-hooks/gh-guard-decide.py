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
  - ``--web`` / ``-w`` opens a URL at that host;
  - a ``GH_HOST=`` / ``GH_REPO=`` assignment in front of the call (bare or behind ``env`` and the
    other wrappers) selects the host the way ``--hostname`` / ``-R`` do.

Two calls of one granted read verb thus suffice to carry an environment-resident token
off the box. This module answers ``allow`` or ``deny <reason>`` for a whole command
line so the bash hook stays a thin caller and the rule is unit-testable.

Standalone stdlib (the ``vault-git-decide.py`` / ``mention-rewrite.py`` precedent). It
refuses only the shapes above; every other ``gh`` call — including the fleet's own
``--json`` / ``--jq '.field'`` reads — is allowed. It reads the *unexpanded* command
text, so a value the shell assembles at run time (a variable, a ``$'...'`` form) is
invisible to it; those are the hook's approver's to gate, not the decider's (the approver
does not approve a gh command in which an expansion can form or change an option word).
That includes a command substitution inside a ``GH_HOST=`` / ``GH_REPO=`` prefix value:
``GH_HOST=$(echo evil.example.com) gh pr list`` is read as the literal text.

It answers for ``git`` too: it denies the git output flags it reads:
``--output`` (or a leading part of that name, or ``--output-directory``) on any verb and ``-o`` on
``diff``, ``log``, ``show``, ``format-patch``, ``archive`` and ``bundle``, except one that names
``/dev/null``, ``/dev/stdout`` or ``/dev/stderr``. It finds the call the way it finds a gh call:
past assignment prefixes, redirections and wrappers, and past git's own options (``git -C DIR
log``). Unlike the gh rule, it reads a git command's words in the ways the comment above
``_GIT_EXPANSION`` lists. On a verb that can write through an output option it also refuses a word a
command substitution makes and a glob that could match a file named like an output option; on any verb,
a substitution before the verb and ``-c alias.*``.
"""

from __future__ import annotations

import fnmatch
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
# It holds every wrapper the permission hook's `is_gh_command` names
# (`plugin-hooks/pretooluse-permissions.sh`), so a gh call the hook reads as wrapped is
# inspected here too; a test keeps the two lists in step.
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
    "sudo",
    "doas",
    "noglob",
    "nocorrect",
    "coproc",
    "repeat",
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
# The verbs that take a second positional after the repository (`gh repo clone
# <repository> [<directory>]`, a skill name). For every other verb gh refuses a second
# positional before it sends anything, so a word after a parameter-only word can only be
# the repository itself (the parameter was empty) and is read as one.
_SECOND_POSITIONAL = {("repo", "clone")} | {
    (g, v) for g in ("skill", "skills") for v in ("install", "add", "preview", "show")}


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


def _repo_positional(args: list[str]) -> tuple[str, bool, tuple[str, str]] | None:
    """The repository positional of a verb that takes one, whether a parameter-only
    word sat in front of it, and the verb; ``None`` when there is none. Options and their values are
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
                return a, after_param, (pos[0], pos[1])
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


# A host nothing allows. A subscripted `GH_HOST[i]=` / `GH_REPO[i]=` prefix means different strings in bash
# (an array element) and zsh (an edit of the string), so the guard reads it as this.
_UNKNOWN_HOST = "unknown-host.invalid"
_MAX_READINGS = 16

# The descriptor in front of a redirection operator: `2` in `2>&1`, `{fd}` in `{fd}>file`.
_FD_WORD = re.compile(r"[0-9]+|\{[A-Za-z_][A-Za-z0-9_]*\}")


def _is_redirect(tok: str) -> bool:
    """A redirection operator token: ``>``, ``>>``, ``<``, ``<<<``, ``>&``, ``&>``, ``>|``. The lexer
    splits it from its target, which is the next token."""
    return bool(tok) and set(tok) <= set("<>&|") and ("<" in tok or ">" in tok)


_SEP_THEN_REDIRECT = re.compile(r"([;&|()`\n]+)([<>][<>&|]*)")
# `&>file` redirects both streams (zsh adds the clobber forms); the shell does not read it as a `&` separator
# followed by `>`. Splitting it would end the gh segment there and hide every later flag from the inspection.
_AMP_REDIRECTS = ("&>", "&>>", "&>|", "&>>|")


def _split_sep_redirect(tokens: list[str]) -> list[str]:
    """The lexer fuses adjacent punctuation, so ``;>f`` is one token that is neither a separator nor a
    redirection. Split a separator run from the redirection operator after it."""
    out: list[str] = []
    for tok in tokens:
        if tok in _AMP_REDIRECTS:
            out.append(tok)
            continue
        m = _SEP_THEN_REDIRECT.fullmatch(tok) if "<" in tok or ">" in tok else None
        out.extend(m.groups() if m else [tok])
    return out


def _segments(tokens: list[str]) -> list[list[str]]:
    """Split a token stream on shell operators into the segments the shell runs one by one."""
    segments: list[list[str]] = []
    current: list[str] = []
    for tok in _split_sep_redirect(tokens):
        if _is_separator(tok):
            segments.append(current)
            current = []
        else:
            current.append(tok)
    segments.append(current)
    return segments


def _gh_command_words(tokens: list[str]) -> list[list[str]]:
    """Split a token stream on shell operators into segments, and return the argument
    lists of the segments whose command word is ``gh`` (bare, ``\\gh``, wrapped, or a
    path ending in ``gh``)."""
    out: list[list[str]] = []
    for seg in _segments(tokens):
        i = 0
        wrapped = False
        # GH_HOST=<host> / GH_REPO=[HOST/]OWNER/REPO prefixes name the host this call talks to. `held` is what
        # each holds if `+=` appends; `readings` is every value a prefix gave it, and any foreign one denies.
        held: dict[str, str] = {}
        readings: dict[str, list[str]] = {}
        while i < len(seg):
            t = seg[i]
            # a redirection before the command word (`2>&1 gh ...`, `>/dev/null gh ...`) is opened by
            # the shell, which then runs the call: skip the operator and its target
            if _is_redirect(t):
                i += 2
                continue
            if _FD_WORD.fullmatch(t) and i + 1 < len(seg) and _is_redirect(seg[i + 1]):
                i += 1
                continue
            # NAME=, NAME+= and NAME[i]= (bash runs a call behind any of them) are assignment prefixes; a
            # token that opens with `]=` is the tail of a subscript the lexer split at a `$(`
            m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(\[[^\]]*\])?(\+?)=(.*)", t, re.S)
            if m or re.fullmatch(r"\]\+?=.*", t, re.S):
                if m and m.group(1) in ("GH_HOST", "GH_REPO"):
                    name, subscript, plus, value = m.groups()
                    seen = readings.setdefault(name, [])
                    if len(seen) >= _MAX_READINGS:
                        # more prefixes of one name than any real call carries: a doubt denies, and the
                        # work stays linear however long the flood is
                        seen[:] = [_UNKNOWN_HOST if name == "GH_HOST" else f"{_UNKNOWN_HOST}/o/r"]
                        held[name] = ""
                    elif subscript:
                        seen.append(_UNKNOWN_HOST if name == "GH_HOST" else f"{_UNKNOWN_HOST}/o/r")
                    else:
                        # `+=` appends to what an earlier prefix set (`GH_HOST=evil GH_HOST+=x` is still evil).
                        # A later prefix never launders an earlier one, whichever way a shell resolves them
                        # (bash 3.2 assigns where zsh appends): every earlier reading stays.
                        held[name] = held.get(name, "") + value if plus else value
                        seen.append(held[name])
                i += 1
                continue
            base = t.lstrip("\\")
            if base in _WRAPPERS:
                wrapped = True
                i += 2 if base == "repeat" else 1  # zsh `repeat` takes a count word: `repeat $n gh ...`
                continue
            if wrapped and base.rsplit("/", 1)[-1] != "gh":
                # A wrapper's own option or its value (`env -u X`, `timeout -s KILL 5`,
                # `xargs -I {}`, `sudo -u x`): which option takes the next word varies by
                # wrapper, so keep reading words until the gh command word, the way the
                # hook's `is_gh_command` finds it. Each word still goes through the
                # assignment, redirection and wrapper handling above, so a GH_HOST= or
                # GH_REPO= prefix after an option is recorded as it is before one.
                i += 1
                continue
            break
        if i < len(seg) and seg[i].lstrip("\\").rsplit("/", 1)[-1] == "gh":
            args = seg[i + 1 :]
            for name, flag in (("GH_HOST", "--hostname"), ("GH_REPO", "-R")):
                for value in readings.get(name, []):
                    if value:
                        args = args + [flag, value]
            out.append(args)
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
    # from the environment). Only for a verb with a second positional can the word after
    # one be something else (clone's directory, a skill name), so only there does it count
    # just when it names a host outright.
    found = _repo_positional(args)
    if found and "--from-local" not in args:
        repo, after_param, verb = found
        host = None if repo.startswith((".", "/", "~")) or _looks_like_repo_url(repo) else _host_of(repo)
        lenient = after_param and verb in _SECOND_POSITIONAL
        if _foreign(host, allowed) and (not lenient or _host_shaped(host)):
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
                return "gh -R/--repo/--hostname/GH_HOST/GH_REPO names a host other than github.com"
            i += 1
            continue

        # a positional argument that is a repository URL naming a foreign host
        if not a.startswith("-") and _looks_like_repo_url(a):
            if _foreign(_host_of(a), allowed):
                return "gh is pointed at a URL on a host other than github.com"
        i += 1
    return None


# git reads --output in its diff and revision options, so every git command that takes them writes
# the file the option names, and opens it before it reads anything: diff, log, show, whatchanged,
# diff-tree, diff-index, diff-files, stash show and list, reflog, shortlog, rev-list, blame,
# range-diff, format-patch and bundle (measured on git 2.39.5). format-patch's --output-directory
# and archive's --output write too. git takes no abbreviation of either name, and no other option is a
# leading part of one, so any long option that is a leading part of either is read as one.
_GIT_OUTPUT_NAME = "--output-directory"
# -o is format-patch's --output-directory and archive's --output; git refuses it on diff, log, show
# and bundle. On other verbs it means something else (grep -o, ls-files -o), so only these read it.
_GIT_DASH_O = {"diff", "log", "show", "format-patch", "archive", "bundle"}
# format-patch reads -o inside a cluster of short options; archive's are read the same way.
_GIT_DASH_O_CLUSTER = {"format-patch", "archive"}
# git's own options that take the next word as their value (git -C DIR log ...).
_GIT_OPTION_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix",
                     "--config-env", "--attr-source"}
# Output written here changes no file.
_GIT_NO_FILE = {"/dev/null", "/dev/stdout", "/dev/stderr"}
# The shell reads a git command's words before git does, and the git rule reads them the same way. Its
# reading starts from the command text with each `$'...'` decoded and each `$"..."` read as `"..."`; with
# each command substitution (`$(...)`, backticks) left as a mark, its command read on its own; and with a
# glob character the shell does not expand (quoted or escaped) masked. A git word with a `$` or a brace
# in it is then read as written, without its `$` signs, with each parameter expansion taken as empty,
# and with a `${X-word}` form taken as its word; each of those gives the words its brace lists expand to
# (comma lists and sequences, nested, at most _GIT_BRACE_MAX of them). An unquoted `$IFS` is also read
# as a word break, and the strings that `eval`, a shell's `-c` and `env -S` run are read as commands. A
# command that gives the rule more than _GIT_WORDS_MAX words to read is refused.
_GIT_EXPANSION = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|\$[0-9@*#?$!-]")
_GIT_DEFAULT_WORD = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?[-=+?]([^}]*)\}")
_GIT_IFS = re.compile(r"\$\{IFS[^}]*\}|\$IFS(?![A-Za-z0-9_])")
_GIT_EXPANDS = set("${")
_GIT_GLOB = set("*?[")
_GIT_BRACE_MAX = 256
_GIT_WORDS_MAX = 65536  # the words one command may give the git rule to read
# Verbs that take no output option. A word the shell forms after one of them cannot make git write a
# file through one, so the substitution and glob rules read only the words before it there.
_GIT_NO_OUTPUT = {"add", "rm", "mv", "status", "commit", "checkout", "switch", "restore", "branch", "tag",
                  "merge", "rebase", "reset", "fetch", "pull", "push", "clone", "init", "remote", "config",
                  "worktree", "submodule", "clean", "grep", "ls-files", "ls-tree", "cat-file", "rev-parse",
                  "describe", "show-ref", "check-ignore", "check-attr", "apply", "am", "cherry-pick",
                  "revert", "notes", "update-index", "bisect", "gc", "fsck", "prune", "help", "version",
                  "var", "sparse-checkout", "maintenance"}
_GIT_DEPTH_MAX = 3
# Marks in the text the git rule lexes: a command substitution, unquoted and inside double quotes, and a
# glob character the shell does not expand.
_SUBST = "\x01"
_SUBST_QUOTED = "\x05"
_QUOTED_GLOB = {"*": "\x02", "?": "\x03", "[": "\x04"}
_UNMASK = str.maketrans({**{v: k for k, v in _QUOTED_GLOB.items()}, _SUBST: "$(...)", _SUBST_QUOTED: "$(...)"})
_ANSI_C = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
           "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}
_ANSI_C_NUMBER = {"x": re.compile(r"[0-9A-Fa-f]{1,2}"), "u": re.compile(r"[0-9A-Fa-f]{1,4}"),
                  "U": re.compile(r"[0-9A-Fa-f]{1,8}")}
_OCTAL = re.compile(r"[0-7]{1,3}")
_SEQUENCE = re.compile(r"(-?[0-9]+)\.\.(-?[0-9]+)(?:\.\.(-?[0-9]+))?|([A-Za-z])\.\.([A-Za-z])(?:\.\.(-?[0-9]+))?")
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "mksh", "ash", "yash"}


def _ansi_c_body(text: str, i: int) -> tuple[str, int]:
    """The decoded body of the ``$'...'`` whose body starts at ``text[i]``, and the index after it."""
    out: list[str] = []
    n = len(text)
    while i < n:
        c = text[i]
        if c == "'":
            return "".join(out), i + 1
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        d = text[i + 1]
        m = (_ANSI_C_NUMBER[d].match(text, i + 2) if d in _ANSI_C_NUMBER
             else _OCTAL.match(text, i + 1) if d in "01234567" else None)
        if d in _ANSI_C:
            out.append(_ANSI_C[d])
            i += 2
        elif m and d in _ANSI_C_NUMBER:
            out.append(chr(min(int(m.group(), 16), 0x10FFFF)))
            i = m.end()
        elif m:
            out.append(chr(int(m.group(), 8) & 0xFF))
            i = m.end()
        elif d == "c" and i + 2 < n:
            out.append(chr(ord(text[i + 2]) & 0x1F))
            i += 3
        else:
            out.append(text[i : i + 2])
            i += 2
    return "".join(out), n


def _substitution_end(text: str, i: int) -> int:
    """The index of the ``)`` or backtick that ends the substitution at ``text[i]``, or the text's length."""
    n = len(text)
    if text[i] == "`":
        j = i + 1
        while j < n and text[j] != "`":
            j += 2 if text[j] == "\\" else 1
        return min(j, n)
    depth, quote, j = 0, "", i + 1
    while j < n:
        c = text[j]
        if quote:
            if c == "\\" and quote == '"':
                j += 1
            elif c == quote:
                quote = ""
        elif c == "\\":
            j += 1
        elif c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return n


def _git_text(command: str) -> tuple[str, list[str]]:
    """The text the git rule lexes, and the commands of the substitutions in it (see above)."""
    out: list[str] = []
    inner: list[str] = []
    n = len(command)
    i = 0
    quote = ""
    while i < n:
        c = command[i]
        if quote == "'":
            quote = "" if c == "'" else quote
            out.append(_QUOTED_GLOB.get(c, c))
            i += 1
        elif c == "\\" and i + 1 < n:
            out.append("\\" + _QUOTED_GLOB.get(command[i + 1], command[i + 1]))
            i += 2
        elif c == "$" and not quote and command.startswith(("$'", '$"'), i):
            if command[i + 1] == '"':
                i += 1  # $"..." is "..."
                continue
            body, i = _ansi_c_body(command, i + 2)
            masked = "".join(_QUOTED_GLOB.get(ch, ch) for ch in body)
            out.append("'" + masked.replace("'", "'\\''") + "'")
        elif c == "`" or command.startswith("$(", i):
            end = _substitution_end(command, i)
            inner.append(command[i + 1 : end] if c == "`" else command[i + 2 : end])
            out.append(_SUBST_QUOTED if quote else _SUBST)
            i = end + 1
        else:
            if c == '"':
                quote = "" if quote else '"'
            elif c == "'" and not quote:
                quote = "'"
            out.append(_QUOTED_GLOB.get(c, c) if quote else c)
            i += 1
    return "".join(out), inner


def _brace_words(body: str) -> list[str] | None:
    """The words one brace body stands for (a comma list or a sequence), or ``None`` for neither."""
    parts, depth, start, k = [], 0, 0, 0
    while k < len(body):
        c = body[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(body[start:k])
            start = k + 1
        k += 1
    if parts:
        return parts + [body[start:]]
    m = _SEQUENCE.fullmatch(body)
    if not m:
        return None
    if m.group(1) is not None:
        lo, hi, step = int(m.group(1)), int(m.group(2)), abs(int(m.group(3) or 1)) or 1
        width = max(len(m.group(1)), len(m.group(2))) if any(
            g.lstrip("-").startswith("0") and len(g.lstrip("-")) > 1 for g in (m.group(1), m.group(2))) else 0
        if abs(hi - lo) // step >= _GIT_BRACE_MAX:
            return [""] * (_GIT_BRACE_MAX + 1)
        values = range(lo, hi + 1, step) if lo <= hi else range(lo, hi - 1, -step)
        return [str(v).zfill(width) if width else str(v) for v in values]
    lo, hi, step = ord(m.group(4)), ord(m.group(5)), abs(int(m.group(6) or 1)) or 1
    values = range(lo, hi + 1, step) if lo <= hi else range(lo, hi - 1, -step)
    return [chr(v) for v in values]


def _brace_expand(word: str) -> list[str] | None:
    """The words the shell's brace expansion makes of ``word``, or ``None`` past _GIT_BRACE_MAX."""
    i = word.find("{")
    while i >= 0:
        depth, k = 0, i
        while k < len(word):
            depth += {"{": 1, "}": -1}.get(word[k], 0)
            if depth == 0:
                break
            k += 1
        alternatives = None if k >= len(word) or (i > 0 and word[i - 1] == "$") else _brace_words(word[i + 1 : k])
        if alternatives is None:
            i = word.find("{", i + 1)
            continue
        tails = _brace_expand(word[k + 1 :])
        if tails is None:
            return None
        out: list[str] = []
        for alternative in alternatives:
            heads = _brace_expand(alternative)
            if heads is None:
                return None
            for head in heads:
                for tail in tails:
                    out.append(word[:i] + head + tail)
                    if len(out) > _GIT_BRACE_MAX:
                        return None
        return out
    return [word]


def _git_command_words(tokens: list[str]) -> list[list[str]]:
    """The argument lists of the segments whose command word is ``git`` (bare, ``\\git``, wrapped,
    or a path ending in ``git``), found the way ``_gh_command_words`` finds a gh call."""
    out: list[list[str]] = []
    for seg in _segments(tokens):
        i = 0
        wrapped = False
        while i < len(seg):
            t = seg[i]
            if _is_redirect(t):
                i += 2
                continue
            if _FD_WORD.fullmatch(t) and i + 1 < len(seg) and _is_redirect(seg[i + 1]):
                i += 1
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=.*|\]\+?=.*", t, re.S):
                i += 1
                continue
            base = t.lstrip("\\")
            if base in _WRAPPERS:
                wrapped = True
                i += 2 if base == "repeat" else 1
                continue
            if wrapped and base.rsplit("/", 1)[-1] != "git":
                i += 1  # a wrapper's own option or its value
                continue
            break
        if i < len(seg) and seg[i].lstrip("\\").rsplit("/", 1)[-1] == "git":
            out.append(seg[i + 1 :])
    return out


def _command_strings(tokens: list[str]) -> list[str]:
    """The strings a segment hands to be run as commands: the words after ``eval``, the string after a
    shell's ``-c``, and the string after ``env -S`` or ``--split-string``."""
    out: list[str] = []
    for seg in _segments(tokens):
        for k, tok in enumerate(seg):
            base = tok.lstrip("\\").rsplit("/", 1)[-1]
            if base == "eval":
                out.append(" ".join(seg[k + 1 :]))
            elif base in _SHELLS:
                for m in range(k + 1, len(seg)):
                    opt = seg[m]
                    if not opt.startswith("-") or opt == "--":
                        break
                    if not opt.startswith("--") and "c" in opt[1:]:
                        out.extend(seg[m + 1 : m + 2])
                        break
            elif base == "env":
                for m in range(k + 1, len(seg)):
                    opt = seg[m]
                    if opt in ("-S", "--split-string"):
                        out.extend(seg[m + 1 : m + 2])
                    elif opt.startswith("--split-string="):
                        out.append(opt.split("=", 1)[1])
                    elif opt.startswith("-S"):
                        out.append(opt[2:])
    return out


def _git_spellings(arg: str) -> set[str] | None:
    """The words the git rule reads a git argument as (see above), or ``None`` past _GIT_BRACE_MAX."""
    if not _GIT_EXPANDS & set(arg):
        return {arg}
    forms = {arg, arg.replace("$", ""), _GIT_EXPANSION.sub("", arg), _GIT_DEFAULT_WORD.sub(lambda m: m.group(1), arg)}
    out: set[str] = set()
    for form in forms:
        words = _brace_expand(form)
        if words is None:
            return None
        out.update(words)
    return out


def _git_output_name(name: str) -> bool:
    """Whether a long option's name is --output, --output-directory or a leading part of either, or a glob
    the shell could match to one."""
    if name.startswith("--ou") and _GIT_OUTPUT_NAME.startswith(name):
        return True
    return bool(_GIT_GLOB & set(name)) and any(fnmatch.fnmatchcase(n, name) for n in ("--output", _GIT_OUTPUT_NAME))


def _git_glob_could_name_output(name: str, known: str) -> bool:
    """Whether a glob in a word's name part could match a file whose name reads as an output option."""
    k = next((j for j, ch in enumerate(name) if ch in _GIT_GLOB), -1)
    if k < 0:
        return False
    lead = name[:k]
    return (_GIT_OUTPUT_NAME.startswith(lead)
            or (known in _GIT_DASH_O and ("-o".startswith(lead) or lead.startswith("-o")))
            or (known in _GIT_DASH_O_CLUSTER and lead.startswith("-") and not lead.startswith("--")))


def _shown(word: str) -> str:
    return word.translate(_UNMASK)


def _inspect_git_args(args: list[str], budget: list[int] | None = None) -> str | None:
    """Return a deny reason for one git invocation's argument list, or ``None``. A word with an unquoted
    ``$IFS`` is read both as one word and split there. ``budget`` counts down the words read."""
    budget = [_GIT_WORDS_MAX] if budget is None else budget
    variants = [args]
    if any(_GIT_IFS.search(a) for a in args):
        variants.append([piece for a in args for piece in _GIT_IFS.split(a) if piece])
    for variant in variants:
        reason = _inspect_git_words(variant, budget)
        if reason:
            return reason
    return None


def _inspect_git_words(args: list[str], budget: list[int]) -> str | None:
    i = 0
    values: set[int] = set()  # where git's own options take their value
    while i < len(args) and args[i].startswith("-"):  # git's own options, before the verb
        opt = args[i]
        takes = opt in _GIT_OPTION_VALUE
        value = (args[i + 1] if i + 1 < len(args) else "") if takes else opt.partition("=")[2]
        if (opt == "-c" or opt.startswith("--config-env")) and value.lower().startswith("alias."):
            return "git -c alias.* defines a git command the guard does not read; run the command it names instead"
        if takes:
            values.add(i + 1)
        i += 2 if takes else 1
    verb = args[i] if i < len(args) else ""
    rest = args[i + 1 :]
    # a verb that may write through an output option: any but those listed, an alias's name included
    open_verb = verb not in _GIT_NO_OUTPUT
    for j, arg in enumerate(args):
        if j > i and arg in ("--", "--end-of-options"):
            break
        if j > i and not open_verb:
            break
        if _SUBST in arg:
            return "git: an unquoted command substitution can make any words of this git command; run git with its words written out"
        if j not in values and _SUBST_QUOTED in arg and (
            arg.startswith(_SUBST_QUOTED) or (arg.startswith("-") and _SUBST_QUOTED in arg.partition("=")[0])
        ):
            return "git: a command substitution makes one of this git command's options or its verb; run git with its words written out"
    # a verb an expansion or a glob forms could be any verb, so it is read as the strictest one
    known = verb if not (_GIT_EXPANDS | _GIT_GLOB) & set(verb) else "format-patch"
    for k, arg in enumerate(rest):
        if arg in ("--", "--end-of-options"):
            break  # what follows is a path or a revision, not an option
        spellings = _git_spellings(arg)
        if spellings is None:
            return f"git {_shown(verb)}: a brace list in {_shown(arg)} makes more than {_GIT_BRACE_MAX} words; write the words out"
        budget[0] -= len(spellings)
        if budget[0] < 0:
            return f"git: this command gives the guard more than {_GIT_WORDS_MAX} words to read; split it into shorter commands"
        for word in spellings:
            name, eq, value = word.partition("=")
            if _git_output_name(name) and (open_verb or not _GIT_GLOB & set(name)):
                target = value if eq else (rest[k + 1] if k + 1 < len(rest) else "")
                if word == arg and target in _GIT_NO_FILE:
                    continue
                shown = _shown(name)
                return f"git {_shown(verb)} {shown} writes its output to a file; run it without {shown} and read the output"
            if word.startswith("-") and not word.startswith("--"):
                if (known in _GIT_DASH_O and word.startswith("-o")) or (
                    known in _GIT_DASH_O_CLUSTER and "o" in word[1:]
                ):
                    return f"git {_shown(verb)} -o writes its output to a file; run it without -o and read the output"
            if open_verb and _git_glob_could_name_output(name, known):
                return (f"git {_shown(verb)}: the shell can expand {_shown(word)} to a file named like an output option; "
                        "quote it, or put it after --")
    return None


def _git_reason(command: str, depth: int = 0, budget: list[int] | None = None) -> str | None:
    """The deny reason for the first git call in ``command`` the git rule refuses, or ``None``."""
    budget = [_GIT_WORDS_MAX] if budget is None else budget
    text, inner = _git_text(command)
    for tokens in _readings(text):
        for args in _git_command_words(tokens):
            reason = _inspect_git_args(args, budget)
            if reason:
                return reason
        if depth < _GIT_DEPTH_MAX:
            for string in _command_strings(tokens):
                reason = _git_reason(string, depth + 1, budget)
                if reason:
                    return reason
    if depth < _GIT_DEPTH_MAX:
        for string in inner:
            reason = _git_reason(string, depth + 1, budget)
            if reason:
                return reason
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
    reason = _git_reason(command)
    if reason:
        return ("deny", reason)
    return ("allow", "")


def main(argv: list[str]) -> int:
    # stdin as bytes: a text-mode read is strict in the locale's encoding and raises on a byte it
    # cannot decode, which the hook reads as "did not answer" and fails open. argv got
    # surrogateescape; so does this.
    command = (
        argv[1]
        if len(argv) > 1
        else sys.stdin.buffer.read().decode("utf-8", "surrogateescape")
    )
    import os

    verdict, reason = decide(command, gh_host=os.environ.get("GH_HOST", ""))
    if verdict == "deny":
        print(reason)
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
