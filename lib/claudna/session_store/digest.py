"""The promotion digest (spec §7.2, phase 5): which drafts a person should look at first.

Harvest writes drafts; only a person promotes them (``draft → verified``).
Harvest records every capture in ``<root>/harvest/ledger.jsonl``: the session
and segment, the note's vault-relative path, the vault, who asserted the claim,
and a **claim key** (the rollup's dedup key: home + subject + claim,
normalized). Everything stored is redacted, and redacted again on read (a line
from before a newer pattern). This module reads that ledger:

* **Evidence** is the number of distinct sessions that asserted the same claim
  key in the same vault. It is §7.2's "recurring across ≥ 2 sessions" signal.
* **The digest** is at most :data:`DIGEST_SIZE` items: draft notes not yet
  reviewed, the most-reinforced first, a user-asserted claim ahead of an
  agent's on a tie, then the most recent; and the other-person facts harvest
  held back (``held.jsonl``), of which one always shows.
* **Review** (``/claudna:capture --review``) is a person's choice per item.
  The mechanical half is deterministic: ``digest --promote`` runs ``claudron
  promote`` itself and marks the item done only when the envelope says so;
  ``digest --done`` records a discard or a captured person fact, in
  ``reviewed.jsonl``. Nothing promotes without a person's pick.

``review.txt`` holds the one line SessionStart shows, rewritten after every
harvest run and every review.

Blocked on Claudron#200 and not here: subject resolution, section-targeted
writes, risk tiers, the inbox and ambiguous queues, and ``revert-run``.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from claudna.redact import redact_strings
from claudna.screen import tripped

from .events import now_ts
from .fsio import append_jsonl, atomic_write_text, ensure_dir, read_jsonl
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
    key = claim_key(block)  # keyed on the claim as summarized, so the same claim keys alike however redaction evolves
    block, title = redact_strings(block), redact_strings(title)  # the ledger holds what the vault got (#387 B2)
    append_jsonl(ensure_dir(home(root)) / "ledger.jsonl", {
        "ts": now_ts(), "sid": sid, "seg": seg, "key": key, "title": title, "claim": block.get("claim"),
        "asserted_by": block.get("asserted_by"), "action": action, "path": path, "vault": vault,
    })  # fsynced: harvest acks right after, and the ack is durable — a crash must not keep it and lose this


def record_held(root: Path, *, sid: str, seg: int, block: dict, vault: str | None = None,
                reason: str = "person") -> None:
    """One ``held.jsonl`` line for a block harvest keeps back for a person (an other-person fact), redacted."""
    append_jsonl(ensure_dir(home(root)) / "held.jsonl", {
        "ts": now_ts(), "sid": sid, "seg": seg, "reason": reason, "key": claim_key(block), "vault": vault,
        "block": redact_strings(block),
    })


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
    held = []
    for rec in read_jsonl(h / "held.jsonl").records:
        block = rec.get("block") if isinstance(rec.get("block"), dict) else {}
        if not isinstance(rec.get("key"), str) and block:  # 0.22 held lines carry no key: derive it
            rec = {**rec, "key": claim_key(block)}
        held.append(rec)
    return read_jsonl(h / "ledger.jsonl").records, held, reviewed


def evidence(root: Path, ledger: list[dict] | None = None,
             held: list[dict] | None = None) -> dict[tuple[str | None, str], set[str]]:
    """``(vault, claim key) -> the sessions that asserted it`` (captures and held person facts alike).

    Per vault: a claim recurring in vault A is no evidence for a draft in vault B.
    """
    if ledger is None or held is None:
        ledger, held, _ = _records(root)
    out: dict[tuple[str | None, str], set[str]] = {}
    for rec in [*ledger, *held]:
        if isinstance(rec.get("key"), str) and isinstance(rec.get("sid"), str):
            out.setdefault((rec.get("vault"), rec["key"]), set()).add(rec["sid"])
    return out


def items(root: Path, *, limit: int | None = DIGEST_SIZE) -> list[Item]:
    """The digest: unreviewed drafts, most-reinforced first, then held person facts — redacted as they leave.

    Redacted again here (a line written before a newer pattern, or by 0.22),
    and only what is returned: never every ledger line.
    """
    return [replace(i, title=redact_strings(i.title), claim=redact_strings(i.claim)) for i in _pending(root, limit)]


def _pending(root: Path, limit: int | None) -> list[Item]:
    """:func:`items` before the read-side redaction (counting needs no redaction)."""
    ledger, held, done = _records(root)
    seen = evidence(root, ledger, held)
    drafts: dict[tuple[str | None, str], dict] = {}
    for rec in ledger:
        path, vault = rec.get("path"), rec.get("vault")
        if rec.get("action") not in ("created", "updated") or not isinstance(path, str) or (vault, path) in done:
            continue  # a note is (vault, path): the same relative path in two vaults is two notes
        if tripped({"title": rec.get("title"), "claim": rec.get("claim")}):
            continue  # instruction-shaped (claudna.screen): never offered for promotion, however it got here
        d = drafts.setdefault((vault, path), {"title": rec.get("title") or path, "claim": rec.get("claim"),
                                              "vault": vault, "sessions": 0, "user": False, "last_ts": ""})
        d["sessions"] = max(d["sessions"], len(seen.get((vault, rec.get("key")), ())))
        d["user"] = d["user"] or rec.get("asserted_by") == "user"
        d["last_ts"] = max(d["last_ts"], rec.get("ts") or "")
    newest = sorted(drafts.items(), key=lambda kv: kv[1]["last_ts"], reverse=True)  # stable: the tiebreak below
    # Ranked by evidence, then newest. Not by asserted_by: the summarizing model picks that label, so text
    # planted in a transcript could claim "user" and climb the list (the hardening note, path 2).
    ranked = [Item("draft", path, d["title"], d["claim"], d["vault"], d["sessions"],
                   "user" if d["user"] else "agent", d["last_ts"])
              for (_, path), d in sorted(newest, key=lambda kv: -kv[1]["sessions"])]
    people: dict[str, Item] = {}
    for rec in held:
        key, block = rec.get("key"), rec.get("block") if isinstance(rec.get("block"), dict) else {}
        if not isinstance(key, str) or (None, item := person_item(key)) in done or tripped(block):
            continue
        name = (block.get("subject_hint") or {}).get("name") or "person fact"
        people[key] = Item("person", item, name, block.get("claim"), None,
                           len(seen.get((rec.get("vault"), key), ())), block.get("asserted_by"), rec.get("ts") or "")
    persons = sorted(people.values(), key=lambda i: i.last_ts, reverse=True)
    if limit is not None and limit > 0 and persons and len(ranked) >= limit:
        found = ranked[:limit - 1] + persons[:1]  # person facts are §7.2's high-risk items: one always shows
    else:
        found = ranked + persons if limit is None else (ranked + persons)[:limit]
    return found


def find(root: Path, item: str, vault: str | None) -> Item:
    """The digest item ``item`` in ``vault``; ``LookupError`` naming the ``--vault`` it is under when that's wrong."""
    pending = _pending(root, limit=None)  # matched on item and vault, which redaction never touches
    match = next((i for i in pending if (i.item, i.vault) == (item, vault)), None)
    if match is not None:
        return match
    vaults = sorted({"no vault (omit --vault)" if i.vault is None else f"--vault {i.vault}"
                     for i in pending if i.item == item})
    raise LookupError(f"no digest item {item!r} in vault {vault!r}" + (f"; it is under {', '.join(vaults)}" if vaults
                                                                        else ""))


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
    pending = _pending(root, limit=None)  # counted, never shown: no redaction pass
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
    atomic_write_text(ensure_dir(home(root)) / "review.txt", line + "\n" if line else "")
