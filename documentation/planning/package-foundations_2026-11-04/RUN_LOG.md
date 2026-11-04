---
title: "Package foundations sprint ledger"
type: runbook
status: current
owner: claudna:build-all
created: 2026-11-04
updated: 2026-11-04
repos: [Claudfather/clauDNA]
links: [https://github.com/Claudfather/clauDNA/issues/462]
---

# Package foundations sprint ledger

## Kickoff gates

- PASSED: owner accepted the comparison and requested build-all; phases/order/goal written before implementation.
- PASSED: live origin/main 51c6be29a4a1a16dcba2cc103e40badaa6bf776f, version 0.34.8. Main checkout remains at d6c376c with its pre-existing untracked skill-usefulness directory untouched.
- PASSED: isolated baseline make check, Python 3.12.13 and pinned requirements: 2322 passed, 9 skipped; exit 0 (63.08s pytest).
- PASSED: isolated baseline make test-runtime on Python 3.9.6: 1002 passed; exit 0 (36.68s). No baseline failures.
- PASSED: real same-host subagent controls available. Explorers foundation_contract_map and foundation_release_map completed; no runtime/client support inferred from their execution.
- PASSED: media decision none; CLI/package evidence is appropriate.
- No gates waived. Source work, branch pushes, PRs authorized; merge, native trust/config changes, live release/promotion remain owner decisions.
- Planning publication: four docs validated with publish frontmatter/body contract. Epic #462 created through gh after connector write permission returned 403. No settings/auth changed.

## Invariant registry

| Invariant | Check | On breakage |
|---|---|---|
| Canonical/selected catalogs remain Claude 40, Cursor 35, Codex 37 | existing test_codex_scope and make check-manifest | stop, repair unintended scope change |
| Cursor remains hook-free; Codex five store plus startup handlers unchanged | make check-manifest; diff hook configs against 51c6be2 | stop, restore scope |
| Runtime remains stdlib/Python 3.9 and no global state writes | runtime layout and behavioral tests; make test-runtime | stop, fix dependency/write |
| Versions match all three manifests | make check-manifest | stop, synchronize |
| Canonical manifests/frontmatter own catalog; generated outputs stay current | P1 generator --check via Makefile | regenerate, never edit projection manually |
| Original main checkout/foreign WIP untouched | git status --short in original checkout | stop and investigate |
| Qualification, native acceptance and publication remain separate | review CLI/receipt/docs claims | correct all in-scope overclaims |

Run after each phase; after merges, owner must rerun against newly landed main.

## Merge topology plan

Single repository. Three dependent PRs; squash is the planned merge method, never performed by this run.
P1 branch implement/package-support-contract targets main.
P2 branch implement/package-doctor branches from P1 and targets P1.
P3 branch implement/package-release-qualification branches from P2 and targets P2.
After P1 squash: rebase P2 --onto origin/main <recorded P1 head>, verify only P2 scope, retarget.
After P2 squash: rebase P3 --onto origin/main <recorded P2 head>, verify only P3 scope, retarget.
Record actual parent SHAs at each branch. Preserve task-created worktrees as review handoffs.
Each phase uses the build-all in-session decomposition path plus separate simplify, verify, scope/reachability and ship steps; no duplicate composed PR pipeline.

## Phase results

| Phase | Doc | Status | PR | CI |
|---|---|---|---|---|
| P1 | 01_support-contract.md | owner-gated merge; source verified | [#463](https://github.com/Claudfather/clauDNA/pull/463) | all 9 provider checks succeeded at 874e6f7 |
| P2 | 02_package-doctor.md | source verified; owner-gated merge | publication next | require provider readback |
| P3 | 03_release-qualification.md | PENDING | pending | pending |

## Per-phase entries

### Baseline and P1 premise review

- Source owners confirmed: scripts/plugin_scope.py imports the PyYAML-bearing skill_checks module. Decision: generator reuses that code; runtime consumes a hash-bound projection, avoiding a second YAML parser or broad classifier move.
- Existing executable pipeline health is reused, not replaced.
- Existing-tag presence is not candidate identity; P3 must compare peeled commits.
- No supported common pin grammar exists across three hosts. P3 emits exact-source artifacts and a documented Claude SHA descriptor; live marketplace promotion remains explicitly separate.
- Baseline log retained privately outside Git at /tmp/claudna-foundations-Tet0Jy/baseline.log.
- Runtime-floor baseline log: /tmp/claudna-foundations-Tet0Jy/baseline-runtime.log.
- P1 worktree: /Users/artemis/Projects/claudna-worktrees/package-support-contract, created from 51c6be2.

### P1 source result and reachability

- Final isolated committed snapshot `9f7914410574f9b151a3a9b27b29c049b02a7314`: `make check` exit 0; `2342 passed, 9 skipped in 68.98s`. Changelog gate, generator drift, all validators and lint passed. Log `/tmp/claudna-foundations-Tet0Jy/p1-release-final.log`. This synthetic test commit is not a remote release or source branch head.
- Real release-helper regression runs in a private fixture, verifies dry-run/no mutation, all committed source hashes, generated version/table, tag identity and clean working tree. No task release tag or push was performed by that fixture.
- Spec and quality reviewers completed re-review with NO FINDINGS. Both prior classes closed; no reopened findings. Four simplify lenses passed; the final quality re-review also assessed the bounded release integration across those lenses.
- Scope: generated support data/docs, generator/gate/tests, existing release-helper integration, version 0.34.9 and sprint planning only. Doctor/runtime and exact-ref release machinery remain P2/P3. No skill/hook selection or global installation changes.
- Reachability: source is not installed. Merging a version bump currently triggers the existing main release workflow; consumers still require native marketplace refresh/update and a fresh session. P3 must land before claiming the new qualification path. Native discovery/trust/execution remains BLOCKED on separate operator acceptance; no native lifecycle command was executed here.
- Parent carries the actual PR URL/head into the next phase ledger after the initial push, avoiding repeated pushes just to self-reference a PR.
- P1 published once as PR #463, head `874e6f735a442ab4389d511b68f7180ec6c97785`, base main `51c6be29a4a1a16dcba2cc103e40badaa6bf776f`. Provider readback confirms open/unmerged, expected head/base, saved body and 24-file scope. This is the P2 rebase boundary after a future P1 squash.

### P2 kickoff

- Created `/Users/artemis/Projects/claudna-worktrees/package-doctor`, branch `implement/package-doctor`, from exact P1 head `874e6f735a442ab4389d511b68f7180ec6c97785`; PR will target `implement/package-support-contract`.
- Real worker `/root/phase2_doctor` owns implementation; parent owns planning/log/shipping. Fresh private baseline export started before worker edits and passed `make check`: 2342 passed, 9 skipped (70.52s), exact candidate P1 head, log `/tmp/claudna-foundations-Tet0Jy/p2-baseline.log`. No baseline failures. Runtime remains stdlib-only/Python 3.9 with no default global store scan.
- Provider check read for P1 at kickoff: nine checks queued; no CI success claimed.
- Subsequent exact-head provider read: all nine P1 checks succeeded, including `make check`, Python 3.9, current Claudron contract and four compatibility floors. [CI run](https://github.com/Claudfather/clauDNA/actions/runs/41881559044). This does not establish native marketplace acceptance or publication.

## Review rounds

### P2 source verification

- Frozen isolated snapshot `4b9870fdfc1ef4a610f89b857413d8e32be529ad`: `make check` exit 0, `2399 passed, 9 skipped in 112.43s`; Python 3.9.6 `make test-runtime` exit 0, `1059 passed in 72.08s`. Logs `/tmp/claudna-foundations-Tet0Jy/p2-full.log` and `p2-floor.log`. No baseline failures carried forward.
- Direct packaged directory CLI from an unrelated cwd with a hostile `json.py`, private HOME/TMP, restricted PATH and irrelevant source override: `python3 -S -B .../package_support doctor --host codex --json` reported 0.34.10 and exit 0; missing explicit root returned exit 2. Native states remained unknown, default store was not read, and package/private file snapshots were unchanged. Receipt `/tmp/claudna-foundations-Tet0Jy/p2-cli-receipt.json`.
- Invariants rechecked: Claude 40 / Cursor 35 / Codex 37; all manifest versions 0.34.10; both hook configs byte-identical to 51c6be2; Cursor remains hook-free and excludes using-claudna. Original main still contains only its pre-existing untracked skill-usefulness directory. `git diff --check` passed.
- Scope: local package doctor, explicit existing-store health aggregation, docs/tests/runtime gates, and version 0.34.10. No native host invocation, authentication, provider work, environment-value output, telemetry store, install or global configuration mutation.
- Reachability: source only, uninstalled. Merge/release and native refresh/fresh-session acceptance remain distinct owner steps; inherited release automation is not yet P3-qualified.

### P2, round 1

- Early implementation checks exposed three compatibility classes: Claude canonical discovery must not enforce host eligibility; ancillary directories without SKILL.md must not become skills; PATH `python3` presence is not its measured version. Worker swept the changed catalog/runtime branches and corrected each, retaining explicit actual-interpreter evidence.
- No-write subprocess tests exposed CPython creating `__main__.pyc` before directory-entrypoint code can disable bytecode. All supported doctor invocations and subprocess tests now use `python3 -B`; no deletion or wrapper workaround. Initial failing log `p2-focused-02.log` is retained; final focused checks and full/floor checks passed. The package main also disables subsequent bytecode writes.
- Independent spec reviewer `/root/p2_spec_review` returned compliant/no findings, inspecting all 15 owned implementation files against the plan and both validated exports. Role hash `27422c452fe226bf12c00a83b5337d0d836697c3e0ec44c1fcb8bec959607185`.
- Fresh independent reuse `/root/p2_simplify_reuse` and efficiency `/root/p2_simplify_efficiency` reviews completed NO FINDINGS. Reviewers used read-only source/diff inspection and did not execute the reviewed branch.
- Independent altitude `/root/p2_simplify_altitude` completed NO FINDINGS. Quality reviewer `/root/p2_quality_simplify` completed APPROVE / NO FINDINGS and the separate simplification lens found no unnecessary state/branches/abstractions. Quality role hash `b7d5159100f8bba6e407406e439c743c69cd3154abcb1533759d761a49e0b15d`. All four real same-host fresh reviewers completed; parent collected completion receipts. No simplification edit or rollback needed.
- Exact remote P1 base refreshed before shipping: `874e6f735a442ab4389d511b68f7180ec6c97785`; remote main remains `51c6be29a4a1a16dcba2cc103e40badaa6bf776f`. Phase-only scope is 15 implementation files plus three parent-owned planning documents. Core CI currently filters PR base main; stacked P2 must be retargeted after rebase before that workflow supplies a verdict.

### P1, round 1

- Fresh isolated `make check`: 2342 passed, 9 skipped; all validators/lint passed (75.17s pytest), `/tmp/claudna-foundations-Tet0Jy/p1-full.log`. Initial uncommitted export left changelog HEAD at baseline, so the final snapshot check will also exercise the branch-aware changelog gate.
- Spec reviewer `/root/p1_spec_review`, fresh non-inheriting same-host spawn, found stale live catalog restatements in canonical policy. Installed role hash `27422c452fe226bf12c00a83b5337d0d836697c3e0ec44c1fcb8bec959607185`; base `51c6be29a4a1a16dcba2cc103e40badaa6bf776f`, all P1 owned changes and new files.
- Class sweep: `rg -n '(35|36|37|39|40).{0,32}skill|skill.{0,32}(35|36|37|39|40)' --glob '*.md' .` returned 38 matching lines (including issue-number false positives, historical release/planning/archive evidence and sprint baseline). Fixed live siblings `SKILL_CONTRACT.md:139` and `PROJECT_MISSION.md:5`. Focused live-surface sweep excluding CHANGELOG and historical plan/archive trees then returned zero matches for literal catalog-size statements. Other sprint branches do not yet exist.
- Four real independent simplify reviews completed: `/root/p1_simplify_reuse` (reuse), `/root/p1_simplify_efficiency` (efficiency), `/root/p1_simplify_altitude` (altitude), `/root/p1_simplify_structure` (simplification). Each returned NO FINDINGS; no simplification edit/rollback was needed. All used the same base/owned scope and clean full-check evidence. Parent collected actual completion receipts.
- Invariants: catalog Claude 40 / Cursor 35 / Codex 37; versions 0.34.9 in all manifests; both hook JSON files byte-identical to baseline; Cursor hook isolation preserved; original main still has only its pre-existing untracked skill-usefulness directory. `git diff --check` passed.
- Media decision remains none: generated package metadata and CLI/check output are the relevant surfaces.
- Final snapshot gate exposed the repository's requirement for new `[Unreleased]` content even with a version bump. Moved this PR's notes under `[Unreleased]`, matching CONTRIBUTING and the existing changelog gate; no gate bypass. P3 owns release-note extraction and exact-candidate qualification.
- Spec re-review completed: spec compliant, no remaining findings. Quality review is separate.
- Quality reviewer `/root/p1_code_review` found an integration defect: `scripts/release.sh` would bump versions without regenerating/staging support data. Accepted as P1 integration scope; worker fixes the helper and existing release regression test. Class sweep `rg -n 'VERSIONED_MANIFESTS|\.version.*=|version.*new_version|version.*NEW_VERSION|\[.version.\].*=' scripts tests/test_validate_manifest.py .github` found only release.sh as a production version mutator. No sibling sprint branches yet. Installed quality-role hash `b7d5159100f8bba6e407406e439c743c69cd3154abcb1533759d761a49e0b15d`; independent non-inheriting same-host spawn.

## Owner-decision queue

- Merge P1, P2, P3 in order only after review/CI; use planned rebase after each squash.
- Native marketplace fresh install/update/rollback/removal and trust/execution acceptance remain separate from fixture checks.
- Publish release assets and promote a SHA-bound catalog only after merge/release review; no live registrations changed by this sprint.
