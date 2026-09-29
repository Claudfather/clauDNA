"""The write API: append events to a session and keep its projections current.

Every mutation takes the session's exclusive lock, appends exactly one event,
then re-projects what that event touched (:func:`session_store.project.refresh`)
— so two hook processes racing on one session can never leave a projection that
reflects fewer events than the log holds.

A session directory is created in exactly one place, :meth:`SessionHandle._locked`,
on the session's first write. That deliberately includes writes that arrive before
``session.opened`` (a missed SessionStart): those events land and project as
``status: "unknown"`` rather than being dropped.

Hook adapters call this module; they never write store files themselves.
"""

from __future__ import annotations

from pathlib import Path

from . import events as ev
from .fsio import DIR_MODE, append_jsonl, ensure_dir, exclusive_lock
from .paths import SessionPaths, session_paths, state_root
from .project import RebuildReport, rebuild, refresh


class StoreError(RuntimeError):
    """An operation that the store's invariants forbid (e.g. activity with no segment)."""


class SessionHandle:
    """All reads and writes for one session id."""

    def __init__(self, paths: SessionPaths):
        self.paths = paths

    @property
    def sid(self) -> str:
        return self.paths.sid

    def exists(self) -> bool:
        return self.paths.dir.is_dir()

    def current_segment(self) -> int | None:
        """The highest existing segment index. Only it can be open (spec §4.2)."""
        indices = self.paths.segment_indices()
        return indices[-1] if indices else None

    # ── generic append ──────────────────────────────────────────────────────

    def _locked(self):
        """The session lock — creating the session directory on first write."""
        ensure_dir(self.paths.dir)
        return exclusive_lock(self.paths.lock)

    def append(self, kind: str, data: dict, *, seg: int | None = None) -> dict:
        """Append one event to the log its kind belongs to, then re-project."""
        with self._locked():
            return self._append_locked(kind, data, seg=seg)

    def _append_locked(self, kind: str, data: dict, *, seg: int | None) -> dict:
        """Append and re-project; the caller holds the session lock."""
        event = ev.make_event(kind, self.sid, data, seg=seg)
        activity = ev.REGISTRY[kind].log == ev.ACTIVITY
        if activity:
            assert seg is not None  # make_event enforces this for activity kinds
            if not self.paths.segment(seg).dir.is_dir():
                raise StoreError(f"segment {seg} does not exist for session {self.sid}")
            append_jsonl(self.paths.segment(seg).events, event)
        else:
            append_jsonl(self.paths.lifecycle, event)
        refresh(self.paths, seg=seg, activity_only=activity)
        return event

    # ── lifecycle verbs (thin, named wrappers over append) ──────────────────

    def open_session(
        self,
        source: str,
        *,
        actor: dict,
        origin: dict,
        transcript_path: str | None,
        parent_sid: str | None = None,
        chain_id: str | None = None,
    ) -> dict:
        """Record ``session.opened``. A session with no parent is its own chain root."""
        return self.append(
            "session.opened",
            {
                "source": source,
                "parent_sid": parent_sid,
                "chain_id": chain_id or self.sid,
                "actor": actor,
                "origin": origin,
                "transcript_path": transcript_path,
            },
        )

    def open_segment(self, opened_by: str, start: int) -> int:
        """Create the next segment directory and record ``segment.opened``; return its index.

        The index is derived under the lock — ``max(existing) + 1`` — and the
        segment exists the moment its ``mkdir`` succeeds.
        """
        with self._locked():
            index = (self.current_segment() or 0) + 1
            self.paths.segment(index).dir.mkdir(mode=DIR_MODE)
            self._append_locked("segment.opened", {"opened_by": opened_by, "start": start}, seg=index)
            return index

    def seal_segment(
        self,
        end: int,
        sealed_by: str,
        *,
        index: int | None = None,
        trigger: str | None = None,
        sha256: str | None = None,
    ) -> dict:
        """Record ``segment.sealed`` for ``index`` (default: current). Safe to repeat.

        The default index is resolved under the lock, so a concurrent
        ``open_segment`` can't slip in between choosing a segment and sealing it.
        """
        data = {"end": end, "sealed_by": sealed_by, "trigger": trigger}
        if sha256 is not None:
            data["sha256"] = sha256
        with self._locked():
            target = index if index is not None else self.current_segment()
            if target is None:
                raise StoreError(f"session {self.sid} has no segment to seal")
            return self._append_locked("segment.sealed", data, seg=target)

    def close_session(self, reason: str) -> dict:
        return self.append("session.closed", {"reason": reason})

    def link_child(self, child_sid: str) -> dict:
        return self.append("session.child_linked", {"child_sid": child_sid})

    def set_private(self, private: bool, *, by: str = "user") -> dict:
        return self.append("session.privacy_set", {"private": private, "by": by})

    def rebuild(self) -> RebuildReport:
        """Regenerate projections from the logs (read-only with respect to logs)."""
        with self._locked():
            return rebuild(self.paths)


class SessionStore:
    """Entry point: resolves the store root once, hands out session handles."""

    def __init__(self, root: Path | None = None):
        self.root = state_root() if root is None else root

    def session(self, sid: str) -> SessionHandle:
        return SessionHandle(session_paths(sid, self.root))

    def session_ids(self) -> list[str]:
        """Every session directory under the root, sorted by name."""
        sessions = self.root / "sessions"
        if not sessions.is_dir():
            return []
        return sorted(p.name for p in sessions.iterdir() if p.is_dir())
