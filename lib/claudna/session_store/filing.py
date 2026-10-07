"""Writing one harvested block to the vault: per claim, or filed under its subject (#200 §4).

Every block becomes one or two writes through the ``claudron`` door, each
handed to ``record`` as it lands, except a new subject's, which waits for its
first fact: a ledger line must name a claim its note holds (a subject whose
fact was refused stays empty, and out of the digest, until one lands). :func:`per_claim` and
:func:`file_block` say what became of the block: ``created``, ``filed``,
``known`` or ``rejected``.

**Per claim** (any engine): one draft note per claim, ``(unverified) <subject>: <claim>``.

**Filed under its subject** (an engine with :data:`FILING_CAPS`, Claudron ≥ 0.7.1), no model in the loop:

* ``claudron resolve`` the block's subject, by its name, its aliases and the
  bannered subject title, within the session's project.
* **Every exact match is a subject note harvest wrote** (a session draft
  tagged :data:`SUBJECT_TAG`): the claim is appended to it as a fact
  (``amend append_fact``, evidence ``session:<sid>:<seg>``, ``expect_trust:
  external``, so a note a person promoted meanwhile is refused, not written).
  A replay writes nothing; the same fact from another session adds only its
  evidence.
* **Another note is an exact match** (reviewed, authored, a web capture):
  per claim. Harvest never edits a note it didn't write; that would launder
  unreviewed text into reviewed memory.
* **No exact match:** a new subject draft, then the fact appended to it.

Whatever Claudron declines (dedup routing the new subject elsewhere, an
amend it refuses) falls back to per claim, whose own answer stands: one odd
block never stops a run. What waits for the plan model (spec §7.2):
supersede, merge, the new-subject threshold, ambiguity parking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from claudna.redact import redact_strings

from . import claudron
from . import events as ev

RUN_CAP = "runs"
#: Claudron ≥ 0.8 files a block under its memory home's own type (#200 §2) rather than ``knowledge``.
HOMES_CAP = "memory-homes"
#: Where a fact goes in each home when the block's ``section_hint`` names none of the home's sections.
#: Placement is clauDNA's judgment (Claudron files where it is told): the home's section for facts.
HOME_SECTIONS = {
    "entity": ("Summary", "Facts", "Behavior & gotchas", "Operating it", "Open questions"),
    "concept": ("Definition", "Why it matters", "Examples", "Related"),
    "project": ("Goal", "Status", "Current state", "Timeline", "Open threads", "Decisions"),
    "decision": ("Context", "Decision", "Rationale", "Alternatives"),
    "practice": ("When", "What", "Why", "Exceptions"),
}
HOME_DEFAULT_SECTION = {"entity": "Facts", "concept": "Definition", "project": "Current state",
                        "decision": "Context", "practice": "What"}
TRUST_CAP = "trust-aware-reads"  #: makes ``source_type: session`` both accepted and withheld (Claudron#200 §1)
#: What filing needs: the 0.7 pipes, trust-aware reads (a subject draft is ``source_type: session``), and
#: 0.7.1's ``subject-filing`` (``exact``, ``--project``, ``--alias``, ``expect_trust``, the refusal envelope).
FILING_CAPS = frozenset({TRUST_CAP, "subjects", "amend", RUN_CAP, "subject-filing"})
HARVEST_TAG = "origin:session-harvest"
SUBJECT_TAG = "harvest:subject"  #: only subject notes carry it, so a per-claim draft is never taken for one
#: Prefixed to every draft's title, so any view that lists it — Claudron's own SessionStart brief
#: included — shows it as unreviewed (spec §7.2's banner; #373 review, M4).
DRAFT_BANNER = "(unverified) "
DEFAULT_SECTION = "Facts"
#: What Claudron's fact format reads as structure (amend.py ``_one_line``): a claim carrying one goes per claim.
FACT_MARKERS = ("<!--", "-->")

Record = Callable[[dict], None]


@dataclass(frozen=True)
class Target:
    """Where a session's blocks go: its vault and project, the run, and the capture door."""

    cwd: str | None
    env: Mapping[str, str]
    vault: str | None
    project: str | None
    run_id: str | None
    capture: Callable[..., dict]
    homes: bool = False  #: the engine declares HOMES_CAP: a note's type is its memory home


def short_title(text: str, limit: int = 100) -> str:
    """``text`` cut at a word boundary to ``limit`` characters, with an ellipsis when cut."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def one_line(text: object) -> str:
    """``text`` as one printable line: whitespace folded, control characters (a NUL) dropped."""
    return "".join(ch for ch in " ".join(str(text or "").split()) if ch.isprintable())


def evidence_ref(sid: str, index: int, agent_cli: str) -> str:
    """Where a harvested claim came from, as a ``source_url`` and an evidence ref.

    ``session:<sid>:<seg>`` for a Claude Code session, byte-identical to every ref written before 0.27,
    and ``session:<agent_cli>/<sid>:<seg>`` for any other agent CLI (Claudlobby#2145 F9, mirroring F2):
    ids from two vendors must not collide in one vault. Claudron treats the string as opaque.
    """
    if agent_cli == ev.DEFAULT_AGENT_CLI:
        return f"session:{sid}:{index}"
    return f"session:{agent_cli}/{sid}:{index}"


def subject_title(name: str) -> str:
    """The title of the subject note harvest writes for ``name`` (whole: two long names must not collide)."""
    return DRAFT_BANNER + one_line(name)


def section_of(block: dict, home: str | None = None) -> str:
    """The section a block's fact goes under: its ``section_hint`` when the fact format can carry it.

    ``home`` is the memory home of the NOTE the fact goes into (not the block's: a concept block can
    land in an entity subject). In a home, only one of its own sections: a hint naming one
    (case-insensitively), else the home's section for facts. A home's sections are fixed (#200 §2),
    so a model's invented heading never becomes one.
    """
    hint = one_line(str(block.get("section_hint") or "").replace("#", " "))
    if home in HOME_SECTIONS:
        own = {s.lower(): s for s in HOME_SECTIONS[home]}
        return own.get(hint.lower(), HOME_DEFAULT_SECTION[home])
    if not hint or hint == "History" or any(m in hint for m in FACT_MARKERS):
        return DEFAULT_SECTION  # History holds superseded facts; Claudron refuses a write into it
    return hint


def per_claim(finding: dict, target: Target, record: Record) -> str:
    """One per-claim draft; the block's outcome."""
    answer = {**target.capture(finding, target.cwd, target.env, target.vault, run_id=target.run_id),
              "title": finding["title"]}
    record(answer)
    action = answer["action"]
    return "created" if action in ("created", "updated") else "rejected" if action == "rejected" else "known"


def _is_subject_draft(candidate: dict) -> bool:
    tags = candidate.get("tags") if isinstance(candidate.get("tags"), list) else []
    return (candidate.get("trust") == "external" and candidate.get("source_type") == "session"
            and SUBJECT_TAG in tags)


def _subject_finding(block: dict, finding: dict, title: str, ref: str) -> dict:
    subject = {
        "type": finding["type"],
        "title": title,
        # No subject name here: it is model-written, and a body line is where it could pass for structure.
        # The ref makes each body unique: Claudron's dedup matches identical bodies vault-wide, so one subject
        # left without facts (its amend refused) would otherwise take in every new subject after it.
        "body": "Facts filed by harvest from session summaries. Unreviewed: check each fact against its "
                f"evidence before relying on it. First filed from {ref}.",
        "tags": sorted({f"home:{block['home']}", HARVEST_TAG, SUBJECT_TAG}),
        "source_type": "session",
        "source_url": ref,
    }
    if finding.get("project"):
        subject["project"] = finding["project"]
    if finding.get("kind"):
        subject["kind"] = finding["kind"]
    return subject


def file_block(block: dict, finding: dict, *, ref: str, target: Target, record: Record) -> str:
    """File one block under its subject (see the module doc); the block's outcome.

    ``finding`` is the block's per-claim draft (``harvest.finding_of``), the
    fallback whenever filing under a subject isn't safe or Claudron declines it.
    """
    block = redact_strings(block)  # names reach argv: redacted like everything else that leaves (defense in depth)
    hint = block["subject_hint"]
    name, claim = one_line(hint["name"]), one_line(block["claim"])
    if not name or not claim or any(m in claim for m in FACT_MARKERS):
        return per_claim(finding, target, record)
    title = subject_title(name)
    names = list(dict.fromkeys(n for n in [name, *(one_line(a) for a in hint.get("aliases", [])), title] if n))
    exact = [c for c in claudron.resolve(names, project=target.project, cwd=target.cwd, env=target.env,
                                         vault=target.vault) if c.get("exact")]
    if exact:
        if not all(_is_subject_draft(c) for c in exact):
            return per_claim(finding, target, record)  # a note harvest didn't write owns the name
        created = None
        path, title = exact[0].get("path"), exact[0].get("title") or title
        note_type = exact[0].get("type") or finding["type"]  # the section is the target note's home's
    else:
        answer = target.capture(_subject_finding(block, finding, title, ref), target.cwd, target.env, target.vault,
                                run_id=target.run_id)
        if answer["action"] != "created" or not answer.get("path"):
            return per_claim(finding, target, record)  # dedup routed it elsewhere: the claim's answer decides
        created = {**answer, "title": title}
        path, note_type = answer["path"], finding["type"]
    request = {"note": path, "op": "append_fact", "section": section_of(block, note_type if target.homes else None),
               "fact": claim,
               "evidence": {"ref": ref, "asserted_by": block["asserted_by"]}, "expect_trust": "external"}
    answer = claudron.amend(request, target.cwd, target.env, target.vault, run_id=target.run_id)
    if answer["action"] == "rejected":
        return per_claim(finding, target, record)  # a subject just created stays empty, and out of the digest
    if created:
        record(created)  # only now: a ledger line names a claim the note holds
    if answer["action"] == "updated":
        record({**answer, "path": answer["path"] or path, "title": title})
    return "created" if created else "filed" if answer["action"] == "updated" else "known"
