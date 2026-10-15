"""The export door (spec §8, phase 6): what a consumer reads, and how it acks.

Claudron (or any consumer) reads the store only through this, never its files,
so the storage layout stays clauDNA's to change and only the envelope is
contract::

    session export --consumer claudron [--since-seg N] [--limit N] --json
    session export --consumer claudron --ack --sid <sid> --through <seg>

The envelope is ``{schema: "claudna.export/1", consumer, items: [...], next: {...}}``.
Each item is ``{sid, seg, session: <a session.json subset>, summary: <the
segment summary>, segment: {sealed_at, sealed_by, counts}}`` (the subset's
``agent_cli`` since 0.27; absent in an older envelope means ``claude``).
Spec §8 "Item fields and rules" is the contract.
``next`` maps each session to the segment index the consumer may ack once it
has taken that session's items.

Per session, segments are walked in order past the consumer's cursor (or
``--since-seg``): a final segment with a ``done`` summary is an item, and so
is a retired one, from its archived summary (no data loss: a consumer behind
retention still gets everything; the archive is read only past the cursor).
A skipped segment passes, and so does one whose summary will never come (its
last attempt spent, or a retry no harvest will run: :func:`_settled`).
Anything still in flight stops that session, so a cursor never skips work
that is still coming — harvest's rule, from the same verdict. Private
sessions are never exported. An ack goes through ``SessionHandle.ack``: one
locked writer, never past the session's last *final* segment, and a cursor
never moves back. The store's own consumers (``harvest``) are reserved names.
"""

from __future__ import annotations

import re
import time

from .fsio import epoch_of
from .project import (HARVEST_CONSUMER, abandoned_at, by_segment, fold_boundary, harvest_skip, load_lifecycle,
                      retired_indices, segment_docs, segment_states, session_doc, session_facts, summary_verdict)
from .rollup import read_archived
from .store import SessionStore

EXPORT_SCHEMA = "claudna.export/1"
CONSUMER = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
#: Consumers the store runs itself, which acks only through their own code: an export ack must not move them.
RESERVED = frozenset({HARVEST_CONSUMER})
#: How long a summary due a retry holds a session's export when harvest should run it but doesn't: the
#: acked-retention floor, so the wait never outlasts what retention would keep anyway.
RETRY_WAIT_DAYS = 7
SESSION_FIELDS = ("sid", "status", "opened_at", "closed_at", "close_reason", "chain_id", "parent_sid", "actor",
                  "origin", "agent_cli")


def check_consumer(name: str) -> str:
    if not isinstance(name, str) or not CONSUMER.fullmatch(name):
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
    or ``claudron`` gone). A stale or unreadable summary is harvest's to
    re-summarize: waited for on the same terms, stepped over when harvest
    never takes the session.
    """
    quiet = bool(events) and now - epoch_of(events[-1]["ts"]) > RETRY_WAIT_DAYS * 86400
    if summary in ("stale", "unreadable"):  # harvest re-summarizes these; nothing else does (#387 review S3)
        return not retried or quiet
    if summary not in ("none", "pending", "failed"):
        return False
    verdict = summary_verdict(events, now, abandoned_at=abandoned)
    if verdict == "retry" and retried and quiet:
        return True  # harvest was to retry it but hasn't in a week (turned off, claudron gone): stop waiting
    return verdict == "give up" or (verdict == "retry" and not retried)


def segment_record(index: int, bucket: list[dict], live: dict[int, dict]) -> dict:
    """The seal from the lifecycle fold and counts from the live projection (spec §8).

    A retired segment still has its seal in the log; its activity counts are
    unavailable because the directory and activity log have been retired.
    """
    seal = fold_boundary(bucket).last_seal
    doc = live.get(index)
    return {"sealed_at": seal["ts"] if seal else None,
            "sealed_by": seal["data"]["sealed_by"] if seal else None,
            "counts": dict(doc["counts"]) if doc else None}


def skip_reason(bucket: list[dict]) -> str | None:
    """The reason in the segment's last ``summary.skipped`` event."""
    return next((e["data"]["reason"] for e in reversed(bucket) if e["kind"] == "summary.skipped"), None)


def export(store: SessionStore, consumer: str, *, since_seg: int | None = None, limit: int = 100,
           now: float | None = None, include_skipped: bool = False) -> dict:
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
        live = handle.paths.segment_indices()
        lifecycle = load_lifecycle(handle.paths)
        retired = {i for i in retired_indices(lifecycle.events) if i > start}
        if max(live, default=0) <= start and max(handle.paths.archived_indices(), default=0) <= start and not retired:
            continue  # nothing past the cursor, including retired segments with no archive: no projections
        facts = session_facts(lifecycle.events)
        if not lifecycle.events or facts.private:
            continue
        through, subset = start, None
        live_docs: dict[int, dict] = {}
        buckets, abandoned = by_segment(lifecycle.events), abandoned_at(lifecycle.events)
        retried = harvest_skip(facts, lifecycle.events) is None
        states = {s.index: s for s in segment_states(handle.paths, lifecycle.events) if s.index > start}

        def take(index: int) -> tuple[bool, dict | None, str | None]:
            """``(go on, summary, pass-over reason)`` for one segment past the cursor."""
            if index in retired and index not in states:  # its archived summary, final and done (owner, #387 S4)
                doc = read_archived(handle.paths, index)
                if doc is not None:
                    return True, doc, None
                reason = "private" if skip_reason(buckets.get(index, [])) == "private" else "retired"
                return True, None, reason
            state = states[index]
            if not state.final:
                return False, None, None
            if state.summary == "done":
                return True, state.doc, None
            if state.summary == "skipped":
                return True, None, skip_reason(buckets.get(index, []))
            settled = _settled(state.summary, buckets.get(index, []), retried=retried, abandoned=abandoned, now=now)
            return settled, None, "gave_up" if settled else None

        for index in sorted({*states, *retired}):
            if len(items) >= limit:
                break
            go_on, doc, reason = take(index)
            if not go_on:
                break
            if doc is not None or (include_skipped and reason not in (None, "private")):
                if subset is None:
                    session = session_doc(handle.paths, lifecycle)
                    subset = {k: session.get(k) for k in SESSION_FIELDS}
                    live_docs = {d["index"]: d for d in segment_docs(handle.paths, lifecycle)}
                item = {"sid": sid, "seg": index, "session": subset, "summary": doc,
                        "segment": segment_record(index, buckets.get(index, []), live_docs)}
                if doc is None:
                    item["skipped"] = {"reason": reason}
                items.append(item)
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
    lifecycle = load_lifecycle(handle.paths).events
    finals = [s.index for s in segment_states(handle.paths, lifecycle) if s.final]
    highest = max([*finals, *retired_indices(lifecycle)], default=0)
    if through > highest:  # a cursor never moves back: past the last *final* segment would skip work still coming
        raise ValueError(f"--through {through} is past session {sid}'s last final segment ({highest})")
    handle.ack(consumer, through)
    return handle.cursor(consumer)
