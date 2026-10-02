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
import unicodedata
from pathlib import Path

from . import schema
from .fsio import atomic_write_json, exclusive_lock, read_json
from .paths import SessionPaths
from .project import load_lifecycle, screened_summary, segment_states

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
    """Whitespace-collapsed, case-folded and NFKC-normalized: ``café`` keys alike in NFC and NFD."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", str(text or ""))).strip().casefold()


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
    for index in paths.archived_indices():
        if index not in out and (doc := read_archived(paths, index)) is not None:
            out[index] = doc
    return out


def read_archived(paths: SessionPaths, index: int) -> dict | None:
    """Retired segment ``index``'s archived summary, if it is a valid one for that index."""
    doc = read_json(paths.archived_summary(index))
    if isinstance(doc, dict) and not schema.validate(doc, schema.load("segment-summary")) and doc["index"] == index:
        return screened_summary(doc)
    return None


def trusted(doc: object) -> bool:
    """Is ``doc`` a rollup this release may show? Its tag, and built from screened summaries."""
    return isinstance(doc, dict) and doc.get("schema") == ROLLUP_SCHEMA and doc.get("screened") is True


def outdated(paths: SessionPaths) -> bool:
    """Is the rollup on disk one 0.23 wrote (unscreened)? Readers recompute past it; the sweep rewrites it.

    Only that known shape: a rollup some other release wrote is left alone, so
    two versions sharing a store don't rewrite each other's files every sweep.
    """
    doc = read_json(rollup_path(paths))
    return isinstance(doc, dict) and doc.get("schema") == ROLLUP_SCHEMA and "screened" not in doc


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
    # "screened": built from summaries the instruction screen has seen (claudna.screen). An extra key, not a new
    # tag, so a 0.23 reader still takes the file; a 0.24 reader takes only a marked one (:func:`trusted`).
    return {"schema": ROLLUP_SCHEMA, "sid": sid, "through_seg": order[-1], "segments": order, "fields": fields,
            "screened": True}


def rollup_path(paths: SessionPaths) -> Path:
    return paths.dir / "summary.json"


def current(paths: SessionPaths, lifecycle: list[dict] | None = None) -> dict | None:
    """The rollup as the summaries on disk make it now, computed in memory (nothing is written)."""
    return compute(paths.sid, summaries(paths, lifecycle))


def discard(paths: SessionPaths, *, written_before: float | None = None) -> None:
    """Remove the rollup under its lock (a failed refresh left it stale); never raises.

    The lock alone only keeps this from racing a write in progress: another
    summarizer's refresh may have written a fresh rollup just before. Given
    ``written_before`` (an epoch: when the summary that made the file stale
    was logged), a rollup written since is kept, since it already counts it.
    """
    path = rollup_path(paths)
    try:
        with exclusive_lock(paths.dir / ".rollup.lock"):
            if written_before is None or path.stat().st_mtime < written_before:
                path.unlink(missing_ok=True)
    except OSError:
        pass  # the directory is gone (so is the rollup), or there is no rollup to drop


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
