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

STATE_DIR_ENV = "CLAUDNA_STATE_DIR"
DEFAULT_STATE_DIR = "~/.claudna"

#: Opaque, but safe as a single path component: no separators, no leading dot.
_SID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SEG_RE = re.compile(r"^seg-(\d{3,})$")


class InvalidSessionId(ValueError):
    """A session id that cannot safely become a directory name."""


def validate_sid(sid: str) -> str:
    """Return ``sid`` unchanged, or raise :class:`InvalidSessionId`."""
    if not isinstance(sid, str) or not _SID_RE.match(sid) or ".." in sid:
        raise InvalidSessionId(f"invalid session id: {sid!r}")
    return sid


def state_root(env: dict[str, str] | None = None) -> Path:
    """Resolve the store root: ``$CLAUDNA_STATE_DIR``, else ``~/.claudna``."""
    env = os.environ if env is None else env
    raw = env.get(STATE_DIR_ENV) or DEFAULT_STATE_DIR
    return Path(raw).expanduser()


def seg_dirname(index: int) -> str:
    """``3`` → ``seg-003``. Widens past 999 without breaking int parsing."""
    if not isinstance(index, int) or isinstance(index, bool) or index < 1:
        raise ValueError(f"segment index must be an int >= 1, got {index!r}")
    return f"seg-{index:03d}"


def parse_seg_dirname(name: str) -> int | None:
    """``seg-003`` → ``3``; anything else → ``None``."""
    m = _SEG_RE.match(name)
    if not m:
        return None
    index = int(m.group(1))
    return index if index >= 1 else None


@dataclass(frozen=True)
class SegmentPaths:
    """Files belonging to one segment directory."""

    dir: Path
    index: int

    @property
    def events(self) -> Path:
        return self.dir / "events.jsonl"

    @property
    def segment_json(self) -> Path:
        return self.dir / "segment.json"

    @property
    def summary_json(self) -> Path:
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
    def summary_json(self) -> Path:
        return self.dir / "summary.json"

    @property
    def consumers_json(self) -> Path:
        return self.dir / "consumers.json"

    @property
    def lock(self) -> Path:
        return self.dir / ".lock"

    def segment(self, index: int) -> SegmentPaths:
        return SegmentPaths(dir=self.dir / seg_dirname(index), index=index)

    def segment_indices(self) -> list[int]:
        """Existing segment indexes, ascending. The directories are the truth."""
        if not self.dir.is_dir():
            return []
        found = (parse_seg_dirname(p.name) for p in self.dir.iterdir() if p.is_dir())
        return sorted(i for i in found if i is not None)


def session_paths(sid: str, root: Path | None = None) -> SessionPaths:
    """Paths for ``sid`` under ``root`` (default: :func:`state_root`)."""
    return SessionPaths(root=state_root() if root is None else root, sid=validate_sid(sid))


def links_dir(root: Path | None = None) -> Path:
    """Directory for ephemeral clear-lineage handoff files (spec §6.9)."""
    return (state_root() if root is None else root) / "links"
