---
title: "Phase 2: Ironclad Review Lens Skills"
type: plan
status: draft
owner: astrid
tags: [planning, skills, ironclad, lenses, clauDNA, dispatch]
created: 2026-06-02
updated: 2026-06-02
ironclad-cycle: 1
---

# Phase 2: Ironclad Review Lens Skills

## Goal

Build the six review lens skills that `/ironclad` (claudlobby) dispatches to harden plans. Each skill is a single-bot, stateless lens that reads a plan and emits structured markdown findings via `--dispatch` mode. Together they give `/ironclad` a multi-angle review surface: first-principles reasoning, mission alignment, codebase extension hygiene, historical precedent, structural health, and cost-benefit analysis.

This is Phase 2 of the plan-hardening ecosystem defined in `documentation/planning/2026-06-01-forge-ironclad-plan-hardening-ecosystem.md`. Phase 1 (foundation — `/forge` hardening, decision-fork-lifecycle, pr-comment-hygiene, plan-synthesis protocols) is shipped. This plan is itself the first dogfood input to `/ironclad`.

## Current State

### Shipped (Phase 1)

- `/forge` skill (`skills/forge/SKILL.md`) — plan scaffolding with decision forks, phasing, `--auto` mode.
- `/adversarial-review --dispatch` — updated to emit markdown with YAML frontmatter (PR #130, merged). This is the contract all lens skills must follow.
- `decision-fork-lifecycle` protocol (claudlobby PR #362) — fork state machine, ratification, convergence gate.
- `pr-comment-hygiene` protocol (claudlobby PR #362) — finding format, verdict format, thread discipline, convergence check.
- `plan-synthesis` protocol (claudlobby PR #361) — dedup, conflict resolution, severity aggregation, iteration limits, partial coverage.

### Exists and Relevant

- `/adversarial-review` (`skills/adversarial-review/SKILL.md`) — the reference implementation for a dispatch-mode lens. Seven internal lenses (First Principles, Gaps, Edge Cases, Alternatives, Implementation Risk, Press Release, Counter-Plan), parallel subagent dispatch, structured markdown output.
- `skills/_shared/orchestration-guide.md` — subagent patterns, scratch dirs, context management.
- `skills/_shared/pre-handoff-checklist.md` — adversarial review gate for all planning skills.
- `skills/_shared/subagent-prompts/adversarial-chain.md` — dispatch prompt template (updated for markdown format).
- `SKILL_CONTRACT.md` — CI-enforced skill structure rules.

### Does Not Exist Yet

- No `/first-principles`, `/align-to-mission`, `/extension-check`, `/precedent-check`, `/plan-health-audit`, or `/cost-benefit` skills.
- `skills/_shared/contracts/lens-result-contract.md` — shared output contract for all lenses (in progress, PR #132).

## Architecture

```
/ironclad (claudlobby)
    │
    ├── dispatches to worker bots via tmux ──┐
    │                                         │
    │   ┌─────────────────────────────────────┤
    │   │                                     │
    ▼   ▼                                     ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ first-   │ │ align-to │ │extension │ │precedent │ │  plan-   │ │  cost-   │
│principles│ │ -mission │ │ -check   │ │ -check   │ │health-   │ │ benefit  │
│          │ │          │ │          │ │          │ │ audit    │ │          │
└────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
     │             │            │             │            │             │
     └─────────────┴────────────┴──────┬──────┴────────────┴─────────────┘
                                       │
                              markdown with YAML
                              frontmatter per lens
                                       │
                                       ▼
                              /ironclad synthesis
                              (plan-synthesis protocol)
```

All six skills live in clauDNA. Each:
- Accepts a plan file path and `--dispatch` flag
- Is non-interactive in `--dispatch` mode (no Plan Mode, no AskUserQuestion)
- Emits markdown with YAML frontmatter per `skills/_shared/contracts/lens-result-contract.md` (PR #132)
- Uses `lens: <skill-name>` in frontmatter so `/ironclad` can identify which lens produced the output
- Uses the canonical severity vocabulary: `critical` > `major` > `minor` > `info`
- Uses the closed concern area vocabulary: `architecture`, `scope`, `dependencies`, `compatibility`, `performance`
- Uses body sections: Blockers, Risks, Gaps, Questions, Observations (omit empty sections)

**Dispatch context for codebase-dependent lenses:** `/extension-check` and `/precedent-check` require access to the target repo, not just the plan document. When `/ironclad` dispatches these lenses, the dispatch context must include a `repo` field (local path or GitHub `owner/repo`) so the lens can clone or navigate to the codebase. Plan-only lenses (`/first-principles`, `/align-to-mission`, `/plan-health-audit`, `/cost-benefit`) ignore this field.

### Shared Dispatch Contract

All six lenses emit the format defined in `skills/_shared/contracts/lens-result-contract.md` (PR #132). That file is the single source of truth for frontmatter fields, body sections, severity vocabulary, and concern area tags. Each lens sets `lens: <skill-name>` in frontmatter; all other structure is identical across lenses.

### Concern Area Vocabulary (closed set)

Every finding is tagged with one concern area from this closed set:

| Concern Area | Meaning |
|-------------|---------|
| `architecture` | Structural design, abstractions, component boundaries, extension points |
| `scope` | Completeness, missing sections, tangential work, scope creep |
| `dependencies` | External/internal dependencies, version constraints, coupling |
| `compatibility` | Migration, backwards compat, naming conventions, existing pattern alignment |
| `performance` | Runtime efficiency, engineering efficiency, cost-to-benefit, resource usage |

Each skill's phase description declares its primary and secondary concern areas from this set. Findings outside these five areas must be mapped to the closest match — do not invent new concern area tags.

## Phases

All six skills are independent — fully parallelizable across engineers. Each phase below is one skill.

### Phase 2a: `/first-principles`

**Purpose:** Step back from the plan's proposed solution and ask whether the right problem is being solved the right way. Catches plans that extend suboptimal foundations, introduce accidental complexity, or miss simpler alternatives.

**Procedure:**
1. Read the plan document.
2. Extract the stated problem (Goal section).
3. Restate the problem in one sentence without referencing the proposed solution.
4. Apply these checks:
   - **Is this the right problem?** Could the underlying need be met differently, or is it not a real need?
   - **Would you build this from scratch?** No legacy, no sunk cost. Does that match what the plan proposes?
   - **Accidental complexity?** Could the same outcome be achieved with dramatically less machinery?
   - **Via negativa** — what should be *removed* from this plan?
   - **Confident assumptions** — which assumptions does the plan treat as obvious? Those are the blind spots.
5. If the plan extends an existing system, assess whether the foundation itself is sound. Building on a flawed foundation compounds the flaw.
6. Emit findings.

**Concern areas:** Primarily `architecture`, `scope`. Secondary: `dependencies`, `compatibility`.

**Relationship to `/adversarial-review`:** The adversarial-review skill includes "Lens 1: First Principles" as one of seven internal lenses. `/first-principles` extracts and deepens this into a standalone skill with its own `--dispatch` output, making it independently dispatchable by `/ironclad` to a dedicated bot. This gives first-principles reasoning a full context window instead of sharing one with six other lenses.

### Phase 2b: `/align-to-mission`

**Purpose:** Check whether every phase and deliverable in the plan serves the project's stated mission. Catches scope creep, tangential work, and misaligned success metrics.

**Procedure:**
1. Read the plan document.
2. Locate the project mission using this fallback hierarchy:
   1. `PROJECT_MISSION.md` in the repo root — the canonical source.
   2. `README.md` mission/purpose section — extract the north-star statement.
   3. GitHub repo description — the one-liner from the repo settings.
   4. `CLAUDE.md` purpose/description section — the repo's self-description for Claude Code.
   If none of these yield a usable mission statement, emit `outcome: blocked` with `blocker_description` explaining what's needed and which sources were checked.
3. For each phase/deliverable in the plan:
   - Does this serve the north star?
   - Is it tangential (useful but not mission-critical)?
   - Is it misaligned (actively pulls away from the mission)?
   - Are success metrics aligned with mission metrics?
4. Check the plan as a whole: does the aggregate work advance the mission, or does the sum of individually-reasonable phases drift from the target?
5. Emit findings with per-phase alignment assessments.

**Concern areas:** Primarily `scope`. Secondary: `architecture` (when misalignment stems from structural choices).

**Interactive mode (no `--dispatch`):** Present findings in chat with a summary table showing phase-by-phase alignment status (aligned / tangential / misaligned). For each concern, include options, a lean, and a rationale — advisory output that helps the developer reason about alignment, not just a verdict.

### Phase 2c: `/extension-check`

**Purpose:** For every new component a plan proposes, check whether an existing abstraction should be extended instead. Catches parallel implementations, duplicate patterns, and codebase sprawl before they happen.

**Procedure:**
1. Read the plan document.
2. Identify every new component the plan proposes to create (new files, new classes, new modules, new endpoints, new schemas).
3. For each proposed component, search the codebase:
   - Is there an existing abstraction (factory, registry, base class, shared pattern) it should extend?
   - Are there parallel implementations that should be consolidated?
   - Does the proposal introduce a second path where one could serve both needs?
4. Check naming conventions — does the proposed name follow existing patterns or introduce a new convention?
5. Emit findings per proposed component.

**Concern areas:** Primarily `architecture`, `compatibility`. Secondary: `scope`, `dependencies`.

**Codebase access:** This skill requires reading the target codebase, not just the plan. In `--dispatch` mode, it uses Explore subagents to search for existing patterns matching each proposed component.

### Phase 2d: `/precedent-check`

**Purpose:** Search git history, closed PRs, closed issues, and planning directories for prior art related to the plan's scope. Surface what was tried before and whether the current plan learns from or repeats past mistakes.

**Procedure:**
1. Read the plan document. Extract key topics, component names, and the problem being solved.
2. Search for prior art:
   - `git log --all --oneline --grep="<keywords>"` for relevant commits
   - `documentation/planning/` and `documentation/archive/` for related plans
   - Closed issues and PRs (via `gh issue list --state closed` and `gh pr list --state closed`) matching the plan's scope
   - `shared/knowledge/` or equivalent knowledge directories
3. For each precedent found:
   - What was tried?
   - Did it succeed or fail? Why?
   - Does the current plan learn from this precedent or repeat the same approach?
   - Is there abandoned code or infrastructure from the prior attempt still in the codebase?
4. Identify areas with no precedent — genuinely novel ground where the plan can't learn from history.
5. Emit findings.

**Concern areas:** Primarily `architecture`, `scope`. Secondary: `compatibility` (when prior art reveals migration/transition issues).

**External tool dependency:** Requires `gh` CLI for issue/PR search. Graceful degradation: if `gh` is unavailable, search only git history and local files, and note the reduced coverage in the output.

### Phase 2e: `/plan-health-audit`

**Purpose:** Structural completeness check — is the plan document itself well-formed, complete, and ready for implementation? This is the convergence gate for `/ironclad`.

**Procedure:**
1. Read the plan document.
2. Check structural completeness:
   - All mandatory `/forge` sections present (Goal, Current State, Architecture, Phases, Decision Forks, Companion Plans, Dependencies, Risks, Validation Strategy, Complexity and Sequencing)
   - Frontmatter complete (title, type, status, owner, tags, created, updated)
   - All phases have effort sizes (S/M/L/XL)
   - Complexity and Sequencing table matches the phases defined
3. Check decision fork health:
   - Every fork has options, a lean, and a ratifier
   - Fork status is documented (open/locked)
   - Count open vs locked forks
4. Check risk coverage:
   - Every risk has an impact level and a mitigation
   - Count unmitigated risks
5. Check validation criteria:
   - Each criterion is objectively testable (not vague like "works correctly")
6. Check cross-references:
   - Companion plan references point to documents that exist
   - Dependency references are valid
7. Emit findings. Include a health summary in the output: `ready` (all checks pass), `needs-work` (non-blocking issues), or `blocked` (structural problems preventing implementation).

**Concern areas:** Primarily `scope` (missing sections, incomplete coverage). Secondary: `architecture` (when structural issues reflect design gaps).

**Scope boundary:** This skill checks the plan *document*, not the codebase. It does not verify that file paths mentioned in the plan exist or that code references are accurate — that's `/extension-check`'s job. `/plan-health-audit` answers "is this document structurally ready to implement?" not "is this document factually correct?"

### Phase 2f: `/cost-benefit`

**Purpose:** For each phase in a plan, estimate engineering cost, operational cost, opportunity cost, and expected benefit. Help prioritize phases and identify low-ROI work that should be cut or deferred.

**Procedure:**
1. Read the plan document.
2. For each phase, assess:
   - **Engineering cost:** Effort estimate based on size (S/M/L/XL), number of files affected, complexity of changes. Express in relative terms (days/weeks), not absolute hours.
   - **Operational cost:** New infrastructure, third-party services, ongoing maintenance burden.
   - **Opportunity cost:** What else could the team build with the same effort? Is this the highest-leverage use of time?
   - **Expected benefit:** User impact, tech debt reduction, risk mitigation, mission alignment.
   - **ROI signal:** critical (must-do) / major (high-value) / minor (nice-to-have) / info (negligible impact).
3. Identify:
   - Phases that could be cut without materially harming the plan's goal
   - Phases that should be reordered for faster time-to-value
   - Phases with disproportionate cost-to-benefit ratio
4. Emit findings with per-phase cost-benefit assessments.

**Concern areas:** Primarily `scope`, `performance` (in the sense of engineering efficiency). Secondary: `dependencies` (when cost stems from dependency chains).

**Severity mapping for ROI:** Findings about low-ROI phases that the plan treats as essential get `major` severity. Reordering suggestions get `minor`. Observations about cost structure get `info`.

## Decision Forks

### Fork F1: Shared Dispatch Contract Location — LOCKED

- **Context:** `/ironclad` needs a shared output contract for all lens skills. The question was whether to use a shared template, per-skill dispatch prompts, or inline construction.
- **Decision:** Shared template at `skills/_shared/contracts/lens-result-contract.md`. No separate `dispatch-prompts/` directory. The contract file defines frontmatter fields, body sections, severity vocabulary, and concern area tags. Each skill's SKILL.md references this contract; `/ironclad` validates output against it.
- **Ratifier:** Human
- **Status:** locked
- **Evidence:** [Locked by human during /ironclad cycle 1.] The six lenses share the exact same output contract (PR #130 format). PR #132 creates the canonical contract file. No per-skill dispatch prompts needed — skill-specific behavior lives in SKILL.md, not the dispatch layer.

### Fork F2: Interactive Mode Shape — LOCKED

- **Context:** Each skill needs both `--dispatch` (non-interactive, structured markdown output) and an interactive mode.
- **Decision:** **(a)** Chat-only interactive mode — but advisory, not just a report. Findings are presented with leans and fork directions. Each concern includes options, a lean, and a rationale explaining why. The interactive output helps a developer reason about the plan, not just read a verdict.
- **Ratifier:** Human
- **Status:** locked
- **Evidence:** [Locked by human during /ironclad cycle 1.] `/adversarial-review` supports both session and github output but `--dispatch` is the primary path for fleet use. Chat-only with advisory framing gives developers actionable guidance without scope creep. `--output github` can be added later without breaking changes.

### Fork F3: `/first-principles` as Standalone vs. Folded into `/adversarial-review` — LOCKED

- **Context:** `/adversarial-review` already includes "Lens 1: First Principles" as one of seven internal lenses. Creating a standalone `/first-principles` skill duplicates this lens.
- **Decision:** **(a)** Standalone `/first-principles`. `/adversarial-review` keeps its internal Lens 1 for single-bot use. Different execution models warrant separate skills: `/adversarial-review` is a comprehensive seven-lens sweep on one bot; `/first-principles` gets a dedicated bot and full context window for fleet-grade depth.
- **Ratifier:** Human
- **Status:** locked
- **Evidence:** [Locked by human during /ironclad cycle 1.] The task dispatch explicitly lists `/first-principles` as a separate skill. The overlap is intentional — same pattern as a general checkup vs. a specialist appointment.

## Companion Plans

- `documentation/planning/2026-06-01-forge-ironclad-plan-hardening-ecosystem.md` — the master plan defining Phases 1-4. This plan details Phase 2.
- Phase 3 (`/ironclad` fleet orchestrator) depends on these lens skills. Not yet planned in detail.

## Dependencies

| Dependency | Blocks | Risk Level |
|-----------|--------|------------|
| `/adversarial-review --dispatch` markdown format (PR #130, merged) | All phases — this is the output contract | None — shipped |
| `skills/_shared/contracts/lens-result-contract.md` (PR #132) | All phases — canonical contract file (Fork F1, locked) | Low — in progress |
| `SKILL_CONTRACT.md` CI validation | All phases — new skills must pass CI | None — exists |
| `skills/_shared/orchestration-guide.md` | Phase 2c, 2d — subagent patterns | None — exists |
| Canonical severity vocabulary (critical/major/minor/info) | All phases — finding severity tags | None — ratified in PR #130 |
| `gh` CLI | Phase 2d (`/precedent-check` PR/issue search) | Low — widely available, graceful degradation if missing |
| `plan-synthesis` protocol (claudlobby PR #361, merged) | Phase 3 consumption of lens outputs | None — shipped |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Lenses produce noisy, low-signal findings that waste reviewer time | High — defeats the purpose | Each skill has a focused scope and strict severity vocabulary. `/plan-health-audit` serves as the convergence gate filtering low-severity noise. Iterate on prompt quality during `/ironclad` dogfooding. |
| Context window pressure when a lens reads a large plan + codebase | Medium — bots hit limits mid-review | `--dispatch` mode is non-interactive (no Plan Mode overhead). `/extension-check` and `/precedent-check` use Explore subagents for codebase search, keeping the main context lean. Other lenses are plan-only and don't read codebase. |
| Six skills in one sprint creates review bottleneck | Medium — PRs pile up waiting for review | All six are fully parallel across engineers. Each skill is self-contained (own SKILL.md, no cross-dependencies). Reviewers can merge independently. |
| `/first-principles` overlaps with `/adversarial-review` Lens 1 | Low — conceptual duplication | Intentional. Different execution models (fleet-dispatched full-context vs. single-bot seven-lens sweep). Documented in Fork F3. |
| Downstream consumer (`/ironclad`) not yet built to parse markdown format | Medium — lenses ship before consumer | The format is ratified (PR #130). `/ironclad` (Phase 3) will be built against this contract. Lenses can be tested standalone via manual `--dispatch` invocation. |
| `/align-to-mission` blocks on repos without any mission source | Medium — many repos lack `PROJECT_MISSION.md` | Fallback hierarchy: `PROJECT_MISSION.md` → `README.md` mission section → GitHub repo description → `CLAUDE.md` purpose. Blocks only when all four are absent. |
| Codebase-dependent lenses receive no repo context | High — `/extension-check` and `/precedent-check` cannot function without codebase access | Dispatch context includes a `repo` field. `/ironclad` must populate it for codebase-dependent lenses. Documented in Architecture section. |

## Validation Strategy

| Criterion | How to Verify |
|-----------|---------------|
| All six skills pass `scripts/validate-skills.py` | CI: validator runs on every PR |
| Each skill's `--dispatch` emits valid markdown with correct YAML frontmatter | Manual test: invoke each skill with `--dispatch` on the Phase 1 plan doc, verify frontmatter fields and body structure |
| Frontmatter `lens:` field matches the skill name | Verify in SKILL.md template and test output |
| Severity vocabulary uses only critical/major/minor/info | Grep SKILL.md bodies for old vocabulary (high/medium/low) — should find zero matches |
| `/extension-check` correctly identifies existing patterns in a codebase | Integration test: run against a plan that proposes duplicating a known existing pattern, verify it surfaces the finding |
| `/precedent-check` finds relevant git history | Integration test: run against a plan in a repo with known prior art, verify precedents are surfaced |
| `/plan-health-audit` correctly identifies incomplete plans | Integration test: run against a plan with missing sections, verify all gaps are flagged |
| `/align-to-mission` correctly identifies tangential phases | Integration test: run against a plan with one phase that clearly doesn't serve PROJECT_MISSION.md |
| Interactive mode presents findings readably in chat | Manual test: invoke each skill without `--dispatch`, verify output is human-friendly |
| No regression in existing skills | CI: full test suite passes |

## Complexity and Sequencing

| Phase | Size | Depends on | Parallel with |
|-------|------|-----------|---------------|
| 2a. `/first-principles` | M | — | 2b, 2c, 2d, 2e, 2f |
| 2b. `/align-to-mission` | M | — | 2a, 2c, 2d, 2e, 2f |
| 2c. `/extension-check` | M | — | 2a, 2b, 2d, 2e, 2f |
| 2d. `/precedent-check` | M | — | 2a, 2b, 2c, 2e, 2f |
| 2e. `/plan-health-audit` | M | — | 2a, 2b, 2c, 2d, 2f |
| 2f. `/cost-benefit` | M | — | 2a, 2b, 2c, 2d, 2e |
| Shared: `lens-result-contract.md` (PR #132) | S | Fork F1 locked ✓ | All phases (needed before `/ironclad` integration, not before individual skill PRs) |

**Critical path:** Any single skill → `/ironclad` integration (Phase 3). All six are on the critical path equivalently since `/ironclad` needs all of them.

**Maximum parallelism:** All six skills are fully independent. Six engineers could build all six simultaneously. The shared contract (Fork F1, locked → PR #132) is in progress and can land alongside or before the skill PRs.

**Estimated total effort:** 6x M-sized skills. Each skill is a SKILL.md with ~200-400 lines of procedural body, no code, no tests beyond CI validation. Comparable to `/adversarial-review` in structure but narrower in scope (one lens vs. seven).
