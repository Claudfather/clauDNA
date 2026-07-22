---
title: "[plan] D2 — Closure-triage ledger: reference payloads inside clauDNA skills"
type: plan
status: draft
owner: chris
created: 2026-07-22
updated: 2026-07-22
tags: [planning, boundary, claudron, knowledge, triage, closure]
repos: clauDNA
links:
---

# D2 — Closure-triage ledger (clauDNA)

The clauDNA-side deliverable of **phase D2** of the Claudron·clauDNA·Claudlobby boundary
re-architecture program (Claudron repo, `documentation/plans/2026-07-20-boundary-rearchitecture/07-d2-closure-triage.md`;
boundary spec `documentation/plans/2026-07-20-claudfather-boundary-separation.md` §10.3 and §10.5.5).

This file is the **ledger** — the durable artifact of D2. It adopts the boundary spec §10.5.5
inventory of skill-embedded reference payloads, records a verdict + one-line rationale + a named
promotion signal for each, and states the move protocol (deferred by default). The authoring rule
it codifies also lives in [`SKILL_CONTRACT.md` §7](../../SKILL_CONTRACT.md) (the binding contract a
skill author reads) and, as placement guidance at the seam, in [`skills/CLAUDE.md`](../../skills/CLAUDE.md).

## The rule (Q-closure)

> **Reference that tracks the world belongs in the vault; reference that tracks your method belongs
> in your skill.**

A reference payload embedded in a skill is one of two things:

- **Closure** — it versions with the *procedure*. It is the method's own rubric, checklist, judgment
  criteria, or the vendor-CLI operands the steps invoke. It changes when *you* change how the skill
  works. **It stays with the skill.**
- **Library** — it versions with the *world or an external SSOT*. It is a domain fact, a service
  inventory, a schema table: it changes when the world changes, independent of your method. **It is
  referential** — move it to a Claudron vault note (typed, deduped) or keep it as a rendered copy
  behind a CI drift gate (the [`skills/_shared/output-guide.md`](../../skills/_shared/output-guide.md)
  §3 pattern, gated by [`scripts/check_schema_drift.py`](../../scripts/check_schema_drift.py)).

## The core discipline: closure-stays is the default; moves are signal-gated

The default verdict for every inventoried payload is **closure — stays**. A payload MOVES only when
its promotion signal has actually fired for it. **No unconditional move step exists**, and no move is
scheduled here — moving rubric content out of a skill breaks the skill for a purity win the boundary
does not ask for. Because the default is no-move, a *missed* signal costs nothing; the observation
channel can be imperfect.

**The promotion signal, named honestly.** A payload's signal fires when either:

1. **Session evidence** — the payload is *consulted outside its skill's execution* (surfaced in a
   session transcript or handoff: an agent pulls the content up while doing something other than
   running that skill), or
2. **Capture-dedup hit** — an agent tries to `/claudna:capture` content that a skill already embeds,
   and the engine's dedup names that skill's payload.

Either is a concrete, after-the-fact observation that the content is being used *referentially*, not
just as the method's closure. Neither has fired for any payload below.

## Ledger

Payload classes are the §10.5.5 inventory, verified against `main` (post-v0.17.0). All verdicts are
**closure — stays**.

| # | Payload (files · lines) | Verdict | Why it is closure (versions with the *method*) | Promotion signal (what would flip it to *library*) |
|---|---|---|---|---|
| 1 | `skills/audit/access-path/scan-categories.md` · 1 file, 205 ln — "Correct Layer Guidance" (which cross-cutting concern belongs at which layer) + per-concern grep rubric | **closure — stays** | The layer-guidance table is *the lens's own judgment criterion* — the file states it is "the key distinction the audit makes." It versions when the access-path audit method changes, not when any external architecture SSOT does. **The most consultable payload here** — the named first cut *if* a signal ever fires. | The layer-guidance table cited in a session that is **not** running `/claudna:audit access-path` (e.g. an architecture-design discussion pulls it up), **or** a `/claudna:capture` dedup hit on the "which concern at which layer" content. |
| 2 | `skills/audit/security/scan-categories.md` · 1 file, 121 ln — scanner/tool catalog per security category | **closure — stays** | The catalog is the security lens's scan rubric — the tools and patterns *this audit runs*. It tracks the method's coverage, not an external vulnerability SSOT. | The scanner catalog consulted outside a `/claudna:audit security` run, **or** a capture-dedup hit on the tool list. |
| 3 | `skills/dbt/SKILL.md` "Quick Commands" · vendor cheat-sheet (dbt CLI verbs/flags) | **closure — stays** | Operands of the procedure: the exact `dbt build/test/compile` invocations the skill's steps run. The vendor surface is versioned by **dbt**, not an ecosystem SSOT; it belongs with the steps that call it. | The command cheat-sheet consulted outside a `/claudna:dbt` invocation, **or** a capture-dedup hit on the dbt command list. |
| 4 | Infra verb depth files · 13 files, 77–187 ln — `vercel/{deploy,logs,status}.md`, `modal/{deploy,logs,status}.md`, `railway/{deploy,logs,status}.md`, `neon/{branch,info,query}.md` + `neon/SKILL.md` (per `skills/_shared/infra-cli-contract.md`) | **closure — stays** | Vendor-CLI flag reference interleaved with per-verb procedure. Each vendor's CLI surface is versioned by **that vendor**, not by an ecosystem SSOT; the flags are the operands the engine's verb dispatch invokes. Splitting them from the procedure would strand the steps. | A vendor's flag reference consulted outside its tool's skill execution, **or** a capture-dedup hit on the vendor CLI flags. (Low likelihood — the vendor owns the surface.) |
| 5 | `skills/ironclad/lenses/*.md` · 6 files, 127–270 ln — `align-to-mission`, `cost-benefit`, `extension-check`, `first-principles`, `plan-health-audit`, `precedent-check` | **closure — stays** | Mostly method, with embedded checklists that *are* each lens's evaluation procedure. They version when the ironclad method changes. Pure closure. | A lens's embedded checklist consulted outside an `/claudna:ironclad` run, **or** a capture-dedup hit. (Very low — this is method, not world-truth.) |
| 6 | `skills/init-project/references/*.md` · 2 files — `CHANGELOG_TEMPLATE.md`, `CLAUDE_MD_TEMPLATE.md` | **closure — stays** | Stamped artifacts: the templates `/claudna:init-project` writes into a new project. They version with the skill that stamps them (change the scaffold → change the template), not with any external SSOT. | A template reused/consulted outside `/claudna:init-project`, **or** a capture-dedup hit on template content. (Very low — these are outputs of the skill.) |

**Verdict summary: 6 payload classes (~24 files) inventoried · 6 closure-stays · 0 library-moves · 0 promotion signals fired.**

## Rendered copies of an external SSOT: the drift-gate assertion

Per D2 step 3, any payload kept as a *rendered copy of an external SSOT* must carry an
output-guide-§3-style CI drift gate. **Audit result: there is exactly one such rendered copy in the
repo, and it is already gated.**

- `skills/_shared/output-guide.md` §3 renders Claudron's `SCHEMA.md` frontmatter vocabulary, stamped
  with the source commit, gated by `scripts/check_schema_drift.py` (wired into
  `scripts/validate-skills.py`; shipped in v0.16.0 #199). This is the R3 model pattern, **not** a D2
  triage target — it is already resolved and is left untouched.

**None of the six inventoried payloads above is a rendered copy of an external SSOT** — every one is
method-coupled closure (a rubric, vendor operands, or a stamped artifact), so **no new drift gate is
warranted.** If a future payload's signal fires and it is promoted as a *rendered copy* rather than a
moved note, it inherits the output-guide-§3 gate pattern at that time.

## Move protocol (deferred — no move is performed by D2)

When (and only when) a row's promotion signal fires for a specific payload, execute a **single-payload,
single-PR** move:

1. **Capture** the payload to the Claudron vault via `/claudna:capture` — typed (`type: knowledge`),
   deduped by the engine, tagged so recall surfaces it.
2. **Replace** the in-skill content with a pointer line to the vault note (a `/claudna:recall`-able
   reference), never a fork.
3. **Verify** the skill's smoke invocation still matches its pre-move behavior, and skill-contract CI
   (`python3 scripts/validate-skills.py`) stays green — no dangling pointer, no broken procedure.

Do **not** fork the content into both homes. If a payload is kept as a rendered copy instead of moved,
it gets the drift gate (above); a bare fork is a contract violation (register rule R3).

## Verification (D2 checklist)

- [x] The ledger exists with a verdict + one-line rationale + a named promotion signal per inventoried
      payload (the six rows above).
- [x] No signal has fired → no move is performed (default posture: closure-stays).
- [x] The Q-closure rule is stated in the authoring guide (`SKILL_CONTRACT.md` §7).
- [x] Rendered-copy audit: exactly one (`output-guide.md` §3), already gated; no new gate warranted.
- [x] `python3 scripts/validate-skills.py` green (this change adds documentation + one contract
      paragraph; no skill body or frontmatter is moved).
