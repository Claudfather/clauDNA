---
title: "Root structure and maintenance cleanup"
type: plan
status: completed
owner: claudna
created: 2026-11-04
updated: 2026-11-04
---

# Root structure and maintenance cleanup

✅ COMPLETE — Implementation verified 2026-11-04; this record lands with its
final PR, which remains unmerged until owner review. Implements the approved root audit, including
the correction that `shell/` and `snowflake/` are optional setup resources, not
examples. One follow-up PR; no installation, release, merge or global settings change.

## Implementation Plan

### Steps

1. Make legacy session import copy-only in both resume modes. Preserve the source
   notes file and use the project handoff's existence to skip repeat imports.
   Keep timestamp conversion and reaping confined to the project copy.
2. Retire the duplicate skill/manifest workflows, move their main-push coverage
   into unified CI, and update live documentation references. Keep checks owned
   by Makefile and dependencies pinned. Inspect effective required checks first.
   Use the existing FULL_VALIDATE override for main pushes: origin/main can
   already equal HEAD, so PR touched-skill scoping is inappropriate there.
3. Extract stdlib-only skill discovery and the strict frontmatter parser from
   `skill_checks.py`; retain its public imports. Integration validation keeps its
   forgiving parser behavior through a small adapter. Preserve all discovery,
   parsing, host-policy and gate behavior; update copied-script fixtures.
4. Document packaged resources, host discovery and manual activation separately.
   Keep `shell/`, `snowflake/`, `project-template/`, both project-template variants,
   host manifests, hook paths and runtime layout in their present locations.
5. Move the completed D2 inventory out of active planning into a living guide,
   with `type: knowledge`, `status: current` and updated references. Preserve its
   decisions and completed historical checklist; do not bulk-archive other plans.
6. Remove only the audited disposable local root caches (`.DS_Store`,
   `.pytest_cache`, `.ruff_cache`) after confirming none contain tracked paths.
   Preserve the existing untracked skill-usefulness planning directory.

## Decisions and codebase comparison

| Concern | Verified codebase | Decision |
|---|---|---|
| Legacy ownership | resume says delete; README and session router prohibit personal-tree writes | Copy-only, no new migration subsystem |
| Required CI names | Effective main rules on 2026-11-04 require PR approval, deletion and force-push protection; no required status checks. Legacy branch-protection endpoint reports unprotected | Remove duplicate jobs; unified CI also runs on main pushes |
| Parser behavior | skill validator raises ValueError; integration parser returns None for malformed/non-mapping YAML but propagates constructor/decoding/I/O errors | Share strict implementation with a ValueError subtype for the two handled cases; catch only that subtype in integration |
| Discovery | plugin_scope imports skill_checks only for SKIP_DIRS; malformed skill dirs must still be reported | Extract discovery without changing caller enumeration |
| D2 lifecycle | Ledger is a durable placement inventory; D2 checklist is complete | Living guide, not a discarded artifact |
| Setup resources | Shell functions and SnowSQL template have documented consumers | Explain optional manual setup; no examples/ move |

## Verification

- Fresh baseline and final `make check` in isolated clones with private HOME/TMP;
  pinned Python 3.12 development toolchain, full validation label.
- Existing discovery, manifest, scope and promotion tests; focused parser
  compatibility and no-site-packages import checks for the new boundaries.
- Instruction regression checks for copy-only resume; a private native fixture
  if available, with source preservation observed separately from discovery.
- Review unified CI event coverage and provider required-check evidence.
- Independent specification/quality review and all four simplification lenses.
- Check links, changelog, host selections, hook configs and final owned diff.

## Merge topology and activation

Base: `implement/package-release-qualification` at
`5ac28ff668012db7399287936cc1a423ae0552c2` (PR #465), after #463 and #464.
If the parent is squash-merged, rebase only this follow-up from that boundary
onto refreshed main, inspect the remaining diff, retarget and rerun required CI.
No version bump in this cleanup: runtime instructions reach installed consumers
only through a later qualified plugin release/update. CI changes activate on
merge. The PR is left unmerged for review.

## Results

- Isolated baseline at `5ac28ff`: `make check` passed, **2473 passed, 9 skipped**.
- Isolated implementation candidate `69a2b7d`: `make check` passed, **2498 passed,
  9 skipped**. Pinned Python 3.12 toolchain, private HOME/TMP, full validation.
- A stale import caught by lint was removed. Independent spec review caught a
  raw YAML-constructor ValueError being swallowed by the forgiving parser;
  a dedicated exception subtype and three-caller regression test preserve the
  original behavior. The final full run above includes both corrections.
- Unified CI YAML parses with all PR bases and main pushes. In an isolated Git
  fixture with origin/main equal to HEAD, the existing selector returns an empty
  set normally and None (full validation) with FULL_VALIDATE=1. The push event
  wires that override; PR behavior is unchanged.
- Private manual Codex procedure check (`/root/resume_fixture`, two completed
  desktop runs): first resume imported both synthetic items into a v2 project
  handoff; external SHA-256/length checks confirmed the legacy source unchanged.
  Second resume skipped legacy import and retained the project copy, even after
  the fixture owner added a later source item. Git history was unavailable in the
  empty fixture; procedure telemetry lacked a native session identity. Neither
  is a native host discovery/trust/execution acceptance claim.
- Native Claude test HOME reports unauthenticated. No credentials/settings were
  copied or changed; native Claude execution remains unverified.
- Main's effective ruleset 16548045 requires one PR approval and prevents deletion
  and non-fast-forward updates; it has no required status checks. The legacy
  protection endpoint reports unprotected. These were read-only inspections.
- Twelve host manifest/hook/setup files are byte-identical to the base; the
  retired live path/claim sweep is clean across ten affected surfaces.
- Removed only `.DS_Store`, `.pytest_cache` and `.ruff_cache` in the original
  root after checking tracked paths. The foreign untracked skill-usefulness
  planning directory remains untouched.
- Media: none; source, command, test and procedure evidence fit these changes.
- Independent spec review (`/root/cleanup_spec_review`) closed the parser and
  main-push findings on final reviewed export `5acb34fe`. Installed spec role
  SHA-256: `27422c452fe226bf12c00a83b5337d0d836697c3e0ec44c1fcb8bec959607185`.
- Quality review (`/root/cleanup_quality`) found one minor routing-eval path-filter
  dependency after discovery moved. Added the new module to that filter; the
  dependency sweep also updated `.gitignore`'s owner pointer. Existing test-copy
  dependency lists already contain both extracted modules. Installed quality
  role SHA-256: `b7d5159100f8bba6e407406e439c743c69cd3154abcb1533759d761a49e0b15d`.
- All four independent simplification lenses completed through desktop spawn and
  completed-return controls: `/root/cleanup_reuse`, `/root/cleanup_simplification`,
  `/root/cleanup_quality` (efficiency), `/root/cleanup_altitude`. No simplification
  edits were recommended; the quality dependency correction is a separate commit.
- Final owned scope: this cleanup alone above PR #465. The PR remains unmerged;
  no plugin installation, publication, version bump or global configuration edit.
