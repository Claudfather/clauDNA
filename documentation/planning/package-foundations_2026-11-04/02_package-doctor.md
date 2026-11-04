---
title: "P2: Read-only package doctor"
type: plan
status: active
owner: claudna:build-all
created: 2026-11-04
updated: 2026-11-04
tags: [enhancement]
repos: [Claudfather/clauDNA]
links: [https://github.com/Claudfather/clauDNA/issues/462]
---
# P2: Read-only package doctor

Status: SOURCE VERIFIED; owner-gated merge and native acceptance, PR publication recorded in RUN_LOG.md.

## Summary
P2: Read-only package doctor implements one bounded slice of the approved package-foundations workstream.

## Evidence
See [overview](00_OVERVIEW.md) and its pinned baseline. Existing owners remain manifests, skill frontmatter, Makefile and the session-store runtime.

## Implementation Plan

### Dependencies
P1 exact branch head.

### Blocks
P3.

### Steps
1. Add stdlib Python 3.9 package_support runtime entrypoint and doctor modules consuming P1 catalog and host policy. Root defaults to its loaded package, never cwd/cache guessing.
2. Check manifest/catalog consistency and hashes, bundled files, selected skills, runtime/platform support and selected workflow prerequisites. Report missing binaries/env presence only; prerequisite versions not actually probed remain unverified. Validate requested host/skill explicitly.
3. Provide text and JSON with stable status rows and exit codes. Keep configured, discovered, trusted and executed evidence separate. No outbound/auth/trust writes; default is local and read-only. Optional explicit --store-root aggregates existing session_store health without new records/workers.
4. Integrate using-claudna health and public support docs with exact invocation and scope limits. Preserve Cursor's existing skill selection: direct CLI diagnostics are available without adding its excluded health skill.
5. Add behavioral tests from relocated/hostile cwd, absent tools, malformed/stale catalog, redaction/no env values, no writes, missing root, symlink escape and optional store evidence. Extend runtime floor target.

## Test Plan
Run directory entrypoint with python -S in a fresh export/private HOME/TMP. Assert no package/state writes, JSON exit-status contract and failure diagnostics. Run focused tests, runtime structural gates and make check.

## Verification Checklist
- [x] Deliverables inspected against this plan.
- [x] Targeted behavioral evidence and fresh isolated checks recorded.
- [x] Independent simplify/review complete; scope excludes unrelated work.
- [ ] PR and deploy reachability recorded in RUN_LOG.md.

## What NOT To Do
No scanning unrelated private caches by default, native host/auth launches, dependency installation, telemetry ledger or unverified native-success claims.

## Context
Owner-approved build-all; one phase per PR. See overview for sequencing rationale, completion condition and boundaries.
