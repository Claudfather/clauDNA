"""The session rollup (spec §6.7): ``sessions/<sid>/summary.json``, with no LLM.

Recomputed from the session's ``done`` segment summaries whenever one
completes, and on demand by the readers. The merge rules are declared once,
as data (:data:`RULES`):

| Field | Rule |
|---|---|
| ``title``, ``intent``, ``outcome`` | the latest segment's |
| ``arc``, ``done``, ``blocks``, ``procedures`` | union, deduplicated on normalized text, keeping ``from_seg`` |
| ``in_progress``, ``next`` | the latest segment's only |

Blocks deduplicate on ``home`` + subject + claim.

A segment that retention retired keeps its summary in
``sessions/<sid>/summaries/seg-NNN.json`` (retention moves it there), so the
rollup stays a pure function of the summaries on disk: a lost or corrupt
rollup is always rebuilt whole. A ``done`` summary whose range no longer ends
at its segment's last seal is stale (a re-seal is being summarized) and is
left out until the new one lands.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .fsio import atomic_write_json, exclusive_lock, read_json
from .paths import SessionPaths
from .project import load_lifecycle, segment_states

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


def summaries(paths: SessionPaths, lifecycle: list[dict] | None = None) -> dict[int, dict]:
    """``index -> summary``: each live segment's current ``done`` summary, and each retired one's archive."""
    lifecycle = load_lifecycle(paths).events if lifecycle is None else lifecycle
    out = {s.index: s.doc for s in segment_states(paths, lifecycle) if s.summary == "done"}
    full = schema.load("segment-summary")
    archive = paths.dir / "summaries"
    for path in sorted(archive.glob("seg-*.json")) if archive.is_dir() else []:
        doc = read_json(path)
        if isinstance(doc, dict) and not schema.validate(doc, full) and doc["index"] not in out:
            out[doc["index"]] = doc
    return out


def compute(sid: str, by_index: dict[int, dict]) -> dict | None:
    """The rollup document for ``by_index`` (``index -> segment summary``), or ``None`` with nothing to roll up."""
    if not by_index:
        return None
    order = sorted(by_index)
    fields: dict[str, object] = {}
    for field, (path, rule) in RULES.items():
        if rule == LATEST:
            fields[field] = _get(by_index[order[-1]], path)
            continue
        seen: set[str] = set()
        merged: list[dict] = []
        for index in order:
            for item in _get(by_index[index], path) or []:
                key = dedup_key(field, item)
                if key not in seen:
                    seen.add(key)
                    merged.append({**item, "from_seg": index})
        fields[field] = merged
    return {"schema": ROLLUP_SCHEMA, "sid": sid, "through_seg": order[-1], "segments": order, "fields": fields}


def rollup_path(paths: SessionPaths) -> Path:
    return paths.dir / "summary.json"


def current(paths: SessionPaths, lifecycle: list[dict] | None = None) -> dict | None:
    """The rollup as the summaries on disk make it now, computed in memory (nothing is written)."""
    return compute(paths.sid, summaries(paths, lifecycle))


def refresh(paths: SessionPaths, lifecycle: list[dict] | None = None) -> dict | None:
    """Recompute and write the rollup (atomically); return it, or ``None`` when there is nothing yet.

    With nothing to roll up, a leftover ``summary.json`` is removed, so the
    file on disk is always current or absent. Serialized on ``.rollup.lock``:
    two summarizers finishing different segments at once must not let the one
    that read first write last.
    """
    if not paths.dir.is_dir():
        return None
    with exclusive_lock(paths.dir / ".rollup.lock"):
        doc = current(paths, lifecycle)
        if doc is not None:
            atomic_write_json(rollup_path(paths), doc)
        else:
            rollup_path(paths).unlink(missing_ok=True)
    return doc
