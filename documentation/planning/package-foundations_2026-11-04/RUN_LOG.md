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
| P2 | 02_package-doctor.md | source verified; owner-gated merge | [#464](https://github.com/Claudfather/clauDNA/pull/464) | stacked base; main-only check awaits retarget |
| P3 | 03_release-qualification.md | source verified; owner-gated merge | [publication receipt in #462](https://github.com/Claudfather/clauDNA/issues/462) | exact-head provider receipt in #462 |

P3's final PR URL, source head and provider CI results are recorded in the linked tracking issue after its one implementation push. This avoids changing the candidate solely to embed its own future PR number. Source plans and this ledger own implementation scope and the owner queue; provider receipts own current publication/CI state.

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

### P3 verification and round 1

- Workers completed isolated focused checks: package suite 30 passed with lint (`p3-package-focus-3.log`); release suite 60 passed with lint (`p3-release-final.log`). Release tests use private Git remotes and a fake GitHub CLI; no real publication occurred.
- Parent invoked the actual default `make qualify-release` controller in an isolated committed export. Snapshot `cb890216f44fe4d081fceb523e332cfbf034d4c5`: nested exact-candidate `make check` passed `2459 passed, 9 skipped in 103.13s`, then staged qualification passed. Log `/tmp/claudna-foundations-Tet0Jy/p3-full-qualification.log`; artifacts `/tmp/claudna-foundations-Tet0Jy/p3-candidate-artifacts` bind 476 tracked files, version 0.34.11 and archive SHA-256 `ffa0310c66b9fdd904815ebf924daa72bd70be3973ff202e7cb487de5092462f`. No tag was created by this default qualification path.
- Independent spec reviewer `/root/p3_spec` found a concrete standalone staged-resource gap: deleting `skills/claudron/lookup.md` from a candidate could pass staged checks despite the unchanged reference in SKILL.md. Full controller source checks catch it, but standalone staged qualification must satisfy the same resource-closure requirement. Accepted fix: reuse staged `integration-test.py` and `validate-skills.py`, plus deleted-depth/shared-resource regressions; no new parser or inventory.
- Class sweep: `rg -n 'for script, flags|validate-skills.py|integration-test.py|validate-manifest.py|generate_package_support.py' scripts/qualify_package.py Makefile` produced six lines: one staged validator loop (two lines) and four existing Makefile-owned validator calls. P1/P2 have no staged qualifier. Added both existing reference validators to the one staged loop; no second resource parser. Deleted-depth and deleted-shared regressions also set ambient CI variables to prove those cannot narrow the private staged gate. Fresh isolated lint/package suite passed 32 tests in 43.58s, log `p3-package-closure-1.log`; spec re-review closed this finding.
- Independent reuse `/root/p3_reuse` and efficiency `/root/p3_efficiency` completed NO FINDINGS. Altitude `/root/p3_altitude` completed NO ALTITUDE FINDINGS, including the resource fix, but identified a separate publication-integrity defect: the independently supplied Git remote and GitHub repository could carry different commits for the same tag. Accepted: bind the repository receiving assets to the candidate's peeled tag commit before creating/uploading assets. Sweep `rg -n 'publish_tag\(|publish_assets\(|release.*create|release.*upload' scripts/release_candidate.py scripts/release.sh .github/workflows` found six lines in one controller: two definitions, two mutation sites and two dispatch calls. That controller owns the fix; earlier phases have no separate publication controller.
- Publication binding now checks the receiving GitHub repository through its refs/tag-object APIs before creating a release, before each upload and after publication. Regression fixtures use real private Git repositories behind the fake GitHub API: matching/wrong lightweight and annotated tags, nested tags, wrong repository with absent/existing release, noncommit tags and final-upload drift. Fresh isolated lint/release suite passed 68 tests in 25.68s (`p3-release-repo-binding.log`). Spec re-review closed both findings with no extras or misunderstandings.
- Actual controller run after the first two fixes: snapshot `cdd235d99cbd112c1b2aec7506190e1052a5f413`, `make check` exit 0 with `2469 passed, 9 skipped in 139.43s`, then staged qualification passed. Log `/tmp/claudna-foundations-Tet0Jy/p3-fixed-qualification.log`; receipts in `p3-fixed-artifacts` bind 476 files, version 0.34.11 and archive SHA-256 `90d0dbbe6188ce725387d8c213645010f6f782a7f16243a2e73185d7f91d6a9e`. A byte comparison of every owned non-planning path against that export found zero differences. These are explicitly synthetic validation commits, not published release artifacts.
- Independent quality reviewer `/root/p3_quality_simplify` found that qualification's private HOME and disabled user site can hide the supported user-installed development dependencies, after the release helper has already committed its bump. Added one shared maintainer-toolchain preflight before mutations/output creation, actionable Python 3.12 venv setup, and a private `python3` shim preserving the selected interpreter. No installation/network or production test override was added. Pure packaging remains stdlib-only.
- Toolchain class sweep: `rg -n 'HOME|PYTHONNOUSERSITE|ensure_toolchain|sys.executable|isolated_python_env' scripts/release_toolchain.py scripts/release_candidate.py scripts/release.sh scripts/package_release.py scripts/qualify_package.py` found 26 lines across five files. All three qualification entrypoints and the release helper use the shared preflight. The controller pins its subprocess interpreter; the staged validators use the selected absolute interpreter, and packaged runtime hooks remain stdlib-only. Earlier phases have no qualification entrypoint.
- Initial toolchain-focused isolated lint and suites passed: package 33 (`p3-package-toolchain-2.log`), release 71 (`p3-release-toolchain-final.log`). Actual controller snapshot `f28602f6239c263699686946e38ee0e12db02bcf` passed `2473 passed, 9 skipped in 147.27s` and staged qualification (`p3-toolchain-qualification.log`). Spec re-review was clean. Quality re-review closed the production preflight finding and retained NO SIMPLIFICATION FINDINGS, but found that the real qualification tests would themselves break ordinary user-site `make check`. A bounded offline test-toolchain fixture and an actual private user-site check are required before approval; the venv run alone does not close this compatibility case.
- The supported user-site check path is preserved through a test-only offline venv: an explicit `.pth` provisions already-selected installed site roots, then real `-I -B` imports verify the toolchain. Only qualification tests opt in; separate empty-venv negative tests still reject ambient-only dependencies. Sweep of qualification consumers covers six package test functions (ten parametrized cases), the release-controller test module and the manifest release-helper regression. No production preflight bypass, skipped coverage, package copies, install or network was added. A Minor review correction preserves the runner's site-root precedence during deduplication.
- Full private user-site reproduction: ordinary imports succeeded while the same base interpreter's `-I` imports failed, proving the dependencies were user-site-only. Snapshot `903ff1dbe139e048574325f647319334cbc1a2a9` then passed all of `make check`: `2473 passed, 9 skipped in 158.54s`. Proof and log: `/tmp/claudna-foundations-Tet0Jy/p3-usersite-reproduction/import-proof.json` and `make-check.log`. After the one-line test-fixture order correction, fresh snapshot `708ddafbc4560497b90388c62421a013c7cab3b9` passed lint, 71 release/helper/changelog tests and 33 package tests (`p3-offline-toolchain-order.log`).
- Final actual controller evidence: snapshot `6ac4fa40bb82ba98e1072267e2c48371493b47e7` passed `2473 passed, 9 skipped in 161.71s` and staged qualification. Log `/tmp/claudna-foundations-Tet0Jy/p3-final-qualification.log`; receipts in `p3-final-artifacts` bind 477 files, version 0.34.11 and archive SHA-256 `1ec924f4a3549bb87d31d4e4df514cb9a5144192396cec8d9a2821554c4c954e`. All production files match this export. Only the subsequently verified test-fixture order correction and planning receipts differ; no broader repeat was needed. These artifacts describe the stated synthetic validation commit, not the final PR head or a published release.
- Independent quality re-review closed both Important toolchain findings and the Minor fixture-order finding: APPROVED / NO REMAINING QUALITY OR SIMPLIFICATION FINDINGS. Spec review remains clean; reuse, efficiency and altitude lenses completed separately. No outstanding source finding, baseline failure or waived gate remains. Final fixture hash: `tests/conftest.py` SHA-256 `52ccb54a23e4198e78f5f06461945ab0011c9a315434efeb3df823a02b11db21`.
- Invariants at the frozen candidate: 40/35/37 selections; versions all 0.34.11; Claude/Codex hook JSON byte-identical to 51c6be2; Cursor zero handlers and excluded using-claudna; Codex six handlers. Original main still contains only its pre-existing foreign untracked directory.
- Final scope: exact-ref exporter, staged qualification, immutable release identity/assets, changelog integration, macOS/stacked CI, shared maintainer preflight and its test fixture, version 0.34.11 and handoff documentation. Reachability remains source-only: no native install, trust change, global settings/auth/cache edit, tag, live release or catalog promotion. Main and both parent remote heads were refreshed unchanged before shipping P3.

### P2 publication and P3 kickoff

- P2 published once as PR #464, head `043f5efcb61924f4e56675eb59c23c3f6e6659c0`, base `implement/package-support-contract` at `874e6f735a442ab4389d511b68f7180ec6c97785`. Provider readback confirms open/unmerged, expected head/base, saved body and 18-file scope. This is P3's future rebase boundary after a P2 squash.
- P3 worktree `/Users/artemis/Projects/claudna-worktrees/package-release-qualification`, branch `implement/package-release-qualification`, created from exact P2 head. Fresh private baseline before worker edits passed `make check`: `2399 passed, 9 skipped in 74.78s`, log `/tmp/claudna-foundations-Tet0Jy/p3-baseline.log`; no baseline failures.
- In-session decomposition: `/root/p3_package` owns artifact/fixture qualification tooling and guide; `/root/p3_release` owns candidate/tag/release workflow and changelog-gate reconciliation. Parent owns Makefile, version/projection integration, ledger, validation and shipping. No overlapping file ownership.
- Live official Claude [marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference#plugin-sources) verified `github` plugin sources accept a full 40-character lowercase `sha`. Output is a review artifact, not a live catalog mutation; Cursor/Codex pin fields are not invented.

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
- After P1 squash and a fresh fetch, P2's boundary is `git rebase --onto origin/main 874e6f735a442ab4389d511b68f7180ec6c97785`; verify phase-only scope and retarget #464 to main. After P2 squash and a fresh fetch, P3's boundary is `git rebase --onto origin/main 043f5efcb61924f4e56675eb59c23c3f6e6659c0`; verify its phase-only scope and retarget. Refresh heads/reviews/CI after either history rewrite.
- Before merging P1/P2, choose whether to permit their intermediate releases or hold the existing release workflow during landing. Both earlier phases bump versions and the old main workflow publishes on that change; P3 qualification is not retroactive. This run does not disable workflows or change repository settings.
- Native marketplace fresh install/update/rollback/removal and trust/execution acceptance remain separate from fixture checks.
- Publish release assets and promote a SHA-bound catalog only after merge/release review; no live registrations changed by this sprint.
- Native acceptance is BLOCKED on an operator selecting an isolated client profile and running the documented lifecycle with dated client versions and package hashes. Required evidence: fresh discovery, hook trust and observed execution for Claude/Codex; Cursor skill discovery and absent hooks; update/rollback identity; uninstall preserves explicitly retained local records and unrelated files. A fixture receipt cannot close this item.
