---
title: "Dispatch Abstraction Framework for clauDNA"
type: plan
status: draft
owner: astrid
tags: [dispatch, orchestration, subagent, fleet, clauDNA, claudlobby]
created: 2026-06-03
updated: 2026-06-03
---

# Dispatch Abstraction Framework for clauDNA

## Goal

Build a generic dispatch framework so clauDNA skills can transparently dispatch work in two modes: subagent dispatch (default, standalone — any Claude Code instance) and fleet dispatch (when running inside a claudlobby fleet). The immediate consumer is `/ironclad` (migrating from claudlobby to clauDNA, PR #140), but the framework serves any skill that needs to fan out work to multiple executors.

This aligns with clauDNA's PROJECT_MISSION.md principle of "no hosted dependencies for the user" — subagent mode works everywhere with zero fleet infrastructure, while fleet mode activates automatically when the environment provides it.

## Current State

### Subagent dispatch (clauDNA)

- `/adversarial-review` (`skills/adversarial-review/SKILL.md`) — Phase 5 "Multi-Reviewer Mode" spawns 5 parallel `general-purpose` subagents via the Agent tool, each writing findings to `/tmp/adversarial-review-<timestamp>/<reviewer>.md`. The 10th Man Rule spawns a 6th Contrarian if all five agree. Orchestrator synthesizes findings after collection.
- `orchestration-guide.md` (`skills/_shared/orchestration-guide.md`) — covers scratch dir patterns (`/tmp/<skill>-<timestamp>/research/`), research-agent-to-disk pattern, plan-agent-to-disk pattern, context window management (§6). Uses `general-purpose` subagents (not Explore — they lack Write tool).
- `lens-result-contract.md` (`skills/_shared/contracts/lens-result-contract.md`) — structured markdown result format (YAML frontmatter + severity-tagged body) for `--dispatch` mode output. Producer: any lens skill. Consumer: `/ironclad`.
- The subagent pattern is well-established but not formalized as a reusable dispatch reference. Each skill re-implements the spawn/collect/retry cycle inline.

### Fleet dispatch (claudlobby)

- `/ironclad` (`library/skills/ironclad/SKILL.md`) — full fleet dispatch cycle:
  1. Creates scratch dir at `state/ironclad-runs/<pr-number>-<timestamp>/`
  2. Reads `$FLEET_STATE_PATH` for idle workers (`status == "idle"`, `current_task == null`)
  3. Writes dispatch file per lens to `<scratch>/lenses/<lens>/dispatch.md`
  4. Two-step tmux send-keys: `tmux send-keys -t <worker> "set +H; cat $DISPATCH_FILE | claude"` + `sleep 0.3` + `tmux send-keys -t <worker> Enter`
  5. Workers write results to `<scratch>/lenses/<lens>/result.md`
  6. Monitors for `[BOTREPORT]` completion signals
  7. Retries failed lenses on different idle workers (max 1 retry, never same worker)
  8. Aggregates results from disk, deduplicates, posts to PR
- `dispatch.md` (`library/protocols/dispatch.md`) — `[BOTCOMMAND]` format, two-step tmux send-keys pattern, `[BOTREPORT]` collection, `dispatch-task.sh` tracked dispatch with deadlines.
- This pattern is battle-tested but lives entirely in claudlobby. A clauDNA skill wanting fleet dispatch must know about tmux, fleet-state.json, `[BOTREPORT]` — concepts foreign to the plugin ecosystem.

### What doesn't exist

- No unified dispatch abstraction that skills reference.
- No execution context detection (skills don't know if they're in a fleet).
- No way for a clauDNA skill to say "dispatch these N tasks" without choosing a specific mode.
- No compositor mechanism to inject fleet dispatch capability into bot CLAUDE.md.
- No `_shared/dispatch-modes/` directory.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│ Skill (e.g., /ironclad, /adversarial-review)         │
│                                                      │
│  "I need to dispatch 5 review tasks in parallel"     │
│                                                      │
│  → reads _shared/dispatch-modes/execution-context.md │
└───────────────────────┬──────────────────────────────┘
                        │
                   ┌────┴────┐
                   │ Mode?   │
                   └────┬────┘
                   │         │
         ┌─────────┘         └──────────┐
         ▼                              ▼
┌──────────────────┐          ┌──────────────────┐
│ FLEET_STATE_PATH │          │ No fleet env     │
│ is set + file    │          │ vars detected    │
│ exists           │          │                  │
└────────┬─────────┘          └────────┬─────────┘
         ▼                             ▼
┌──────────────────┐          ┌──────────────────┐
│ fleet-dispatch   │          │ subagent-dispatch │
│                  │          │                   │
│ - Read fleet-    │          │ - Agent tool with │
│   state.json     │          │   general-purpose │
│ - Select idle    │          │ - Scratch dir at  │
│   workers        │          │   /tmp/<skill>/   │
│ - dispatch-      │          │ - Parallel launch │
│   task.sh        │          │   run_in_bg: true │
│ - tmux send-keys │          │ - Collect results │
│ - [BOTREPORT]    │          │   from disk       │
│   monitoring     │          │ - Retry on fail   │
│ - Retry on       │          │                   │
│   different bot  │          │                   │
└──────────────────┘          └──────────────────┘
```

### Key design principle

The SKILL.md never contains dispatch mode logic. The skill says "dispatch these tasks" and references `execution-context.md`, which determines how. This means:

1. **clauDNA standalone users** — execution-context.md detects no fleet → subagent-dispatch.md pattern → works everywhere.
2. **Fleet bots** — compositor injects fleet dispatch protocol → execution-context.md detects fleet → fleet-dispatch.md pattern → leverages idle workers across the fleet.
3. **Skill authors** — reference execution-context.md once, get both modes for free.

### Where fleet-dispatch.md lives

`fleet-dispatch.md` lives in clauDNA `_shared/dispatch-modes/` alongside the other two docs. It describes the generic fleet dispatch pattern (worker selection, tmux send-keys, BOTREPORT collection). Standalone users can see this file but are never directed to follow it — `execution-context.md` only routes to it when `FLEET_STATE_PATH` is set.

The compositor injects a **protocol** into fleet bots' CLAUDE.md that provides runtime-specific details (script paths, fleet-state schema, env var semantics). `fleet-dispatch.md` references "the fleet dispatch protocol in your CLAUDE.md" for these details, keeping itself portable and free of hardcoded claudlobby paths.

## Phases

### Phase 1: Execution Context Detection

Create `skills/_shared/dispatch-modes/execution-context.md` — the entry point for any skill that needs to dispatch work.

#### 1a. Detection logic

Check environment variables in order:

1. `FLEET_STATE_PATH` — path to fleet-state.json. If set and file exists at that path → fleet mode available.
2. `CLAUDLOBBY_ROOT` — claudlobby installation root. Confirms fleet infrastructure is present.
3. `BOT_NAME` — the current bot's identity. Required for fleet dispatch (self-exclusion from worker pool).

All three must be set for fleet mode. Missing any one → subagent mode.

#### 1b. Mode branching template

The doc provides a standard branching pattern that skills copy:

```
## Dispatch Mode

Check execution context per `skills/_shared/dispatch-modes/execution-context.md`:

- If fleet mode available → follow `skills/_shared/dispatch-modes/fleet-dispatch.md`
- Otherwise → follow `skills/_shared/dispatch-modes/subagent-dispatch.md`
```

#### 1c. Fallback guarantee

Subagent mode ALWAYS works — it requires only the Agent tool, which every Claude Code instance has. Fleet mode is an optimization. If fleet dispatch fails at runtime (no idle workers, tmux error, timeout), the skill should fall back to subagent dispatch with a warning rather than failing entirely.

#### 1d. Task definition contract

Both modes share a common task definition shape so skills don't need mode-specific task descriptions:

```markdown
## Dispatch Task
- **name:** <task identifier, e.g., "align-to-mission-lens">
- **prompt:** <the full prompt for the executor>
- **result_path:** <where the executor writes its output>
- **result_format:** <reference to contract, e.g., lens-result-contract.md>
- **timeout:** <max seconds, default 1800>
```

This shape is consumed by both `subagent-dispatch.md` (as Agent tool prompt + scratch dir path) and `fleet-dispatch.md` (as dispatch file content + result path).

**Files created:** `skills/_shared/dispatch-modes/execution-context.md`

### Phase 2: Subagent Dispatch Reference Pattern

Create `skills/_shared/dispatch-modes/subagent-dispatch.md` — the generalized subagent dispatch pattern extracted from `/adversarial-review` and `orchestration-guide.md`.

#### 2a. Scratch directory setup

Follow `orchestration-guide.md` §1: `/tmp/<skill>-<timestamp>/tasks/`. No Bash `mkdir` — Write tool creates parents automatically. The `tasks/` subdirectory (not `research/`) distinguishes dispatch scratch from research scratch.

#### 2b. Subagent spawning

For each dispatch task:
- Launch a `general-purpose` subagent via the Agent tool (not Explore — Explore lacks Write).
- Pass the task prompt directly as the Agent `prompt` parameter.
- Set `run_in_background: true` for parallel execution.
- Include the result path in the prompt: "Write your result to `<scratch>/tasks/<task-name>/result.md`".

Maximum parallelism: launch ALL subagents in a single message with multiple Agent tool calls. The underlying system handles parallel execution.

#### 2c. Result collection

Follow `orchestration-guide.md` §6: collect completions ONE AT A TIME via sequential TaskOutput calls. Each subagent returns a 2-4 line summary (not the full result). Full results stay on disk at the result paths.

The orchestrator reads results from disk ONLY for aggregation/synthesis. Never load full results into the orchestrator's context window.

#### 2d. Retry on failure

If a subagent fails (returns error or doesn't write a result file):
1. Spawn a new `general-purpose` subagent with the same prompt. Max 1 retry per task.
2. If retry also fails, mark the task as failed and proceed with partial results.
3. Report partial coverage in the skill's output (e.g., "4/5 lenses completed").

#### 2e. Concrete example

A 5-way parallel dispatch (mirrors `/adversarial-review` Phase 5):

```
1. Define 5 tasks with unique names, prompts, and result paths
2. Launch 5 Agent calls in one message with run_in_background: true
3. Collect completions via TaskOutput, one at a time
4. Read result files from /tmp/<skill>-<timestamp>/tasks/*/result.md
5. Aggregate and synthesize
```

**Relationship to orchestration-guide.md:** This document is dispatch-focused (spawn, collect, retry, aggregate). `orchestration-guide.md` covers broader orchestration concerns (research-to-disk, plan-to-disk, context management, archive, permissions). The two complement each other. A skill doing research → planning → dispatch would reference `orchestration-guide.md` for phases 1-2 and `subagent-dispatch.md` for the dispatch phase.

**Files created:** `skills/_shared/dispatch-modes/subagent-dispatch.md`

### Phase 3: Fleet Dispatch Reference Pattern

Create `skills/_shared/dispatch-modes/fleet-dispatch.md` — the generalized fleet dispatch pattern extracted from `/ironclad` and the claudlobby dispatch protocol.

#### 3a. Worker selection

1. Read `$FLEET_STATE_PATH` (JSON file at the path specified by the env var).
2. Filter for workers where `status == "idle"` AND `current_task == null`.
3. Exclude self (`BOT_NAME`) from the pool.
4. Sort by `last_idle_since` (longest idle first — reduces dispatch collision when multiple orchestrators run concurrently).
5. If no idle workers available → fall back to subagent dispatch (per `execution-context.md` fallback guarantee).

#### 3b. Scratch directory

Use `$CLAUDLOBBY_ROOT/state/<skill>-runs/<run-id>/` for fleet-persistent state. NOT `/tmp/` — fleet scratch dirs must survive bot restarts and be accessible to other bots in the fleet.

`<run-id>` format: `<context-id>-<YYYYMMDD-HHMMSS>` (e.g., `pr-142-20260603-143022`).

Create one subdirectory per task: `<scratch>/tasks/<task-name>/dispatch.md` (the prompt) and `<scratch>/tasks/<task-name>/result.md` (where the worker writes output).

#### 3c. Dispatch file and tmux send-keys

For each task:

1. Write the dispatch prompt to `<scratch>/tasks/<task-name>/dispatch.md`. Include:
   - The `[BOTCOMMAND]` header per the dispatch protocol in the bot's CLAUDE.md.
   - The task prompt.
   - The expected result path: `<scratch>/tasks/<task-name>/result.md`.
   - The expected result format (reference to contract).
   - Instructions to run `report-back.sh <bot-id> completed "<task-name> complete"` on completion.

2. Two-step tmux send-keys (critical — prevents keystroke race):
   ```bash
   tmux send-keys -t <worker> "set +H; cat <dispatch-file> | claude"
   sleep 0.3
   tmux send-keys -t <worker> Enter
   ```
   The `set +H;` prefix disables bash history expansion (prevents `!` mangling). The split text/Enter with 0.3s pause prevents TUI keystroke swallowing.

3. Use `dispatch-task.sh` (at `$CLAUDLOBBY_ROOT/lib/dispatch-task.sh`) for tracked dispatch with deadline logging to `state/dispatch-log.jsonl`.

#### 3d. Result collection via [BOTREPORT]

Workers report completion via `report-back.sh`, which sends a structured `[BOTREPORT]` message into the manager's tmux session:

```
[BOTREPORT] <bot> | completed | <task-name> complete | skill:<skill-name>
```

The orchestrator monitors for these reports. When all tasks have reported (or timed out), proceed to aggregation.

Timeout: `$OBSERVABILITY_DISPATCH_DEADLINE` from `bot.conf` (default 1800s). After timeout, mark the task as timed-out.

#### 3e. Retry strategy

On task failure:
1. Select a DIFFERENT idle worker (never retry on the same worker — the failure may be worker-specific).
2. Write a new dispatch file. Re-dispatch via tmux send-keys.
3. Max 1 retry per task. If retry fails, mark as failed and proceed with partial results.

#### 3f. Concrete example

A 4-way parallel dispatch to fleet workers (mirrors `/ironclad` Phases 4-6):

```
1. Read fleet-state.json → find 4 idle workers
2. Write 4 dispatch files to state/<skill>-runs/<run-id>/tasks/*/dispatch.md
3. dispatch-task.sh to each worker with deadline
4. Monitor for [BOTREPORT] from each worker
5. On completion: read result.md from each task dir
6. On failure: retry on different worker (1 attempt)
7. Aggregate results from all task dirs
```

**Files created:** `skills/_shared/dispatch-modes/fleet-dispatch.md`

### Phase 4: Compositor Injection

Update claudlobby to inject fleet dispatch capability into bot CLAUDE.md.

#### 4a. Fleet dispatch capability protocol

Create `library/protocols/fleet-dispatch-capability.md` in claudlobby. Content:

- **Declaration:** "This bot has fleet dispatch capability. Skills that dispatch work will automatically use fleet mode when they detect `FLEET_STATE_PATH`."
- **Available env vars:** `FLEET_STATE_PATH` (path to fleet-state.json), `CLAUDLOBBY_ROOT` (claudlobby root), `BOT_NAME` (this bot's identity).
- **Available scripts:**
  - `$CLAUDLOBBY_ROOT/lib/dispatch-task.sh` — tracked dispatch with deadline logging.
  - `$CLAUDLOBBY_ROOT/lib/report-back.sh` — structured `[BOTREPORT]` emission.
- **Fleet-state schema:** The expected structure of `fleet-state.json` (bots array with name, status, current_task, last_idle_since fields).
- **Reference:** "For the full fleet dispatch pattern, see `skills/_shared/dispatch-modes/fleet-dispatch.md` in clauDNA."

This protocol is behavioral guidance: it tells the bot what fleet dispatch means and what tools are available. It complements the `fleet-dispatch.md` reference doc in clauDNA, which describes the generic pattern.

#### 4b. fleet.yaml integration

No new fleet.yaml fields or compositor code changes needed. The existing `protocols:` list in fleet.yaml handles injection. Fleet operators add `fleet-dispatch-capability` to the protocols list for bots that orchestrate dispatch:

```yaml
bots:
  ari:
    protocols:
      - report-back
      - context-management
      - fleet-dispatch-capability  # ← new
```

Worker bots (those receiving dispatched work, not orchestrating it) don't need this protocol — they already understand `[BOTCOMMAND]` via the existing dispatch protocol.

**Files created:** `library/protocols/fleet-dispatch-capability.md` (claudlobby)
**Files modified:** none (fleet.yaml changes are fleet-specific, not committed)

### Phase 5: Skill Integration Pattern

Define how skills reference the dispatch framework and update one existing skill as proof-of-concept.

#### 5a. Reference pattern for SKILL.md

A skill that dispatches work includes this in its procedure:

```markdown
## Dispatch

For parallel dispatch, determine the execution mode per
`skills/_shared/dispatch-modes/execution-context.md`:

- Fleet mode (FLEET_STATE_PATH set) → `skills/_shared/dispatch-modes/fleet-dispatch.md`
- Subagent mode (default) → `skills/_shared/dispatch-modes/subagent-dispatch.md`

Define each dispatch task using the task definition shape from execution-context.md §1d.
```

The skill defines WHAT to dispatch (task names, prompts, result formats). The dispatch-modes docs handle HOW.

#### 5b. Proof of concept: /adversarial-review

Update `skills/adversarial-review/SKILL.md` Phase 5 (Multi-Reviewer Mode) to reference the dispatch framework instead of inline subagent patterns:

**Before:** Phase 5 contains ~40 lines describing how to spawn 5 parallel Explore subagents, create scratch dirs, collect results.

**After:** Phase 5 defines 5 dispatch tasks (one per reviewer lens) and references `execution-context.md` for mode detection and dispatch execution. The subagent spawning details move to `subagent-dispatch.md`.

The behavioral outcome is identical — `/adversarial-review` still spawns 5 parallel subagents in standalone mode. The change is structural: dispatch logic is now referenced, not inlined.

#### 5c. Future consumer: /ironclad migration (PR #140)

When `/ironclad` migrates from claudlobby to clauDNA (PR #140), it will:
1. Define its lens dispatch tasks using the task definition shape.
2. Reference `execution-context.md` for mode detection.
3. In fleet mode: follow `fleet-dispatch.md` (dispatch lenses to idle workers via tmux).
4. In standalone mode: follow `subagent-dispatch.md` (dispatch lenses to subagents).

This plan is a prerequisite for PR #140. The framework must be merged before the migration begins.

**Files modified:** `skills/adversarial-review/SKILL.md`

### Phase 6: Validation and Documentation

#### 6a. Contract validation

Run `python3 scripts/validate-skills.py` after Phase 5 modifications. Verify no SKILL_CONTRACT.md violations.

#### 6b. Behavioral verification

Invoke `/adversarial-review` on a test plan after the Phase 5 update. Verify:
- 5 parallel subagents spawn correctly.
- Results collected from scratch dir.
- Findings synthesized as before.
- No behavioral regression.

#### 6c. Compositor verification

After Phase 4, run `claudlobby --fleet <fleet> generate` with `fleet-dispatch-capability` in a bot's protocols list. Verify:
- Fleet dispatch protocol section appears in generated CLAUDE.md.
- Env vars referenced correctly.
- Script paths use `$CLAUDLOBBY_ROOT` (no hardcoded paths).

#### 6d. Documentation

- Update `CHANGELOG.md` with the dispatch framework addition.
- Add cross-reference from `orchestration-guide.md` to `dispatch-modes/` directory.
- No README changes needed (dispatch-modes is internal infrastructure, not a user-facing skill).

**Files modified:** `CHANGELOG.md`, `skills/_shared/orchestration-guide.md` (cross-reference only)

## Decision Forks

### Fork F1: Directory Structure

- **Context:** Where do the dispatch mode reference documents live in clauDNA?
- **Options:**
  - **(a)** `_shared/dispatch-modes/` — new subdirectory with three docs: `execution-context.md`, `subagent-dispatch.md`, `fleet-dispatch.md`. Purpose-built for the framework.
  - **(b)** `_shared/contracts/dispatch-*.md` — co-locate with existing contracts (`lens-result-contract.md`, `synthesis-contract.md`). Naming: `dispatch-execution-context.md`, `dispatch-subagent.md`, `dispatch-fleet.md`.
  - **(c)** `_shared/` top level — place directly alongside `orchestration-guide.md`. Same naming as (b) but no subdirectory.
- **Lean:** **(a)** — `_shared/dispatch-modes/`. The dispatch framework is a cohesive unit (three docs that cross-reference each other), not standalone contracts. `contracts/` has a specific purpose: result schemas for `--dispatch` mode output. Dispatch modes are orthogonal — they describe HOW to dispatch, not the result format. A dedicated subdirectory is discoverable and follows the existing pattern of purpose-scoped subdirectories (`contracts/`, `subagent-prompts/`).
- **Ratifier:** Human
- **Status:** open
- **Evidence:** Existing `_shared/` structure uses purpose-scoped subdirectories: `contracts/` for result schemas, `subagent-prompts/` for dispatch prompt templates. `dispatch-modes/` follows this established pattern.

### Fork F2: Compositor Injection Scope

- **Context:** How does claudlobby inject fleet dispatch capability into a bot's CLAUDE.md?
- **Options:**
  - **(a)** Protocol — create `library/protocols/fleet-dispatch-capability.md`. Composed into the Protocols section of CLAUDE.md like other protocols (report-back, context-management). Contains runtime-specific details: script paths, fleet-state schema, env var semantics. Skills' `fleet-dispatch.md` references this protocol for runtime specifics.
  - **(b)** Resource — create `library/resources/fleet-dispatch-reference.md`. Composed into the Resources section. Purely informational: "here's what fleet dispatch means and what's available." No behavioral directives.
  - **(c)** Inline compositor generation — the compositor generates fleet dispatch instructions directly from fleet.yaml fields (e.g., a new `dispatch_mode:` field). No library file; content is template-generated.
  - **(d)** No compositor injection — `fleet-dispatch.md` in clauDNA is fully self-contained. It uses env vars directly (`$FLEET_STATE_PATH`, `$CLAUDLOBBY_ROOT/lib/dispatch-task.sh`) without referencing CLAUDE.md content. Fleet bots work because the env vars are set in `bot.conf`.
- **Lean:** **(a)** — protocol. Fleet dispatch is behavioral guidance ("when dispatching in fleet mode, use these scripts, follow this flow"). That's what protocols are for. Resources (b) are informational-only and don't provide actionable patterns. Inline generation (c) is brittle, hard to test, and can't be versioned independently. Option (d) works but means `fleet-dispatch.md` must hardcode script path patterns relative to `$CLAUDLOBBY_ROOT` — a protocol provides these as explicit, verified references and documents the fleet-state schema so the skill doesn't have to rediscover it. The protocol also serves as the opt-in mechanism: only bots with `fleet-dispatch-capability` in their protocols list get fleet dispatch instructions.
- **Ratifier:** Human
- **Status:** open
- **Evidence:** Existing protocols (report-back, context-management, telegram-routing) all provide behavioral guidance with runtime-specific paths and schemas. Fleet dispatch follows the same pattern.

### Fork F3: Execution Context Detection

- **Context:** How does a skill determine whether fleet dispatch is available?
- **Options:**
  - **(a)** Env var only — check `FLEET_STATE_PATH`. If set and the file exists at that path → fleet mode. Simple, already the convention in `/ironclad`. Supplementary vars (`CLAUDLOBBY_ROOT`, `BOT_NAME`) provide runtime details but the primary gate is `FLEET_STATE_PATH`.
  - **(b)** Structured context file — a `dispatch-context.json` written by the compositor at `generate` time. Contains: `{ "mode": "fleet", "workers": [...], "scripts": {...}, "capabilities": [...] }`. Read once at dispatch time.
  - **(c)** Capability discovery — skill probes for available tools and scripts at runtime. Checks: does `dispatch-task.sh` exist? Is tmux available? Is fleet-state.json readable? Progressive discovery builds a capability profile.
- **Lean:** **(a)** — env var only. `FLEET_STATE_PATH` is already the convention in `/ironclad` (claudlobby). It's the simplest detection: one env var check + one file existence check. The compositor already sets env vars in `bot.conf` — no new mechanism needed. Option (b) adds a new file that must stay in sync with `bot.conf` (two sources of truth). Option (c) is fragile — tmux could be installed but not configured for fleet use, scripts could exist but be non-functional.
- **Ratifier:** Human
- **Status:** open
- **Evidence:** `/ironclad` (claudlobby) already uses `$FLEET_STATE_PATH` as the sole fleet detection mechanism. Env var detection is a zero-dependency pattern.

## Companion Plans

- `documentation/planning/2026-06-01-forge-ironclad-plan-hardening-ecosystem.md` — the parent ecosystem plan. This dispatch framework is infrastructure that enables Phase 3 of that plan (`/ironclad` migration from claudlobby to clauDNA).
- `documentation/planning/2026-06-02-phase2-ironclad-lens-skills.md` — the lens skills plan. The six lens skills are the first dispatch consumers via `/ironclad`.
- PR #140 (`docs/ironclad-migration-plan` branch) — the `/ironclad` migration itself. This framework is a prerequisite; PR #140 should not proceed until this plan is implemented and merged.

## Dependencies

| Dependency | Blocks | Risk Level |
|-----------|--------|------------|
| `orchestration-guide.md` (exists, stable) | Phase 2 (subagent patterns extracted from here) | Low |
| `/adversarial-review --dispatch` (PR #130, merged) | Phase 2 (pattern extraction), Phase 5 (proof of concept) | Low |
| `/ironclad` SKILL.md (claudlobby, exists) | Phase 3 (fleet pattern extraction) | Low |
| `dispatch.md` protocol (claudlobby, exists) | Phase 3 (BOTCOMMAND format reference) | Low |
| Claudlobby compositor protocol injection (battle-tested) | Phase 4 (fleet dispatch protocol injection) | Low |
| `lens-result-contract.md` (PR #132, merged) | Phase 1d (result format reference) | Low |
| SKILL_CONTRACT.md CI validation | Phase 5 (modified skill must pass) | Low |
| PR #140 /ironclad migration (not started) | None — this plan is a prerequisite for #140, not blocked by it | N/A |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Subagent and fleet dispatch patterns diverge over time | Medium — skills switching modes hit stale patterns | `execution-context.md` is the single entry point. Both mode docs share the same task definition shape (§1d). Version them together in the same PR when updating dispatch semantics. |
| `fleet-dispatch.md` in clauDNA references claudlobby-specific concepts unfamiliar to standalone users | Low — standalone users never follow it (no env vars trigger it) | Keep `fleet-dispatch.md` focused on the generic pattern. Runtime specifics (script paths, fleet-state schema) live in the injected protocol, not hardcoded in the doc. |
| Existing `/adversarial-review` regresses when migrated to dispatch framework reference | Medium — working skill breaks | Phase 5b is a behavioral-preservation refactor. Phase 6b verifies identical behavior. The subagent pattern is extracted, not changed. |
| PR #140 scope creep if framework isn't well-defined | High — ironclad migration depends on this | This plan ships BEFORE PR #140 starts. The framework defines the exact interface /ironclad will consume. |
| Compositor injection adds config burden for fleet operators | Low — one protocol name to add per bot | Uses existing `protocols:` list in fleet.yaml. No new fields, no new compositor code. Operator adds one line to their yaml. |

## Validation Strategy

| Criterion | How to Verify |
|-----------|---------------|
| `execution-context.md` correctly detects fleet mode | Set `FLEET_STATE_PATH` env var, create a dummy fleet-state.json. Verify detection returns fleet mode. Unset var, verify subagent mode. |
| `execution-context.md` falls back on missing fleet-state file | Set `FLEET_STATE_PATH` to nonexistent path. Verify fallback to subagent mode (not crash). |
| `subagent-dispatch.md` patterns match existing `/adversarial-review` behavior | Invoke `/adversarial-review` after Phase 5 update. Verify 5 parallel subagents spawn, write to scratch dir, findings synthesized identically. |
| `fleet-dispatch.md` patterns match existing `/ironclad` behavior | Diff `fleet-dispatch.md` against `/ironclad` SKILL.md Phases 4-6. All steps accounted for: worker selection, dispatch file, tmux send-keys, BOTREPORT, retry, timeout. |
| Shared task definition shape works for both modes | Define a sample task per §1d. Verify it can be consumed by both `subagent-dispatch.md` (as Agent prompt) and `fleet-dispatch.md` (as dispatch file content) without modification. |
| Compositor injects fleet dispatch protocol | `claudlobby --fleet <fleet> generate` with `fleet-dispatch-capability` in bot's protocols. Grep generated CLAUDE.md for "Fleet Dispatch Capability" section. |
| `/adversarial-review` SKILL.md passes contract validation | `python3 scripts/validate-skills.py` after Phase 5 modification. |
| No orphaned references | Grep all three dispatch-modes docs for cross-references. Every file path mentioned must exist. Every cross-reference must be bidirectional. |

## Adversarial Review Findings

Self-audit findings from the plan author (pre-handoff stress test per `/forge` Phase 3 step 8):

- [x] **"Never sees" vs "never follows" clarification.** The task states "standalone user's clauDNA install never even sees fleet dispatch instructions." Since `fleet-dispatch.md` is a file in the plugin, standalone users CAN see it. The plan clarifies: "never sees" means "never gets directed to follow" — `execution-context.md` only routes to fleet-dispatch.md when env vars are present. No user is told to read fleet-dispatch.md without fleet context.
- [x] **Overlap with orchestration-guide.md.** `subagent-dispatch.md` extracts patterns from `orchestration-guide.md` §§1-3,6. Potential duplication. Plan addresses this: `subagent-dispatch.md` is dispatch-focused (spawn, collect, retry). `orchestration-guide.md` covers broader orchestration (research-to-disk, plan-to-disk, archive). The two complement each other; the relationship is documented in Phase 2.
- [ ] **No automated tests for reference docs.** The framework is documentation, not code. Validation is manual (invoke skills, check behavior). Acceptable given the nature of the deliverable, but any future code components (e.g., a dispatch helper script) should have tests.
- [ ] **Fallback path not exercised by proof of concept.** Phase 5 updates `/adversarial-review` (subagent-only skill). The fleet→subagent fallback path is documented but not exercised until `/ironclad` migrates (PR #140). Flag for PR #140 validation checklist.
- [x] **Task definition shape is new.** §1d introduces a common task definition contract. This is a net-new abstraction — verified it doesn't conflict with existing contracts (`lens-result-contract.md` defines result format, not task input; `synthesis-contract.md` defines inter-skill communication, not dispatch tasks).

## Complexity and Sequencing

| Phase | Size | Depends on | Parallel with |
|-------|------|-----------|---------------|
| 1. execution-context.md | S | — | 2, 3 |
| 2. subagent-dispatch.md | M | — | 1, 3 |
| 3. fleet-dispatch.md | M | — | 1, 2 |
| 4. Compositor injection (claudlobby) | M | 3 | 5 |
| 5. Skill integration (clauDNA) | S | 1, 2 | 4 |
| 6. Validation + docs | S | 1, 2, 3, 4, 5 | — |

**Critical path:** Phases 1+2+3 (parallel, all S/M) → Phase 4 or 5 (parallel across repos) → Phase 6

**Maximum parallelism:** Phases 1, 2, 3 are fully independent (three docs, no cross-dependencies during creation). Phases 4 (claudlobby) and 5 (clauDNA) can run in parallel after their dependencies complete.

**Repo split:** Phases 1, 2, 3, 5, 6 → clauDNA. Phase 4 → claudlobby. Assign by repo familiarity.

**Estimated total effort:** 2 M + 3 S + 1 M = 3 M + 3 S. All phases are documentation + one skill refactor. No new code, no new tests beyond CI validation.
