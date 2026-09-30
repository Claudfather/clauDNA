"""Fixtures shared by the session store's test files."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from claudna.session_store.store import SessionStore  # noqa: E402

ACTOR = {"kind": "interactive", "fleet": None, "bot_id": None, "bot_name": None, "model": None, "entrypoint": "cli"}
ORIGIN = {"cwd": "/work", "repo": None, "branch": None, "head": None}


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    """An empty store rooted in the test's temp dir."""
    return SessionStore(tmp_path / "state")
