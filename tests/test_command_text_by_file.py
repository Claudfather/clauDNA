"""Text a command carries arrives by file.

A title, a body, a message or a search term is written to a file with the
Write tool, and the command reads that file: `--body-file`, `-F body=@<file>`,
`--input <file>`, a JSON job file for a bundled script, or `"$(cat <file>)"`
where a flag takes the text itself.

These tests read every skill and agent file and fail on a command that carries
such text any other way. Each failure names the file and line. The lint's own
cases are pinned in `test_the_lint_flags_each_shape` and
`test_the_lint_passes_the_file_forms`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FILES = sorted(p for d in ("skills", "agents") for p in (REPO / d).rglob("*.md"))

_PLACEHOLDER = r"<[^<>\n]+>"
# A flag's value that holds a placeholder: double-quoted (it may span lines),
# single-quoted, or bare. `"$(cat <file>)"` is the file form and is not a hit.
_QUOTED_VALUE = r'"(?!\$\(cat )[^"]*' + _PLACEHOLDER + r'[^"]*"' r"|'[^'\n]*" + _PLACEHOLDER + r"[^'\n]*'"
_TEXT_VALUE = r"(?:" + _QUOTED_VALUE + r"|" + _PLACEHOLDER + r")"
_FLAG = (
    r"(?:--(?:body|title|message|notes|(?:add-|remove-)?label|tags|search|grep|query|description|comment|source-url|source-type)"
    r"|(?<![\w-])-m)"
)
# A bare placeholder after a flag that opens an inline code span documents a
# skill's own argument (`--title <s>`), not a command, so only the quoted
# forms count there.
_TEXT_FLAG = re.compile(
    _FLAG + r"(?:=|\s+)(?:" + _QUOTED_VALUE + r")" + r"|(?<!`)" + _FLAG + r"(?:=|\s+)" + _PLACEHOLDER
)
_API_TEXT_FIELD = re.compile(
    r"(?:(?<![\w-])-[fF]|--(?:raw-)?field)\s+(?:body|title|message|description|comment|text|notes|summary)="
    + _TEXT_VALUE
)
# Commands whose positional arguments are free text.
_TEXT_ARGUMENTS = re.compile(r"\bclaudron lookup\b(?![^\n`]*\$\(cat )[^\n`]*" + _PLACEHOLDER)
_CAT_HEREDOC = re.compile(r"\$\(\s*cat\s*<<")
_HEREDOC_START = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1")
_POSTS_TEXT = re.compile(r"\bgh (?:pr (?:create|review|comment)|issue comment)\b")
_SAYS_NOT = re.compile(r"\b(?:[Nn]ever|not|NOT)\b")
_NAMES_A_FILE = re.compile(r"--body-file|-F body=@|--input\b")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _heredocs_with_text(text: str) -> list[int]:
    """Start lines of heredocs whose body holds a placeholder."""
    lines = text.splitlines()
    hits = []
    for number, line in enumerate(lines, 1):
        m = _HEREDOC_START.search(line)
        if not m:
            continue
        for body in lines[number:]:
            if body.strip() == m.group(2):
                break
            if re.search(_PLACEHOLDER, body):
                hits.append(number)
                break
    return hits


def _posting_lines(text: str) -> list[int]:
    """Lines that run a gh command posting text without naming the file it reads.

    A command continued with a trailing backslash is read as one line."""
    hits = []
    lines = text.splitlines()
    number = 0
    while number < len(lines):
        start, logical = number, lines[number]
        while logical.endswith("\\") and number + 1 < len(lines):
            number += 1
            logical = logical[:-1] + " " + lines[number]
        if _POSTS_TEXT.search(logical) and not _NAMES_A_FILE.search(logical) and not _SAYS_NOT.search(logical):
            hits.append(start + 1)
        number += 1
    return hits


def text_hits(text: str) -> list[tuple[int, str]]:
    """``(line, rule)`` for every place ``text`` puts text into a command."""
    hits = [(_line_of(text, m.end() - 1), "text flag") for m in _TEXT_FLAG.finditer(text)]
    hits += [(_line_of(text, m.end() - 1), "api field") for m in _API_TEXT_FIELD.finditer(text)]
    hits += [(_line_of(text, m.end() - 1), "text argument") for m in _TEXT_ARGUMENTS.finditer(text)]
    hits += [(_line_of(text, m.start()), "cat heredoc") for m in _CAT_HEREDOC.finditer(text)]
    hits += [(n, "heredoc") for n in _heredocs_with_text(text)]
    return sorted(set(hits))


def _report(check) -> list[str]:
    out = []
    for path in FILES:
        text = path.read_text()
        lines = text.splitlines()
        for number, rule in check(text):
            out.append(f"{path.relative_to(REPO)}:{number}: [{rule}] {lines[number - 1].strip()[:120]}")
    return out


def test_files_are_found():
    # Positive control: an empty scan would pass every test below.
    assert len(FILES) > 40


def test_text_is_passed_by_file():
    hits = _report(text_hits)
    assert not hits, "write the text to a file and pass the file:\n" + "\n".join(hits)


def test_posting_commands_name_the_file_they_read():
    hits = _report(lambda text: [(n, "posting command") for n in _posting_lines(text)])
    assert not hits, "name --body-file, -F body=@<file> or --input <file>:\n" + "\n".join(hits)


def test_program_text_carries_no_placeholders():
    # `python3 -c "..."` whose program holds a placeholder: pass the value as an
    # argument or in a JSON file, never inside the program.
    pattern = re.compile(r'python3? -c "((?:[^"\\]|\\.)*)"', re.DOTALL)
    hits = []
    for path in FILES:
        text = path.read_text()
        for m in pattern.finditer(text):
            program = m.group(1)
            if re.search(r"<[A-Za-z][^>\n]*>|\b[A-Z]+_(?:URL|NAME|FILE|PATH)\b", program):
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{path.relative_to(REPO)}:{line}")
    assert not hits, "pass the value as an argument or in a JSON file:\n" + "\n".join(hits)


@pytest.mark.parametrize(
    "sample",
    [
        pytest.param('gh issue create --body "<body>"', id="double-quoted"),
        pytest.param('gh issue create --title="<title>"', id="equals"),
        pytest.param('gh issue create --body "## Summary\n\n<summary>\n"', id="multi-line"),
        pytest.param('gh api repos/o/r/issues -f body="<body>"', id="api-field"),
        pytest.param('gh issue list --search "<term>"', id="search"),
        pytest.param('git log --oneline --grep="<keyword>"', id="grep"),
        pytest.param("gh issue create --body-file - <<'EOF'\n<body>\nEOF", id="heredoc"),
        pytest.param("gh pr comment 1 --body '<body>'", id="single-quoted"),
        pytest.param("gh issue edit 1 --body <updated body>", id="bare"),
        pytest.param("git commit -F- --message \"$(cat<<'EOF'\n<message>\nEOF\n)\"", id="cat-heredoc"),
        pytest.param('claudron recall --query "<terms>" --json', id="query"),
        pytest.param('gh issue edit 1 --add-label "<tag>"', id="add-label"),
        pytest.param('Build the query: `--query "<terms>"`.', id="quoted-in-a-span"),
        pytest.param("claudron lookup <terms...> --json", id="text-argument"),
        pytest.param("claudron capture --stdin --source-url <url> --json", id="source-url"),
    ],
)
def test_the_lint_flags_each_shape(sample):
    assert text_hits(sample)


@pytest.mark.parametrize(
    "sample",
    [
        pytest.param('gh issue create --title "$(cat <title-file>)" --body-file <body-file>', id="files"),
        pytest.param("gh api repos/o/r/issues/1/comments -F body=@<file>", id="api-file"),
        pytest.param('gh issue list --search "$(cat <term-file>)" --state all', id="search-file"),
        pytest.param('gh issue edit <number> --add-label "in-progress"', id="label-name"),
        pytest.param("psql -X <<'EOF'\nSELECT 1;\nEOF", id="static-heredoc"),
        pytest.param("- `--title <s>` — short, unique title.", id="skill-argument"),
        pytest.param('claudron lookup --json -- "$(cat <terms-file>)"', id="text-argument-file"),
    ],
)
def test_the_lint_passes_the_file_forms(sample):
    assert not text_hits(sample)


@pytest.mark.parametrize(
    "sample, flagged",
    [
        ("Use `gh pr review <number>` with `--approve` or `--comment`.", True),
        ('gh pr create --title "$(cat <title-file>)" \\\n  --body-file <body-file>', False),
        ("gh pr review <number> --comment --body-file <review-file>", False),
        ("Never run `gh pr create` directly; delegate to publish.", False),
    ],
)
def test_the_posting_rule(sample, flagged):
    assert bool(_posting_lines(sample)) is flagged


def test_the_crawler_reads_routes_from_job_files():
    # Routes reach the browser through a JSON job file read by the bundled
    # script, never through a command line or program text.
    text = (REPO / "skills" / "qa" / "deep-crawl.md").read_text()
    assert "python3 -c" not in text
    assert "crawl_page.py" in text
    assert not re.search(r"curl -sI\b[^\n]*(?:href|<url>|<route)", text)


def test_capture_carries_provenance_in_its_json():
    text = (REPO / "skills" / "capture" / "SKILL.md").read_text()
    assert "--source-url <" not in text
    assert "`source_url`" in text


def test_a_file_name_on_a_command_line_has_a_stated_pattern():
    text = (REPO / "skills" / "modal" / "deploy.md").read_text()
    assert re.search(r"app file's path matches `\^\[A-Za-z0-9\._/-\]\+\$`", text)


def test_a_port_read_from_the_project_must_be_digits():
    text = (REPO / "skills" / "qa" / "SKILL.md").read_text()
    assert re.search(r"port[^\n]*`\^\[0-9\]\{1,5\}\$`", text)
