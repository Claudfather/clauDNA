---
title: "Phase 3: Migrate /ironclad from claudlobby to clauDNA"
type: plan
status: ✅ COMPLETE (clauDNA-side); superseded by later §4.1 unification
owner: alex
tags: [planning, ironclad, migration, dispatch, clauDNA, claudlobby]
created: 2026-06-02
updated: 2026-06-03
---

> **✅ COMPLETE, clauDNA-side (verified 2026-07-06 docs audit).** `skills/ironclad/SKILL.md` exists, is explicitly subagent-only (its own text: "the skill itself contains no fleet concepts (no tmux, no `[BOTREPORT]`, no `fleet-state.json`)" — grep-verified zero matches), dispatches lenses as parallel `general-purpose` subagents to a `/tmp/ironclad-<timestamp>/` scratch dir, and supports `--auto`. Phases 3a/3b (clauDNA-side) are done. Phase 3c (fleet-dispatch-capability protocol) and 3e (removal from claudlobby) are **UNVERIFIABLE FROM THIS REPO** — claudlobby is a sibling repo. Since this doc was written, the shipped skill evolved further: it now works on §4.1 plan Issues (not PRs) with a `--loops N` hardening loop and `forge --reforge`, superseding this doc's PR-based, single-cycle design. Candidate for archival once claudlobby-side Phase 3c/3e status is confirmed out-of-band.

# Phase 3: Migrate /ironclad from claudlobby to clauDNA

## Goal

Move `/ironclad` from claudlobby (`library/skills/ironclad/SKILL.md`) to clauDNA (`skills/ironclad/SKILL.md`) so that standalone users — anyone running Claude Code with the clauDNA plugin, no fleet required — get multi-lens plan review. Fleet users retain the current behavior via compositor-injected fleet dispatch protocol.

**Design principle (ratified via PR #141 /ironclad review):** clauDNA skills are subagent-only. Fleet dispatch is a claudlobby concern, injected at composition time — the same pattern used for report-back, context-management, and telegram-routing protocols. No fleet concepts (tmux, BOTREPORT, fleet-state.json) appear in clauDNA.

The lens result contract, scratch directory layout, aggregation logic, convergence check, and PR comment format remain identical regardless of dispatch backend. The only thing that changes is _how_ lenses execute: subagent dispatch (default, in clauDNA) vs fleet dispatch (compositor-injected override for fleet bots).

## Current State

### Shipped (Phase 1 + Phase 2)

- `/ironclad` skill in claudlobby (`library/skills/ironclad/SKILL.md`) — fleet-orchestrated multi-lens review. 9 phases: classify PR, create scratch dir, identify workers, dispatch lenses via tmux, collect via `[BOTREPORT]`, retry failed lenses, aggregate findings, post to PR, convergence check.
- 6 lens skills in clauDNA — all merged to main: `/first-principles` (#133), `/align-to-mission` (#134), `/extension-check` (#135), `/plan-health-audit` (#136), `/precedent-check` (#137), `/cost-benefit` (#138). Plus `/adversarial-review` (#130, updated for `--dispatch` mode).
- `lens-result-contract.md` (#132) — canonical output schema for all lenses.
- 3 protocols in claudlobby — `decision-fork-lifecycle`, `pr-comment-hygiene`, `plan-synthesis` (PRs #361, #362).

### Exists and Relevant

- `/adversarial-review` already demonstrates subagent-based internal dispatch: spawns 5 parallel subagents (Architect, Skeptic, Operator, User, Counter-Planner), collects results, synthesizes into a single structured result. This is the reference pattern for `/ironclad`'s subagent mode.
- `skills/_shared/orchestration-guide.md` — scratch directory patterns, subagent lifecycle, context management rules.
- `skills/_shared/contracts/lens-result-contract.md` — the integration contract between lenses and `/ironclad`.
- `SKILL_CONTRACT.md` — CI validation rules for skill structure.

### Fleet-Specific Infrastructure (stays in claudlobby)

- `lib/dispatch.sh`, `lib/dispatch-task.sh` — tmux dispatch with sanitization + ledger recording.
- `lib/report-back.sh` — worker-to-manager structured reporting + state sync.
- `lib/fleet-state-update.sh` — atomic `fleet-state.json` updates with flock locking.
- `lib/lib-common.sh` — cross-platform helpers (`with_lock`, `check_tmux_session`, `sanitize_tmux_input`).
- `state/fleet-state.json` — real-time bot availability.
- `state/dispatch-log.jsonl`, `state/report-back.jsonl` — audit ledgers.
- `state/ironclad-runs/` — scratch directory persistence (fleet-mode only).

## Architecture

```
               /ironclad (clauDNA SKILL.md)
               Subagent-only. No fleet concepts.
                         │
                         ▼
              ┌──────────────────┐
              │ Subagent Dispatch │
              │                  │
              │ Agent tool ×N    │
              │ (parallel)       │
              │ /tmp scratch dir │
              │ retry on fail    │
              └────────┬─────────┘
                       │
                       ▼
             ┌────────────────────────────┐
             │   Shared Aggregation Layer  │
             │                            │
             │  Read result.md from       │
             │    lenses/*/               │
             │  Deduplicate               │
             │  Sort by severity          │
             │  Collapse prior comments   │
             │  Post merged findings      │
             │  Convergence check         │
             └────────────────────────────┘


  Fleet Override (claudlobby compositor injection)
  ────────────────────────────────────────────────
  For fleet bots, the compositor injects a
  fleet-dispatch-capability protocol into CLAUDE.md
  that overrides /ironclad's subagent dispatch
  with fleet dispatch (tmux, fleet-state.json,
  BOTREPORT collection, retry on different worker).

  The SKILL.md in clauDNA never sees this — it's
  a runtime override at the composed CLAUDE.md level.
```

### Scratch Directory

**Subagent mode (default):**
```
/tmp/ironclad-<YYYYMMDD-HHMMSS>/
  source.md
  lenses/<lens>/result.md
```
Ephemeral. No `dispatch.md` (dispatch is in-process, not serialized). Cleaned up after aggregation completes, or left for debugging on failure.

**Fleet mode (compositor-injected override):**
```
$CLAUDLOBBY_ROOT/state/ironclad-runs/<pr>-<timestamp>/
  source.md
  lenses/<lens>/dispatch.md
  lenses/<lens>/result.md
```
Persisted for audit trail. Cleanup is human/cron responsibility.

### Subagent Dispatch Pattern

Each lens runs as a `general-purpose` subagent (not Explore — subagents need the Write tool to emit results to the scratch dir). The launch prompt follows `adversarial-review`'s established pattern:

```
Read skills/<lens>/SKILL.md
Apply skill with --dispatch to: <PLAN_PATH>
Write result to: <RESULT_PATH>
Operate non-interactively (no EnterPlanMode, no AskUserQuestion).
Emit structured markdown per skills/_shared/contracts/lens-result-contract.md.
```

The subagent writes its result to `lenses/<lens>/result.md` in the scratch dir. The orchestrator (main `/ironclad` context) never reads the full result into its own context — it reads only frontmatter (first 15 lines) to check `status` and `severity`, then passes the file path to the aggregation phase.

## Phases

### Phase 3a: Move SKILL.md to clauDNA (subagent-only)
**✅ COMPLETE** — `skills/ironclad/SKILL.md` exists, subagent-only, dispatch preamble and mode-indicator both present in the shipped skill text.

**Purpose:** Create `/ironclad` as a subagent-only skill in clauDNA. The SKILL.md describes the core algorithm: classify PR, create scratch dir, dispatch lenses as subagents, collect results, aggregate, post to PR, check convergence. No fleet concepts.

**Deliverables:**
1. `skills/ironclad/SKILL.md` in clauDNA — subagent-only skill definition.
2. Updated frontmatter: `name: ironclad`, `description: "Use when..."`, `argument-hint`, `allowed-tools`, `requires`.
3. `requires:` field declaring `gh` CLI dependency.
4. **Pre-flight checks** at skill entry:
   - `gh auth status` — verify GitHub CLI is authenticated before proceeding. Fail with a clear error if not.
   - **Dispatch preamble (protocol override hook):** "Before dispatching lenses, check if your CLAUDE.md contains a `fleet-dispatch-capability` protocol. If so, follow it instead of the subagent dispatch below." This is a generic override directive — zero fleet concepts. It makes the compositor protocol override explicit rather than relying on implicit LLM instruction priority.
5. **Mode indicator:** At dispatch time, emit a visible line: "Dispatching N lenses via [fleet|subagent] mode." Include this in the PR comment header and any Telegram post. If `FLEET_STATE_PATH` is set but no fleet dispatch protocol is detected, emit a warning: "FLEET_STATE_PATH is set but no fleet dispatch protocol found — falling back to subagent mode."
6. The 9-phase procedure adapted for subagent dispatch:
   - Phase 1 (Classify PR): unchanged. Includes transitive reference reading (if the plan links to other files, read those too and include in source.md).
   - Phase 2 (Scratch dir): `/tmp/ironclad-<timestamp>/` location. Cycle is always `1` in v1 — no prior-run scanning in `/tmp/`. Prior comment minimization (Phase 8) is skipped when cycle is 1.
   - Phase 3 (Identify executors): skip — subagents are always available.
   - Phase 4 (Dispatch): launch `general-purpose` Agent per lens with `run_in_background: true`. All applicable lenses in parallel (Fork F2 locked: full parallel).
   - Phase 5 (Collect): sequential collection via task completion notifications. Read frontmatter only.
   - Phase 6 (Retry): retry once on failure. No alternative worker — same machine, fresh subagent.
   - Phase 7 (Aggregate): unchanged — read `result.md` files, dedup, sort by severity.
   - Phase 8 (Post to PR): unchanged — single aggregated comment via `gh pr comment`. Prior comment minimization skipped when cycle is 1 (subagent mode v1). All 6 lens statuses updated to "Active" in the lens selection table.
   - Phase 9 (Convergence): blockers + forks (plan PRs) or blockers only (implementation PRs). Fork state is determined by scanning PR comments for `[FORK-LOCK FN]` and `[FORK-REOPEN FN]` patterns — this is self-contained in the SKILL.md, no external protocol needed. The `decision-fork-lifecycle` protocol in fleet contexts adds richer fork management but the basic convergence check is built into the skill.

**Size:** M

### Phase 3b: --auto mode
**✅ COMPLETE** — `--auto` present in `skills/ironclad/SKILL.md` argument-hint and structured-result emission.

**Purpose:** `--auto` must work in subagent mode for machine-consumable output.

**Changes:**
1. Structured JSON result shape: identical to current fleet mode (`outcome`, `artifacts`, `summary`, `next`, `errors` fields).
2. No `report-back.sh` call — subagent mode has no manager to report to. The structured JSON is emitted as final output.
3. Callers (other skills, automation) parse the JSON directly.

**Size:** S

### Phase 3c: Fleet dispatch protocol in claudlobby
**UNVERIFIABLE FROM THIS REPO** — `library/protocols/fleet-dispatch-capability.md` would live in the sibling claudlobby repo, not here. clauDNA's `skills/ironclad/SKILL.md` does carry its side of the contract (the dispatch-preamble override hook and mode indicator), so the clauDNA half of this integration is confirmed complete.

**Purpose:** Create a `fleet-dispatch-capability` protocol in claudlobby that, when composed into a fleet bot's CLAUDE.md, overrides `/ironclad`'s default subagent dispatch with fleet dispatch. This is the mechanism that preserves current fleet behavior without putting fleet concepts into clauDNA.

**Deliverables:**
1. `library/protocols/fleet-dispatch-capability.md` in claudlobby — a composed protocol that:
   - Describes how to override `/ironclad`'s subagent dispatch with fleet dispatch when `FLEET_STATE_PATH` is set.
   - References `$CLAUDLOBBY_ROOT/lib/dispatch-task.sh` for tracked dispatch.
   - References `$CLAUDLOBBY_ROOT/lib/report-back.sh` for structured reporting.
   - Describes fleet scratch dir location (`$CLAUDLOBBY_ROOT/state/ironclad-runs/`), cycle numbering, `dispatch.md` serialization.
   - Describes `[BOTREPORT]` collection, timeout via `OBSERVABILITY_DISPATCH_DEADLINE`, retry on different worker.
   - References `$FLEET_STATE_PATH` for worker selection (idle workers, round-robin).
2. Add `fleet-dispatch-capability` to the manager bot's `protocols:` list in fleet.yaml.
3. Verify via `claudlobby generate` that the protocol appears in the manager bot's composed CLAUDE.md.

**How it works at runtime:** The composed CLAUDE.md contains both the clauDNA `/ironclad` skill (subagent-only) and the fleet-dispatch-capability protocol (fleet override). When the bot reads both, the protocol's instructions to "use fleet dispatch when `FLEET_STATE_PATH` is set" take precedence over the skill's default subagent path. This is the same mechanism by which report-back, context-management, and telegram-routing protocols augment skill behavior in fleet contexts.

**Size:** M

### Phase 3d: Backwards compatibility validation
**UNVERIFIABLE FROM THIS REPO** — requires a live fleet bot invocation to confirm empirically; cannot be checked via static docs audit.

**Purpose:** Verify that the migration is seamless for both standalone and fleet users.

**Validation checklist:**
1. Standalone: invoke `/ironclad` without `FLEET_STATE_PATH`. Lenses run as subagents. Results aggregate. PR comment posted.
2. Fleet: invoke `/ironclad` with `FLEET_STATE_PATH` and fleet-dispatch-capability protocol in CLAUDE.md. Lenses dispatch to workers via tmux. Identical behavior to pre-migration.
3. `--auto` emits correct structured JSON in both contexts.
4. Convergence check works (forks + blockers for plan PRs).
5. `claudlobby generate` produces a valid manager CLAUDE.md with both the skill and the protocol.

**Size:** S

### Phase 3e: Remove /ironclad from claudlobby
**UNVERIFIABLE FROM THIS REPO** — this is a claudlobby-side deletion; clauDNA has no visibility into whether it happened.

**Purpose:** Clean removal of the skill from claudlobby after clauDNA version is shipped and validated.

**Deliverables:**
1. Delete `library/skills/ironclad/SKILL.md` from claudlobby.
2. Update any claudlobby documentation that references `library/skills/ironclad/`.
3. Verify `claudlobby validate` and `claudlobby generate` pass cleanly.

**This is a separate PR in the claudlobby repo.** Lands after Phase 3a-3b are merged in clauDNA, fleet-dispatch-capability protocol is added (Phase 3c), and Phase 3d validation passes.

**Size:** S

## Decision Forks

### Fork F1: Single SKILL.md vs two separate skills

**Context:** Should `/ironclad` be one skill in clauDNA, or two skills (`/ironclad` in clauDNA for subagent mode, `/ironclad-fleet` in claudlobby for fleet mode)?

**Options:**

**(a) Single SKILL.md in clauDNA (subagent-only)** — One skill, one name. Fleet behavior comes from compositor-injected protocol, not a separate skill. The user invokes `/ironclad` regardless of context.

**(b) Two separate skills** — `/ironclad` in clauDNA (subagent-only), `/ironclad-fleet` in claudlobby (fleet-only). Each is simpler but the aggregation/convergence logic is duplicated.

**Lean:** (a) — Single SKILL.md.

**Rationale:** The aggregation layer (Phases 7-9: deduplicate, post to PR, convergence check) is identical in both modes. Duplicating it across two skills violates "consolidate, don't fork." The compositor protocol augments the single skill with fleet capability — same pattern as other protocols. The user experience is simpler: `/ironclad` always works.

**Risk of (b):** Two skills that do the same thing but diverge over time. Bug fixes need to land in two places. The aggregation logic, the most complex part, would be maintained in parallel.

**Status:** locked
**Ratifier:** Human
**Evidence:** [Locked by owner](https://github.com/Claudfather/clauDNA/pull/140#issuecomment-4614718970) — /ironclad cycle 1 review, all lenses unanimous on (a). Ratified 2026-06-03.

### Fork F2: Subagent dispatch parallelism

**Context:** In subagent mode, should all applicable lenses run in parallel or sequentially?

**Options:**

**(a) Parallel (all lenses at once)** — Launch all applicable lenses as background subagents simultaneously. Fastest wall-clock time. Higher resource consumption. Matches fleet behavior (fleet dispatches all lenses in parallel).

**(b) Sequential (one lens at a time)** — Launch, collect, launch next. Slowest wall-clock time. Lowest resource consumption. Simpler error handling.

**(c) Batched parallelism** — Launch lenses in batches of 3. Balances speed and resource consumption.

**Lean:** (a) — Full parallel.

**Rationale:** The lenses are independent — no lens depends on another's output. The orchestration guide explicitly recommends `run_in_background: true` for independent Agent launches. Resource consumption is bounded: at most 7 subagents, each running a focused single-lens review. Context pressure is on the subagents, not the orchestrator.

**Risk of (a):** On resource-constrained machines, 7 parallel Claude contexts might be slow. Mitigation: this is the standalone path — standalone users typically have adequate resources. Fleet users on constrained hardware use fleet mode, which distributes load across workers.

**Status:** locked
**Ratifier:** Human
**Evidence:** [Locked by owner](https://github.com/Claudfather/clauDNA/pull/140#issuecomment-4614718970) — /ironclad cycle 1 review, lenses aligned. Ratified 2026-06-03.

## Prior Decisions (from PR #141 /ironclad review)

The dispatch abstraction framework plan (PR #141) was reviewed by /ironclad cycle 1 (6/6 lenses). Three findings drove a rescoping decision:

1. **Fleet concepts in clauDNA rejected.** `fleet-dispatch.md` inside clauDNA put claudlobby-specific concepts (tmux, BOTREPORT, fleet-state.json) in a standalone plugin — unacceptable. Decision: fleet dispatch is a claudlobby concern, injected at composition time.
2. **Framework scope reduced.** The framework was sized for N consumers but N=1 today. first-principles lens recommended inline branching over a 3-doc framework. Owner agreed.
3. **`subagent-dispatch.md` dropped.** Duplicated `orchestration-guide.md` §§1-3,6. Cross-reference suffices.

PR #141 closed. The rescoped approach folds into this plan as Phase 3c (fleet-dispatch-capability protocol in claudlobby). No standalone dispatch abstraction plan needed.

## Companion Plans

- `documentation/archive/2026-06-01-forge-ironclad-plan-hardening-ecosystem.md` — master plan defining Phases 1-4 (archived 2026-07-06, fully shipped). This plan details Phase 3.
- `documentation/archive/2026-06-02-phase2-ironclad-lens-skills.md` — Phase 2 plan (all lens skills, shipped; archived 2026-07-06).
- Phase 4 (convergence UX, multi-cycle automation) depends on this migration completing. Not yet planned.

## Dependencies

| Dependency | Blocks | Risk Level |
|-----------|--------|------------|
| All 6 lens skills merged to clauDNA main | Phase 3a (dispatch needs lenses to dispatch to) | None — shipped |
| `lens-result-contract.md` (PR #132, merged) | All phases — canonical contract | None — shipped |
| `SKILL_CONTRACT.md` CI validation | Phase 3a — new skill must pass CI | None — exists |
| `gh` CLI for PR diff/comment operations | All phases — `/ironclad` reads PRs and posts comments | Low — widely available |
| claudlobby `lib/dispatch-task.sh`, `lib/report-back.sh` | Phase 3c fleet protocol — referenced by path | None — exists, stable |
| `FLEET_STATE_PATH` env var in fleet bot.conf | Phase 3c fleet protocol — detection signal | None — compositor sets this |
| clauDNA plugin installed on fleet bots | Phase 3e — bots need the plugin for `/ironclad` | Low — already a fleet dependency |
| `orchestration-guide.md` | Phase 3a — subagent dispatch patterns | None — exists |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Compositor-injected protocol doesn't cleanly override SKILL.md subagent dispatch | Medium — fleet bots might run subagents instead of fleet dispatch | Mitigated by dispatch preamble in SKILL.md: explicit "check for fleet-dispatch-capability protocol before dispatching" directive. Plus mode indicator emitted at dispatch time. Plus warning when FLEET_STATE_PATH set but no protocol detected. Validate empirically in Phase 3d. |
| Subagent mode resource consumption on constrained machines | Low — 7 parallel subagents might be slow | This is the standalone path. Users on constrained hardware use fleet mode. Subagent users have a single machine with normal resources. |
| Fleet dispatch references claudlobby `lib/` scripts by absolute path | Medium — path breaks if env var is wrong | `$CLAUDLOBBY_ROOT` is always set in fleet bot.conf. References use `$CLAUDLOBBY_ROOT/lib/...`, not hardcoded paths. |
| Removing `/ironclad` from claudlobby breaks fleets that haven't updated the clauDNA plugin | Medium — old skill symlink disappears, new plugin skill not yet available | Phase 3e (claudlobby removal) lands AFTER clauDNA version is bumped and fleets have updated. Explicit validation step in Phase 3d. |
| Subagent mode can't do multi-cycle hardening (no persistent scratch dir) | Low — standalone users typically run once | v1 sets `cycle: 1`. Multi-cycle support can be added later by persisting scratch dirs to a project-local path. |

## Validation Strategy

| Criterion | How to Verify |
|-----------|---------------|
| `skills/ironclad/SKILL.md` passes `scripts/validate-skills.py` | CI: validator runs on PR |
| `/ironclad` works in subagent mode | Manual: invoke `/ironclad` without fleet context, against a plan PR with known issues. Verify lenses run as subagents, results aggregate, PR comment is posted. |
| `/ironclad` works in fleet mode after migration | Manual: verify fleet-dispatch-capability protocol is composed into manager CLAUDE.md. Invoke `/ironclad`. Verify lenses dispatch to workers via tmux. Identical behavior to pre-migration. |
| `--auto` emits correct structured JSON | Manual: invoke with `--auto`. Parse JSON output, verify schema matches current format. |
| Convergence check works in subagent mode | Manual: run against a plan PR with decision forks. Verify fork state is read, convergence correctly determined. |
| claudlobby `generate` still works after removing `library/skills/ironclad/` | Manual: run `claudlobby generate`, verify manager bot has `/ironclad` via the clauDNA plugin and fleet-dispatch-capability protocol is composed. |
| No regression in existing lens skills | CI: full test suite passes |
| Scratch dir created in correct location | Manual: check `/tmp/ironclad-*` in subagent mode, `$CLAUDLOBBY_ROOT/state/ironclad-runs/` in fleet mode. |
| Protocol override empirically validated | Manual: spin up a test bot with both the clauDNA `/ironclad` skill and the fleet-dispatch-capability protocol. Invoke `/ironclad`. Verify fleet dispatch activates (lenses dispatched via tmux, not subagents). |
| Mode indicator emitted | Manual: verify PR comment header includes "Dispatching N lenses via [fleet|subagent] mode" in both contexts. |
| Fleet.yaml skill removal safe | Manual: check if any bots list `skills: [ironclad]` in fleet.yaml. If so, verify they still get `/ironclad` via the clauDNA plugin after `library/skills/ironclad/` is removed. |

## Complexity and Sequencing

| Phase | Size | Depends on | Parallel with |
|-------|------|-----------|---------------|
| 3a. Move SKILL.md to clauDNA (subagent-only) | M | — | 3c |
| 3b. --auto mode | S | 3a | 3c |
| 3c. Fleet dispatch protocol in claudlobby | M | — | 3a, 3b |
| 3d. Backwards compat validation | S | 3a, 3b, 3c | — |
| 3e. Remove from claudlobby | S | 3d validated | — |

**Critical path:** 3a → 3b → 3d → 3e (clauDNA side); 3c can develop in parallel (claudlobby side).

**Sequencing:** Phase 3a must land first in clauDNA (the SKILL.md must exist). Phase 3b depends on 3a (--auto depends on the dispatch backend). Phase 3c is independent — it's in a different repo (claudlobby) and can develop in parallel with 3a and 3b. Phase 3d is a validation gate that requires all three prior phases. Phase 3e lands last (claudlobby removal).

**Recommended PR structure:**
1. **PR 1 (clauDNA):** Phases 3a + 3b — move SKILL.md (subagent-only), adapt --auto. One PR because they modify the same file.
2. **PR 2 (claudlobby):** Phase 3c — fleet-dispatch-capability protocol. Can land in parallel with PR 1.
3. **PR 3 (claudlobby):** Phase 3e — remove old skill. Lands after PR 1 merged, PR 2 merged, Phase 3d validation passes.

**Total effort:** 2 M + 3 S. Reduced from original scope (1 L + 2 M + 3 S) by eliminating the dual-dispatch branching complexity from the SKILL.md.

## Adversarial Review Findings (Self-Audit)

- [x] **Protocol override mechanism untested.** The compositor-injected fleet-dispatch-capability protocol overriding the SKILL.md's subagent default is the core architectural bet. This pattern is used by other protocols (report-back, context-management) but has never been used to override a skill's dispatch mechanism. Phase 3d explicitly validates this.
- [x] **No automated tests for protocol composition.** The validation strategy is manual. Acceptable for v1 — the test matrix is small (2 modes × 2 PR types). Automated validation can be added to `scripts/validate-skills.py` later.
- [x] **Subagent fallback not observable.** Resolved: Phase 3a now includes a mode indicator ("Dispatching N lenses via [fleet|subagent] mode") and an explicit warning when FLEET_STATE_PATH is set but no fleet dispatch protocol is detected.
- [ ] **Multi-cycle hardening not supported in subagent mode.** v1 limitation. Standalone users run `/ironclad` once per PR. Fleet users get multi-cycle via persistent scratch dirs. Acceptable tradeoff for v1.
