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
was skipped passes, and so does one whose summary will never come (its last
attempt spent, or a retry no harvest will run: :func:`_settled`). Anything
still in flight stops that session, so a cursor never skips work that is
still coming — harvest's rule, from the same verdict. Private sessions are
never exported. An ack goes through ``SessionHandle.ack``: one locked writer,
never past the session's last segment, and a cursor never moves back. The
store's own consumers (``harvest``) are reserved names.
"""

from __future__ import annotations

import re
import time

from .fsio import epoch_of
from .project import (abandoned_at, by_segment, harvest_skip, load_lifecycle, next_segment_index, segment_states,
                      session_doc, session_facts, summary_verdict)
from .store import SessionStore

EXPORT_SCHEMA = "claudna.export/1"
CONSUMER = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
#: Consumers the store runs itself, which acks only through their own code: an export ack must not move them.
RESERVED = frozenset({"harvest"})
#: How long a summary due a retry holds a session's export when harvest should run it but doesn't: the
#: acked-retention floor, so the wait never outlasts what retention would keep anyway.
RETRY_WAIT_DAYS = 7
SESSION_FIELDS = ("sid", "status", "opened_at", "closed_at", "close_reason", "chain_id", "parent_sid", "actor",
                  "origin")


def check_consumer(name: str) -> str:
    if not isinstance(name, str) or not CONSUMER.match(name):
        raise ValueError(f"invalid consumer name: {name!r}")
    if name in RESERVED:
        raise ValueError(f"consumer name {name!r} is reserved for the store's own use")
    return name


def _settled(summary: str, events: list[dict], *, retried: bool, abandoned: str | None, now: float) -> bool:
    """Is a final segment with no usable summary past waiting for, so export may step over it (no item)?

    Its summary has had its last attempt (:func:`project.summary_verdict`),
    or it is due a retry that nothing will run: only harvest retries
    summaries, and ``retried`` says whether harvest takes this session
    (:func:`project.harvest_skip`) — or would, but a retry has been due for
    :data:`RETRY_WAIT_DAYS` without one running (harvest since switched off,
    or ``claudron`` gone). A stale or unreadable summary is still waited for.
    """
    if summary not in ("none", "pending", "failed"):
        return False
    verdict = summary_verdict(events, now, abandoned_at=abandoned)
    if verdict == "retry" and retried and events and now - epoch_of(events[-1]["ts"]) > RETRY_WAIT_DAYS * 86400:
        return True  # harvest was to retry it but hasn't in a week (turned off, claudron gone): stop waiting
    return verdict == "give up" or (verdict == "retry" and not retried)


def export(store: SessionStore, consumer: str, *, since_seg: int | None = None, limit: int = 100,
           now: float | None = None) -> dict:
    """The envelope of everything ``consumer`` hasn't taken yet, up to ``limit`` items."""
    check_consumer(consumer)
    now = time.time() if now is None else now
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
        facts = session_facts(lifecycle.events)
        if not lifecycle.events or facts.private:
            continue
        through, subset = start, None
        buckets, abandoned = by_segment(lifecycle.events), abandoned_at(lifecycle.events)
        retried = harvest_skip(facts, lifecycle.events) is None
        for state in (s for s in segment_states(handle.paths, lifecycle.events) if s.index > start):
            if not state.final or len(items) >= limit:
                break
            if state.summary not in ("done", "skipped") and not _settled(
                    state.summary, buckets.get(state.index, []), retried=retried, abandoned=abandoned, now=now):
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
    highest = next_segment_index(handle.paths) - 1
    if through > highest:  # a cursor never moves back: one past the end would skip segments not yet made
        raise ValueError(f"--through {through} is past session {sid}'s last segment ({highest})")
    handle.ack(consumer, through)
    return handle.cursor(consumer)
