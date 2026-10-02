"""Subject filing: one harvested block into the vault through Claudron's pipes (#200 §4, the deterministic slice).

Harvest's thin slice writes one draft note per claim. When the engine declares
``subjects``, ``amend`` and ``runs`` (Claudron ≥ 0.7), a block is filed under
its subject instead, with no model in the loop:

* ``claudron resolve`` the block's ``subject_hint``: its name, its aliases, and
  the bannered title a subject note harvest wrote carries. Only a note whose
  title or alias *is* one of those names counts as the subject.
* **An exact match on a subject note harvest wrote** (an external draft tagged
  :data:`HARVEST_TAG`): ``amend append_fact`` into it, with the session and
  segment as the evidence ref. A replayed fact writes nothing, and the same fact
  from another session adds only its evidence (recurrence counts).
* **An exact match on any other note** (trusted, an authored draft, a web
  capture): a per-claim draft, as before. Harvest never edits a note it didn't
  write: that would launder unreviewed text into reviewed memory.
* **No exact match**: a new subject draft, then the fact appended to it. If
  Claudron's dedup routes the new subject elsewhere, the claim falls back to a
  per-claim draft, whose own dedup answer stands.

Every write carries the run id, so ``claudron revert-run <id>`` undoes a whole
run. What this slice still leaves to the plan model (spec §7.2): supersede,
merge, the new-subject threshold, and ambiguity parking.
"""

from __future__ import annotations

from typing import Callable, Mapping

from claudna.redact import redact_strings

from . import claudron

#: What filing needs from the engine; without all three, harvest writes per-claim drafts.
FILING_CAPS = frozenset({"subjects", "amend", "runs"})
HARVEST_TAG = "origin:session-harvest"
#: Prefixed to every draft's title, so any view that lists it — Claudron's own SessionStart brief
#: included — shows it as unreviewed (spec §7.2's banner; #373 review, M4).
DRAFT_BANNER = "(unverified) "
DEFAULT_SECTION = "Facts"
#: Text the fact format reads as structure (Claudron SCHEMA.md §Facts); a claim carrying one is filed per-claim.
FACT_MARKERS = ("<!--", "-->")

Capture = Callable[..., dict]


def short_title(text: str, limit: int = 100) -> str:
    """``text`` cut at a word boundary to ``limit`` characters, with an ellipsis when cut."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def evidence_ref(sid: str, index: int) -> str:
    """Where a harvested claim came from, as a ``source_url`` and an evidence ref: ``session:<sid>:<seg>``."""
    return f"session:{sid}:{index}"


def subject_title(name: str) -> str:
    """The title of the subject note harvest writes for ``name``."""
    return DRAFT_BANNER + short_title(name)


def section_of(block: dict) -> str:
    """The section a block's fact goes under: its ``section_hint`` when the fact format can carry it."""
    hint = " ".join(str(block.get("section_hint") or "").replace("#", " ").split())
    if not hint or hint == "History" or any(m in hint for m in FACT_MARKERS):
        return DEFAULT_SECTION  # History holds superseded facts; Claudron refuses a write into it
    return hint


def _fold(name: object) -> str:
    return " ".join(str(name).lower().split())


def _names_exactly(candidate: dict, names: list[str]) -> bool:
    """Does the note's title or one of its aliases equal one of ``names`` (case- and space-folded)?

    Checked here, not read off ``match_type``: ``resolve`` labels a fuzzy title
    hit ``title`` too, so a note that merely shares a word ("(unverified)") would
    pass for the subject itself.
    """
    wanted = {_fold(n) for n in names}
    aliases = candidate.get("aliases") if isinstance(candidate.get("aliases"), list) else []
    return any(_fold(n) in wanted for n in [candidate.get("title", ""), *aliases])


def _is_harvest_draft(candidate: dict) -> bool:
    tags = candidate.get("tags") if isinstance(candidate.get("tags"), list) else []
    return candidate.get("trust") == "external" and HARVEST_TAG in tags


def _subject_finding(block: dict, finding: dict, ref: str) -> dict:
    name = block["subject_hint"]["name"]
    subject = {
        "type": finding["type"],
        "title": subject_title(name),
        "body": f"Facts about {name}, filed by harvest from session summaries. Unreviewed: check each fact "
                "against its evidence before relying on it.",
        "tags": sorted({f"home:{block['home']}", HARVEST_TAG}),
        "source_type": "session",
        "source_url": ref,
    }
    if finding.get("project"):
        subject["project"] = finding["project"]
    return redact_strings(subject)


def file_block(block: dict, finding: dict, *, sid: str, index: int, cwd: str | None, env: Mapping[str, str],
               vault: str | None, run_id: str, capture: Capture) -> dict:
    """File one block; ``{"action", "path", "vault", "title", "amended"}``, in capture's action vocabulary.

    ``finding`` is the block's per-claim draft (``harvest.finding_of``), written
    when filing under a subject isn't safe. An amend into an existing subject
    answers ``updated`` (a fact or its evidence added) or ``unchanged``, with
    ``amended`` set; a new subject answers ``created``.
    """
    def per_claim() -> dict:
        return {**capture(finding, cwd, env, vault, run_id=run_id), "title": finding["title"]}

    if any(m in block["claim"] for m in FACT_MARKERS):
        return per_claim()
    hint = block["subject_hint"]
    title = subject_title(hint["name"])
    names = [hint["name"], *hint.get("aliases", []), title]
    candidates = claudron.resolve(names[0], aliases=names[1:], note_type=finding["type"], cwd=cwd, env=env,
                                  vault=vault)
    top = candidates[0] if candidates else None  # exact matches rank first, so only the top can be one
    ref = evidence_ref(sid, index)
    if top and _names_exactly(top, names):
        if not _is_harvest_draft(top):
            return per_claim()
        path, action, title = top.get("path"), None, top.get("title") or title
    else:
        created = capture(_subject_finding(block, finding, ref), cwd, env, vault, run_id=run_id)
        if created["action"] != "created" or not created.get("path"):
            return per_claim()  # dedup routed the subject elsewhere: the claim's own answer decides
        path, action = created["path"], "created"
    request = redact_strings({"note": path, "op": "append_fact", "section": section_of(block),
                              "fact": block["claim"], "evidence": {"ref": ref, "asserted_by": block["asserted_by"]}})
    answer = claudron.amend(request, cwd, env, vault, run_id=run_id)
    return {"action": action or answer["action"], "path": answer["path"] or path, "vault": answer["vault"],
            "title": title, "amended": action is None}
