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

The redaction convention: any span matching a known credential shape, a
``SECRET=value`` assignment, or a high-entropy token backstop is replaced with
the sentinel below. Extend PATTERNS as new credential shapes appear.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MASK = "[REDACTED]"

# Ordered most-specific → most-general. Each (pattern, replacement) is applied
# in turn; a span matched by an earlier rule is masked before a later, more
# general rule sees it. Most replacements are MASK; the flag and connection-
# string rules keep the surrounding structure (flag name, URL scheme/host) so
# redacted output stays readable.
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Telegram bot token: <8-10 digits>:<35+ base64url> (a real leak).
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35,}\b"), MASK),
    # Vendor-prefixed keys. The prefix is the signal; length guards false hits.
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{20,}\b"), MASK),  # OpenAI / Stripe-style
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), MASK),  # GitHub PAT / token
    (re.compile(r"\bnapi_[A-Za-z0-9]{20,}\b"), MASK),  # neon API key (a real leak)
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9]{8,}(?:-[A-Za-z0-9]+)*\b"), MASK),  # Slack token
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),  # AWS access key id
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), MASK),  # Google API key
    # Secret inlined as a CLI flag (`--api-key X`, `--token X`, `--password X`).
    # Infra engines pass credentials this way; a failed command echoed verbatim
    # (infra-cli-contract §7) leaks the value whatever shape it takes. Keep the
    # flag name so the redacted command stays legible.
    (
        re.compile(
            r"(--(?:(?:api|access|secret)[-_]?key|client[-_]secret"
            r"|token(?:[-_](?:secret|id))?|password|passwd|secret|auth[-_]?token)[=\s])\S+",
            re.IGNORECASE,
        ),
        r"\1" + MASK,
    ),
    # Credential in a connection string: scheme://user:PASSWORD@host. neon's
    # DATABASE_URL is the primary neon credential and matches no vendor prefix.
    # Keep scheme and host; drop the userinfo.
    (re.compile(r"(://)[^:/@\s]+:[^@/\s]+(@)"), r"\1" + MASK + r"\2"),
    # Structural: a secret-named field assigned a value, incl. prefixed names
    # (DATABASE_PASSWORD, MY_API_KEY) and JSON ("api_key": "...").
    (
        re.compile(
            r"(?i)\b[a-z0-9_]*(?:api[_-]?key|secret|token|password|passwd"
            r"|auth[_-]?token|access[_-]?key)\b"
            r"""["']?\s*[:=]\s*["']?[A-Za-z0-9_\-./+]{8,}""",
        ),
        MASK,
    ),
    # High-entropy backstop for unknown-prefix secrets: a 32+ char run that
    # mixes lower, upper, AND digit. The lookaheads deliberately spare
    # lowercase-hex git SHAs, UUID segments, and digit-free identifiers.
    (
        re.compile(
            r"\b(?=[A-Za-z0-9]{32,}\b)"
            r"(?=[A-Za-z0-9]*[a-z])(?=[A-Za-z0-9]*[A-Z])(?=[A-Za-z0-9]*[0-9])"
            r"[A-Za-z0-9]{32,}\b",
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
    """
    paths = sys.argv[1:]
    if paths:
        for path in paths:
            target = Path(path)
            target.write_text(redact_text(target.read_text()))
        return 0
    sys.stdout.write(redact_text(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
