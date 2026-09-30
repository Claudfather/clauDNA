"""Connections and tokens come from each tool's own config, never from a command line.

A token or a connection string written into a command is readable by every
local user from the process table while the command runs, and it stays in the
session's transcript afterwards. A project file sourced for its variables runs
as code. So a skill or agent lets each CLI read its own credentials (a libpq
service or pass file, `~/.snowsql/config`, `neon auth`, the Vercel and Railway
CLI configs), hands a dotenv value to one command through its environment
(`scripts/env_from_file.py`), sends HTTP headers from stdin (`curl -K -`), and
writes SQL to a file (`-f`).

These tests read every skill and agent file and fail on the shapes that break
that. Each failure names the file and line.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FILES = sorted(p for d in ("skills", "agents") for p in (REPO / d).rglob("*.md"))

_PROSE_SAYS_NOT = re.compile(r"\b(?:not|never|NOT|Never|NEVER)\b")


def _hits(pattern: re.Pattern, skip: re.Pattern | None = None) -> list[str]:
    """``path:line: text`` for every match; the line is the one the match ends on."""
    out = []
    for path in FILES:
        text = path.read_text()
        lines = text.splitlines()
        for m in pattern.finditer(text):
            line = text.count("\n", 0, m.end() - 1) + 1
            full = lines[line - 1]
            if skip is not None and skip.search(full):
                continue
            out.append(f"{path.relative_to(REPO)}:{line}: {full.strip()[:120]}")
    return out


def test_files_are_found():
    # Positive control: an empty scan would pass every test below.
    assert len(FILES) > 40


def test_no_project_file_is_sourced():
    # `source X` anywhere; `. X` only where a command starts (a line, or after
    # an operator), so a sentence ending in a period is not read as a command.
    pattern = re.compile(r"(?:(?<![\w-])source|(?:^|[;&|(`])[ \t]*\.)[ \t]+(?:[^\s`]*\.env\b|<)", re.MULTILINE)
    hits = _hits(pattern, skip=_PROSE_SAYS_NOT)
    assert not hits, "hand the value to the command instead:\n" + "\n".join(hits)


def test_sql_is_passed_by_file():
    hits = _hits(re.compile(r"\b(?:psql|snowsql)\b[^\n]*\s(?:-c|-q|--query|--command)\s+[\"']"))
    assert not hits, "write the SQL to a file and pass -f:\n" + "\n".join(hits)


def test_no_connection_string_is_an_argument():
    pattern = re.compile(r"\bpsql\s+[\"']?(?:<[^>\n]*(?:url|URL)[^>\n]*>|\$\{?[A-Z_]*URL\b|postgres(?:ql)?://)")
    hits = _hits(pattern)
    assert not hits, "let psql take its target from its own config:\n" + "\n".join(hits)


def test_no_token_rides_a_command_line():
    pattern = re.compile(
        r"Authorization: Bearer\s+[<$]"
        r"|--api-key\s+[\"'$<]"
        r"|--token-secret\s+[\"'$<]"
        r"|--token\s+\"?\$"
    )
    hits = _hits(pattern)
    assert not hits, "the CLI reads its own token; send a header from stdin:\n" + "\n".join(hits)


def test_no_credential_is_printed_into_the_session():
    pattern = re.compile(
        r"\bcat\s+[^\n|]*(?:config\.json|auth\.json|credentials)"
        r"|\becho\s+\"?\$\{?[A-Z_]*(?:TOKEN|API_KEY|SECRET|PASSWORD)\b"
    )
    hits = _hits(pattern, skip=_PROSE_SAYS_NOT)
    assert not hits, "check presence only; never print a credential:\n" + "\n".join(hits)


def test_no_contract_says_to_inline_a_value():
    pattern = re.compile(
        r"(?i)\binline(?:s)?\b[^.\n]*(?:discovered value|connection string|--api-key|--token)"
        r"|pass the value inline"
    )
    hits = _hits(pattern, skip=_PROSE_SAYS_NOT)
    assert not hits, "no value is inlined into a command:\n" + "\n".join(hits)
