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

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from .events import now_ts
from .fsio import append_jsonl, ensure_dir, read_jsonl
from .rollup import dedup_key

DIGEST_SIZE = 5


def home(root: Path) -> Path:
    return root / "harvest"


def claim_key(block: dict) -> str:
    """What makes two blocks "the same claim": home + subject + claim, normalized (the rollup's rule)."""
    return dedup_key("blocks", block)


def person_item(key: str) -> str:
    """A held fact's digest id: its claim key joins fields with ``\\x1f``, which no shell argument carries."""
    return "person:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def record_capture(root: Path, *, sid: str, seg: int, block: dict, title: str, action: str,
                   path: str | None, vault: str | None) -> None:
    """One ledger line for one ``claudron capture`` answer: its vault-relative path and the vault it is in.

    Harvest's capture adapter makes the path relative to the root Claudron
    reports, so the digest's ``item``/``vault`` are exactly what ``claudron
    --vault <vault> promote <item>`` takes.
    """
    append_jsonl(ensure_dir(home(root)) / "ledger.jsonl", {
        "ts": now_ts(), "sid": sid, "seg": seg, "key": claim_key(block), "title": title, "claim": block.get("claim"),
        "asserted_by": block.get("asserted_by"), "action": action, "path": path, "vault": vault,
    }, durable=False)


def record_held(root: Path, *, sid: str, seg: int, block: dict, reason: str = "person") -> None:
    """One ``held.jsonl`` line for a block harvest keeps back for a person (an other-person fact)."""
    append_jsonl(ensure_dir(home(root)) / "held.jsonl", {
        "ts": now_ts(), "sid": sid, "seg": seg, "reason": reason, "key": claim_key(block), "block": block,
    }, durable=False)


@dataclass(frozen=True)
class Item:
    kind: str  #: "draft" (a note to promote or discard) or "person" (a held other-person fact)
    item: str  #: what marks it reviewed: the note's vault path, or the held fact's :func:`person_item` id
    title: str
    claim: str | None
    vault: str | None
    sessions: int
    asserted_by: str | None
    last_ts: str

    def as_dict(self) -> dict:
        return asdict(self)


def _records(root: Path) -> tuple[list[dict], list[dict], set[tuple[str | None, str]]]:
    """``(ledger, held, reviewed (vault, item) pairs)``, each file read once."""
    h = home(root)
    reviewed = {(r.get("vault"), r["item"]) for r in read_jsonl(h / "reviewed.jsonl").records
                if isinstance(r.get("item"), str)}
    return read_jsonl(h / "ledger.jsonl").records, read_jsonl(h / "held.jsonl").records, reviewed


def evidence(root: Path, ledger: list[dict] | None = None, held: list[dict] | None = None) -> dict[str, set[str]]:
    """``claim key -> the sessions that asserted it`` (captures and held person facts alike)."""
    if ledger is None or held is None:
        ledger, held, _ = _records(root)
    out: dict[str, set[str]] = {}
    for rec in [*ledger, *held]:
        if isinstance(rec.get("key"), str) and isinstance(rec.get("sid"), str):
            out.setdefault(rec["key"], set()).add(rec["sid"])
    return out


def items(root: Path, *, limit: int | None = DIGEST_SIZE) -> list[Item]:
    """The digest: unreviewed drafts, most-reinforced first, then held person facts."""
    ledger, held, done = _records(root)
    seen = evidence(root, ledger, held)
    drafts: dict[tuple[str | None, str], dict] = {}
    for rec in ledger:
        path, vault = rec.get("path"), rec.get("vault")
        if rec.get("action") not in ("created", "updated") or not isinstance(path, str) or (vault, path) in done:
            continue  # a note is (vault, path): the same relative path in two vaults is two notes
        d = drafts.setdefault((vault, path), {"title": rec.get("title") or path, "claim": rec.get("claim"),
                                              "vault": vault, "sessions": 0, "user": False, "last_ts": ""})
        d["sessions"] = max(d["sessions"], len(seen.get(rec.get("key"), ())))
        d["user"] = d["user"] or rec.get("asserted_by") == "user"
        d["last_ts"] = max(d["last_ts"], rec.get("ts") or "")
    newest = sorted(drafts.items(), key=lambda kv: kv[1]["last_ts"], reverse=True)  # stable: the tiebreak below
    ranked = [Item("draft", path, d["title"], d["claim"], d["vault"], d["sessions"],
                   "user" if d["user"] else "agent", d["last_ts"])
              for (_, path), d in sorted(newest, key=lambda kv: (-kv[1]["sessions"], not kv[1]["user"]))]
    people: dict[str, Item] = {}
    for rec in held:
        key, block = rec.get("key"), rec.get("block") if isinstance(rec.get("block"), dict) else {}
        if not isinstance(key, str) or (None, item := person_item(key)) in done:
            continue
        name = (block.get("subject_hint") or {}).get("name") or "person fact"
        people[key] = Item("person", item, name, block.get("claim"), None, len(seen.get(key, ())),
                           block.get("asserted_by"), rec.get("ts") or "")
    found = ranked + sorted(people.values(), key=lambda i: i.last_ts, reverse=True)
    return found if limit is None else found[:limit]


def mark_reviewed(root: Path, item: str, *, outcome: str, vault: str | None = None) -> None:
    """Take ``item`` out of the digest, recording what the person did.

    ``item`` and ``vault`` are the digest item's own fields: a note's
    vault-relative path and its vault, or a held fact's ``person:`` id (no
    vault).
    """
    if outcome not in ("promoted", "discarded", "kept"):
        raise ValueError(f"invalid outcome: {outcome!r}")
    append_jsonl(ensure_dir(home(root)) / "reviewed.jsonl",
                 {"ts": now_ts(), "item": item, "vault": vault, "outcome": outcome}, durable=False)
    write_review_line(root)


def review_line(root: Path) -> str:
    """SessionStart's line about the digest, or ``""`` when there's nothing to review."""
    pending = items(root, limit=None)
    drafts = [i for i in pending if i.kind == "draft"]
    if not pending:
        return ""
    reinforced = sum(1 for i in drafts if i.sessions >= 2)
    parts = [f"{len(drafts)} draft(s)" + (f", {reinforced} seen in 2+ sessions" if reinforced else "")]
    if len(pending) > len(drafts):
        parts.append(f"{len(pending) - len(drafts)} person fact(s)")
    return f"to review: {'; '.join(parts)} (/claudna:capture --review)"


def write_review_line(root: Path) -> None:
    line = review_line(root)
    path = ensure_dir(home(root)) / "review.txt"
    path.write_text(line + "\n" if line else "", encoding="utf-8")
