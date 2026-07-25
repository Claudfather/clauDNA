Panel lens for /claudna:ironclad — steps back from a plan's proposed solution to assess whether the right problem is being solved the right way, catching plans that extend suboptimal foundations, introduce accidental complexity, or miss simpler alternatives.
Dispatched by the panel (or via /claudna:ironclad --lens first-principles); emits structured markdown per skills/_shared/contracts/lens-result-contract.md. Not user-invocable.

# First Principles

Stand back from the proposed solution. Forget the plan exists. Ask: what is the actual problem, and does this plan solve it the right way? Plans drift from first principles when they inherit assumptions from the codebase they extend, the process they follow, or the vocabulary they use. This lens strips those layers away.

**This is a plan-only lens.** It reads the plan document and reasons about problem, approach, and complexity. It does not read the target codebase — that is the job of the extension-check panel lens (lenses/extension-check.md).

**Applies to:** `plan` and `mixed` targets.

## Dispatch Rules

Follow the dispatch discipline in `skills/_shared/contracts/lens-result-contract.md` (§ Dispatch Rules): run non-interactively (no `EnterPlanMode`, no `AskUserQuestion`), execute silently, and emit the structured result as the FINAL output with no text after it.

**Blocked condition:** If the plan lacks a Goal section or is too ambiguous to review, emit `status: blocked` with a description of what is missing.

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

If the plan lacks a Goal section (or equivalent), stop and emit `status: blocked` — the plan needs a stated problem before first-principles analysis is meaningful.

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

Tag each finding with a concern area. This lens's primary concern areas are `architecture` and `scope`. Secondary: `dependencies`, `compatibility`. Use the closest match from the canonical set in the contract.

Map findings to body sections:

| Section | Typical findings |
|---------|-----------------|
| **Blockers** | Wrong problem; foundation is unsound and plan compounds the flaw |
| **Risks** | Large divergence from a from-scratch design; high accidental complexity |
| **Gaps** | Unstated assumptions with high impact if wrong |
| **Questions** | Ambiguities in the restated problem; unclear whether a phase serves the problem or the approach |
| **Observations** | Via negativa candidates; phases that could be cut without weakening the plan |

---

## Structured Result Emission

**Format:** Follow the canonical schema at `skills/_shared/contracts/lens-result-contract.md`. That contract is the single source of truth for all panel lens output.

For this lens, set `lens: first-principles` in frontmatter. All other fields, severity vocabulary, body sections (Blockers/Risks/Gaps/Questions/Observations), concern area values, and blocked/failed output shape are defined in the contract.

---

## Relationship to `/adversarial-review`

`/adversarial-review` includes "Lens 1: First Principles" as one of seven internal lenses. This panel lens deepens that lens for independent dispatch by `/ironclad`, with a full context window and structured findings output. The overlap is intentional — general checkup vs. specialist appointment.

---

## Red Flags — You Are Doing This Wrong

| Symptom | Problem |
|---------|---------|
| You referenced the plan's solution in the restated problem | The restatement is contaminated. Strip solution language and redo Step 2. |
| Every finding is `info` severity | You are describing the plan, not challenging it. Push harder on Checks 2-4. |
| You skipped the foundation assessment for a plan that extends existing code | This is where first-principles analysis adds the most value. Go back. |
| Your from-scratch design looks identical to the plan | Either the plan is excellent or you inherited its assumptions. Try designing with a different technology stack to break out. |
| You listed assumptions but didn't assess impact | Assumptions without impact analysis are trivia. For each assumption, state what changes if it is wrong. |
| You added new scope or features to the plan | This lens subtracts. Via negativa means removing, not adding. |
