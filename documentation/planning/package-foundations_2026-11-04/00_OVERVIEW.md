---
title: "Package foundations: portable support, diagnostics and qualified releases"
type: plan
status: active
owner: claudna:build-all
created: 2026-11-04
updated: 2026-11-04
tags: [enhancement]
repos: [Claudfather/clauDNA]
links: [https://github.com/Claudfather/clauDNA/issues/462]
---
# Package foundations

## Summary

Implement the owner-approved comparison of Superpowers and gstack in three ordered, reviewable PRs. Preserve native marketplace installation, canonical skill scope and the existing local session store.

Source implementation and independent reviews are complete for all three phases. Merge, release and native acceptance remain owner-gated. The [sprint ledger](RUN_LOG.md) records validation and merge boundaries; [tracking issue #462](https://github.com/Claudfather/clauDNA/issues/462) carries the final publication and exact-head CI receipts.

## Evidence

Baseline: 51c6be29a4a1a16dcba2cc103e40badaa6bf776f (0.34.8). Existing manifests select Claude 40, Cursor 35 and Codex 37 skills; Cursor has no hooks. The health skill and pipeline health already exist. CONTRIBUTING still carries stale catalog counts. Release tagging does not require an existing tag to point to the candidate.

## Implementation Plan

### Dependencies
None beyond the existing pinned developer toolchain.

### Blocks
A release owner can publish only after PR review/merge and separate native acceptance.

### Steps
1. [P1: support contract and consumer docs](01_support-contract.md): derive a runtime catalog and support table from manifests/frontmatter and one small host policy file. This comes first so later consumers share one inventory.
2. [P2: package doctor](02_package-doctor.md): read-only package and prerequisite diagnostics using P1; reuse pipeline health. This precedes packaging so staged artifacts can exercise the actual diagnostic entrypoint.
3. [P3: release staging and lifecycle qualification](03_release-qualification.md): stage exact commits, record hashes, test package behavior in isolation and guard tag identity. P1/P2 become the artifact contract being verified.

## Goal condition

All three scoped implementations have independently reviewed PRs, fresh isolated checks and recorded CLI evidence; catalogs remain 40/35/37, Cursor remains hook-free and Codex handlers unchanged. Each release output identifies its source commit and bytes. Remaining live native/marketplace acceptance and merge decisions are explicitly queued, never inferred from fixtures. No source-only completion claim means installed or live.

## Test Plan
Fresh isolated exports with private HOME/TMP, pinned Python 3.12 tooling, targeted regressions, make check and Python 3.9 runtime qualification where available. Keep baseline failures separate. Media: none (CLI/package work).

## Verification Checklist
- [x] Three phase implementations independently reviewed and checked.
- [x] Final invariants recorded in RUN_LOG.md.
- [x] Native acceptance and release/promotion owner queue recorded; acceptance itself remains pending.

## What NOT To Do
No global auth/settings/cache edits, new skills, extra analytics or runtime dependencies, automatic updates, new hooks, unsupported manifest fields, default branch pushes, merges or live release publication.

## Context
User approved the three slices and invoked build-all. Inspirations: obra/superpowers@22f0b46 (port contract and packaging), garrytan/gstack@b244e6d (doctor and lifecycle tests). Patterns are adapted, not copied wholesale. Repository docs remain canonical; this epic issue is a tracking copy.
