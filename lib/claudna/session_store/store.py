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
from .fsio import DIR_MODE, append_jsonl, ensure_dir, exclusive_lock, read_json
from .paths import SessionPaths, session_paths, state_root
from .project import RebuildReport, by_segment, load_lifecycle, rebuild, refresh


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
        """The highest existing segment index — the only one that can be open.

        The store enforces that: :meth:`open_segment` seals an unsealed
        predecessor before opening the next segment.
        """
        indices = self.paths.segment_indices()
        return indices[-1] if indices else None

    # ── generic append ──────────────────────────────────────────────────────

    def _locked(self):
        """The session lock — creating the session directory on first write."""
        ensure_dir(self.paths.dir)
        return exclusive_lock(self.paths.lock)

    def append(self, kind: str, data: dict, *, seg: int | None = None) -> dict:
        """Append one event to the log its kind belongs to, then re-project.

        A segment-scoped kind with ``seg=None`` goes to the current segment,
        resolved under the lock so a concurrent ``open_segment`` can't slip in.
        """
        with self._locked():
            if seg is None and ev.REGISTRY[kind].seg:
                seg = self.current_segment()
                if seg is None:
                    raise StoreError(f"session {self.sid} has no segment for {kind}")
            return self._append_locked(kind, data, seg=seg)

    def _append_locked(self, kind: str, data: dict, *, seg: int | None) -> dict:
        """Append and re-project; the caller holds the session lock.

        Any segment-scoped event requires its segment directory to exist (only
        :meth:`open_segment` creates segments). Activity is accepted only into
        the *current* segment of a session that isn't closed: a superseded or
        closed segment's log is frozen. A current segment that is sealed still
        accepts activity — a blocked compaction seals at PreCompact, work goes
        on, and the next PreCompact re-seals with a later end.
        """
        event = ev.make_event(kind, self.sid, data, seg=seg)
        if seg is not None and not self.paths.segment(seg).dir.is_dir():
            raise StoreError(f"segment {seg} does not exist for session {self.sid}")
        if ev.REGISTRY[kind].log == ev.ACTIVITY:
            if seg != self.current_segment():
                raise StoreError(f"segment {seg} of session {self.sid} is superseded; its log is frozen")
            if self._is_closed():
                raise StoreError(f"session {self.sid} is closed; its logs are frozen")
            log = self.paths.segment(seg).events
        else:
            log = self.paths.lifecycle
        bytes_before = log.stat().st_size if log.exists() else 0
        append_jsonl(log, event)
        refresh(self.paths, event, bytes_before=bytes_before)
        return event

    def _is_closed(self) -> bool:
        """Is the session closed? ``session.json`` answers when it's current; the log otherwise."""
        projected = read_json(self.paths.session_json)
        if isinstance(projected, dict) and projected.get("status") in ("open", "closed", "unknown"):
            return projected["status"] == "closed"
        status = None
        for e in load_lifecycle(self.paths).events:
            status = {"session.opened": "open", "session.closed": "closed"}.get(e["kind"], status)
        return status == "closed"

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
        """Create the next segment and record ``segment.opened``; return its index.

        Under the lock:

        * the index is one past every index the session has *ever* used — the
          directories and every ``segment.opened`` in the log — so a segment
          deleted by retention never has its index (and its old lifecycle
          events) inherited by a new one;
        * an unsealed predecessor is sealed first, at this segment's start
          (never before its own), ``sealed_by`` ``"compact"`` or ``"resume"``
          — a missed PreCompact or a lost SessionEnd can't leave two open.
        """
        with self._locked():
            buckets = by_segment(load_lifecycle(self.paths).events)
            named = [i for i, events in buckets.items() if any(e["kind"] == "segment.opened" for e in events)]
            previous = self.current_segment()
            if previous is not None and not any(e["kind"] == "segment.sealed" for e in buckets[previous]):
                sealed_by = "compact" if opened_by == "compact" else "resume"
                end = max(start, _segment_start(buckets[previous]))
                self._append_locked("segment.sealed", {"end": end, "sealed_by": sealed_by, "trigger": None},
                                    seg=previous)
            index = max([*self.paths.segment_indices(), *named], default=0) + 1
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

        Under the lock: the default index is resolved there, and ``end`` may not
        precede the segment's ``start`` — an inverted range would hand the
        summarizer nonsense.
        """
        data = {"end": end, "sealed_by": sealed_by, "trigger": trigger}
        if sha256 is not None:
            data["sha256"] = sha256
        with self._locked():
            target = index if index is not None else self.current_segment()
            if target is None:
                raise StoreError(f"session {self.sid} has no segment to seal")
            start = _segment_start(by_segment(load_lifecycle(self.paths).events)[target])
            if end < start:
                raise StoreError(f"segment {target} starts at {start}; cannot seal it at {end}")
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


def _segment_start(boundary: list[dict]) -> int:
    """A segment's start offset from its lifecycle events (0 if it never logged an open)."""
    return next((e["data"]["start"] for e in boundary if e["kind"] == "segment.opened"), 0)
