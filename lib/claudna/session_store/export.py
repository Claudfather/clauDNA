"""The export door (spec §8, phase 6): what a consumer reads, and how it acks.

Claudron (or any consumer) reads the store only through this, never its files,
so the storage layout stays clauDNA's to change and only the envelope is
contract::

    session export --consumer claudron [--since-seg N] [--limit N] --json
    session export --consumer claudron --ack --sid <sid> --through <seg>

The envelope is ``{schema: "claudna.export/1", consumer, items: [...], next: {...}}``.
Each item is ``{sid, seg, session: <a session.json subset>, summary: <the
segment summary>}``. ``next`` maps each session to the segment index the
consumer may ack once it has taken that session's items.

Per session, segments are walked in order past the consumer's cursor (or
``--since-seg``): a final segment with a ``done`` summary is an item; one that
was skipped passes; anything still in flight (not final, pending, failed,
never summarized) stops that session, so a cursor never skips work that is
still coming. That is harvest's rule. Private sessions are never exported.
An ack goes through ``SessionHandle.ack``: one locked writer, and a cursor
never moves back.
"""

from __future__ import annotations

import re

from .project import load_lifecycle, segment_states, session_doc, session_facts
from .store import SessionStore

EXPORT_SCHEMA = "claudna.export/1"
CONSUMER = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SESSION_FIELDS = ("sid", "status", "opened_at", "closed_at", "close_reason", "chain_id", "parent_sid", "actor",
                  "origin")


def check_consumer(name: str) -> str:
    if not isinstance(name, str) or not CONSUMER.match(name):
        raise ValueError(f"invalid consumer name: {name!r}")
    return name


def export(store: SessionStore, consumer: str, *, since_seg: int | None = None, limit: int = 100) -> dict:
    """The envelope of everything ``consumer`` hasn't taken yet, up to ``limit`` items."""
    check_consumer(consumer)
    items: list[dict] = []
    nxt: dict[str, int] = {}
    for sid in store.session_ids():
        if len(items) >= limit:
            break
        handle = store.session(sid)
        start = max(handle.cursor(consumer), since_seg or 0)
        indices = handle.paths.segment_indices()
        if not indices or indices[-1] <= start:
            continue  # nothing past the cursor: no log read
        lifecycle = load_lifecycle(handle.paths)
        if not lifecycle.events or session_facts(lifecycle.events).private:
            continue
        through, subset = start, None
        for state in (s for s in segment_states(handle.paths, lifecycle.events) if s.index > start):
            if not state.final or state.summary not in ("done", "skipped") or len(items) >= limit:
                break  # still in flight, stale or unreadable: the session's cursor holds here
            if state.summary == "done":
                if subset is None:
                    doc = session_doc(handle.paths, lifecycle)
                    subset = {k: doc.get(k) for k in SESSION_FIELDS}
                items.append({"sid": sid, "seg": state.index, "session": subset, "summary": state.doc})
            through = state.index
        if through > start:
            nxt[sid] = through
    return {"schema": EXPORT_SCHEMA, "consumer": consumer, "items": items, "next": nxt}


def ack(store: SessionStore, consumer: str, sid: str, through: int) -> int:
    """Move ``consumer``'s cursor for ``sid`` to ``through`` (never back); return the cursor after."""
    check_consumer(consumer)
    if not isinstance(through, int) or isinstance(through, bool) or through < 0:
        raise ValueError(f"invalid --through: {through!r}")
    handle = store.session(sid)
    if not handle.exists():
        raise LookupError(f"no session {sid}")
    handle.ack(consumer, through)
    return handle.cursor(consumer)
