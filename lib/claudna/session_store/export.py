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

from . import schema
from .fsio import read_json
from .project import by_segment, fold_boundary, load_lifecycle, session_facts, session_status
from .store import SessionStore

EXPORT_SCHEMA = "claudna.export/1"
CONSUMER = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SESSION_FIELDS = ("sid", "status", "opened_at", "closed_at", "close_reason", "chain_id", "parent_sid", "actor",
                  "origin")


def check_consumer(name: str) -> str:
    if not isinstance(name, str) or not CONSUMER.match(name):
        raise ValueError(f"invalid consumer name: {name!r}")
    return name


def _session_subset(doc: dict | None, sid: str) -> dict:
    doc = doc if isinstance(doc, dict) else {}
    return {k: doc.get(k) for k in SESSION_FIELDS} | {"sid": sid}


def export(store: SessionStore, consumer: str, *, since_seg: int | None = None, limit: int = 100) -> dict:
    """The envelope of everything ``consumer`` hasn't taken yet, up to ``limit`` items."""
    check_consumer(consumer)
    full = schema.load("segment-summary")
    items: list[dict] = []
    nxt: dict[str, int] = {}
    for sid in store.session_ids():
        if len(items) >= limit:
            break
        handle = store.session(sid)
        lifecycle = load_lifecycle(handle.paths).events
        if not lifecycle or session_facts(lifecycle).private:
            continue
        closed = session_status(lifecycle)[0] == "closed"
        indices = handle.paths.segment_indices()
        start = max(handle.cursor(consumer), since_seg or 0)
        buckets = by_segment(lifecycle)
        through = start
        session_doc = None
        for index in (i for i in indices if i > start):
            boundary = fold_boundary(buckets.get(index, []))
            final = boundary.sealed and (closed or index < indices[-1])
            status = boundary.summary["status"]
            if not final or status not in ("done", "skipped"):
                break
            if status == "done":
                summary = read_json(handle.paths.segment(index).summary)
                if not isinstance(summary, dict) or schema.validate(summary, full):
                    break  # unreadable: hold here rather than skip it
                if len(items) >= limit:
                    break
                if session_doc is None:
                    session_doc = _session_subset(read_json(handle.paths.session_json), sid)
                items.append({"sid": sid, "seg": index, "session": session_doc, "summary": summary})
            through = index
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
