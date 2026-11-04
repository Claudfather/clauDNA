---
title: "P3: Exact-commit release staging and lifecycle qualification"
type: plan
status: active
owner: claudna:build-all
created: 2026-11-04
updated: 2026-11-04
tags: [enhancement]
repos: [Claudfather/clauDNA]
links: [https://github.com/Claudfather/clauDNA/issues/462]
---
# P3: Exact-commit release staging and lifecycle qualification

Status: SOURCE VERIFIED; independent review complete. Publication receipts are tracked in [#462](https://github.com/Claudfather/clauDNA/issues/462); merge and native acceptance remain owner-gated.

## Summary
P3: Exact-commit release staging and lifecycle qualification implements one bounded slice of the approved package-foundations workstream.

## Evidence
See [overview](00_OVERVIEW.md) and its pinned baseline. Existing owners remain manifests, skill frontmatter, Makefile and the session-store runtime.

## Implementation Plan

### Dependencies
P1 and P2 exact branch heads.

### Blocks
Owner-controlled merge, native acceptance and distribution promotion.

### Steps
1. Add maintainer tooling that resolves an explicit Git ref once and exports tracked source with modes preserved into an owned output. Normalize archive metadata, emit SHA-256 and external receipt containing commit/version/file hashes. Keep runtime dependencies intact; full tracked export matches existing source distribution and avoids a speculative allowlist.
2. Validate staged catalog/manifest/resource closure and run a focused subprocess lifecycle under private HOME/TMP/state from an unrelated cwd. Exercise packaged hook commands, opt-outs and doctor; do not start providers or harvest. Verify selected-host isolation and retain fixture evidence distinct from native installation.
3. Add Makefile package/qualification targets. Extend CI platform coverage to macOS through those existing targets; keep costly authenticated native acceptance separate and document its receipt requirements.
4. Harden release-tag workflow to qualify its exact candidate before tagging, verify existing/raced tags peel to the same commit, and attach qualification/checksum artifacts. All commands/tests remain Makefile-owned. Add meaningful regression tests around wrong tag identity, missing closure and nondeterministic output.
   Reconcile the existing contributor `[Unreleased]` gate with the release helper's versioned notes: qualified release candidates need meaningful notes for their version, and contributor checks must still reject unchanged/missing notes. Do not bypass the changelog gate.
5. Generate a reviewable SHA-pinned Claude marketplace descriptor as release output using the documented source grammar; do not inject unsupported fields into Cursor/Codex. Keep current live marketplace registration unchanged and explicitly queue promotion/native acceptance rather than claiming delivery pinned.
6. Record release reachability, upgrade/rollback/uninstall acceptance instructions and final owner queue.

## Test Plan
Reproduce identical artifact bytes twice for one ref; dirty working files do not leak. Negative cases reject missing dependencies, path escapes and mismatched version tags. Packaged CLI/hook smoke verifies actual exported code. Fresh make check plus qualification target. Native discovery/trust/update/remove proof is separately queued if unavailable.

## Verification Checklist
- [x] Deliverables inspected against this plan.
- [x] Targeted behavioral evidence and fresh isolated checks recorded.
- [x] Independent simplify/review complete; scope excludes unrelated work.
- [x] Publication, merge and native reachability recorded in RUN_LOG.md; final PR/head/CI receipts are linked through the tracking issue.

## What NOT To Do
No guessed cross-host pin fields, tag rewrites, automatic merge/release, global installation changes, provider network calls or fake native acceptance. Do not turn full source tests into a claim that users received that commit.

## Context
Owner-approved build-all; one phase per PR. See overview for sequencing rationale, completion condition and boundaries.
