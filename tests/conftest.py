"""Fixtures shared by the session store's test files."""

from __future__ import annotations

import json
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


@pytest.fixture
def quiet_hooks(monkeypatch):
    """Stub every worker the hook adapter starts, so no test launches a real detached process."""
    from claudna.session_store import boundaries, harvest

    monkeypatch.setattr(boundaries, "spawn_summarizer", lambda handle, index, env: None)
    monkeypatch.setattr(boundaries, "spawn_sweep", lambda root, env: None)
    monkeypatch.setattr(harvest, "is_due", lambda root, env: False)  # whatever this machine has installed


def fire(store: SessionStore, event: str, sid: str, tmp_path: Path, *, env: dict | None = None,
         find_pid=None, **fields) -> str:
    """One hook event for ``sid``, whose (empty) transcript lives in ``tmp_path``."""
    from claudna.session_store import boundaries

    transcript = tmp_path / f"{sid}.jsonl"
    transcript.touch()
    payload = {"session_id": sid, "transcript_path": str(transcript), "cwd": str(tmp_path), **fields}
    return boundaries.handle(event, payload, store=store, env=CLI_ENV if env is None else env, find_pid=find_pid)


CLI_ENV = {"CLAUDE_CODE_ENTRYPOINT": "cli"}


def session_doc(store: SessionStore, sid: str) -> dict:
    return json.loads(store.session(sid).paths.session_json.read_text())


def segment_summary(sid: str, index: int, blocks=(), *, title: str = "t", start: int = 0, end: int = 1,
                    done=(), next_=(), outcome: str = "shipped") -> dict:
    """A schema-valid ``seg-NNN/summary.json`` summarizing ``[start, end)`` and carrying ``blocks``."""
    return {
        "schema": "claudna.segment-summary/1", "sid": sid, "index": index,
        "input": {"transcript_path": "/t.jsonl", "range": {"start": start, "end": end}, "sha256": "0" * 64,
                  "turns": 1},
        "producer": {"model": "haiku", "prompt_version": "segment-summary/1", "duration_ms": 1, "cost_usd": None},
        "journey": {"title": title, "intent": "i", "outcome": outcome, "arc": [{"step": "s", "result": "r"}],
                    "done": [{"text": t} for t in done], "in_progress": [], "next": [{"text": t} for t in next_]},
        "blocks": list(blocks), "procedures": [],
    }


def complete_segment(handle, index: int, doc: dict) -> None:
    """Write ``doc`` as segment ``index``'s summary and log its ``summary.completed``."""
    from claudna.session_store.fsio import atomic_write_json

    atomic_write_json(handle.paths.segment(index).summary, doc)
    handle.append("summary.completed", {"job_id": f"j{index}", "artifact": f"seg-{index:03d}/summary.json",
                                        "input_sha256": "0" * 64, "duration_ms": 1}, seg=index)
