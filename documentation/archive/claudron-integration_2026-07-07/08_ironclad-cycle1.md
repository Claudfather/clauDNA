---
title: "[review] Ironclad cycle 1 — panel record for the Claudron-integration epic"
type: review
status: completed
owner: chris
created: 2026-07-07
updated: 2026-07-07
tags: [ironclad, panel-record, claudron]
repos: clauDNA
links:
---

# Ironclad cycle 1 — panel record

Pre-publication hardening pass over the draft family (epic + 6 phase docs, as then
numbered P1–P6). Six lenses dispatched as parallel subagents per
`skills/ironclad/SKILL.md` Phase 4 (`extension-check` skipped — implementation-only);
`cost-benefit` retried once after an API failure (retry completed). Cycle 1 found
**4 Blockers, ~14 majors, ~20 minors**; all were folded before filing — the committed
docs are the post-fold family (restructured to P1–P7 + fork F6). Convergence per
ironclad's plan rule (0 open blockers AND all forks locked) is deliberately **not**
claimed: blockers are folded, but all six forks ship open — the epic Issue is the
ratification surface, and fork gates are phase-scoped (F3→P1, F1/F2/F5/F6→P4, F4→P7).

## Panel

| Lens | Severity | Headline |
|---|---|---|
| adversarial-review | critical | 4 blockers: P1 mechanically unsound (publish single-file vs audit families + Step 1b gate); P6-old capability regression hidden from the ratifier; stacking contract event-incomplete (SessionEnd) with an unobservable detection surface; concurrency hole (0.2.0 single-writer vs parallel-worktree house workflow). Counter-plan: ownership inversion. |
| first-principles | major | Track A should be independently ratifiable; permanent dual-path needs a bound (freeze, not sunset); SSOT sovereignty needs an escape hatch; F2/F5 are thin forks; P1 bundled gated+ungated work. |
| cost-benefit | major | P4-old undersized (resize or shed); P2-old (cheapest value, fixes today-broken seam) gated behind L-sized externally-gated P1; detection doc born one phase late; author-skill sweep undercounted (~8 not 3); per-phase ROI healthy, no cut candidates. |
| plan-health-audit | major | needs-work: F2/F4/F5 missing Context; `updated:` absent ×7; risk severity ungraded; P4-old gate cell missing the P1 edge; F5 markdown broken. 10/10 sections present; 62/62 criteria testable; 38/38 cross-refs resolve. |
| precedent-check | minor | #110 latent conflict needs a disposition, not a cross-link; disk-alias needs F4-doctrine scoping vs the no-stub precedent; missing overlaps #116/#159/#114/#192 (+#111/#41/#176); #106/#107 wait-condition needs the capability reading recorded; #36 close-out needs "engine-only by design"; stub residue (`repo-documentation-standard.md`). All evidence anchors verified accurate. |
| align-to-mission | minor | Zero misaligned phases; P7 semver vs the mission's major-version promise unaddressed; "materially smarter" never measured; stacking surface's stability-promise status unstated. |

## Fold ledger (finding → disposition)

| # | Finding (lens) | Folded as |
|---|---|---|
| B1 | publish can't route audit families; forge prose already contradicts the adapter (adversarial) | P1 rebuilt: family mode (per-doc loop, master presence-validation vs phase §4.1 gate), grep-derived ~8-skill sweep incl. forge prose fix; sized L honestly |
| B2 | notes/lessons removal = hidden capability regression + read-door gap + mission tension (adversarial) | Fork F4 rewritten with the full price; `read` verb added to P4 as parity precondition; adoption-evidence gate + named breakage channel; F4(b) kept live; capability reading of #106/#107 made an explicit ratification item |
| B3 | stacking claim false on SessionEnd; detection surface unobservable (adversarial) | P6 contract made per-event (PreCompact: ours; SessionEnd: theirs; cross-event dedup-absorbed); purpose-built `claudna-active-<session_id>` marker written by session-start.sh, integration-tested; siblings warned off internal surfaces |
| B4 | 0.2.0 single-writer vs parallel worktrees → silent reflection loss (adversarial) | claudron-engine.md failure posture: bounded retry → loud degrade; reflect's fallback write mandatory at PreCompact; lock pull-forward ask to Claudron#16; epic risk row |
| R1 | gates keyed to issue states / draft bullets (adversarial) | Artifact gates everywhere + 0.2.0 re-confirmation checkpoint as P4 step 0 |
| R2 | ownership inversion never considered (adversarial) | New fork F6 with lean (a) + written rebuttal (engine-preference edits are clauDNA-side under any owner) |
| R3 | P2/P4 seam incoherence — engine roots have no INDEX.md (adversarial) | `(claudron vault)` annotation + precedence rule (P3); degraded messages honor it (P5) |
| R4 | version ritual unimplementable; silent fallback invisible in --auto (adversarial) | Envelope validation per call; F5 amended: `engine` field + degradation in `errors[]` |
| R5 | SSOT drift undetectable; sovereignty (adversarial + first-principles) | P2: source-commit stamp + CI drift check; `x-*` escape hatch; dormancy clause |
| R6 | four-way write-door confusion (adversarial) | Which-door table in P1 doctrine; reciprocal negative routing in P4 |
| R7 | fork gating inconsistent with Track A implementing fork outcomes (adversarial) | Per-phase fork gates (F3→P1; F1/F2/F5/F6→P4; F4→P7) in the sequencing table + checklist |
| R8 | P2-old gated behind bundled P1; Track A ratifiability (cost-benefit + first-principles) | P1 split: router (P1, ungated) / vocabulary SSOT (P2, artifact-gated); Track A declared independently ratifiable; seam phase gates only on the doctrine section |
| R9 | P4-old undersized (cost-benefit) | Scope shed to P4-new (contract doc, publish upgrade, routing lines) + interim grep cut (engine title-dedup instead); P4-new sized L, P5 honest M |
| R10 | field remediation missing; sweep hand-listed (adversarial) | P7: template update same release, re-run-init guidance, Installation Health stale-reference row, gate-derived sweep |
| R11 | untestable parity attestations; no hook harness (adversarial) | Parity restated as prose-diff + behavioral spot-checks + capture-field parity assertion; marker gets a real integration-test row; "byte-identical" language dropped |
| R12 | #110/#112/#36 dispositions; missing overlaps (precedent-check) | Epic Reconciliation section: 12 issues dispositioned; #192 hard-sequenced before P7 |
| R13 | disk-alias vs no-stub doctrine (precedent-check) | Scoping recorded: F4 doctrine = picker entries; flags get one-release grace (stranding-incident rationale) in P1 + CHANGELOG |
| R14 | semver promise; smarter-never-measured; surface stability (align-to-mission) | P7 semver statement; P5 retrieval-delta fixture; P6 marker/contract enter the stability promise |
| R15 | mechanical (plan-health) | Context on all forks; `updated:` ×8; risk Level column; gate-cell edges; markdown fixed |
| Q1 | #17 as sole gap sink; init flag naming (adversarial) | Gap routing: capture/CLI gaps → #16, MCP-surface gaps → #17, cross-referenced; `init --personal` used, flags re-confirmed at checkpoint |

Minor items not individually ledgered (SETUP_GUIDE consolidation → P3 opens one
section; `~/shared` default; advisory-wording alignment; no-vault ladder branch;
migration idempotency semantics) are folded in the respective phase docs.

## Residue (accepted, not folded)

- Cycle 2 re-verification of the folded family was not run pre-filing — the epic files
  with cycle-1 hardening only; `/ironclad <epic-issue> --loops N` remains available
  against the live Issue once filed. (Chris's call at ratification.)
- PROJECT_MISSION.md's stale sprint-focus section (align-to-mission observation) —
  noted for the ratifier; out of this epic's scope.
- Stale branch `origin/feat/knowledge-skills-learn-reflect` + the leftover worktree
  checkout (precedent-check residue) — housekeeping, not plan content.
