---
title: "[plan] P2: vocabulary SSOT — output-guide renders SCHEMA.md, with a drift check and an escape hatch"
type: plan
status: draft
owner: chris
created: 2026-07-07
updated: 2026-07-07
tags: [planning, claudron, schema, output-guide]
repos: clauDNA
links:
---

# P2 — vocabulary SSOT

Part of the Claudron-integration epic (`00_OVERVIEW.md`). Size: **M**. Gate (artifact):
**SCHEMA.md file exists on Claudron `main`** — not E1's issue state (the panel verified
issue-state ≠ artifact-state in that repo today).

## Summary

Make clauDNA's field vocabulary a *rendered copy* of Claudron's SCHEMA.md instead of a
third independent schema — with the two things a rendered copy needs to be safe: a
source stamp + CI drift check (so divergence fails a check instead of starting a
cross-repo dispute), and a namespaced escape hatch (so clauDNA is never blocked on an
external pre-1.0 SSOT going quiet — the sovereignty concern the panel raised).

## Evidence

- Three near-identical type/status enum tables live at `skills/publish/SKILL.md`
  (Step 1a), `skills/index/SKILL.md` (Step 2), and `skills/_shared/output-guide.md` §3;
  none validates against the others. Claudron `01-schema.md` names this three-repo
  drift and builds SCHEMA.md as the executable SSOT (status activity union with
  documented mappings, e.g. `current≈active`; `maturity` as a second axis;
  `schema_version` reserved).
- `/learn` and `/reflect` hardcode `status: current` (`learn/SKILL.md:98`,
  `reflect/SKILL.md:106`) — sitting exactly on the `current≈active` mapping most prone
  to silent divergence (panel).
- Claudron's E1 PR4 lands the *pointer* from their side into `output-guide.md`; this
  phase is the *behavioral* half (one table, stamped, checked).
- Claudron dormancy base rate (their own overview: 7-week gap, solo maintainer) — the
  escape-hatch motivation.

## Implementation Plan

### Dependencies
SCHEMA.md on Claudron `main` (artifact gate). Coordinates with (does not block on)
Claudron E1 PR4.

### Blocks
Nothing hard; P4/P5 read the rendered table.

### Steps

1. **output-guide §3 becomes the rendered copy:** the type/status table + the
   equivalence mapping + the `maturity` axis, headed by a source stamp:
   `Rendered from Claudfather/Claudron SCHEMA.md @ <commit-sha> (<date>)`. Local
   additions prohibited **except** `x-*`-prefixed fields (accepted, passed through,
   never validated) — the escape hatch. Gap channel: schema gaps → comment on the open
   Claudron epic issue that owns the surface (E2 #16 for capture/CLI, #17 for MCP),
   cross-referenced here. Dormancy clause: if the SSOT is unmaintained when a needed
   change arrives, the rendered copy becomes de-facto canonical by a recorded decision
   on this epic — never by silent local edit.
2. **Publish/index accept the new axes:** `maturity` and `schema_version` validated as
   pass-through (present = fine, never rejected, never required); `status` validation
   accepts the union with the mapping.
3. **Deduplicate:** `publish/SKILL.md` Step 1a and `index/SKILL.md` Step 2 replace
   inline tables with a pointer to output-guide §3. Index `--fix` defaults unchanged.
4. **Drift check:** a small CI step (extend `validate-skills.py` or a sibling script)
   that, when network permits, fetches SCHEMA.md at the stamped ref and diffs the
   vocabulary block; offline it verifies the stamp exists and the three-way
   internal consistency (output-guide vs publish vs index pointers). A stamped-ref
   mismatch with SCHEMA.md HEAD is a *warning* (update available); a content mismatch
   at the stamped ref is a *failure* (the copy was hand-edited).

## Test Plan

- Doc with `maturity: draft`, `schema_version: 1`, and an `x-review-round: 2` field
  passes publish validation untouched.
- Hand-edit the rendered table → drift check fails; bump the stamp honestly → passes.
- `status: current` knowledge doc still validates (mapping intact).

## Verification Checklist

- [ ] Exactly one type/status table remains in clauDNA, stamped with its SCHEMA.md source commit
- [ ] Drift check wired into CI and green
- [ ] `x-*` escape hatch documented in §3
- [ ] learn/reflect's hardcoded statuses covered by the mapping (no skill-body edits needed in this phase)

## What NOT To Do

- Don't copy SCHEMA.md prose — render the table, link the spec.
- Don't validate `x-*` fields — the hatch's value is that it needs no upstream round-trip.
- Don't block this phase on Claudron E1 PR4 (their pointer PR) — the two land
  independently and reference each other.

## Context

- Source skill: forge · Area: skills/_shared/output-guide.md, skills/publish, skills/index, scripts/ · Effort: M · Risk: Low-Med · Priority: High
- Dependencies: SCHEMA.md artifact on Claudron main · Blocks: none hard (P4/P5 read it)
