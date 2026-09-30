#!/usr/bin/env python3
"""Deterministic credential redactor for review + subagent output (#548).

Bots that echo infra/CLI output into their findings must not surface a
live-looking credential. Prose guidance ("mask secrets") failed twice — a
Telegram bot token and a neon API key both leaked — because it only ever
illustrated the ``sk-****`` shape and left redaction to the model's memory.

This module makes the redaction step mechanical: once output is run through
it, masking no longer depends on the model remembering which shapes to hide.
Invocation stays by instruction — the review + subagent chains run it over a
findings file before that file is returned or published (a bare command, no
pipe, per orchestration-guide §7):

    python3 scripts/redact.py <findings-file>

It also reads stdin → stdout, and ``redact_text`` can be imported directly. It
is intentionally conservative about over-redaction: git SHAs (lowercase hex),
UUIDs, file:line references, and plain identifiers pass through untouched, so
review output stays readable.

WHAT IT COVERS is exactly what ``tests/test_redact.py`` tests, one case per
shape: vendor-prefixed keys (current and legacy formats), a value named by its
context (a secret-named assignment, a secret flag, an ``Authorization`` header,
a ``curl -u user:password``, a URL password), PEM private-key blocks, and a long
mixed-case token as a backstop. A shape with no test is not covered. A bare
UUID-shaped or lowercase-hex token with nothing naming it passes through, since
it cannot be told from a request id or a commit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MASK = "[REDACTED]"

# A token's edges. Several current formats join their parts with `_` or `-`
# (`github_pat_…`, `sk_live_…`, `sk-proj-…`), which `\b` treats as the inside of
# a word, so those rules bound a token with lookarounds instead.
_START = r"(?<![A-Za-z0-9_-])"
_END = r"(?![A-Za-z0-9_-])"


# One line of a PEM key's body, after the line break before it (a real one, or
# `\n` escaped inside a JSON string): an encryption header, or base64, possibly
# empty (the blank line after the headers) and possibly with trailing spaces. The
# lookahead makes the line end where the key's line ends, so the pattern never
# takes the start of the prose line after a key (the `F3` of `F3: README typo`).
_KEY_LINE = (
    r"(?:\r?\n|\\n)"
    r"(?:(?:Proc-Type|DEK-Info|Comment): (?:(?!\\n)[^\r\n])*|[A-Za-z0-9+/=]*[ \t]*)"
    r"(?=\r?\n|\\n|\Z|[\"'])"
)


def _pem(m: re.Match) -> str:
    kind, whole = m.group(1), m.group(0)
    begin = f"-----BEGIN {kind}PRIVATE KEY-----"
    if whole == begin:
        return whole  # a BEGIN line quoted with no key after it
    sep = "\n" if "\n" in whole else "\\n"
    tail = f"{sep}-----END {kind}PRIVATE KEY-----" if m.group(2) else ""
    return f"{begin}{sep}{MASK}{tail}"


# Ordered most-specific → most-general. Each (pattern, replacement) is applied
# in turn; a span matched by an earlier rule is masked before a later, more
# general rule sees it. Most replacements are MASK; the flag, header, userinfo
# and assignment rules keep what names the value, so output stays readable.
PATTERNS: list[tuple[re.Pattern[str], object]] = [
    # A PEM private key, whole block. Base64 lines carry `+` and `/`, which split
    # them into runs too short for the backstop. A block that is cut off (a
    # BEGIN line quoted in prose, a capture of the first lines of a key file) is
    # masked through its key lines and no further: what follows it survives.
    (
        re.compile(
            r"-----BEGIN ((?:[A-Z0-9]+ )*)PRIVATE KEY-----"
            r"(?:.*?(-----END \1PRIVATE KEY-----)|(?:" + _KEY_LINE + r")*)",
            re.S,
        ),
        _pem,
    ),
    # Telegram bot token: <8-10 digits>:<35+ base64url> (a real leak). A digit
    # lookbehind, not \b: inside a bot URL (`/bot<id>:<secret>`) the digits
    # follow a letter.
    (re.compile(r"(?<!\d)\d{8,10}:[A-Za-z0-9_-]{35,}" + _END), MASK),
    # Vendor-prefixed keys. The prefix is the signal; length guards false hits.
    (re.compile(_START + r"github_pat_[A-Za-z0-9_]{22,}"), MASK),  # GitHub fine-grained PAT
    (re.compile(_START + r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"), MASK),  # Stripe
    (re.compile(_START + r"whsec_[A-Za-z0-9+/=]{16,}"), MASK),  # Stripe webhook secret
    # OpenAI project and service keys, Anthropic, OpenRouter
    (re.compile(_START + r"sk-(?:proj|svcacct|admin|ant|or)-[A-Za-z0-9_-]{20,}"), MASK),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{20,}\b"), MASK),  # OpenAI / Stripe-style (older)
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), MASK),  # GitHub PAT / token
    (re.compile(_START + r"(?:npm|hf|gsk)_[A-Za-z0-9]{20,}"), MASK),  # npm, Hugging Face, Groq
    (re.compile(_START + r"glpat-[A-Za-z0-9_-]{20,}"), MASK),  # GitLab PAT
    (re.compile(r"\bnapi_[A-Za-z0-9]{20,}\b"), MASK),  # neon API key (a real leak)
    (re.compile(_START + r"xox[a-z](?:\.xox[a-z])?-[A-Za-z0-9-]{10,}"), MASK),  # Slack token
    (re.compile(_START + r"xapp-[A-Za-z0-9-]{20,}"), MASK),  # Slack app-level token
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), MASK),  # AWS access key id (long-term, temporary)
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), MASK),  # Google API key
    # An auth header: keep the header's name and scheme.
    (
        re.compile(
            r"(?i)\b((?:proxy-)?authorization|x-api-key|x-auth-token)"
            r"([\"']?\s*:\s*[\"']?(?:(?:bearer|basic|token|bot|digest)\s+)?)[^\s'\"]+"
        ),
        r"\1\2" + MASK,
    ),
    # Secret inlined as a CLI flag (`--api-key X`, `--access-token X`, `--password X`).
    # Infra engines pass credentials this way; a failed command echoed verbatim
    # (infra-cli-contract §7) leaks the value whatever shape it takes. Keep the
    # flag name so the redacted command stays legible.
    (
        re.compile(
            r"(--(?:(?:api|access|secret|private)[-_]?key|client[-_]secret"
            r"|token(?:[-_](?:secret|id))?|(?:api|access|refresh|bearer|auth)[-_]?token"
            r"|password|passwd|secret)[=\s])\S+",
            re.IGNORECASE,
        ),
        r"\1" + MASK,
    ),
    # `curl -u user:password` / `--user user:password`: keep the user. Only on a
    # curl or wget line: elsewhere `-u` is another flag (`date -u +%H:%M`,
    # `docker run -u 1000:1000`, `rsync -u host:/path`).
    (
        re.compile(r"(\b(?:curl|wget)\b[^\n]*?\s(?:-u|--user)[=\s]*[^:\s]+:)\S+"),
        r"\1" + MASK,
    ),
    # Credential in a connection string: scheme://user:PASSWORD@host, the user
    # possibly empty (`redis://:pw@host`). neon's DATABASE_URL is the primary
    # neon credential and matches no vendor prefix. Keep scheme and host.
    (re.compile(r"(://)[^:/@\s]*:[^@/\s]+(@)"), r"\1" + MASK + r"\2"),
    # A secret-named field assigned a value, in shell, env, YAML or JSON form.
    # The keyword may sit anywhere in the name (SECRET_KEY, apiKey, clientSecret)
    # but may not run on into a lowercase word (tokenizer, max_tokens); a name
    # ending in _PAT, _PASS or _PWD counts (GITHUB_PAT, DB_PASS). Keep the name.
    (
        re.compile(
            r"(?<![A-Za-z0-9_])("
            r"[A-Za-z0-9_]*?(?i:api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret"
            r"|secret|token|password|passwd|credential|auth[_-]?token)(?![a-z])[A-Za-z0-9_]*"
            r"|[A-Za-z0-9_]*_(?i:pat|pass|pwd)"
            r""")("?'?\s*[:=]\s*["']?)([^\s"'`]{8,})"""
        ),
        r"\1\2" + MASK,
    ),
    # High-entropy backstop for unknown-prefix secrets: a 32+ char run that
    # mixes lower, upper, AND digit. The lookaheads deliberately spare
    # lowercase-hex git SHAs, UUID segments, and digit-free identifiers. The run
    # is bounded by any non-alphanumeric, so `_` and `-` end it as `.` does.
    (
        re.compile(
            r"(?<![A-Za-z0-9])(?=[A-Za-z0-9]{32,}(?![A-Za-z0-9]))"
            r"(?=[A-Za-z0-9]*[a-z])(?=[A-Za-z0-9]*[A-Z])(?=[A-Za-z0-9]*[0-9])"
            r"[A-Za-z0-9]{32,}",
        ),
        MASK,
    ),
]


def redact_text(text: str) -> str:
    """Return ``text`` with every credential-shaped span replaced by ``MASK``."""
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def main() -> int:
    """Redact file arguments in place, or stdin → stdout when none are given.

    The in-place file form is the pipe-free invocation the review + subagent
    chains use: they already write findings to disk, so ``python3 redact.py
    <file>`` scrubs credentials without a shell pipe (orchestration-guide §7).

    Each file is handled on its own: one that cannot be read or written is
    reported and the rest are still redacted, and the exit status is non-zero
    if any failed. A file that is not valid UTF-8 is still redacted, its other
    bytes kept as they were. A symlink is refused rather than written through.
    """
    paths = sys.argv[1:]
    if not paths:
        sys.stdout.write(redact_text(sys.stdin.read()))
        return 0
    failed = 0
    for path in paths:
        target = Path(path)
        try:
            if target.is_symlink():
                raise OSError("a symlink; not writing through it")
            text = target.read_text(encoding="utf-8", errors="surrogateescape")
            target.write_text(redact_text(text), encoding="utf-8", errors="surrogateescape")
        except OSError as exc:
            failed += 1
            print(f"redact.py: {path}: not redacted ({exc.strerror or exc})", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
