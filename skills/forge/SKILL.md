---
name: forge
user-invocable: true
description: "Use when planning a workstream that spans multiple PRs, involves decision forks, or needs structured phasing before implementation. Produces a structured plan with decision forks, phasing, validation strategy, risks, and companion plan references. The output is a docs PR (single markdown file) ready for multi-lens review and iterative hardening. Use before /implement-plan when the scope is large enough to need a plan. Use with /ironclad (claudlobby) for fleet-orchestrated review cycles."
argument-hint: "[topic-or-issue-url] [--output github|session] [--auto]"
---

# Forge

You are a plan architect. Your job is to produce a structured planning document that can survive multi-lens review, iterative hardening, and decision-fork ratification. A good plan is a contract between the humans who ratify it and the engineers who implement it. A vague plan wastes more time than no plan — it creates false alignment.

**Enter Plan Mode.** Call `EnterPlanMode`. All analysis is read-only during research phases. If declined, proceed by convention.

## Arguments

Parse `$ARGUMENTS` at invocation:
- **First positional arg:** Topic description, issue URL, or path to an existing rough plan. If omitted, prompt for it.
- `--auto`: Non-interactive mode. Suppresses Plan Mode and all interactive gates. Requires topic in `$ARGUMENTS`. Emits structured-result JSON and stops.
- `--output github`: Create a docs PR with the plan as a single markdown file.
- `--output session`: Present the plan in chat only (default).

Default (no flag): Interactive mode, session output.

## When to Use

You are about to start a workstream that is:
- Multi-phase (more than a single PR)
- Multi-person (needs coordination across engineers/reviewers)
- Decision-heavy (has forks where reasonable people disagree)
- High-stakes (wrong direction creates weeks of rework)

This is for **workstream-level planning** — initiatives that span multiple PRs and weeks. Not for single-PR task scoping (use `/weigh-development-paths` for that) or implementation details (use `/implement-plan` after the plan is ratified).

## Phase 1: Research

### Step 1: Understand the Scope

Read everything relevant:
- **Topic input** — the user's description, issue body, or rough plan
- **PROJECT_MISSION.md** — if it exists in the repo, read it. The plan must align with the north star.
- **Existing plans** — search for related plans in `documentation/planning/`, `shared/planning/active/`, or `planning/`. Don't duplicate or contradict.
- **Codebase state** — read the actual code in the target area. Plans based on assumed architecture drift on contact with reality.
- **Prior art** — `git log --all --oneline --grep="<keywords>"` for past attempts. Check closed issues and merged PRs for context on what was tried before.

### Step 2: Identify Decision Forks

As you research, catalog every point where:
- There are multiple viable approaches
- A choice constrains downstream work
- Reasonable people would disagree
- The decision needs explicit ratification (not just engineering judgment)

Each fork becomes a formal entry in the plan's Decision Forks section.

### Step 3: Identify Risks

Catalog risks in three categories:
- **Technical risks** — things that might not work as designed
- **Coordination risks** — things that depend on multiple people/systems aligning
- **Scope risks** — things that might grow beyond the plan's boundary

For each risk, draft a mitigation. If no mitigation exists, flag it as an open risk requiring human decision.

---

## Phase 2: Draft the Plan

### Plan Document Structure

Every /forge plan follows this structure. All sections are mandatory. If a section is genuinely empty (e.g., no companion plans), write "None identified" — don't omit the heading.

```markdown
---
title: "<Plan Title>"
type: plan
status: draft
owner: <author>
tags: [<relevant-tags>]
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---

# <Plan Title>

## Goal
<2-3 sentences: what this plan achieves and why it matters. Reference PROJECT_MISSION.md alignment if applicable.>

## Current State
<What exists today. Be specific — file paths, table names, API endpoints. Claims here must be verified against the codebase.>

## Architecture
<Diagram or description of the target state. Show how components connect.>

## Phases
<Sequential phases with clear boundaries. Each phase should deliver standalone value.>

### Phase N: <Name> (<effort estimate>)
<For each phase:>
#### Na. <Sub-deliverable>
<What to build, how it works, effort estimate.>

## Decision Forks

### Fork F1: <Title>
- **Context:** <Why this fork exists>
- **Options:**
  - **(a)** <Option A> — <1-line trade-off>
  - **(b)** <Option B> — <1-line trade-off>
  - **(c)** <Option C> — <1-line trade-off> (if applicable)
- **Lean:** <Which option the plan recommends and why>
- **Ratifier:** <Who locks this — human, manager, or framework>
- **Status:** open | locked
- **Evidence:** <Link to analysis, PR comment, or conversation>

<Repeat for each fork.>

## Companion Plans
<Cross-references to related planning documents. "None identified" if standalone.>

## Dependencies
<Table: dependency | blocks | risk level>

## Risks
<Table: risk | impact | mitigation>

## Validation Strategy
<How do we know this plan worked? Acceptance criteria, test strategy, metrics.>

## Estimated Effort
<Table: phase | effort>
<Total with calendar estimate.>

## Dispatch Recommendation
<Suggested execution order, parallelization opportunities, engineer assignment guidance.>
```

### Decision Fork Discipline

- Every fork gets an ID (F1, F2, ...) for reference in discussions
- Options are mutually exclusive and collectively exhaustive
- The "lean" is the plan's recommendation, not a decision — it's ratified by the designated ratifier
- A locked fork includes the commit or message reference where it was ratified
- Forks that are obvious (one option clearly dominates) should still be documented — "obvious" to the author may not be obvious to the reviewer

### Anti-Patterns to Avoid

- **Vague phases** — "Phase 2: Build the thing" is not a plan. Each phase names specific deliverables.
- **Missing current state** — Plans that start from assumptions instead of verified codebase state drift immediately.
- **No decision forks** — If there are zero forks, either the plan is trivially simple (don't need /forge) or the author hasn't thought hard enough.
- **Effort without phases** — "Total: 6 weeks" with no breakdown is a guess, not a plan.
- **Companion plan references without cross-validation** — If you reference another plan, verify it exists and the cross-reference is bidirectional.

---

## Phase 3: Self-Audit

Before presenting or committing the plan, run these checks:

1. **Mission alignment** — Does every phase serve the north star in PROJECT_MISSION.md? Flag any phase that's tangential.
2. **Extension check** — For every new component proposed, is there an existing abstraction (factory, registry, base class, shared pattern) it should extend rather than build adjacent to? This is the #1 cause of parallel slop. Search the codebase.
3. **Fork completeness** — Every decision fork has options, a lean, and a ratifier? No hidden forks buried in phase descriptions?
4. **Claim verification** — Every factual claim about current state is verified against the codebase? File paths exist? Column names match? API endpoints are real?
5. **Validation testability** — Can each validation criterion be objectively checked? "Works correctly" is not testable. "Returns 200 with valid JSON matching schema X" is.
6. **Dependency chain** — Are phases correctly ordered? Could any phases run in parallel that are listed as sequential?

---

## Phase 4: Output

### --output session (default)

Present the plan in chat with a summary:
- Plan title and goal (1-2 sentences)
- Phase count and total effort estimate
- Fork count and how many are open vs locked
- Key risks (top 3)
- Recommended next step (usually: "open a docs PR and run /ironclad for multi-lens review")

### --output github

Follow `skills/_shared/output-guide.md` for house-style validation and routing. For `/forge`, the output is a planning doc (not an issue), so write directly to the planning directory rather than routing through `/claudna:publish`.

1. Create a branch: `<author>/forge-<slugified-title>`
2. Write the plan to `documentation/planning/<date>-<slug>.md` (or the repo's established planning directory if different)
3. Commit with message: `docs(planning): <title> — forged plan v0`
4. Open a PR with:
   - Title: `docs(planning): <title>`
   - Body: summary (goal, phases, fork count, effort, key risks)
   - Label: `planning` (if label exists)
5. Report the PR URL

### --auto

Emit structured-result JSON per `skills/_shared/orchestration-guide.md` §10 (Structured Result Shape):
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
  "next": "<orchestrator hint, e.g. 'run /ironclad <pr-url> for fleet review', or null>",
  "errors": [],
  "blocker_description": null
}
```
