"""Strict frontmatter parsing shared by maintainer validators."""

from __future__ import annotations

from pathlib import Path

import yaml


class FrontmatterError(ValueError):
    """Invalid YAML syntax or a non-mapping frontmatter document."""


def parse_frontmatter(path: Path) -> tuple[dict, str] | None:
    """Return (frontmatter, body), None if absent, or raise FrontmatterError.

    FrontmatterError remains a ValueError for existing strict callers. Lenient
    callers can catch it without hiding file, decoding or YAML-constructor errors.
    """
    text = path.read_text()
    if not text.startswith("---"):
        return None
    lines = text.splitlines(keepends=True)
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return None
    frontmatter_text = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        data = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as e:
        raise FrontmatterError(f"frontmatter YAML parse error: {e}")
    if not isinstance(data, dict):
        raise FrontmatterError("frontmatter is not a YAML mapping")
    return data, body
