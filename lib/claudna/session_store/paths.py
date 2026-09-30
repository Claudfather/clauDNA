"""Where the session store lives on disk, and the rules for naming things in it.

Layout (spec §5)::

    ${CLAUDNA_STATE_DIR:-~/.claudna}/
      sessions/<sid>/
        lifecycle.jsonl   session.json   summary.json   consumers.json   .lock
        seg-001/  events.jsonl  segment.json  summary.json
      links/<pid>.json

Session ids come from the host and are treated as opaque, but they become path
components, so they are validated before any path is built from them.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .schema import is_instance

STATE_DIR_ENV = "CLAUDNA_STATE_DIR"
#: Set in every process clauDNA spawns (summarizer, its claude -p): nothing under it records.
CHILD_ENV = "CLAUDNA_SESSION_CHILD"
DEFAULT_STATE_DIR = "~/.claudna"

#: Opaque, but safe as a single path component: no separators, no leading dot.
#: Always ``fullmatch`` with ``re.ASCII``: ``$`` also matches before a trailing
#: newline, and ``\d`` matches non-ASCII digits.
_SID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", re.ASCII)
_SEG_RE = re.compile(r"seg-([0-9]{3,})", re.ASCII)


class InvalidSessionId(ValueError):
    """A session id that cannot safely become a directory name."""


class InvalidStateDir(ValueError):
    """A store root that isn't an absolute path."""


def validate_sid(sid: str) -> str:
    """Return ``sid`` unchanged, or raise :class:`InvalidSessionId`."""
    if not isinstance(sid, str) or not _SID_RE.fullmatch(sid):
        raise InvalidSessionId(f"invalid session id: {sid!r}")
    return sid


def state_root(env: dict[str, str] | None = None) -> Path:
    """Resolve the store root: ``$CLAUDNA_STATE_DIR``, else ``~/.claudna``.

    A relative ``$CLAUDNA_STATE_DIR`` is rejected: hooks run in the user's
    project, so it would put the store — captured text included — inside a
    repository where it can be committed.
    """
    env = os.environ if env is None else env
    return validate_root(Path(env.get(STATE_DIR_ENV) or DEFAULT_STATE_DIR))


def validate_root(root: Path) -> Path:
    """Expand ``~`` and require an absolute path, however the root was supplied.

    Relative roots are rejected — from ``$CLAUDNA_STATE_DIR``, ``--root``, or
    code alike: hooks run in the user's project, so a relative root would put
    the store, captured text included, inside a repository that can be committed.
    """
    root = Path(root).expanduser()
    if not root.is_absolute():
        raise InvalidStateDir(f"the session store root must be an absolute path, got {str(root)!r}")
    return root


def seg_dirname(index: int) -> str:
    """``3`` → ``seg-003``. Widens past 999 without breaking int parsing."""
    if not is_instance(index, int) or index < 1:
        raise ValueError(f"segment index must be an int >= 1, got {index!r}")
    return f"seg-{index:03d}"


def parse_seg_dirname(name: str) -> int | None:
    """``seg-003`` → ``3``; anything else → ``None``.

    Only the canonical spelling counts (``seg_dirname(i) == name``), so
    ``seg-0002`` or ``seg-02`` can never claim index 2 beside ``seg-002``.
    """
    m = _SEG_RE.fullmatch(name)
    if m and int(m[1]) >= 1 and seg_dirname(int(m[1])) == name:
        return int(m[1])
    return None


@dataclass(frozen=True)
class SegmentPaths:
    """Files belonging to one segment directory."""

    dir: Path

    @property
    def events(self) -> Path:
        return self.dir / "events.jsonl"

    @property
    def segment_json(self) -> Path:
        return self.dir / "segment.json"

    @property
    def summary(self) -> Path:
        return self.dir / "summary.json"


@dataclass(frozen=True)
class SessionPaths:
    """Files belonging to one session directory."""

    root: Path
    sid: str

    @property
    def dir(self) -> Path:
        return self.root / "sessions" / self.sid

    @property
    def lifecycle(self) -> Path:
        return self.dir / "lifecycle.jsonl"

    @property
    def session_json(self) -> Path:
        return self.dir / "session.json"

    @property
    def consumers(self) -> Path:
        return self.dir / "consumers.json"

    @property
    def lock(self) -> Path:
        return self.dir / ".lock"

    def segment(self, index: int) -> SegmentPaths:
        return SegmentPaths(dir=self.dir / seg_dirname(index))

    def segment_indices(self) -> list[int]:
        """Existing segment indexes, ascending. The directories are the truth."""
        if not self.dir.is_dir():
            return []
        found = (parse_seg_dirname(p.name) for p in self.dir.iterdir() if p.is_dir())
        return sorted(i for i in found if i is not None)


def session_ids(root: Path) -> list[str]:
    """Every valid session id under ``root``, sorted. Anything else in ``sessions/`` is ignored."""
    sessions = root / "sessions"
    if not sessions.is_dir():
        return []
    return sorted(p.name for p in sessions.iterdir() if p.is_dir() and _SID_RE.fullmatch(p.name))


def session_paths(sid: str, root: Path | None = None) -> SessionPaths:
    """Paths for ``sid`` under ``root`` (default: :func:`state_root`)."""
    return SessionPaths(root=state_root() if root is None else root, sid=validate_sid(sid))

