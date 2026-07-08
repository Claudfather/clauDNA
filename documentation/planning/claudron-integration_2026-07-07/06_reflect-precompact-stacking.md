---
title: "[plan] P6: /reflect writes vault-ward + the per-event stacking contract — one prompt per event, nothing lost"
type: plan
status: draft
owner: chris
created: 2026-07-07
updated: 2026-07-07
tags: [planning, claudron, reflect, hooks]
repos: clauDNA
links:
---

# P6 — `/reflect` vault-write + the per-event stacking contract

Part of the Claudron-integration epic (`00_OVERVIEW.md`). Size: **M**. Gate: P4 merged.
**Timing constraint:** the contract posts to Claudron#16 before their E2 PR3 (hook
pack) merges — their hook implements against a written contract, not by reading our
script.

## Summary

`/reflect` is the session-distillation half of what Claudron's E2 calls "capture" — so
on the event both plugins share, reflect **subsumes** capture. But the panel showed the
naive claim is event-incomplete and the naive detection surface unobservable, and 0.2.0
is single-writer. So this phase ships three precise things: (1) reflect's write step
routes through the engine with retry-then-fallback (a reflection is never lost at
compaction), (2) a **per-event** stacking contract — PreCompact: clauDNA prompts,
Claudron defers; SessionEnd: Claudron prompts, clauDNA is silent — and (3) a
purpose-built presence marker a sibling hook can actually observe. clauDNA adds no new
prompting hook.

## Evidence

- `plugin-hooks/precompact-reflect.sh` — block-first-compaction, session-keyed marker,
  `CLAUDNA_PRECOMPACT_REFLECT=0` opt-out. `plugin-hooks/hooks.json` — clauDNA registers
  **no SessionEnd hook**; most sessions end without compacting (panel blocker: an
  event-blind "we subsume capture" claim would zero out end-of-session capture for
  claudna users, a regression vs running Claudron alone).
- **Detection-surface reality (panel):** the reflect marker is transient (created on
  first block, deleted on the allow pass, absent in non-compacting sessions, skipped
  without a session id — `precompact-reflect.sh:31-33,:38-41,:45`);
  `CLAUDNA_PRECOMPACT_REFLECT` is read, never exported, and unset in the default-on
  case. Neither is observable by a sibling hook; a purpose-built signal is required.
- Claudron `02-session-loop.md` deliverable 3 — their capture prompts fire on
  **PreCompact and SessionEnd**; they commit to detecting claudna and deferring; their
  deliverable 4 + `03-mcp-server.md`: **the write lock arrives in E3** — 0.2.0 capture
  is single-writer while parallel worktree sessions are the house workflow.
- `skills/reflect/SKILL.md` Phases 3–4 — target heuristic, raw write to
  `shared/knowledge/reflections/`, same-day append rule, auto-`/index`.
- #112 asks for persist nudges in the flows that end sessions — this phase is their
  clauDNA home.

## Implementation Plan

### Dependencies
P4 (engine conventions, retry/degrade posture). Coordinate with Claudron E2 PR3 (soft
gate: contract posted first).

### Blocks
P7 (lessons content routes through reflect's vault path); closes #112's clauDNA half.

### Steps

1. **`/reflect` vault routing (Phase 3–4):** vault detected and target=shared → write
   via `claudron capture` (`--type knowledge`, `--project <repo>` for repo-scoped
   sessions, tags `[process, retrospective]`; engine stamps `maturity: draft`).
   Same-day re-reflect rides the engine's dedup (`suggest_update` → `--update`
   addendum) instead of the filename-append rule. **Failure posture:** bounded retry
   then fall back to today's raw target (shared tree or `memory/`) with a loud note —
   at PreCompact the marker is already consumed, so the fallback write is what
   guarantees no reflection is ever lost to a lock collision. **Subsumption parity,
   testable:** the vault note carries every field capture requires
   (type/title/tags/project/body) — asserted in the test plan, so "reflect subsumes
   capture" is a checkable claim. Fallback rows unchanged; auto-`/index` skipped on the
   engine path.
2. **Presence marker (the observable detection surface):**
   `plugin-hooks/session-start.sh` writes `${TMPDIR}/claudna-active-<session_id>` at
   SessionStart. Documented semantics: "clauDNA is active in session S" — checked by
   sibling hooks against their own stdin session id (stale other-session markers are
   inert; TMPDIR hygiene handles them). One-line hook change + an
   `integration-test.py` row (marker written on startup, absent under
   `CLAUDNA_SESSION_BRIEFING=0`? No — the marker writes unconditionally when the hook
   runs; the briefing env gates output, not presence). Siblings are explicitly warned
   **off** the reflect marker and the opt-out env var.
3. **The per-event stacking contract** (SETUP_GUIDE, appended to the P3-opened
   section; posted to Claudron#16):
   - **PreCompact:** clauDNA prompts (`/reflect`, which now vault-writes); a sibling
     capture hook detecting `claudna-active-<session_id>` defers.
   - **SessionEnd:** Claudron's capture prompt runs; clauDNA has no hook on this event
     and adds none — end-of-session capture is theirs.
   - **Compact-then-end sessions:** double *capture* is absorbed by engine dedup
     (second write routes to update); double *prompting* per event never occurs.
   - The marker + this contract enter the pinned-version stability promise: renaming
     either is a breaking change with a CHANGELOG entry.
   - The post to #16 also carries the **write-lock pull-forward ask** (capture's
     dedup→write critical section under the E3 flock spec, at 0.2.0) — with the note
     that our retry+fallback posture stands either way.
4. **#112's clauDNA half:** persist-nudge lines in `/session` handoff mode ("learnings
   worth persisting? run `/claudna:reflect` first") and `/review-work` post-verdict
   prose (reusable-pattern nudge). #112 closes at this phase with the pointer; the
   claudlobby `library/protocols/` half stays theirs.
5. **SessionStart budget note** (same section): claudna briefing + claudron recall
   brief co-inject; both budgeted short; opt-outs named (`CLAUDNA_SESSION_BRIEFING=0`,
   claudron hook config). Cross-links #104 (auto-resume unaffected) and #176.

## Test Plan

- Two-plugin simulation (their hook per E2 PR3 shape): PreCompact → one prompt
  (reflect); SessionEnd → one prompt (capture); compact-then-end → second write routes
  to update, not duplicate.
- Marker: `integration-test.py` row — present after SessionStart, keyed to session id;
  sibling-check simulation (a stub script reading stdin session_id) sees it.
- Lock-collision simulation: capture fails twice → reflection lands at the raw target
  with the loud note; nothing lost, nothing silent.
- Parity assertion: the engine-path vault note contains every capture-required field.
- No vault → reflect behavior prose-diff clean vs current release.

## Verification Checklist

- [ ] One prompt per event with both plugins installed; zero-capture-on-non-compacting-session regression impossible (SessionEnd explicitly assigned)
- [ ] Reflection survives a simulated lock collision (fallback write observed)
- [ ] Marker observable by a sibling process keyed to session id; documented as a stable contract
- [ ] Contract + lock ask posted to Claudron#16 before their PR3 merges
- [ ] `/session` + `/review-work` persist nudges live; #112 closed with pointer

## What NOT To Do

- Don't add a clauDNA SessionEnd (or any new prompting) hook — SessionEnd is assigned
  to Claudron by contract; one prompter per event.
- Don't point siblings at the reflect marker or the opt-out env var — they are
  internal; the presence marker is the contract.
- Don't let a lock collision at PreCompact eat a reflection — the fallback write is
  mandatory, not best-effort.
- Don't write reflections raw into the vault "because it's just markdown" — every
  vault write goes through the engine.

## Context

- Source skill: forge · Area: skills/reflect, skills/session, skills/review-work (nudge lines), plugin-hooks/session-start.sh (one line), scripts/integration-test.py, SETUP_GUIDE.md · Effort: M · Risk: Medium (cross-plugin contract; concurrency) — mitigated by per-event assignment + fallback write · Priority: High
- Dependencies: P4; contract posted before Claudron E2 PR3 · Blocks: P7; closes #112 (clauDNA half)
