"""The session rollup (spec §6.7): ``sessions/<sid>/summary.json``, with no LLM.

Recomputed from the session's ``done`` segment summaries whenever one
completes, and on demand by the readers. The merge rules are declared once,
as data (:data:`RULES`):

| Field | Rule |
|---|---|
| ``title``, ``intent``, ``outcome`` | the latest segment's |
| ``arc``, ``done``, ``blocks``, ``procedures`` | union, deduplicated on normalized text, keeping ``from_seg`` |

Blocks deduplicate on ``home`` + subject + claim.
| ``in_progress``, ``next`` | the latest segment's only |

A segment that retention retired (phase 6) no longer has its ``summary.json``,
but what it contributed is kept: items whose ``from_seg`` is no longer on disk
carry over from the previous rollup, so a session's knowledge outlives its
segment directories. A ``done`` summary whose range doesn't end at its
segment's last seal is stale (a re-seal is being summarized) and is left out
until the new one lands.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .fsio import atomic_write_json, exclusive_lock, read_json
from .paths import SessionPaths
from .project import by_segment, fold_boundary, load_lifecycle

ROLLUP_SCHEMA = "claudna.session-summary/2"

LATEST = "latest"  #: the newest segment's value wins
UNION = "union"  #: every segment's items, deduplicated, each tagged with from_seg
#: field -> (where it lives in a segment summary, rule)
RULES: dict[str, tuple[tuple[str, ...], str]] = {
    "title": (("journey", "title"), LATEST),
    "intent": (("journey", "intent"), LATEST),
    "outcome": (("journey", "outcome"), LATEST),
    "arc": (("journey", "arc"), UNION),
    "done": (("journey", "done"), UNION),
    "in_progress": (("journey", "in_progress"), LATEST),
    "next": (("journey", "next"), LATEST),
    "blocks": (("blocks",), UNION),
    "procedures": (("procedures",), UNION),
}

_SPACE = re.compile(r"\s+")


def _norm(text: object) -> str:
    return _SPACE.sub(" ", str(text or "")).strip().casefold()


def dedup_key(field: str, item: dict) -> str:
    """What makes two items "the same" for :data:`UNION` (spec §6.7)."""
    if field == "blocks":
        subject = (item.get("subject_hint") or {}).get("name")
        return "\x1f".join((_norm(item.get("home")), _norm(subject), _norm(item.get("claim"))))
    if field == "arc":
        return "\x1f".join((_norm(item.get("step")), _norm(item.get("result"))))
    return _norm(item.get("text"))


def _get(doc: dict, path: tuple[str, ...]):
    for key in path:
        doc = doc.get(key) if isinstance(doc, dict) else None
    return doc


def done_summaries(paths: SessionPaths, lifecycle: list[dict] | None = None) -> dict[int, dict]:
    """``index -> summary`` for each segment whose summary is done, valid, and covers its last seal."""
    lifecycle = load_lifecycle(paths).events if lifecycle is None else lifecycle
    full = schema.load("segment-summary")
    out: dict[int, dict] = {}
    for index, events in sorted(by_segment(lifecycle).items()):
        boundary = fold_boundary(events)
        if boundary.summary["status"] != "done" or not boundary.last_seal:
            continue
        summary = read_json(paths.segment(index).summary)
        if not isinstance(summary, dict) or schema.validate(summary, full):
            continue
        if summary["input"]["range"]["end"] != boundary.last_seal["data"]["end"]:
            continue  # stale: the segment was re-sealed after this summary
        out[index] = summary
    return out


def compute(sid: str, summaries: dict[int, dict], previous: dict | None = None,
            on_disk: set[int] | None = None) -> dict | None:
    """The rollup document for ``summaries`` (``index -> segment summary``), or ``None`` with nothing to roll up.

    ``previous`` (the last rollup) and ``on_disk`` (segment indices still
    present) carry over what retired segments contributed.
    """
    kept: dict[str, list[dict]] = {}
    retired = set()
    if isinstance(previous, dict) and on_disk is not None:
        for field, (_, rule) in RULES.items():
            if rule == UNION:
                items = (previous.get("fields") or {}).get(field) or []
                kept[field] = [i for i in items if isinstance(i, dict) and i.get("from_seg") not in on_disk]
        retired = {s for s in previous.get("segments", []) if s not in on_disk}
    if not summaries and not any(kept.values()):
        return None
    order = sorted(summaries)
    fields: dict[str, object] = {}
    for field, (path, rule) in RULES.items():
        if rule == LATEST:
            fields[field] = _get(summaries[order[-1]], path) if order else (previous or {}).get("fields", {}).get(field)
            continue
        seen: set[str] = set()
        merged: list[dict] = []
        for item in kept.get(field, []):
            key = dedup_key(field, item)
            if key not in seen:
                seen.add(key)
                merged.append(item)
        for index in order:
            for item in _get(summaries[index], path) or []:
                key = dedup_key(field, item)
                if key not in seen:
                    seen.add(key)
                    merged.append({**item, "from_seg": index})
        fields[field] = merged
    segments = sorted(set(order) | retired)
    return {"schema": ROLLUP_SCHEMA, "sid": sid, "through_seg": max(segments), "segments": segments,
            "fields": fields}


def rollup_path(paths: SessionPaths) -> Path:
    return paths.dir / "summary.json"


def refresh(paths: SessionPaths, lifecycle: list[dict] | None = None) -> dict | None:
    """Recompute and write the rollup (atomically); return it, or ``None`` when there is nothing yet.

    Serialized on ``.rollup.lock``: two summarizers finishing different
    segments at once must not let the one that read first write last.
    """
    if not paths.dir.is_dir():
        return None
    with exclusive_lock(paths.dir / ".rollup.lock"):
        previous = read_json(rollup_path(paths))
        doc = compute(paths.sid, done_summaries(paths, lifecycle), previous if isinstance(previous, dict) else None,
                      set(paths.segment_indices()))
        if doc is not None:
            atomic_write_json(rollup_path(paths), doc)
    return doc
