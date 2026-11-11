"""Shared parsing preserves strict validator and lenient integration behavior."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from skill_checks import parse_frontmatter as parse_compat  # noqa: E402
from skill_frontmatter import parse_frontmatter  # noqa: E402

SPEC = importlib.util.spec_from_file_location("integration_test", ROOT / "scripts/integration-test.py")
integration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(integration)


@pytest.mark.parametrize("parser", [parse_frontmatter, parse_compat, integration.parse_frontmatter])
@pytest.mark.parametrize("text,expected", [
    ("plain body\n", None),
    ("---\nname: incomplete\n", None),
    ("---\n---\nBody\n", ({}, "Body\n")),
    (
        '---\nname: demo\ndescription: "Use when testing: parser boundaries."\n'
        'hosts: [claude-code, codex]\n---\n\n# Body\n\n---\nTrailing body\n',
        ({"name": "demo", "description": "Use when testing: parser boundaries.",
          "hosts": ["claude-code", "codex"]}, "\n# Body\n\n---\nTrailing body\n"),
    ),
])
def test_valid_or_missing_frontmatter_agrees_across_callers(tmp_path, parser, text, expected):
    path = tmp_path / "SKILL.md"
    path.write_text(text)
    assert parser(path) == expected


@pytest.mark.parametrize("frontmatter,error", [
    ("name: [unterminated", "frontmatter YAML parse error"),
    ("- a list", "frontmatter is not a YAML mapping"),
    ("a scalar", "frontmatter is not a YAML mapping"),
])
def test_invalid_frontmatter_is_strict_for_validation_and_missing_for_integration(tmp_path, frontmatter, error):
    path = tmp_path / "SKILL.md"
    path.write_text(f"---\n{frontmatter}\n---\nBody\n")
    for parser in (parse_frontmatter, parse_compat):
        with pytest.raises(ValueError, match=error):
            parser(path)
    assert integration.parse_frontmatter(path) is None


@pytest.mark.parametrize("parser", [parse_frontmatter, parse_compat, integration.parse_frontmatter])
def test_unreadable_files_are_not_misreported_as_missing_frontmatter(tmp_path, parser):
    with pytest.raises(FileNotFoundError):
        parser(tmp_path / "missing.md")


@pytest.mark.parametrize("parser", [parse_frontmatter, parse_compat, integration.parse_frontmatter])
def test_decoding_errors_are_not_misreported_as_missing_frontmatter(tmp_path, parser):
    path = tmp_path / "SKILL.md"
    path.write_bytes(b"---\nname: \xff\n---\nBody\n")
    with pytest.raises(UnicodeDecodeError):
        parser(path)


@pytest.mark.parametrize("parser", [parse_frontmatter, parse_compat, integration.parse_frontmatter])
def test_yaml_constructor_errors_keep_propagating(tmp_path, parser):
    path = tmp_path / "SKILL.md"
    path.write_text("---\ndate: 2026-13-01\n---\nBody\n")
    # PyYAML's datetime constructor raises a raw ValueError, not YAMLError.
    # The former integration parser propagated it; the adapter must too.
    with pytest.raises(ValueError, match="month must be in"):
        parser(path)
