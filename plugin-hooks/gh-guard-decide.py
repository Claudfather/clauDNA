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
text, so a value the shell assembles at run time (a variable, a command substitution) is
invisible to it; those are the hook's approver's to gate, not the decider's (the approver
does not approve a gh command in which an expansion can form or change an option word).
That includes a command substitution inside a ``GH_HOST=`` / ``GH_REPO=`` prefix value:
``GH_HOST=$(echo evil.example.com) gh pr list`` is read as the literal text. A ``$'...'`` or
``$"..."`` string is quoting, not a value assembled at run time: the decider also reads the
command with each one written as the value bash gives it (``_dollar_quotes``).

It answers for ``git`` too: it denies the git output flags it reads:
``--output`` (or a leading part of that name, or ``--output-directory``) on any verb, except one
that names ``/dev/null``, ``/dev/stdout`` or ``/dev/stderr``, and ``-o`` on ``diff``, ``log``,
``show``, ``format-patch``, ``archive`` and ``bundle``, whatever it names. It finds the call the
way it finds a gh call:
past assignment prefixes, redirections and wrappers, and past git's own options (``git -C DIR
log``). Unlike the gh rule, it also reads an option word the shell would form from an expansion,
a brace list or a glob, in the forms its parser handles.
"""

from __future__ import annotations

import bisect
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


# A backslash and the character it escapes, paired from the left as bash pairs them, so a backslash
# that another one escapes continues no line. A backslash before a CR-LF line end pairs with both.
_ESCAPE_PAIR = re.compile(r"\\(?:\r\n|.)", re.S)
# Where a word starts, so that a ``#`` there starts a comment: after a blank, a newline or an
# operator character.
_WORD_START = " \t\n;&|()<>`"
# The run of characters each quoting state passes over unchanged.
_SHELL_PLAIN = {
    "": re.compile(r"[^\\'\"#]+"),
    '"': re.compile(r'[^\\"]+'),
    "$'": re.compile(r"[^\\']+"),
}


def _joined(command: str) -> str:
    """The text with each backslash-newline continuation removed. Backslashes pair from the left, so
    a line that ends in an escaped backslash keeps the newline that ends its command. A backslash
    before a CR-LF line end continues the line here, as in a shell that drops the carriage return;
    ``_shell_text`` reads it the way bash does on Linux, as an escaped carriage return and then the
    end of the command."""
    return _ESCAPE_PAIR.sub(
        lambda m: "" if m.group(0) in ("\\\n", "\\\r\n") else m.group(0), command
    )


def _shell_text(command: str) -> str:
    """The text as bash reads its lines, in one pass from the left with the quoting carried from
    line to line: a continuation is removed outside quotes and inside double quotes, a comment is
    dropped up to the newline that ends it (a backslash at its end included), and a quoted string
    runs to its closing quote with every line and ``#`` in it kept. It knows no heredoc; the other
    readings cover that doubt."""
    out: list[str] = []
    quote = ""  # "", "'", '"' or "$'"
    prev = "\n"
    i, n = 0, len(command)
    while i < n:
        if quote == "'":
            j = command.find("'", i)
            j = n if j < 0 else j + 1
            out.append(command[i:j])
            quote, prev, i = "", "'", j
            continue
        m = _SHELL_PLAIN[quote].match(command, i)
        if m:
            out.append(m.group())
            prev, i = command[m.end() - 1], m.end()
            continue
        ch = command[i]
        if ch == "\\":
            if quote != "$'" and command.startswith("\n", i + 1):
                i += 2  # a continuation
                continue
            out.append(command[i : i + 2])
            prev, i = "a", i + 2  # an escaped character is part of a word
            continue
        if quote:  # the quote that closes the string
            quote = ""
        elif ch == "#" and prev in _WORD_START:
            j = command.find("\n", i)
            i = n if j < 0 else j  # the newline that ends the comment stays
            continue
        elif ch != "#":  # a quote that opens a string
            quote = "$'" if ch == "'" and prev == "$" else ch
        out.append(ch)
        prev, i = ch, i + 1
    return "".join(out)


# The one-character escapes of a $'...' string; \cX and the numeric forms are read in _ansi_c_value.
_ANSI_C_SIMPLE = {
    "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
    "\\": "\\", "'": "'", '"': '"', "?": "?",
}
# Octal (one to three digits), \xHH (one or two), \uHHHH (one to four) and \UHHHHHHHH (one to eight).
_ANSI_C_NUMERIC = re.compile(r"[0-7]{1,3}|x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})")
# \x{...}: any number of hex digits, the value cut to one byte, the closing brace optional.
_ANSI_C_BRACED = re.compile(r"x\{([0-9A-Fa-f]*)\}?")


class _Unreadable(ValueError):
    """A string whose value the decider does not give the way bash does; ``decide`` denies the command."""


def _ansi_c_value(body: str) -> str:
    """The value bash gives the body of a ``$'...'`` string: its backslash escapes decoded, an octal
    one to eight bits, and the value cut at a NUL. An escape bash does not decode keeps its backslash.
    A value above 0x7F is read as a character, not as bash's bytes. ``_Unreadable`` for a ``\\c``
    before a backslash pair, a DEL byte or a 0x01 byte: bash 5.2 takes the pair whole, and its reader
    keeps a DEL or 0x01 byte behind a 0x01 byte of its own, which the ``\\c`` then takes."""
    out: list[str] = []
    i, n = 0, len(body)
    while i < n:
        if body[i] != "\\" or i + 1 == n:
            out.append(body[i])
            i += 1
            continue
        nxt = body[i + 1]
        if nxt in _ANSI_C_SIMPLE:
            out.append(_ANSI_C_SIMPLE[nxt])
            i += 2
            continue
        if nxt == "c" and i + 2 < n:  # \cX: the control character, and \c? is DEL
            x = body[i + 2]
            if x in "\x01\x7f" or body.startswith("\\\\", i + 2):
                raise _Unreadable(
                    "the gh read-guard does not read a $'...' string in which \\c comes before a backslash"
                    " pair, a DEL byte or a 0x01 byte"
                )
            if x == "?":
                out.append("\x7f")
            elif x < "\x80":
                out.append(chr(ord(x.upper()) & 0x1F))
            else:  # bash works on the first UTF-8 byte; 0xE0 (U+0800 to U+0FFF) gives 0, which ends the value
                first, *rest = x.encode("utf-8", "surrogatepass")
                out.append(chr(first & 0x1F) + bytes(rest).decode("latin-1"))
            i += 3
            continue
        m = _ANSI_C_BRACED.match(body, i + 1)
        if m:  # as bash 5.2 reads \x{...}: no digit gives 0, which ends the value
            out.append(chr(int(m.group(1) or "0", 16) & 0xFF))
            i = m.end()
            continue
        m = _ANSI_C_NUMERIC.match(body, i + 1)
        if m:
            digits = m.group(1) or m.group(2) or m.group(3)
            if digits is None:
                out.append(chr(int(m.group(), 8) & 0xFF))
            elif int(digits, 16) < 0x80000000:  # a \U value of 0x80000000 or more gives nothing, as in bash
                out.append(chr(min(int(digits, 16), 0x10FFFF)))
            i = m.end()
            continue
        out.append(body[i : i + 2])
        i += 2
    return "".join(out).split("\0", 1)[0]


def _ansi_c_end(command: str, start: int) -> int:
    """Where the quote that closes a ``$'...'`` body starting at ``start`` is (the text's length if
    none): in the body a backslash escapes the next character, an apostrophe included."""
    i, n = start, len(command)
    while i < n:
        if command[i] == "'":
            return i
        i += 2 if command[i] == "\\" else 1
    return n


def _dollar_quotes(command: str) -> str:
    """The text with each ``$'...'`` string written as the single-quoted value bash gives it, and the
    ``$`` of each ``$"..."`` string dropped: with no message catalog, bash reads that string as the
    double-quoted one. Read in one pass from the left with the quoting carried, as ``_shell_text``
    reads it, so a ``$'`` inside another string or in a comment stays as it is."""
    out: list[str] = []
    quote = ""  # "", "'" or '"'
    prev = "\n"
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote == "'":
            j = command.find("'", i)
            j = n if j < 0 else j + 1
            out.append(command[i:j])
            quote, prev, i = "", "'", j
        elif ch == "\\":
            out.append(command[i : i + 2])
            prev, i = "a", i + 2  # an escaped character is part of a word
        elif quote == '"':
            out.append(ch)
            quote = "" if ch == '"' else quote
            prev, i = ch, i + 1
        elif ch == "#" and prev in _WORD_START:
            j = command.find("\n", i)
            j = n if j < 0 else j
            out.append(command[i:j])  # a comment, as it is
            prev, i = "#", j
        elif ch == "$" and command.startswith("$", i + 1):
            out.append("$$")
            prev, i = "$", i + 2
        elif ch == "$" and command.startswith("'", i + 1):
            end = _ansi_c_end(command, i + 2)
            out.append(shlex.quote(_ansi_c_value(command[i + 2 : end])))
            prev, i = "'", end + 1
        elif ch == "$" and command.startswith('"', i + 1):
            out.append('"')
            quote, prev, i = '"', '"', i + 2
        else:
            quote = ch if ch in "'\"" else quote
            out.append(ch)
            prev, i = ch, i + 1
    return "".join(out)


# A here-document operator, `<<` or `<<-` but not the `<<<` of a here-string, and the blanks after it.
_HEREDOC_OP = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*")
# The most here-document delimiters, and the most body ends, that the guard reads in one command, and
# the most text it reads after the body ends, in all; more denies, so the work stays bounded however
# many a command holds.
_MAX_HEREDOCS = 16
_MAX_HEREDOC_TEXT = 1 << 20


def _heredoc_word(command: str, i: int) -> tuple[str, bool] | None:
    """The delimiter bash makes of the word at ``i`` after a here-document operator, and whether any
    part of that word is quoted. bash removes the word's quotes and backslashes, decodes a ``$'...'``
    string in it, drops the ``$`` of a ``$"..."`` one and expands nothing else, so ``<<$X`` ends at a
    line that reads ``$X``. ``None`` when no word starts at ``i``."""
    out: list[str] = []
    quoted = False
    start, n = i, len(command)
    while i < n and command[i] not in " \t\n;&|()<>":
        ch = command[i]
        if ch == "\\":
            if not command.startswith("\n", i + 1):  # a backslash-newline joins the word's lines
                quoted = True
                out.append(command[i + 1 : i + 2])
            i += 2
        elif ch == "'":
            quoted = True
            j = command.find("'", i + 1)
            j = n if j < 0 else j
            out.append(command[i + 1 : j])
            i = j + 1
        elif ch == '"' or (ch == "$" and command.startswith('"', i + 1)):
            quoted = True
            i += 1 if ch == '"' else 2
            while i < n and command[i] != '"':
                if command[i] == "\\" and command[i + 1 : i + 2] in ("\\", '"', "$", "`", "\n"):
                    out.append(command[i + 1] if command[i + 1] != "\n" else "")
                    i += 2
                    continue
                out.append(command[i])
                i += 1
            i += 1
        elif ch == "$" and command.startswith("'", i + 1):
            quoted = True
            end = _ansi_c_end(command, i + 2)
            out.append(_ansi_c_value(command[i + 2 : end]))
            i = end + 1
        else:
            out.append(ch)
            i += 1
    return ("".join(out), quoted) if i > start else None


def _heredoc_restarts(command: str) -> list[int] | None:
    """Where bash may read commands again after a here-document body: after each later line that would
    end a body, for each delimiter in the text, wherever its operator stands, so that a reading can
    start there with no quote open (a doubt adds a reading). bash ends a body at the first line that
    is its delimiter, once it drops the line's NUL bytes, joins each backslash-newline when no part of
    the delimiter is quoted, and, for ``<<-``, drops the leading tabs. In a command substitution a
    line that starts with the delimiter and holds a ``)`` after it ends one too, and bash reads on
    from the rest of that line. ``None`` when the command holds more delimiters or body ends than the
    guard reads, more joined lines than it walks, or more text after the body ends than it reads."""
    if "<<" not in command:
        return []
    lines = command.split("\n")
    starts = [0]
    for ln in lines[:-1]:
        starts.append(starts[-1] + len(ln) + 1)
    plain = [ln.replace("\0", "") for ln in lines]
    # a body line that ends in an odd run of backslashes joins the next one
    joins = [(len(ln) - len(ln.rstrip("\\"))) % 2 == 1 for ln in plain]
    delims: dict[tuple[str, bool, bool], int] = {}  # (delimiter, <<-, quoted) -> the first operator's line
    for m in _HEREDOC_OP.finditer(command):
        word = _heredoc_word(command, m.end())
        if word is not None:
            delims.setdefault((word[0], m.group(1) == "-", word[1]), bisect.bisect_right(starts, m.start()) - 1)
            if len(delims) > _MAX_HEREDOCS:
                return None
    found: set[int] = set()
    walk = 64 * len(lines) + 4096  # the joined lines walked, over every delimiter
    for (delim, strip, quoted), first in delims.items():
        for k in range(first + 1, len(lines)):
            text, last = plain[k], k
            if not quoted and joins[k]:
                # the body line that starts here, its backslash-newlines joined, walked only while it
                # is no longer than the delimiter
                text = ""
                while joins[last] and last + 1 < len(lines) and len(text.lstrip("\t") if strip else text) <= len(delim):
                    text += plain[last][:-1]
                    last += 1
                    walk -= 1
                    if walk < 0:
                        return None
                if joins[last] and last + 1 < len(lines):
                    continue  # longer than the delimiter: this line ends no body
                text += plain[last]
            body = text.lstrip("\t") if strip else text
            if delim in (text, body):
                if last + 1 < len(lines):
                    found.add(starts[last + 1])
            elif last == k and body.startswith(delim) and ")" in body[len(delim) :]:
                raw = lines[k]
                found.add(starts[k] + (len(raw) - len(raw.lstrip("\t")) if strip else 0) + len(delim))
            if len(found) > _MAX_HEREDOCS:
                return None
    if sum(len(command) - start for start in found) > _MAX_HEREDOC_TEXT:
        return None
    return sorted(found)


def _readings(command: str, lines: bool = True) -> list[list[str]]:
    """The token streams to inspect: the whole text, then every line on its own (unless ``lines`` is
    false), for each of two readings of the lines.

    The first joins each continuation as bash joins one outside quotes (``_joined``), then drops
    each line's comment. The second (``_shell_text``) carries the quoting from line to line as bash
    does, so a comment ends at its newline and a quoted string that spans lines keeps all it holds;
    it is read where it differs from the first. A quote that pairs up across lines (an apostrophe in
    a comment or in a heredoc body) hides the lines between in a whole-text reading only; each line
    read alone still shows them, and ``decide`` also reads the text after each line that may end a
    heredoc body (``_heredoc_restarts``), so a quoted string that spans lines after a body is read
    from its start. A heredoc body is not skipped. Every reading only adds denials, so a doubt is
    inspected, not skipped.

    The trade: prose in a heredoc body that holds a gh call with a denied flag is denied. In
    recorded traffic that is a markdown code span, since a backtick starts a command for this
    reading, and not a line that starts with the call (which is denied too). Write such prose
    with the file tools and pass it with --body-file.
    """
    parts = [_strip_comment(ln) for ln in _joined(command).split("\n")]
    text = "\n".join(parts)
    out = [_lex(text)]
    if lines and len(parts) > 1:
        out.extend(_lex(ln) for ln in parts)
    shell = _shell_text(command)
    if shell != text:
        out.append(_lex(shell))
        seen = set(parts)
        for raw in shell.split("\n") if lines else []:
            ln = _strip_comment(raw)
            if ln not in seen:
                seen.add(ln)
                out.append(_lex(ln))
    return out


def _texts(command: str) -> list[str]:
    """The command's text, then the text with its $'...' and $"..." strings as bash gives them, read
    after it: as it stands, with its continuations joined (bash joins a line that ends in `$\\` to the
    next, so a quote there opens a string), and line by line (an apostrophe in a heredoc body opens
    no string)."""
    joined = _joined(command)
    texts = [command]
    for raw, text in (
        (command, _dollar_quotes(command)),
        (joined, _dollar_quotes(joined)),
        (joined, "\n".join(_dollar_quotes(line) for line in joined.split("\n"))),
    ):
        if text != raw and text not in texts:
            texts.append(text)
    return texts


def _after_heredocs(command: str, restarts: list[int]):
    """The whole-text readings of the text after each here-document body, read as it stands and as the
    rest of a double-quoted string (a body inside ``"$(...)"`` ends inside one)."""
    for start in restarts:
        for rest in (command[start:], '"' + command[start:]):
            for text in _texts(rest):
                yield from _readings(text, lines=False)


def _first_reason(streams, allowed: set[str]) -> str | None:
    """The deny reason for the first gh or git call in ``streams`` that the guard refuses, if any."""
    for tokens in streams:
        for args in _gh_command_words(tokens):
            reason = _inspect_gh_args(args, allowed)
            if reason:
                return reason
        for args in _git_command_words(tokens):
            reason = _inspect_git_args(args)
            if reason:
                return reason
    return None


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
# The decider reads the text after quote removal. It also reads an option word the shell would form
# from an expansion, a brace list or a glob, in the forms its parser handles (`_git_spellings`).
_GIT_EXPANSION = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|\$[0-9@*#?$!-]")
_GIT_DEFAULT_WORD = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?[-=+?]([^}]*)\}")
_GIT_BRACE_LIST = re.compile(r"\{([^{}]*,[^{}]*)\}")
_GIT_EXPANDS = set("${")
_GIT_GLOB = set("*?[")


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


def _git_spellings(arg: str) -> set[str]:
    """The words the decider reads a git argument as, in the forms its parser handles."""
    if not _GIT_EXPANDS & set(arg):
        return {arg}
    forms = {arg, arg.replace("$", ""), _GIT_EXPANSION.sub("", arg), _GIT_DEFAULT_WORD.sub(lambda m: m.group(1), arg)}
    out = set(forms)
    for form in forms:
        m = _GIT_BRACE_LIST.search(form)
        if m:
            out.update(form[: m.start()] + alt + form[m.end() :] for alt in m.group(1).split(","))
    return out


def _git_output_name(name: str) -> bool:
    """Whether a long option's name is --output, --output-directory or a leading part of either, or a glob
    that matches --output or --output-directory."""
    if name.startswith("--ou") and _GIT_OUTPUT_NAME.startswith(name):
        return True
    return bool(_GIT_GLOB & set(name)) and any(fnmatch.fnmatchcase(n, name) for n in ("--output", _GIT_OUTPUT_NAME))


def _inspect_git_args(args: list[str]) -> str | None:
    """Return a deny reason for one git invocation's argument list, or ``None``."""
    i = 0
    while i < len(args) and args[i].startswith("-"):  # git's own options, before the verb
        i += 2 if args[i] in _GIT_OPTION_VALUE else 1
    verb = args[i] if i < len(args) else ""
    rest = args[i + 1 :]
    # a verb an expansion forms could be any verb, so it is read as the strictest one
    known = verb if not (_GIT_EXPANDS | _GIT_GLOB) & set(verb) else "format-patch"
    for k, arg in enumerate(rest):
        if arg in ("--", "--end-of-options"):
            break  # what follows is a path or a revision, not an option
        for word in _git_spellings(arg):
            name, eq, value = word.partition("=")
            if _git_output_name(name):
                target = value if eq else (rest[k + 1] if k + 1 < len(rest) else "")
                if word == arg and target in _GIT_NO_FILE:
                    continue
                return f"git {verb} {name} writes its output to a file; run it without {name} and read the output"
            if word.startswith("-") and not word.startswith("--"):
                if (known in _GIT_DASH_O and word.startswith("-o")) or (
                    known in _GIT_DASH_O_CLUSTER and "o" in word[1:]
                ):
                    return f"git {verb} -o writes its output to a file; run it without -o and read the output"
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
    try:
        reason = _first_reason((t for text in _texts(command) for t in _readings(text)), allowed)
        if reason is None:
            # the text after each here-document body, read from where bash reads it, once the
            # command's own readings allow it
            restarts = _heredoc_restarts(command)
            if restarts is None:
                reason = (
                    f"the gh read-guard reads at most {_MAX_HEREDOCS} here-documents, and"
                    f" {_MAX_HEREDOC_TEXT >> 20} MiB of text after them, in one command"
                )
            else:
                reason = _first_reason(_after_heredocs(command, restarts), allowed)
    except _Unreadable as exc:
        reason = str(exc)
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
