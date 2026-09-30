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
from .fsio import DIR_MODE, append_jsonl, atomic_write_json, ensure_dir, exclusive_lock, file_size, read_json
from .paths import SessionPaths, session_ids, session_paths, state_root, validate_root
from .project import (
    SESSION_SCHEMA,
    RebuildReport,
    by_segment,
    fold_boundary,
    load_lifecycle,
    next_segment_index,
    read_projection,
    rebuild,
    refresh,
    segment_transcript_paths,
    session_facts,
    transcript_path_of,
)


class StoreError(RuntimeError):
    """An operation that the store's invariants forbid (e.g. activity with no segment)."""


class NotAppendable(StoreError):
    """The event has nowhere to go: no segment yet, or a closed session. Expected for async activity hooks."""


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
        spec = ev.REGISTRY.get(kind)
        if spec is None:
            raise ev.EventError(f"unknown event kind: {kind}")
        with self._locked():
            current = None
            if spec.seg and (seg is None or spec.log == ev.ACTIVITY):
                current = self.current_segment()  # one directory listing, reused below
                if seg is None:
                    if current is None:
                        raise NotAppendable(f"session {self.sid} has no segment for {kind}")
                    seg = current
            return self._append_locked(kind, data, seg=seg, current=current)

    def _append_locked(self, kind: str, data: dict, *, seg: int | None, current: int | None = None) -> dict:
        """Append and re-project; the caller holds the session lock.

        Any segment-scoped event requires its segment directory to exist (only
        :meth:`open_segment` creates segments). Activity is accepted only into
        the *current* segment of a session that isn't closed: a superseded or
        closed segment's log is frozen. A current segment that is sealed still
        accepts activity — a blocked compaction seals at PreCompact, work goes
        on, and the next PreCompact re-seals with a later end.
        """
        event = ev.make_event(kind, self.sid, data, seg=seg)
        if ev.REGISTRY[kind].log == ev.ACTIVITY:
            current = current if current is not None else self.current_segment()
            if seg != current:  # the current segment's directory exists by definition
                state = "is superseded; its log is frozen" if self.paths.segment(seg).dir.is_dir() else "does not exist"
                raise StoreError(f"segment {seg} of session {self.sid} {state}")
            if self._current_session()["status"] == "closed":
                raise NotAppendable(f"session {self.sid} is closed; its logs are frozen")
            log = self.paths.segment(seg).events
        else:
            if seg is not None and not self.paths.segment(seg).dir.is_dir():
                raise StoreError(f"segment {seg} does not exist for session {self.sid}")
            log = self.paths.lifecycle
        bytes_before = file_size(log)
        # Lifecycle events fix byte ranges and are a handful per session: fsynced.
        # Activity lines are derived tallies: a crash may lose one (spec §11.11).
        append_jsonl(log, event, durable=log == self.paths.lifecycle)
        refresh(self.paths, event, bytes_before=bytes_before)
        return event

    def _current_session(self) -> dict:
        """``session.json``, rebuilt first if it doesn't reflect the whole lifecycle log.

        A stale ``session.json`` means a lifecycle refresh was lost (a killed
        hook), so every projection derived from the lifecycle — including the
        current segment's status and range — may be stale too. Rebuilding here
        heals them once, instead of letting activity appends carry stale
        segment fields forward or re-fold the log on every append.
        """
        projected = read_projection(self.paths.session_json, SESSION_SCHEMA,
                                    bytes_before=file_size(self.paths.lifecycle))
        if projected is None:
            rebuild(self.paths)
            projected = read_projection(self.paths.session_json, SESSION_SCHEMA)
        return projected

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
        claude_pid: int | None = None,
        harvest: dict | None = None,
    ) -> dict:
        """Record ``session.opened``. A session with no parent is its own chain root.

        ``claude_pid`` (the owning Claude Code process) and ``harvest`` (this
        session's own ``{enabled, vault}``) are optional, recorded by the hook.
        """
        data = {
            "source": source,
            "parent_sid": parent_sid,
            "chain_id": chain_id or self.sid,
            "actor": actor,
            "origin": origin,
            "transcript_path": transcript_path,
        }
        if claude_pid is not None:
            data["claude_pid"] = claude_pid
        if harvest is not None:
            data["harvest"] = harvest
        return self.append("session.opened", data)

    def boundary(self, index: int, lifecycle: list[dict] | None = None):
        """Segment ``index``'s open/seal boundary, folded from the lifecycle log."""
        events = load_lifecycle(self.paths).events if lifecycle is None else lifecycle
        return fold_boundary(by_segment(events)[index])

    def open_segment(self, opened_by: str, start: int) -> int:
        """Create the next segment and record ``segment.opened``; return its index.

        Under the lock:

        * a ``"compact"`` segment starts where its predecessor's last seal ended
          (spec §4.2) — ``start`` is only the fallback for a missed PreCompact.
          Resolving it here, under the lock, means a concurrent re-seal can't
          slip between reading the seal and opening the segment;

        * the index is one past every index the session has *ever* used — the
          directories and every ``segment.opened`` in the log — so a segment
          deleted by retention never has its index (and its old lifecycle
          events) inherited by a new one;
        * a rejected call changes nothing: arguments are validated before the
          predecessor is sealed or a directory is made;
        * an unsealed predecessor is sealed first, ``sealed_by`` ``"compact"``
          or ``"resume"`` — a missed PreCompact or a lost SessionEnd can't leave
          two open. Its end is this segment's start when both share a
          transcript; when a resume moved to a new transcript file, the new
          start means nothing in the old file, so the end is the old
          transcript's size (never before the predecessor's own start).
        """
        ev.check_data("segment.opened", {"opened_by": opened_by, "start": start})  # before any side effect
        with self._locked():
            lifecycle = load_lifecycle(self.paths).events
            previous = self.current_segment()
            if previous is not None:
                before = self.boundary(previous, lifecycle)
                if before.sealed and opened_by == "compact":
                    start = before.last_seal["data"]["end"]
                if not before.sealed:
                    old_path = segment_transcript_paths(lifecycle)[previous]
                    same_file = old_path == transcript_path_of(lifecycle)
                    end = start if same_file or not old_path else file_size(old_path)
                    self._append_locked("segment.sealed", {
                        "end": max(end, before.start or 0),
                        "sealed_by": "compact" if opened_by == "compact" else "resume",
                        "trigger": None,
                    }, seg=previous)
            index = next_segment_index(self.paths)
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
        clamp: bool = False,
    ) -> dict:
        """Record ``segment.sealed`` for ``index`` (default: current). Safe to repeat.

        Under the lock: the default index is resolved there, and ``end`` may not
        precede the segment's ``start`` — an inverted range would hand the
        summarizer nonsense. ``clamp=True`` raises ``end`` to the start instead
        of refusing: for a hook whose transcript size is unknown or behind.
        """
        with self._locked():
            target = index if index is not None else self.current_segment()
            if target is None:
                raise StoreError(f"session {self.sid} has no segment to seal")
            start = self.boundary(target).start or 0
            if clamp:
                end = max(end, start)
            if end < start:
                raise StoreError(f"segment {target} starts at {start}; cannot seal it at {end}")
            data = {"end": end, "sealed_by": sealed_by, "trigger": trigger}
            if sha256 is not None:
                data["sha256"] = sha256
            return self._append_locked("segment.sealed", data, seg=target)

    def close_session(self, reason: str) -> dict:
        return self.append("session.closed", {"reason": reason})

    def close_abandoned(self, *, owner_pid: int | None = None) -> int | None:
        """Seal the open segment at its transcript's size and close as ``abandoned``: one locked step.

        For a session whose SessionEnd never ran (``unclosed.py``). Everything is
        decided under the lock, so a ``resume`` can't slip in between the check
        and the writes: the session must still be open and, given ``owner_pid``,
        still owned by that (dead) process. Returns the index it sealed, or
        ``None`` when no segment was left unsealed.
        """
        with self._locked():
            lifecycle = load_lifecycle(self.paths).events
            facts = session_facts(lifecycle)
            if facts.status != "open":
                raise StoreError(f"session {self.sid} is not open")
            if owner_pid is not None and facts.claude_pid != owner_pid:
                raise StoreError(f"session {self.sid} was resumed by another process; left open")
            index = self.current_segment()
            sealed = None
            if index is not None:
                boundary = self.boundary(index, lifecycle)
                if not boundary.sealed:
                    end = max(file_size(segment_transcript_paths(lifecycle)[index]), boundary.start or 0)
                    self._append_locked("segment.sealed", {"end": end, "sealed_by": "abandoned", "trigger": None},
                                        seg=index)
                    sealed = index
            self._append_locked("session.closed", {"reason": "abandoned"}, seg=None)
            return sealed

    def link_child(self, child_sid: str) -> dict:
        return self.append("session.child_linked", {"child_sid": child_sid})

    def set_private(self, private: bool, *, by: str = "user") -> dict:
        return self.append("session.privacy_set", {"private": private, "by": by})

    def cursor(self, consumer: str) -> int:
        """How far ``consumer`` has taken this session's segments (``consumers.json``, spec §6.8); 0 if never."""
        doc = read_json(self.paths.consumers)
        try:
            return int(doc["consumers"][consumer]["through_seg"])
        except (TypeError, KeyError, ValueError):
            return 0

    def ack(self, consumer: str, through: int) -> None:
        """Record, under the lock, that ``consumer`` has taken every segment up to ``through``.

        The one writer of ``consumers.json``: harvest and (later) ``session
        export --ack`` both come through here. A cursor never moves back.
        """
        with self._locked():
            doc = read_json(self.paths.consumers)
            if not isinstance(doc, dict) or doc.get("schema") != "claudna.consumers/1":
                doc = {"schema": "claudna.consumers/1", "sid": self.sid, "consumers": {}}
            if through > self.cursor(consumer):
                doc["consumers"][consumer] = {"through_seg": through, "acked_at": ev.now_ts()}
                atomic_write_json(self.paths.consumers, doc)

    def rebuild(self) -> RebuildReport:
        """Regenerate projections from the logs (read-only with respect to logs)."""
        with self._locked():
            return rebuild(self.paths)


class SessionStore:
    """Entry point: resolves the store root once, hands out session handles."""

    def __init__(self, root: Path | None = None):
        self.root = state_root() if root is None else validate_root(root)

    def session(self, sid: str) -> SessionHandle:
        return SessionHandle(session_paths(sid, self.root))

    def session_ids(self) -> list[str]:
        return session_ids(self.root)

