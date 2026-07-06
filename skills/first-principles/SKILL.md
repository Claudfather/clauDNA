---
name: first-principles
description: "Use when you want to step back from a plan's proposed solution and assess whether the right problem is being solved the right way. Catches plans that extend suboptimal foundations, introduce accidental complexity, or miss simpler alternatives. Runs standalone or as a lens in the /claudna:ironclad review panel."
argument-hint: "[plan-file-path] [--dispatch]"
---

# First Principles

Stand back from the proposed solution. Forget the plan exists. Ask: what is the actual problem, and does this plan solve it the right way? Plans drift from first principles when they inherit assumptions from the codebase they extend, the process they follow, or the vocabulary they use. This skill strips those layers away.

**This is a plan-only lens.** It reads the plan document and reasons about problem, approach, and complexity. It does not read the target codebase (that is `/extension-check`'s job).

## Arguments

Parse `$ARGUMENTS` at invocation:

- **First positional arg:** Path to the plan document. If omitted, prompt for it.
- `--dispatch`: Non-interactive mode for fleet orchestration. Suppresses all interactive elements (no Plan Mode, no AskUserQuestion). Emits a single markdown document with YAML frontmatter per `skills/_shared/contracts/lens-result-contract.md`. Use this when invoked by `/ironclad` or another orchestrator.

---

## `--dispatch` Mode

When `--dispatch` is passed:

- **Do NOT call `EnterPlanMode`.** The dispatcher owns the lifecycle.
- **Do NOT call `AskUserQuestion`.** No human is present.
- **Do NOT prompt for clarification.** If the plan lacks a Goal section or is too ambiguous to review, emit `status: blocked` with a description of what is missing.
- Execute the procedure below silently.
- Emit the structured markdown result as the FINAL output and stop. No text after the result document.

When `--dispatch` is NOT passed, follow the interactive procedure (see Interactive Mode below).

---

## Procedure

### Step 1: Read the Plan

Read the full plan document. Identify these sections (names may vary):

- **Goal / Problem Statement** — what the plan claims to solve.
- **Current State** — what exists today.
- **Architecture / Approach** — what the plan proposes to build.
- **Phases** — the breakdown of work.
- **Decision Forks** — choices the plan defers or locks.
- **Risks** — what the plan acknowledges could go wrong.

If the plan lacks a Goal section (or equivalent), stop. In `--dispatch` mode, emit `status: blocked`. In interactive mode, tell the user the plan needs a stated problem before first-principles analysis is meaningful.

### Step 2: Extract and Restate the Problem

1. **Extract** the stated problem from the Goal section. Copy it verbatim.
2. **Restate** the problem in one sentence **without referencing the proposed solution, any technology choice, or any implementation detail**. Strip away the how; keep only the what and the why.

This restatement is the anchor for every check that follows. If you cannot restate the problem without referencing the solution, that is itself a finding — the plan may be solution-first rather than problem-first.

### Step 3: Five Checks

Apply each check against the restated problem (Step 2), not the plan's original framing.

#### Check 1: Is This the Right Problem?

- Could the underlying need be met by solving a **different** problem entirely?
- Is this a symptom being treated as a root cause?
- Who experiences this problem? Is their pain real and current, or hypothetical and future?
- If the problem disappeared tomorrow with no effort, what would actually change? If the answer is "not much," the problem may not warrant a plan.

#### Check 2: Would You Build This From Scratch?

- Imagine no legacy code, no existing system, no sunk cost. You have a blank editor and the restated problem.
- What would you build? Describe it in 2-3 sentences.
- Now compare: does the plan propose something that looks like a fresh build, or does it propose patching, extending, or wrapping something that already exists?
- Divergence is not automatically wrong — migration cost is real. But large divergence is a signal worth surfacing.

#### Check 3: Accidental Complexity

- Could the same outcome be achieved with **dramatically less machinery**?
- Count the moving parts the plan introduces: new files, new abstractions, new protocols, new integrations, new config surface. For each, ask: is this essential to the outcome, or is it essential to the approach?
- Look for complexity that exists because of the plan's architecture, not because of the problem.

#### Check 4: Via Negativa

- What should be **removed** from this plan?
- What phases, deliverables, or features are present because they seem useful rather than because the problem demands them?
- What common mistakes in this domain should the plan explicitly avoid? Absence of a known anti-pattern is a form of design.
- Would the plan be stronger with fewer phases? Fewer abstractions? Fewer decision forks?

#### Check 5: Confident Assumptions

- Which assumptions does the plan treat as obvious — so obvious they are unstated or stated without evidence?
- List them. For each: what would change if this assumption were wrong?
- Pay special attention to assumptions about: user behavior, system load, dependency stability, team capacity, timeline, and the durability of decisions made in adjacent systems.

### Step 4: Foundation Assessment

If the plan extends an existing system (adds features to an existing tool, builds on an existing protocol, extends an existing architecture):

- Is the foundation itself sound? Or does the plan build on something the team would not choose if starting fresh?
- Does extending this foundation **compound an existing flaw** — making it harder to fix later?
- Is the plan's scope partly driven by working around limitations of the foundation rather than solving the stated problem?

If the plan does NOT extend an existing system (greenfield), skip this step.

### Step 5: Emit Findings

Classify each finding using the severity vocabulary defined in `skills/_shared/contracts/lens-result-contract.md` (`critical` > `major` > `minor` > `info`).

Tag each finding with a concern area. This skill's primary concern areas are `architecture` and `scope`. Secondary: `dependencies`, `compatibility`. Use the closest match from the canonical set in the contract.

Map findings to body sections:

| Section | Typical findings |
|---------|-----------------|
| **Blockers** | Wrong problem; foundation is unsound and plan compounds the flaw |
| **Risks** | Large divergence from a from-scratch design; high accidental complexity |
| **Gaps** | Unstated assumptions with high impact if wrong |
| **Questions** | Ambiguities in the restated problem; unclear whether a phase serves the problem or the approach |
| **Observations** | Via negativa candidates; phases that could be cut without weakening the plan |

---

## Structured Result Emission (`--dispatch` only)

After Step 5, emit a single markdown document with YAML frontmatter as the FINAL output. No text before or after this document.

**Format:** Follow the canonical schema at `skills/_shared/contracts/lens-result-contract.md`. That contract is the single source of truth for all lens skill `--dispatch` output.

For this skill, set `lens: first-principles` in frontmatter. All other fields, severity vocabulary, body sections (Blockers/Risks/Gaps/Questions/Observations), concern area values, and blocked/failed output shape are defined in the contract.

---

## Interactive Mode (no `--dispatch`)

When invoked without `--dispatch`, this skill is an **advisor**, not a report generator.

**Enter Plan Mode.** Call `EnterPlanMode`. All analysis is read-only.

Execute Steps 1-5 above, then present findings as an advisory conversation:

### Advisory Format

For each finding, present:

1. **The concern** — what the check revealed, stated concretely.
2. **Options** — 2-3 ways the plan could address the concern (including "keep as-is" when the concern is minor).
3. **Lean** — which option you'd pick and why, in one sentence.
4. **Rationale** — the reasoning behind the lean, grounded in what the check revealed.

Group findings by check (not by severity). Lead with the restated problem (Step 2) so the developer sees the anchor before the analysis.

### Example Advisory Output

```
## First Principles Review: [Plan Title]

### Restated Problem
[One sentence — the problem stripped of solution references]

### Check 2: From-Scratch Design
[2-3 sentence description of what you'd build from scratch]
[Comparison to the plan's proposal]

**Concern:** [Concrete concern, if any]
- **(a)** [Option: e.g., restructure Phase 2 to match the from-scratch design]
- **(b)** [Option: e.g., keep the current approach, accept migration cost as justified]
- **Lean:** (a) — [one-sentence reason]

### Summary
[2-3 sentences. One-line verdict: what is the single most important thing to reconsider?]
```

Use one heading per check. Not every check will produce a concern with options — some will confirm the plan is sound. Say so briefly and move on.

---

## Relationship to `/adversarial-review`

`/adversarial-review` includes "Lens 1: First Principles" as one of seven internal lenses. This standalone skill deepens that lens for independent fleet dispatch by `/ironclad`, with a full context window and structured advisory output. The overlap is intentional — general checkup vs. specialist appointment.

---

## Red Flags — You Are Doing This Wrong

| Symptom | Problem |
|---------|---------|
| You referenced the plan's solution in the restated problem | The restatement is contaminated. Strip solution language and redo Step 2. |
| Every finding is `info` severity | You are describing the plan, not challenging it. Push harder on Checks 2-4. |
| You skipped the foundation assessment for a plan that extends existing code | This is where first-principles analysis adds the most value. Go back. |
| Your from-scratch design looks identical to the plan | Either the plan is excellent or you inherited its assumptions. Try designing with a different technology stack to break out. |
| You listed assumptions but didn't assess impact | Assumptions without impact analysis are trivia. For each assumption, state what changes if it is wrong. |
| You added new scope or features to the plan | This skill subtracts. Via negativa means removing, not adding. |
