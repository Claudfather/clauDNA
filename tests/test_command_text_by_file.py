"""Text a command carries arrives by file, never as part of the command.

A skill tells the model how to build a shell command. When a title, a body, a
message, a URL, a SQL statement or a value from a project file is written INTO
the command, the shell reads it as shell: inside double quotes a backtick or a
`$(...)` runs, and a heredoc placed inside `$(...)` ends at the first line that
matches its delimiter. So the rule is one line: write the text to a file with
the Write tool and hand the command the file (`--body-file`, `-F`, `psql -f`,
a JSON job file for a bundled script), or pass `"$(cat <file>)"`, whose output
the shell does not parse again.

These tests read every skill and agent file and fail on the command shapes that
break that rule. Each failure names the file and line.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FILES = sorted(p for d in ("skills", "agents") for p in (REPO / d).rglob("*.md"))

_FENCE = re.compile(r"^```[a-z]*\n(.*?)^```", re.DOTALL | re.MULTILINE)


def _hits(pattern: re.Pattern, *, fenced_only: bool = False, skip: re.Pattern | None = None) -> list[str]:
    """``path:line: text`` for every match, in fenced blocks only if asked.

    The line is the one the match ENDS on, so a pattern that may begin at the
    newline before a command still names the command's line. ``skip`` drops a
    match whose whole line it finds (prose that says not to do the thing)."""
    out = []
    for path in FILES:
        text = path.read_text()
        lines = text.splitlines()
        spans = [(m.start(1), m.group(1)) for m in _FENCE.finditer(text)] if fenced_only else [(0, text)]
        for offset, chunk in spans:
            for m in pattern.finditer(chunk):
                line = text.count("\n", 0, offset + m.end() - 1) + 1
                full = lines[line - 1]
                if skip is not None and skip.search(full):
                    continue
                out.append(f"{path.relative_to(REPO)}:{line}: {full.strip()[:120]}")
    return out


def test_files_are_found():
    # Positive control: an empty scan would pass every test below.
    assert len(FILES) > 40


def test_no_heredoc_is_read_inside_a_command_substitution():
    hits = _hits(re.compile(r"\$\(\s*cat\s+<<"))
    assert not hits, "write the text to a file and pass the file:\n" + "\n".join(hits)


def test_bodies_titles_and_messages_are_passed_by_file():
    # A value in double quotes that holds a placeholder is text written into the
    # command. `"$(cat <file>)"` is the allowed form: its output is not parsed.
    pattern = re.compile(r'(?:--body|--title|--message|--notes|(?<![\w-])-m)\s+"(?!\$\(cat )[^"\n]*<[^>"\n]+>[^"\n]*"')
    hits = _hits(pattern)
    assert not hits, "pass the text by file:\n" + "\n".join(hits)


def test_program_text_carries_no_placeholders():
    # `python3 -c "..."` with a value substituted into the program: pass the
    # value as an argument or in a JSON file, never inside the program.
    pattern = re.compile(r'python3? -c "((?:[^"\\]|\\.)*)"', re.DOTALL)
    hits = []
    for path in FILES:
        text = path.read_text()
        for m in pattern.finditer(text):
            program = m.group(1)
            if re.search(r"<[A-Za-z][^>\n]*>|\b[A-Z]+_(?:URL|NAME|FILE|PATH)\b", program):
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{path.relative_to(REPO)}:{line}")
    assert not hits, "a value is substituted into program text:\n" + "\n".join(hits)


def test_no_project_file_is_sourced():
    # Sourcing runs a project file as code. Lines that say not to are prose.
    # `source X` anywhere; `. X` only where a command starts (a line, or after
    # an operator), so a sentence ending in a period is not read as a command.
    pattern = re.compile(r"(?:(?<![\w-])source|(?:^|[;&|(`])[ \t]*\.)[ \t]+(?:[^\s`]*\.env\b|<)", re.MULTILINE)
    hits = _hits(pattern, skip=re.compile(r"\b(?:not|never|NOT|Never)\b"))
    assert not hits, "read the value you need; never source a project file:\n" + "\n".join(hits)


def test_sql_is_passed_by_file():
    hits = _hits(
        re.compile(r"\b(?:psql|snowsql)\b[^\n]*\s(?:-c|-q|--query|--command)\s+[\"']"),
        fenced_only=False,
    )
    assert not hits, "write the SQL to a file and pass -f:\n" + "\n".join(hits)


@pytest.mark.parametrize("name", ["deep-crawl.md", "SKILL.md"])
def test_the_crawler_runs_its_bundled_script(name):
    # Routes come from the site being crawled. They reach the browser through a
    # JSON job file read by the bundled script, never through a command line.
    text = (REPO / "skills" / "qa" / name).read_text()
    assert "python3 -c" not in text
    assert not re.search(r"curl -sI\b[^\n]*(?:href|<url>|<route)", text)
