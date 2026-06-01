---
title: "Build the /forge and /ironclad Plan-Hardening Skill Ecosystem"
type: plan
status: draft
owner: alex
tags: [planning, skills, orchestration, forge, ironclad, claudlobby, clauDNA]
created: 2026-06-01
updated: 2026-06-01
---

# Build the /forge and /ironclad Plan-Hardening Skill Ecosystem

## Goal

Establish a two-layer plan-hardening pipeline: `/forge` (clauDNA) scaffolds structured planning documents with decision forks, and `/ironclad` (claudlobby) orchestrates multi-bot fleet review cycles to harden those plans iteratively. Supporting skills (`/align-to-mission`, `/extension-check`, `/precedent-check`, `/plan-health-audit`, `/cost-benefit`) provide specialized review lenses, while supporting protocols (`decision-fork-lifecycle`, `pr-comment-hygiene`, `plan-synthesis`) govern the workflow. The result: plans that survive contact with reality because they've been stress-tested by multiple agents before a single line of code is written.

This aligns with clauDNA's PROJECT_MISSION.md north star ("curated quality over quantity") by extending the existing autonomy and orchestration infrastructure (v0.4 structured-result contracts, discipline chains, `/implement-plan --auto`) into the planning phase that precedes implementation.

## Current State

### clauDNA (Claudfather/clauDNA)

**Existing planning-adjacent skills:**
- `/forge` (`skills/forge/SKILL.md`) — just written, untracked. Scaffolds multi-section planning docs with decision forks, phasing, validation strategy, risks, and companion plan references. Supports `--output github` and `--auto`.
- `/adversarial-review` (`skills/adversarial-review/SKILL.md`) — stress-tests plans via 7 lenses (First Principles, Gaps, Edge Cases, Alternatives, Implementation Risk, Press Release, Counter-Plan). Has `--dispatch` mode for parallel subagent execution.
- `/weigh-development-paths` (`skills/weigh-development-paths/SKILL.md`) — junction analysis across 7 dimensions. Has `--auto` mode consumed by `/implement-plan`.
- `/implement-plan` (`skills/implement-plan/SKILL.md`) — execution engine with synthesis pass via `/weigh-development-paths --auto`.

**Existing shared infrastructure:**
- `skills/_shared/orchestration-guide.md` — multi-agent coordination patterns (scratch dirs, research→disk→plan agent, context window management).
- `skills/_shared/synthesis-contract.md` — producer/consumer schema between `/weigh-development-paths --auto` and `/implement-plan --auto`.
- `skills/_shared/output-guide.md` — house-style for planning/audit output (frontmatter, issue body skeleton, labels).
- `skills/_shared/subagent-prompts/adversarial-chain.md` — dispatch prompt for chaining `/adversarial-review --dispatch`.

**What doesn't exist yet:**
- No `/align-to-mission`, `/extension-check`, `/precedent-check`, `/plan-health-audit`, or `/cost-benefit` skills.
- No `--auto` structured-result contract for `/forge`.
- No `forge-chain.md` subagent dispatch prompt for orchestrators to invoke `/forge` non-interactively.
- No protocol for decision-fork lifecycle (ratification, locking, evidence trails).

### claudlobby (Claudfather/Claudlobby)

**Existing fleet-level skills:**
- `library/skills/` contains 40 skills focused on fleet operations (dispatch, lifecycle, sweep, briefing, status, etc.).
- No `/ironclad` skill exists.
- No multi-bot review orchestration skill exists — the closest pattern is the dispatch protocol (`library/protocols/dispatch.md`) which routes work from manager to workers.

**Existing orchestration infrastructure:**
- Manager dispatches via `tmux send-keys` to worker sessions.
- Workers report back via `lib/report-back.sh` with structured `[BOTREPORT]` messages.
- `library/protocols/` contains reusable workflow patterns but nothing for iterative plan review.

**What doesn't exist yet:**
- No `/ironclad` fleet-level skill.
- No `decision-fork-lifecycle` protocol.
- No `pr-comment-hygiene` protocol.
- No `plan-synthesis` protocol.

## Architecture

```
                          Human writes rough plan idea
                                    │
                                    ▼
                        ┌───────────────────┐
                        │    /forge          │  clauDNA skill
                        │  (plan scaffold)  │  Produces structured plan
                        └────────┬──────────┘  with decision forks
                                 │
                          Plan PR opened
                                 │
                                 ▼
                        ┌───────────────────┐
                        │   /ironclad       │  claudlobby fleet skill
                        │ (fleet hardening) │  Orchestrates multi-bot
                        └────────┬──────────┘  review cycles
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
           ┌──────────┐  ┌──────────┐  ┌──────────┐
           │ Bot A:   │  │ Bot B:   │  │ Bot C:   │
           │ align-to │  │ extension│  │ precedent│
           │ -mission │  │ -check   │  │ -check   │
           └────┬─────┘  └────┬─────┘  └────┬─────┘
                │              │              │
                └──────────────┼──────────────┘
                               │
                        PR comment threads
                        (per-fork, per-risk)
                               │
                               ▼
                    ┌───────────────────┐
                    │ /plan-health-audit│  clauDNA skill
                    │ (convergence)     │  Checks: all forks locked?
                    └────────┬──────────┘  All risks mitigated?
                             │
                     ┌───────┴───────┐
                     │ Converged?    │
                     │  Yes → merge  │
                     │  No → re-run  │
                     └───────────────┘
```

### Skill Boundaries

| Skill | Lives In | Scope |
|-------|----------|-------|
| `/forge` | clauDNA | Single-bot plan scaffolding |
| `/align-to-mission` | clauDNA | Single-bot mission alignment check |
| `/extension-check` | clauDNA | Single-bot extension-vs-build-new check |
| `/precedent-check` | clauDNA | Single-bot prior-art search |
| `/cost-benefit` | clauDNA | Single-bot cost-benefit analysis |
| `/plan-health-audit` | clauDNA | Single-bot plan convergence check |
| `/ironclad` | claudlobby | Fleet-level multi-bot review orchestration |

**Why the split:** clauDNA skills are single-bot, stateless review lenses — they read a plan and emit structured findings. `/ironclad` is fleet-level — it dispatches those lenses to multiple bots in parallel, collects results, and decides whether to iterate. This follows clauDNA's principle of "no hosted dependencies" and claudlobby's role as the fleet orchestrator.

## Phases

### Phase 1: Foundation — `/forge` Hardening + Decision Fork Protocol (2.5 person-days, ~1 week elapsed)

The `/forge` skill exists but lacks `--auto` mode and a dispatch prompt. The decision-fork-lifecycle protocol doesn't exist. Both are prerequisites for `/ironclad`. Sub-items 1a+1b (clauDNA) can run in parallel with 1c+1d (claudlobby), compressing 2.5 person-days into ~1 week elapsed.

#### 1a. `/forge --auto` Structured-Result Contract

Add `--auto` mode to `/forge` following the existing contract pattern in `skills/_shared/orchestration-guide.md` §10 (Structured Result Shape). The structured-result JSON:

```json
{
  "skill": "forge",
  "outcome": "completed",
  "artifacts": {
    "plan_path": "<path-to-plan-file>",
    "fork_count": N,
    "forks_open": N,
    "phases": N,
    "total_effort_weeks": N,
    "risks_high": N
  },
  "summary": "<1-2 sentence plan summary>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

This enables orchestrators to invoke `/forge` non-interactively and consume its output programmatically.

**Effort:** 0.5 day. Pattern is well-established.

#### 1b. `forge-chain.md` Subagent Dispatch Prompt

Create `skills/_shared/subagent-prompts/forge-chain.md` — a dispatch prompt for orchestrators to invoke `/forge --auto` as a subagent, parallel to the existing `adversarial-chain.md`.

**Effort:** 0.5 day.

#### 1c. Decision Fork Lifecycle Protocol (claudlobby)

Create `library/protocols/decision-fork-lifecycle.md` in claudlobby. Governs:

- **Fork states:** `open` → `leaning` → `locked` (ratified) or `reopened`
- **Ratification:** a human or designated ratifier locks a fork by posting a comment with `[FORK-LOCK F<N>] <chosen option> — <rationale>`
- **Evidence trail:** every locked fork links to the comment/commit where it was ratified
- **Reopen:** any reviewer can reopen a locked fork with new evidence via `[FORK-REOPEN F<N>] <reason>`
- **Convergence gate:** a plan is "ironclad" when all forks are locked and no reopens are pending

**Effort:** 1 day. Protocol design + documentation.

#### 1d. PR Comment Hygiene Protocol (claudlobby)

Create `library/protocols/pr-comment-hygiene.md` in claudlobby. Governs:

- **Thread discipline:** one top-level comment per finding/fork. Responses go in-thread, not as new top-level comments.
- **Verdict format:** `[VERDICT] <approve|request-changes|comment> — <one-line summary>`
- **Fork comment format:** `[FORK F<N>] <option-letter> — <reasoning>` for expressing a preference on a decision fork
- **No orphans:** every comment must be resolved (replied to or marked resolved) before convergence
- **Bot attribution:** comments from review bots include `[<bot-name>]` prefix for traceability

**Effort:** 0.5 day.

### Phase 2: Review Lens Skills (9.5 person-days, ~1.5 weeks elapsed with 2 engineers)

Five new clauDNA skills that each provide a single focused review lens. Each reads a plan (markdown file or PR diff) and emits structured findings. Skills are independent — parallelizable across 2-3 engineers. At 2 engineers, 9.5 person-days compress to ~1.5 weeks elapsed.

#### 2a. `/align-to-mission`

Reads the plan + `PROJECT_MISSION.md` (or repo's equivalent). For each phase/deliverable, checks:
- Does this serve the north star?
- Is anything tangential or scope-creeping?
- Are success metrics aligned with mission metrics?

Output: list of alignment findings (aligned, tangential, misaligned) per phase, with recommendations.

Supports `--auto` for fleet dispatch. Structured result: `{ findings: [{phase, alignment, detail}], overall: "aligned|drift|misaligned" }`.

**Effort:** 2 days.

#### 2b. `/extension-check`

Reads the plan + scans the target codebase. For each new component proposed:
- Is there an existing abstraction it should extend?
- Are there parallel implementations that should be consolidated?
- Does the proposal introduce a second path where one could be consolidated?

This is the anti-fork-bomb lens — catches the #1 cause of codebase sprawl before it happens.

Output: list of extension findings per proposed component.

Supports `--auto`. Structured result: `{ findings: [{component, existing_pattern, recommendation}], parallel_path_count: N }`.

**Effort:** 2 days.

#### 2c. `/precedent-check`

Searches git history, closed PRs, closed issues, and `documentation/planning/` for prior art related to the plan's scope. For each match:
- What was tried before?
- Why did it succeed/fail?
- Does the current plan learn from or repeat past mistakes?

Output: list of precedents with relevance assessment.

Supports `--auto`. Structured result: `{ precedents: [{source, summary, relevance, lesson}], novel_ground: ["<areas with no precedent>"] }`.

**Effort:** 2 days.

#### 2d. `/plan-health-audit`

The convergence checker. Reads a plan (markdown) and checks:
- All decision forks have options, a lean, and a ratifier
- All forks are locked (or flags open ones)
- All risks have mitigations (or flags unmitigated ones)
- All phases have effort estimates
- Validation criteria are testable (not vague)
- No cross-references to non-existent companion plans
- Frontmatter is complete

This is the "is this plan ready to implement?" gate.

Supports `--auto`. Structured result: `{ health: "ready|needs-work|blocked", issues: [{section, issue, severity}], forks_open: N, risks_unmitigated: N }`.

**Effort:** 1.5 days.

#### 2e. `/cost-benefit`

For each phase in a plan, estimates:
- Engineering cost (effort in days/weeks)
- Operational cost (infrastructure, third-party services)
- Opportunity cost (what else could the team build instead?)
- Expected benefit (user impact, tech debt reduction, risk mitigation)
- ROI signal (high/medium/low)

Helps prioritize phases and identify low-ROI work that should be cut.

Supports `--auto`. Structured result: `{ phases: [{phase, cost, benefit, roi}], recommendation: "<cut/reorder suggestions>" }`.

**Effort:** 2 days.

### Phase 3: `/ironclad` Fleet Orchestrator (1.5 weeks)

#### 3a. `/ironclad` Skill (claudlobby)

Create `library/skills/ironclad/SKILL.md` in claudlobby. This is the fleet-level orchestrator.

**Input:** a plan PR URL (from `/forge --output github`).

**Procedure:**
1. Read the plan from the PR diff or the file on the branch.
2. Dispatch review lenses to available worker bots in parallel via `tmux send-keys`:
   - Bot A: `/claudna:align-to-mission --auto <plan-path>`
   - Bot B: `/claudna:extension-check --auto <plan-path>`
   - Bot C: `/claudna:precedent-check --auto <plan-path>`
   - Bot D: `/claudna:cost-benefit --auto <plan-path>`
3. Collect structured results from `[BOTREPORT]` payloads.
4. Post findings as PR comments following `pr-comment-hygiene` protocol.
5. Run `/claudna:plan-health-audit --auto <plan-path>` to check convergence.
6. If converged (all forks locked, all risks mitigated, all findings addressed): post `[IRONCLAD] Plan hardened. Ready for ratification.`
7. If not converged: post summary of open items and notify the human. Wait for fork resolutions, then re-run health audit.

**Dispatch strategy:** use all available worker bots, max 4 parallel dispatches. If fewer bots available, run lenses sequentially on a single bot.

**Effort:** 4 days. Most complexity is in dispatch orchestration and result collection.

#### 3b. Plan Synthesis Protocol (claudlobby)

Create `library/protocols/plan-synthesis.md` in claudlobby. Governs:

- How findings from multiple review lenses are merged into a coherent revision
- Conflict resolution when two lenses disagree (e.g., cost-benefit says cut phase 3, align-to-mission says it's critical)
- How the plan author (or manager) resolves conflicts and locks forks
- Iteration limit: max 3 `/ironclad` cycles before escalating to human for manual resolution

**Effort:** 1 day.

#### 3c. `/ironclad --auto` Mode

Non-interactive mode for programmatic invocation (e.g., from a CI pipeline or higher-level orchestrator). Runs one full review cycle, posts findings, checks convergence, emits structured result:

```json
{
  "outcome": "completed|needs-iteration|blocked",
  "artifacts": {
    "pr_url": "<plan-pr-url>",
    "review_cycle": N,
    "findings_posted": N,
    "forks_open": N,
    "forks_locked": N,
    "converged": true|false
  },
  "summary": "<1-2 sentence result>"
}
```

**Effort:** 1 day (pattern established by Phase 1a).

### Phase 4: Integration + End-to-End Pipeline (1 week)

#### 4a. `/forge` → `/ironclad` Handoff

When `/forge --output github` creates a plan PR, it should emit a suggestion: "Run `/ironclad <pr-url>` for multi-bot fleet review." In `--auto` mode, the structured result includes the PR URL so an orchestrator can chain `/ironclad` automatically.

**Effort:** 0.5 day.

#### 4b. `/ironclad` → `/implement-plan` Handoff

When `/ironclad` declares a plan converged, it should emit a suggestion: "Plan is ironclad. Run `/implement-plan <plan-path>` to execute." In `--auto` mode, the structured result includes the plan path for chaining.

**Effort:** 0.5 day.

#### 4c. End-to-End Pipeline Test

Run the full pipeline on a real planning scenario:
1. `/forge "some real initiative" --output github` → plan PR
2. `/ironclad <pr-url>` → multi-bot review cycle
3. Resolve decision forks from findings
4. `/ironclad <pr-url>` (re-run) → convergence check
5. `/implement-plan <plan-path>` → execution

Verify: findings are accurate, forks lock correctly, convergence detection works, handoffs chain properly.

**Effort:** 2 days (includes fixing issues found).

#### 4d. Documentation + Changelog

- Update `CHANGELOG.md` with new skills and protocols
- Update `README.md` skill inventory
- Add planning ecosystem overview to `documentation/`
- Cross-reference from `skills/_shared/orchestration-guide.md`

**Effort:** 1 day.

## Decision Forks

### Fork F1: Where Do Review Lens Skills Live?

- **Context:** The 5 review lens skills (`/align-to-mission`, `/extension-check`, `/precedent-check`, `/plan-health-audit`, `/cost-benefit`) need a home. They're invoked by individual bots, which suggests clauDNA — but they're designed to be orchestrated by `/ironclad` (claudlobby).
- **Options:**
  - **(a)** All in clauDNA — individual bots get them via plugin install. `/ironclad` dispatches them as `/claudna:<skill> --auto`. Consistent with clauDNA's role as the skill genome.
  - **(b)** All in claudlobby — fleet-level skills dispatched only via `/ironclad`. Tighter coupling to fleet orchestration but breaks clauDNA's "every bot inherits" model.
  - **(c)** Split: generic lenses in clauDNA, fleet-specific orchestration in claudlobby — same as (a) but explicitly acknowledges the dual-repo pattern.
- **Lean:** **(a)** — clauDNA skills, claudlobby orchestration. This follows the existing pattern where `/adversarial-review` lives in clauDNA and can be dispatched by any orchestrator. The lenses are useful standalone (a developer running `/align-to-mission` by hand on a plan) and shouldn't require a fleet.
- **Ratifier:** Human
- **Status:** open
- **Evidence:** Existing pattern: `/adversarial-review` (clauDNA) + `adversarial-chain.md` dispatch prompt. `/implement-plan` (clauDNA) invokes `/weigh-development-paths --auto` (clauDNA).

### Fork F2: Iteration Model — Push vs. Pull

- **Context:** After `/ironclad` posts findings, how does the next review cycle trigger? Does `/ironclad` poll for fork resolutions (push), or does the human/manager re-invoke `/ironclad` when ready (pull)?
- **Options:**
  - **(a)** Pull — human or manager re-invokes `/ironclad <pr-url>` when they've addressed findings and locked forks. Simple, explicit, no background polling.
  - **(b)** Push — `/ironclad` watches the PR for comment resolutions and fork locks, re-runs automatically when all items are addressed. More autonomous but requires persistent state.
  - **(c)** Hybrid — pull by default, push via `--watch` flag that sets up a cron/timer to check periodically.
- **Lean:** **(a)** — pull model. Avoids persistent state complexity. The human decides when the plan is ready for re-review, which preserves the "human merges" principle. The `--auto` mode is already pull (one-shot cycle → result).
- **Ratifier:** Human
- **Status:** open
- **Evidence:** claudlobby's current dispatch model is pull — manager dispatches, worker executes, no background polling.

### Fork F3: Finding Deduplication Across Cycles

- **Context:** If `/ironclad` runs 2+ review cycles, later cycles may re-flag issues that were already addressed. How do we prevent duplicate findings?
- **Options:**
  - **(a)** PR-comment threading — each finding is a top-level comment. On re-run, `/ironclad` reads existing comments and only posts new findings. Resolved findings get a `[RESOLVED]` tag.
  - **(b)** Finding fingerprints — hash each finding by (lens, section, issue-type) and skip known fingerprints on re-run.
  - **(c)** Clean-slate — each cycle posts all findings fresh. Reviewer resolves the old threads manually.
- **Lean:** **(a)** — PR-comment threading with resolved tags. Leverages GitHub's existing comment model. The `pr-comment-hygiene` protocol already mandates one thread per finding, so dedup is a natural extension.
- **Ratifier:** Human
- **Status:** open
- **Evidence:** `pr-comment-hygiene` protocol (Phase 1d) establishes thread-per-finding convention.

### Fork F4: `/plan-health-audit` Scope — Plan-Only vs. Plan-Plus-Codebase

- **Context:** Should `/plan-health-audit` only check the plan document's structural health (forks, risks, effort, frontmatter), or should it also verify claims against the codebase (like `/forge`'s self-audit step 4)?
- **Options:**
  - **(a)** Plan-only — structural health check. Fast, stateless, no codebase access needed. Codebase verification is `/extension-check`'s job.
  - **(b)** Plan-plus-codebase — also verifies factual claims (file paths exist, API endpoints are real). More thorough but overlaps with `/extension-check` and `/forge`'s own self-audit.
- **Lean:** **(a)** — plan-only. Each lens should have a single responsibility. Codebase verification belongs to `/extension-check` (existing patterns) and `/forge`'s self-audit (authoring-time check). `/plan-health-audit` is the convergence gate — "is this document structurally ready?" not "is this document factually correct?"
- **Ratifier:** Human
- **Status:** open
- **Evidence:** Single-responsibility pattern in existing skills: `/adversarial-review` doesn't check code, `/review-pr` doesn't check plans.

## Companion Plans

- `documentation/planning/autonomous-mode-and-orchestration_2026-05-17/` — the v0.4 autonomy rollout plan that established the `--auto` contract, structured-result emission, and discipline chains. This plan extends that foundation into the planning phase.

## Dependencies

| Dependency | Blocks | Risk Level |
|-----------|--------|------------|
| clauDNA `--auto` structured-result contract (v0.4, shipped) | Phase 1a (extend to /forge) | Low — already shipped |
| claudlobby dispatch protocol (`library/protocols/dispatch.md`) | Phase 3a (/ironclad dispatch) | Low — already exists |
| `tmux send-keys` dispatch infra in claudlobby | Phase 3a (parallel bot dispatch) | Low — battle-tested |
| `[BOTREPORT]` report-back protocol | Phase 3a (result collection) | Low — battle-tested |
| SKILL_CONTRACT.md CI validation | Phase 2 (all new skills) | Low — CI enforces automatically |
| `/adversarial-review --dispatch` pattern | Phase 2 (design reference) | Low — shipped in v0.3 |
| Fleet with 2+ worker bots | Phase 3 end-to-end test | Medium — requires active fleet |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Review lens skills produce noisy/low-signal findings | High — defeats the purpose of the ecosystem | Each lens has strict output format with severity ratings. `/plan-health-audit` filters low-severity items from convergence checks. Iterate on prompt quality during Phase 4c testing. |
| Context window pressure from reading large plans + codebase | Medium — bots may hit limits during lens execution | Skills use `--auto` mode which suppresses interactive UI. Large plans: read only the relevant section per lens, not the whole plan. Follow `orchestration-guide.md` scratch-dir pattern. |
| `/ironclad` dispatch fails silently when a bot is busy | Medium — incomplete review cycle | `/ironclad` checks bot availability before dispatch. If a bot is busy, queue the lens or redistribute to another bot. Report partial coverage in structured result. |
| Decision fork protocol is too bureaucratic for small plans | Low — developers skip the process | `/forge` already has a "when to use" gate (multi-phase, multi-person, decision-heavy). Small plans don't need `/ironclad`. The protocol is opt-in. |
| Two-repo coordination (clauDNA + claudlobby) makes releases harder | Medium — version coupling | Phase 1 (clauDNA foundation) ships independently. Phase 3 (claudlobby) depends on specific clauDNA version. Pin `claudna_version` in fleet.yaml. |

## Validation Strategy

| Criterion | How to Verify |
|-----------|---------------|
| `/forge --auto` emits valid structured-result JSON | Unit test: parse output against JSON schema |
| `/forge --output github` creates a well-formed plan PR | Integration test: invoke on a test topic, verify PR has all mandatory sections |
| Each review lens skill passes SKILL_CONTRACT.md validation | CI: `scripts/validate-skills.py` catches violations |
| Each review lens `--auto` emits valid structured result | Unit test: invoke with a sample plan, parse result |
| `/ironclad` dispatches to N bots and collects all results | Integration test: run against a fleet with 2+ workers, verify all lenses execute |
| PR comments follow `pr-comment-hygiene` protocol format | Manual review: check comment format on test PR |
| Decision forks lock/unlock correctly | Manual test: post `[FORK-LOCK F1]` comment, re-run `/plan-health-audit`, verify fork shows as locked |
| End-to-end pipeline completes: `/forge` → `/ironclad` → `/implement-plan` | Integration test: full pipeline on a real planning scenario (Phase 4c) |
| No regression in existing skills | CI: full test suite passes |

## Estimated Effort

| Phase | Person-days | Elapsed (with parallelization) |
|-------|-------------|-------------------------------|
| Phase 1: Foundation (/forge hardening + protocols) | 2.5 days | ~1 week (1a+1b parallel with 1c+1d) |
| Phase 2: Review lens skills (5 new clauDNA skills) | 9.5 days | ~1.5 weeks (2-3 engineers in parallel) |
| Phase 3: /ironclad fleet orchestrator | 6 days | ~1.5 weeks |
| Phase 4: Integration + end-to-end pipeline | 4 days | ~1 week |
| **Total** | **22 person-days** | **~5 weeks elapsed** |

The person-day totals are the sum of sub-item estimates. Elapsed calendar time assumes parallelization: Phase 1 clauDNA work (1a+1b) runs alongside claudlobby protocol work (1c+1d). Phase 2 skills are independent and split across 2 engineers. Phases 1 and 2 can partially overlap (protocol design in Phase 1 doesn't block skill implementation in Phase 2 after 1a/1b are done). Phase 3 requires Phase 1 protocols and Phase 2 skills. Phase 4 requires everything.

## Dispatch Recommendation

**Execution order:**
1. Phase 1a + 1b (clauDNA: `/forge --auto` + dispatch prompt) — unblocks everything
2. Phase 1c + 1d (claudlobby: protocols) — can run in parallel with 2a-2e
3. Phase 2a-2e (clauDNA: review lens skills) — parallelize across engineers, 2-3 at a time
4. Phase 3a-3c (claudlobby: `/ironclad`) — after Phase 1 protocols + Phase 2 skills land
5. Phase 4a-4d (integration) — after Phase 3

**Parallelization:** Phase 2 skills are independent of each other — assign to different engineers. Phase 1c/1d (protocols) can run alongside Phase 2.

**Engineer assignment:** Phase 1-2 (clauDNA skills) suit an engineer familiar with the `--auto` contract and SKILL_CONTRACT.md. Phase 3 (claudlobby `/ironclad`) suits an engineer familiar with fleet dispatch and tmux orchestration.
