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

That script is a thin CLI over this module, which is the runtime home: the
session store imports ``redact_text`` so every free-text field it writes, and
every transcript slice it hands the summarizer, is scrubbed the same way. It
is intentionally conservative about over-redaction: git SHAs (lowercase hex),
UUIDs, file:line references, and plain identifiers pass through untouched, so
review output stays readable.

The redaction convention: any span matching a known credential shape, a
``SECRET=value`` assignment, or a high-entropy token backstop is replaced with
the sentinel below. Extend PATTERNS as new credential shapes appear.
"""

from __future__ import annotations

import re

MASK = "[REDACTED]"

# Ordered most-specific → most-general. Each (pattern, replacement) is applied
# in turn; a span matched by an earlier rule is masked before a later, more
# general rule sees it. Most replacements are MASK; the flag and connection-
# string rules keep the surrounding structure (flag name, URL scheme/host) so
# redacted output stays readable.
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # A PEM private-key block, whole: its base64 lines hold + and /, which no
    # token rule below sees as one run.
    (
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)"),
        MASK,
    ),
    # Telegram bot token: <8-10 digits>:<35+ base64url> (a real leak).
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35,}\b"), MASK),
    # Vendor-prefixed keys. The prefix is the signal; length guards false hits.
    # Anthropic (sk-ant-api03-…, sk-ant-admin01-…) and OpenAI project keys: dashed, so
    # the plain sk- rule below can't span them. The most common secret in a Claude Code transcript.
    (re.compile(r"\bsk-(?:ant|proj|svcacct|admin)-[A-Za-z0-9_-]{20,}"), MASK),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{20,}\b"), MASK),  # OpenAI / Stripe-style
    (re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test)[-_][A-Za-z0-9]{10,}\b"), MASK),  # Stripe live/test keys
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), MASK),  # GitHub PAT / token
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), MASK),  # GitHub fine-grained PAT
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
    # An HTTP bearer token (`Authorization: Bearer X`, `-H 'Bearer X'`): any shape.
    # Keep the scheme word so the redacted header stays legible.
    (re.compile(r"(\bBearer\s+)[A-Za-z0-9._~+/-]{16,}=*", re.IGNORECASE), r"\1" + MASK),
    # HTTP Basic credentials: base64 of user:password.
    # (A digit or base64 punctuation is required, so "Basic configuration" stays prose.)
    (re.compile(r"(\bBasic\s+)(?=[A-Za-z0-9+/]*[0-9+/=])[A-Za-z0-9+/]{12,}=*"), r"\1" + MASK),
    # Credential in a connection string: scheme://user:PASSWORD@host. neon's
    # DATABASE_URL is the primary neon credential and matches no vendor prefix.
    # Keep scheme and host; drop the userinfo.
    (re.compile(r"(://)[^:/@\s]*:[^@/\s]+(@)"), r"\1" + MASK + r"\2"),  # user may be empty: redis://:pw@
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


def redact_strings(value):
    """``value`` with every string inside it redacted: dicts, lists and scalars, recursively."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_strings(v) for v in value]
    return value


def redact_text(text: str) -> str:
    """Return ``text`` with every credential-shaped span replaced by ``MASK``."""
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text

