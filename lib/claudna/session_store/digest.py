"""The promotion digest (spec §7.2, phase 5): which drafts a person should look at first.

Harvest writes drafts; only a person promotes them (``draft → verified``).
Harvest records every capture in ``<root>/harvest/ledger.jsonl``: the session
and segment, the note's vault path, the vault, who asserted the claim, and a
**claim key** (the rollup's dedup key: home + subject + claim, normalized). This
module reads that ledger:

* **Evidence** is the number of distinct sessions that asserted the same claim
  key. It is §7.2's "recurring across ≥ 2 sessions" signal.
* **The digest** is at most :data:`DIGEST_SIZE` draft notes not yet reviewed:
  the most-reinforced first, a user-asserted claim ahead of an agent's on a
  tie, then the most recent. The other-person facts harvest held back
  (``held.jsonl``) are queued beside them.
* **Review** (``/claudna:capture --review``) promotes through ``claudron
  promote`` and then marks the item done here, in ``reviewed.jsonl``, so it
  leaves the digest. clauDNA never promotes anything itself.

``review.txt`` holds the one line SessionStart shows, rewritten after every
harvest run and every review.

Blocked on Claudron#200 and not here: subject resolution, section-targeted
writes, risk tiers, the inbox and ambiguous queues, and ``revert-run``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .fsio import append_jsonl, ensure_dir, read_jsonl
from .events import now_ts

DIGEST_SIZE = 5


def home(root: Path) -> Path:
    return root / "harvest"


def record_capture(root: Path, *, sid: str, seg: int, key: str, block: dict, title: str, action: str,
                   path: str | None, vault: str | None) -> None:
    """One ledger line for one ``claudron capture`` answer."""
    append_jsonl(ensure_dir(home(root)) / "ledger.jsonl", {
        "ts": now_ts(), "sid": sid, "seg": seg, "key": key, "title": title, "claim": block.get("claim"),
        "asserted_by": block.get("asserted_by"), "action": action, "path": path, "vault": vault,
    }, durable=False)


def evidence(root: Path) -> dict[str, set[str]]:
    """``claim key -> the sessions that asserted it`` (captures and held person facts alike)."""
    out: dict[str, set[str]] = {}
    for rec in read_jsonl(home(root) / "ledger.jsonl").records:
        if isinstance(rec.get("key"), str) and isinstance(rec.get("sid"), str):
            out.setdefault(rec["key"], set()).add(rec["sid"])
    for rec in read_jsonl(home(root) / "held.jsonl").records:
        if isinstance(rec.get("key"), str) and isinstance(rec.get("sid"), str):
            out.setdefault(rec["key"], set()).add(rec["sid"])
    return out


def _reviewed(root: Path) -> set[str]:
    return {r["item"] for r in read_jsonl(home(root) / "reviewed.jsonl").records if isinstance(r.get("item"), str)}


@dataclass(frozen=True)
class Item:
    kind: str  #: "draft" (a note to promote or discard) or "person" (a held other-person fact)
    item: str  #: what marks it reviewed: the note's vault path, or the held fact's claim key
    title: str
    claim: str | None
    vault: str | None
    sessions: int
    asserted_by: str | None
    last_ts: str

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def items(root: Path, *, limit: int = DIGEST_SIZE) -> list[Item]:
    """The digest: unreviewed drafts, most-reinforced first, then held person facts."""
    seen = evidence(root)
    done = _reviewed(root)
    drafts: dict[str, Item] = {}
    for rec in read_jsonl(home(root) / "ledger.jsonl").records:
        path = rec.get("path")
        if rec.get("action") not in ("created", "updated") or not isinstance(path, str) or path in done:
            continue
        sessions = len(seen.get(rec.get("key"), ()))
        prior = drafts.get(path)
        user = rec.get("asserted_by") == "user" or bool(prior and prior.asserted_by == "user")
        drafts[path] = Item("draft", path, rec.get("title") or path, rec.get("claim"), rec.get("vault"),
                            max(sessions, prior.sessions if prior else 0), "user" if user else rec.get("asserted_by"),
                            max(rec.get("ts") or "", prior.last_ts if prior else ""))
    newest = sorted(drafts.values(), key=lambda i: i.last_ts, reverse=True)  # stable: the tiebreak below
    ranked = sorted(newest, key=lambda i: (-i.sessions, i.asserted_by != "user"))
    people: dict[str, Item] = {}
    for rec in read_jsonl(home(root) / "held.jsonl").records:
        key, block = rec.get("key"), rec.get("block") if isinstance(rec.get("block"), dict) else {}
        if not isinstance(key, str) or key in done:
            continue
        people[key] = Item("person", key, (block.get("subject_hint") or {}).get("name") or "person fact",
                           block.get("claim"), None, len(seen.get(key, ())), block.get("asserted_by"),
                           rec.get("ts") or "")
    return (ranked + sorted(people.values(), key=lambda i: i.last_ts, reverse=True))[:limit]


def mark_reviewed(root: Path, item: str, *, outcome: str) -> None:
    """Take ``item`` (a note path or a held fact's key) out of the digest, recording what the person did."""
    if outcome not in ("promoted", "discarded", "kept"):
        raise ValueError(f"invalid outcome: {outcome!r}")
    append_jsonl(ensure_dir(home(root)) / "reviewed.jsonl", {"ts": now_ts(), "item": item, "outcome": outcome},
                 durable=False)
    write_review_line(root)


def review_line(root: Path) -> str:
    """SessionStart's line about the digest, or ``""`` when there's nothing to review."""
    pending = items(root, limit=10**6)
    if not pending:
        return ""
    drafts = sum(1 for i in pending if i.kind == "draft")
    people = len(pending) - drafts
    reinforced = sum(1 for i in pending if i.kind == "draft" and i.sessions >= 2)
    parts = [f"{drafts} draft(s)" + (f", {reinforced} seen in 2+ sessions" if reinforced else "")]
    if people:
        parts.append(f"{people} person fact(s)")
    return f"to review: {'; '.join(parts)} (/claudna:capture --review)"


def write_review_line(root: Path) -> None:
    line = review_line(root)
    path = ensure_dir(home(root)) / "review.txt"
    path.write_text(line + "\n" if line else "", encoding="utf-8")
