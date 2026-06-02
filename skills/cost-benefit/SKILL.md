---
name: cost-benefit
description: "Use when you want to evaluate whether a plan's phases or a PR's changes justify their cost. Assesses engineering effort, maintenance burden, complexity, dependencies, and risk surface against user impact, mission alignment, future enablement, and tech debt reduction. Flags low-ROI work and suggests sequencing by value."
argument-hint: "[plan-or-source-path] [--dispatch]"
---

# Cost-Benefit

For each phase in a plan or change in a PR, assess whether the cost justifies the benefit. Plans accumulate scope that feels productive but delivers diminishing returns. This skill makes cost-benefit trade-offs explicit so low-ROI work can be cut, deferred, or descoped before resources are committed.

**This lens applies to plans, implementation PRs, and mixed PRs.** For plans, it assesses phases. For implementation PRs, it assesses the changes introduced. It does not read the broader codebase beyond what is needed to understand the change — deep codebase analysis is `/extension-check`'s job.

**No time estimates.** This skill uses relative sizing (S/M/L/XL) and qualitative ROI signals, never absolute hours, days, or deadlines. Estimation is the plan author's job; this skill evaluates whether the effort-to-value ratio makes sense.

## Arguments

Parse `$ARGUMENTS` at invocation:

- **First positional arg:** Path to the plan document or PR source file. If omitted, prompt for it.
- `--dispatch`: Non-interactive mode for fleet orchestration. Suppresses all interactive elements (no Plan Mode, no AskUserQuestion). Emits a single markdown document with YAML frontmatter per `skills/_shared/contracts/lens-result-contract.md`. Use this when invoked by `/ironclad` or another orchestrator.

---

## `--dispatch` Mode

When `--dispatch` is passed:

- **Do NOT call `EnterPlanMode`.** The dispatcher owns the lifecycle.
- **Do NOT call `AskUserQuestion`.** No human is present.
- **Do NOT prompt for clarification.** If the source lacks identifiable phases or changes to assess, emit `status: blocked` with a description of what is missing.
- Execute the procedure below silently.
- Emit the structured markdown result as the FINAL output and stop. No text after the result document.

When `--dispatch` is NOT passed, follow the interactive procedure (see Interactive Mode below).

---

## Procedure

### Step 1: Read the Source

Read the plan document or PR source. Identify every unit of work to assess:

- **Plan document:** each phase (and sub-deliverables within phases if they are distinct enough to have different cost-benefit profiles).
- **Implementation PR:** each logical change — new files, new modules, refactored components, added dependencies, new configuration surfaces.
- **Mixed PR:** both plan sections and implementation changes.

If zero assessable units are identified, emit a `completed` result with a single Observation: "No phases or changes identified in the source. Nothing to assess."

### Step 2: Cost Assessment

For each unit of work, evaluate five cost dimensions. Use relative sizing (S/M/L/XL) for each dimension, not absolute numbers.

#### 2a. Implementation Effort

The direct engineering cost to build this.

- What is the stated effort size (S/M/L/XL)? If the plan provides one, start there.
- Does the size feel calibrated? An "S" that touches 8 files across 3 services is likely undersized. An "XL" for a single config change is likely oversized.
- What is the complexity of the changes? Greenfield code vs. modifying hot paths vs. cross-cutting refactors each have different cost profiles at the same nominal size.

#### 2b. Maintenance Burden

The ongoing cost after the work ships.

- Does this introduce new infrastructure, services, or processes that need monitoring?
- Does it add code surface area that future changes must account for?
- Does it create a new abstraction that all future contributors must learn?
- Is the maintenance cost proportionate to the deliverable's lifespan?

#### 2c. Complexity Added

The structural cost to the codebase.

- How many new concepts, abstractions, or indirection layers does this introduce?
- Does it increase coupling between components?
- Does it make the codebase harder for a new contributor to understand?
- Could a simpler design achieve the same outcome?

#### 2d. Dependencies Introduced

The external cost and risk surface.

- New third-party libraries, services, or APIs?
- New internal dependencies between modules or repos?
- Version constraints that limit future upgrades?
- Each dependency is a commitment — assess whether the value justifies the coupling.

#### 2e. Risk Surface

What could go wrong, and what is the blast radius?

- Does this touch data paths, auth flows, or financial logic?
- Does it introduce new failure modes?
- How reversible is this change if it goes wrong?
- Is the risk proportionate to the benefit?

### Step 3: Benefit Assessment

For each unit of work, evaluate four benefit dimensions.

#### 3a. User Impact

Direct value delivered to users (human or bot consumers).

- Does this solve a real user problem? How many users are affected?
- Is the benefit visible and immediate, or deferred and speculative?
- Would users notice or care if this phase were cut?

#### 3b. Mission Alignment

How directly this serves the project's north star.

- Does this advance the mission, or is it adjacent infrastructure?
- Would the mission be materially harmed if this were deferred indefinitely?
- Note: deep alignment analysis is `/align-to-mission`'s job. Here, use alignment as one factor in the cost-benefit equation, not as the sole lens.

#### 3c. Future Enablement

Does this unlock or enable future high-value work?

- Does this lay foundation that multiple future phases depend on?
- Would deferring this create a bottleneck for subsequent work?
- Is the "enablement" concrete (Phase 3 literally depends on this) or speculative ("we might need this someday")?

#### 3d. Tech Debt Reduction

Does this reduce existing maintenance cost or complexity?

- Does it replace a fragile workaround with a proper solution?
- Does it eliminate a known pain point (flaky tests, manual processes, error-prone workflows)?
- Is the debt being paid genuinely harmful, or is it tolerable debt that the team can live with?

### Step 4: ROI Classification

For each unit of work, synthesize the cost and benefit assessments into an ROI signal:

| ROI Signal | Meaning | Typical profile |
|-----------|---------|-----------------|
| **Critical** | Must-do. Benefit is high and the work cannot be deferred. | High user impact or mission-critical; cost is justified regardless of size |
| **High** | Strong value. Benefit clearly outweighs cost. | Moderate-to-high benefit with proportionate cost; enables future work |
| **Moderate** | Reasonable. Benefit exists but cost is non-trivial. | Benefit is real but not urgent; could be deferred without harm |
| **Low** | Questionable. Cost may outweigh benefit. | Small or speculative benefit with disproportionate cost |
| **Negative** | Cut or rethink. Cost clearly exceeds benefit. | High cost with negligible, speculative, or redundant benefit |

### Step 5: Portfolio Analysis

After individual assessments, step back and evaluate the plan as a portfolio:

#### 5a. ROI-Ordered Sequencing

Rank units of work by ROI signal (critical first, then high, moderate, low, negative). Compare this ranking to the plan's stated sequencing. If the plan schedules low-ROI work before high-ROI work, flag it — value should be delivered early.

#### 5b. Cut Candidates

Identify phases that could be cut without materially harming the plan's goal. A phase is a cut candidate when:

- ROI is low or negative
- No high-ROI phase depends on it
- The plan's goal can be achieved without it

#### 5c. The 80% Alternative

For any phase with moderate or lower ROI, ask: is there a simpler alternative that achieves 80% of the benefit at 20% of the cost? This is the most valuable check in the skill — it surfaces phases where the plan over-engineers a solution when a lighter approach would suffice.

#### 5d. Concentration Risk

Is the plan's value concentrated in one or two phases? If Phase 1 delivers 80% of the benefit and Phases 2-5 deliver the remaining 20%, the plan should acknowledge this and consider whether the later phases are worth the investment.

### Step 6: Emit Findings

Assemble findings from Steps 2-5 into the output format. Severity assignments follow the ROI classification:

| Finding type | Severity |
|-------------|----------|
| Negative-ROI phase that the plan treats as essential | `critical` |
| Low-ROI phase with disproportionate cost | `major` |
| Sequencing improvement (high-ROI work blocked behind low-ROI) | `major` |
| 80% alternative available for a moderate-ROI phase | `minor` |
| Cut candidate (low-ROI, no downstream dependencies) | `minor` |
| Cost structure observation (concentration risk, dependency chain costs) | `info` |

Tag each finding with a concern area. This skill's primary concern areas are `scope` and `performance` (in the sense of engineering efficiency, not runtime performance). Secondary: `dependencies` (when cost stems from dependency chains).

Map findings to body sections:

| Section | Typical findings |
|---------|-----------------|
| **Blockers** | Negative-ROI phase treated as essential; plan invests most effort in lowest-value work |
| **Risks** | Low-ROI phases with disproportionate cost; high-ROI work blocked behind low-ROI prerequisites |
| **Gaps** | Missing 80% alternatives; no acknowledgment of concentration risk |
| **Questions** | Ambiguous benefit — phase could be high-value or speculative depending on assumptions |
| **Observations** | Per-phase ROI summary; cut candidates; sequencing suggestions; overall portfolio health |

---

## Structured Result Emission (`--dispatch` only)

After Step 6, emit a single markdown document with YAML frontmatter as the FINAL output. No text before or after this document.

**Format:** Follow the canonical schema at `skills/_shared/contracts/lens-result-contract.md`. That contract is the single source of truth for all lens skill `--dispatch` output.

For this skill, set `lens: cost-benefit` in frontmatter. All other fields, severity vocabulary, body sections (Blockers/Risks/Gaps/Questions/Observations), concern area values, and blocked/failed output shape are defined in the contract.

---

## Interactive Mode (no `--dispatch`)

When invoked without `--dispatch`, this skill is an **advisor**, not a report generator.

**Enter Plan Mode.** Call `EnterPlanMode`. All analysis is read-only.

Execute Steps 1-5 above, then present findings as an advisory conversation:

### Advisory Format

Lead with a per-phase ROI summary table, then present concerns with options and leans.

For each finding, present:

1. **The concern** — what the cost-benefit assessment revealed, stated concretely.
2. **Options** — 2-3 ways to address the imbalance (cut, descope, reorder, simplify).
3. **Lean** — which option you'd pick and why, in one sentence.
4. **Rationale** — the reasoning, grounded in the cost and benefit dimensions.

### Example Advisory Output

```
## Cost-Benefit Review: [Plan Title]

### ROI Summary

| Phase | Effort | Cost Profile | Benefit Profile | ROI |
|-------|--------|-------------|-----------------|-----|
| 2a. [name] | M | Low maintenance, no new deps | High user impact, enables Phase 3 | High |
| 2b. [name] | L | High complexity, 2 new deps | Moderate, tangential to mission | Low |
| 2c. [name] | S | Minimal | Removes known tech debt | High |
| 2d. [name] | M | Moderate maintenance | Speculative future enablement | Moderate |

### Portfolio Assessment

[1-2 sentences: overall cost-benefit health. Where is the value concentrated?
Are there phases that should be cut, reordered, or simplified?]

### Concerns

**Concern:** Phase 2b has low ROI — L-sized effort for tangential benefit
- **(a)** Cut Phase 2b entirely; the plan's goal is achievable without it
- **(b)** Descope to an S-sized version that delivers the core value without the two new dependencies
- **(c)** Defer to a follow-up plan after the mission-critical phases ship
- **Lean:** (b) — the core value is real but the current design over-engineers it

**Concern:** Phase 2a should ship before 2d — higher ROI and 2d depends on patterns 2a establishes
- **(a)** Reorder: 2a → 2c → 2d → 2b
- **(b)** Keep current order but acknowledge the sequencing trade-off
- **Lean:** (a) — delivers value sooner and surfaces integration risks earlier

### Summary

[1-2 sentences: the single most impactful change to improve the plan's cost-benefit profile]
```

Group findings by concern. Phases with clean ROI (critical or high, proportionate cost) need only their summary table row — no separate section.

---

## Relationship to `/adversarial-review`

`/adversarial-review` includes "Lens 5: Implementation Risk" which touches on cost and feasibility, and "Lens 4: Alternatives Not Considered" which asks about simpler options. This standalone skill deepens cost-benefit into a systematic per-phase assessment with explicit ROI classification, portfolio analysis, and 80% alternatives — giving cost-benefit its own context window for independent fleet dispatch by `/ironclad`.

---

## Red Flags — You Are Doing This Wrong

| Symptom | Problem |
|---------|---------|
| You are giving time estimates ("this will take 3 days") | This skill uses relative sizing (S/M/L/XL), never absolute time. Time estimation is the plan author's job. |
| Every phase has "High" ROI | You are evaluating benefit without weighing cost. A phase can have high benefit and still have low ROI if the cost is disproportionate. |
| You are assessing code quality or correctness | This is a value lens, not a quality lens. Whether the code is well-written is other skills' job. Whether the work is worth doing is yours. |
| You flagged a phase as low-ROI without explaining the cost dimension that drives it | "Low ROI" is a conclusion. State which cost dimension (effort, maintenance, complexity, dependencies, risk) makes the cost disproportionate. |
| You skipped the 80% alternative check | This is the highest-value check in the skill. Every moderate-or-lower ROI phase should be tested against a simpler alternative. |
| Your cut candidates still have downstream dependents | A phase cannot be cut if other high-ROI phases depend on it. Check the Complexity and Sequencing table for dependency chains. |
| You treated "enables future work" as high benefit without checking if the future work is concrete | Speculative enablement is not a benefit. "Phase 3 literally depends on this" is a benefit. "We might need this someday" is not. |
