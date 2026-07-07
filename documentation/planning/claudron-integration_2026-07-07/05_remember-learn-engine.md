---
title: "[plan] P5: /remember + /learn prefer the Claudron engine — INDEX scan becomes the frozen fallback"
type: plan
status: draft
owner: chris
created: 2026-07-07
updated: 2026-07-07
tags: [planning, claudron, remember, learn]
repos: clauDNA
links:
---

# P5 — `/remember` + `/learn` prefer the engine

Part of the Claudron-integration epic (`00_OVERVIEW.md`). Size: **M** (scope shed to P4
per panel: the shared contract doc, the publish-vault upgrade, and the reciprocal
description lines live there; the interim source_url grep was cut for the engine's own
title-dedup).

## Summary

When a vault is detected, `/remember` swaps its INDEX.md line-scan for
`claudron recall --json` (ranked, cross-tier — the retrieval ceiling gone) and `/learn`
writes through the engine's validate+dedup path. When claudron is absent, both run
today's behavior as the **frozen fallback** — prose unchanged, no new features ever
land there. The 5-doc cap survives on both paths: it is a presentation budget, not the
ceiling. The retrieval-delta fixture makes "materially smarter" a checkable claim
instead of a slogan.

## Evidence

- `skills/remember/SKILL.md:24-37` (INDEX enumeration), `:51`/`:98-99` (5-doc cap;
  INDEX-scan-only) — the scan is the F3 ceiling (~100–200 pages); the cap is a context
  budget this phase keeps by design.
- `skills/learn/SKILL.md` Phase 2 (dedup = grep INDEX.md for `source_url` — blind to
  anything unindexed) and Phase 4 (raw write + `/claudna:index`).
- Claudron `02-session-loop.md` deliverable 1 — `recall [--project] [--query]`:
  project-tier-first ranked brief, `--json`, abstention threshold; "gets better under
  E4 without interface change."
- Capture dedup keys are title+alias — **no `source_url` key**: the contract gap, filed
  as a comment on Claudron#16 (E2 owns capture) at epic filing, cross-referenced from
  #17. Interim: the engine's own title-dedup covers the common re-ingestion case
  (same article → same title); no local grep glue (panel: 80% value, zero interim
  code to later delete).
- Engine-managed roots carry no INDEX.md — remember's fallback must honor P3's
  `(claudron vault)` annotation (degraded message, never an `/index` suggestion).

## Implementation Plan

### Dependencies
P4 merged (claudron-engine.md, write conventions, publish upgrade). Claudron 0.2.0 (via
P4's gate). P3 (annotation semantics).

### Blocks
#36's disposition (superseded at this phase); P7 (remember must surface vault content
before notes/lessons point there).

### Steps

1. **`/remember` engine path** (new Step 1a, before today's Step 1): vault detected
   (per claudron-engine.md) → `claudron recall --project <repo> --query "<task>" --json`;
   render in remember's existing format; **5-doc presentation cap kept**; `--full`
   reads the returned paths (≤5). **Door reporting:** "via claudron engine" / "via
   INDEX scan (claudron not detected)". Fallback Steps 1–4 unchanged (frozen), plus:
   the no-root failure message gains a `/claudna:init-project` pointer (the
   installed-base adoption path), and an annotated `(claudron vault)` root without a
   working claudron produces the engine-managed-root message from P3 — never an
   `/index` suggestion.
2. **`/learn` engine path:** vault detected → write via `claudron capture` with
   `source_url`/`source_type`/`tags` passed through; dedup rides the engine
   (title+alias now; source_url when the upstream key lands); `--update` maps to
   capture's `--update <path>` addendum mode; suggestion envelopes surfaced per P4
   conventions with the retry-then-degrade posture (fallback = today's raw write,
   loudly). Fallback: INDEX grep + raw write, frozen.
3. **Docs:** remember/learn Rules gain the frozen-fallback framing; CHANGELOG;
   SETUP_GUIDE append (one paragraph in the P3-opened section).

## Test Plan

- **Retrieval-delta fixture (the "materially smarter" check):** fixture vault where a
  known-relevant note is invisible to the INDEX scan (unindexed or beyond the scan's
  reach) — engine path surfaces it, fallback path provably cannot. Recorded as a
  fixture, rerunnable.
- Fixture vault >5 relevant notes: engine path returns ranked ≤5 + door line.
- claudron removed → fallback output's *prose path* unchanged (prose-diff of the skill
  body sections + behavioral spot-check — not a byte-identical attestation; skills are
  LLM-interpreted).
- `/learn <url>` twice → second run routes to suggestion; `--update` refreshes via
  addendum.
- Annotated-root-no-claudron → correct degraded message.
- `validate-skills.py` + integration tests green.

## Verification Checklist

- [ ] `/remember` names its door in both directions
- [ ] Retrieval-delta fixture demonstrates the engine finding what the scan cannot
- [ ] Fallback sections' prose untouched by this PR (diffable)
- [ ] No INDEX.md written on the engine path; no `/index` suggestion against annotated roots
- [ ] source_url gap comment live on Claudron#16 (cross-referenced on #17)

## What NOT To Do

- Don't delete or weaken the INDEX fallback — claudron is optional by design; the
  fallback is frozen, not deprecated.
- Don't raise the 5-doc cap on either path — presentation budget, kept deliberately.
- Don't reimplement ranking or dedup locally — the engine owns both; no interim grep
  glue.
- Don't let a capture failure kill an ingestion — degrade to the raw write, loudly.

## Context

- Source skill: forge · Area: skills/remember, skills/learn · Effort: M · Risk: Medium · Priority: High
- Dependencies: P4, P3 · Blocks: P7; #36 disposition
