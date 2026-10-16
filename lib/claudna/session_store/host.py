"""Shared immutable host boundary types, below the adapters and orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .project import SessionFacts
from .transcript import Turn


@dataclass(frozen=True)
class Normalized:
    session_id: str | None
    source: str | None
    transcript_path: str | None
    cwd: str | None
    trigger: str | None
    reason: str | None
    activity: dict

    def as_payload(self) -> dict:
        return {**self.activity, "session_id": self.session_id, "source": self.source,
                "transcript_path": self.transcript_path, "cwd": self.cwd,
                "trigger": self.trigger, "reason": self.reason}


def normalize(event: str, payload: dict) -> Normalized:
    """Both measured envelopes use these field names; activity policy is unchanged."""
    return Normalized(*(payload.get(key) for key in
                        ("session_id", "source", "transcript_path", "cwd", "trigger", "reason")),
                      activity=payload)


@dataclass(frozen=True)
class Host:
    name: str
    events: Mapping[str, str]
    normalize: Callable[[str, dict], Normalized]
    owner_pid: Callable[[Mapping[str, str]], int | None]
    actor: Callable[[Mapping[str, str]], dict]
    inherited: Callable[[str, dict, SessionFacts, Mapping[str, str]], bool]
    read_range: Callable[[Path, int, int | None], list[Turn]]
