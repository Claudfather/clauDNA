---
title: "P1: Support contract and consumer documentation"
type: plan
status: active
owner: claudna:build-all
created: 2026-11-04
updated: 2026-11-04
tags: [enhancement]
repos: [Claudfather/clauDNA]
links: [https://github.com/Claudfather/clauDNA/issues/462]
---
# P1: Support contract and consumer documentation

Status: SOURCE VERIFIED; PR/merge owner-gated. See RUN_LOG.md.

## Summary
P1: Support contract and consumer documentation implements one bounded slice of the approved package-foundations workstream.

## Evidence
See [overview](00_OVERVIEW.md) and its pinned baseline. Existing owners remain manifests, skill frontmatter, Makefile and the session-store runtime.

## Implementation Plan

### Dependencies
None.

### Blocks
P2 and P3.

### Steps
1. Add a small host policy JSON under lib/claudna/package_support/ for existing hosts: manifest paths, runtime prerequisites, agents/hook policy and explicit evidence limits. Preserve every selected skill and handler.
2. Add scripts/generate_package_support.py. Reuse existing plugin_scope and skill_checks parsing/validation in development; emit deterministic catalog.json with source-relative paths and hashes of authoritative manifests/frontmatter. Do not move their parser into runtime.
3. Generate a marked public support table in documentation/guides/PACKAGE_SUPPORT.md and link README/SETUP_GUIDE/CONTRIBUTING. Remove live catalog-count restatements in canonical policy docs in favor of derived descriptions; keep historical plans/releases intact.
4. Document per-host install, update, pin/rollback availability, removal and retained data. Use verified native interfaces; unsupported paths stay explicit. Include privacy/support guidance and existing marketplace assets; do not invent native API fields.
5. Add generator drift check to Makefile and tests for invalid inputs, catalog restrictions and source drift. Keep version bump coordinated across three manifests.

## Test Plan
Generator --check must detect modified frontmatter and manifest selection without writing. Check generated counts against actual sources. Existing scope/manifest/runtime tests plus fresh make check. Validate docs links.

## Verification Checklist
- [x] Deliverables inspected against this plan.
- [x] Targeted behavioral evidence and fresh isolated checks recorded.
- [x] Independent simplify/review complete; scope excludes unrelated work.
- [ ] PR and deploy reachability recorded in RUN_LOG.md.

## What NOT To Do
No duplicate YAML parser, new runtime dependency, expanded host scope, or new skill. Do not infer installed/native support from generated metadata.

## Context
Owner-approved build-all; one phase per PR. See overview for sequencing rationale, completion condition and boundaries.
