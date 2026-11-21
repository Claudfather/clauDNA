"""Shared strict numeric version grammar for source-package boundaries."""

from __future__ import annotations

import re

VERSION_RE = re.compile(r"\A[0-9]+\.[0-9]+\.[0-9]+\Z", re.ASCII)


def is_numeric_version(value: object) -> bool:
    """Whether ``value`` is exactly three ASCII numeric components."""
    return isinstance(value, str) and VERSION_RE.fullmatch(value) is not None
