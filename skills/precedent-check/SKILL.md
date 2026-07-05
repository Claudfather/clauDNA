---
name: precedent-check
description: "Use when you want to check whether a plan or implementation PR has prior art in the project's history — previous attempts at the same problem, what was tried, what succeeded or failed, and whether the current plan learns from or repeats the past. Runs standalone or as a lens in the /claudna:ironclad review panel."
argument-hint: "[plan-or-source-path] [--dispatch]"
---

# Precedent Check

Before building something new, check what came before. Plans that ignore prior art risk repeating mistakes, re-introducing reverted approaches, or duplicating work that already shipped under a different name. This skill searches the project's history — git log, closed PRs, closed issues, planning archives — and surfaces relevant precedents so the plan can build on them rather than around them.

**This is a codebase-dependent lens.** It reads the plan document AND searches the target repository's history using `git log`, `gh` CLI, and Explore subagents. It applies the "consolidate, don't fork" principle across time: if the team solved this problem before, the plan should acknowledge that history.

## Arguments

Parse `$ARGUMENTS` at invocation:

- **First positional arg:** Path to the plan document or PR source file. If omitted, prompt for it.
- `--dispatch`: Non-interactive mode for fleet orchestration. Suppresses all interactive elements (no Plan Mode, no AskUserQuestion). Emits a single markdown document with YAML frontmatter per `skills/_shared/contracts/lens-result-contract.md`. Use this when invoked by `/ironclad` or another orchestrator.

---

## `--dispatch` Mode

When `--dispatch` is passed:

- **Do NOT call `EnterPlanMode`.** The dispatcher owns the lifecycle.
- **Do NOT call `AskUserQuestion`.** No human is present.
- **Do NOT prompt for clarification.** If the plan lacks identifiable topics or scope, emit `status: blocked` with a description of what is missing.
- Execute the procedure below silently.
- Emit the structured markdown result as the FINAL output and stop. No text after the result document.

When `--dispatch` is NOT passed, follow the interactive procedure (see Interactive Mode below).

---

## Procedure

### Step 1: Read the Plan

Read the full plan document. Extract:

- **Key topics** — the domain, subsystem, or feature area the plan addresses (e.g., "auth middleware," "skill validation," "session handoff").
- **Component names** — specific files, classes, modules, endpoints, or tools the plan proposes to create or modify.
- **The problem being solved** — what the plan claims to fix, replace, or build.
- **Approach** — the high-level strategy (refactor, rewrite, extend, greenfield).

Build a list of **search terms** from these extractions: component names, domain keywords, problem descriptions. These drive the history searches in Step 2.

If the plan lacks identifiable topics (no goal, no component names, no domain references), stop. In `--dispatch` mode, emit `status: blocked`. In interactive mode, tell the user the plan needs enough specificity for a history search to be meaningful.

### Step 2: Search for Prior Art

Launch **Explore subagents** for codebase history searches. Use subagents aggressively to keep the main context lean. Batch related searches by topic — if three search terms target the same subsystem, combine them into one subagent.

Search these sources (listed in decreasing order of reliability, but all three can be searched in parallel via separate subagents):

#### 2a: Git History

Search the commit log for relevant prior work. Start with recent history (last 12 months) — extend to full history only when the initial search reveals a pattern of repeated churn or yields no hits for a topic that should have prior art.

- `git log --all --oneline --since="12 months ago" --grep="<keyword>"` for each search term from Step 1.
- `git log --all --oneline --since="12 months ago" -- <path>` for files/directories the plan proposes to create or modify — shows who touched them before and why.
- `git log --all --oneline --diff-filter=D -- <path>` for deleted files in the plan's target area — reveals abandoned approaches (no date limit here — deletions are inherently worth knowing about).

Look for: refactors, reverts, renames, and repeated touches to the same area. A file modified 8 times in 3 months tells a different story than one touched once.

#### 2b: Closed PRs and Issues

If `gh` CLI is available, search for prior art in the project's PR and issue history:

- `gh pr list --state closed --search "<keyword>" --limit 20` for each search term. Combine related terms into a single query where possible to reduce API calls and deduplicate results.
- `gh issue list --state closed --search "<keyword>" --limit 20` for related issues.
- For promising hits, read the PR/issue body with `gh pr view <number>` or `gh issue view <number>` to understand context.

Look for: PRs that were merged then reverted, PRs that were closed without merge (abandoned approaches), issues that were closed as "won't fix" or "duplicate."

**Graceful degradation:** If `gh` is unavailable (not installed, not authenticated, rate-limited), skip this step and note the reduced coverage in the output. The git history search (2a) and local file search (2c) still provide value. Do NOT emit `status: blocked` for missing `gh` — proceed with what's available.

#### 2c: Planning and Knowledge Archives

Search local planning and knowledge directories for related documents. Check which of these paths exist before searching — not every repo uses these conventions:

- `documentation/planning/` and `documentation/archive/` for prior plans targeting the same area.
- `shared/knowledge/` or equivalent knowledge directories for recorded learnings.
- `documentation/decisions/` for ADRs that constrain or inform the plan's approach.

If none of these directories exist, skip this step and note the reduced coverage in the output. This is common for repos without formalized planning practices.

Look for: plans that were completed, superseded, or abandoned. Decision records that locked an approach the current plan reopens or contradicts.

### Step 3: Analyze Each Precedent

If Step 2 surfaces many hits, rank by relevance before detailed analysis: reverts and abandonments rank higher than clean merges, recent history ranks higher than old. Take the top 5-7 precedents for full analysis (3a-3d below). List remaining hits as a summary table in Observations — they provide context without consuming analysis budget.

For each selected precedent, assess:

#### 3a: What Was Tried?

Summarize the prior attempt in 1-2 sentences. Include the PR/commit reference so the reader can dig deeper.

#### 3b: What Was the Outcome?

Classify the outcome:

- **Shipped and active** — the prior work is still in the codebase, doing its job.
- **Shipped then reverted** — it landed but was backed out. Why?
- **Merged then superseded** — it shipped but was later replaced by something better.
- **Abandoned (closed without merge)** — the approach was tried and rejected. Why?
- **In progress** — there is open, active work in the same area (open PRs, active branches).

#### 3c: Does the Current Plan Acknowledge This Precedent?

- Does the plan reference the prior work explicitly?
- Does the plan's approach (refactor vs. rewrite vs. extend vs. greenfield — from Step 1) differ from the prior attempt's approach? A plan that rewrites something previously rewritten and reverted is a stronger signal than one that takes a fundamentally different strategy.
- Does the plan risk repeating the same approach that was previously reverted or abandoned without explaining what changed?

#### 3d: Is There Residue?

- Is there abandoned code, configuration, or infrastructure from the prior attempt still in the codebase?
- Does the plan need to clean up residue from a prior attempt, or will it layer on top of it?

### Step 4: Identify Novel Ground

After analyzing precedents, identify areas of the plan that have **no relevant prior art**. These are genuinely novel — the plan is entering uncharted territory.

Novel ground is not a finding. It is context: the plan cannot learn from history in these areas, so other lenses (first-principles, extension-check) carry more weight there. Note novel areas briefly in Observations.

### Step 5: Emit Findings

Classify each finding using the severity vocabulary defined in `skills/_shared/contracts/lens-result-contract.md` (`critical` > `major` > `minor` > `info`).

Tag each finding with a concern area. This skill's primary concern areas are `architecture` and `scope`. Secondary: `compatibility` (when prior art reveals that a previous approach was abandoned due to migration or compatibility barriers). Use the closest match from the canonical set in the contract.

Map findings to body sections:

| Section | Typical findings |
|---------|-----------------|
| **Blockers** | Plan repeats a previously reverted approach without addressing the revert reason; active open PR conflicts with the plan's scope |
| **Risks** | Plan ignores a failed prior attempt at the same problem; residual code from an abandoned approach creates hidden interaction |
| **Gaps** | Plan does not reference relevant prior art that exists; prior decision record constrains the plan's approach but is not acknowledged |
| **Questions** | Ambiguous whether the plan's approach differs enough from a prior attempt; prior art outcome unclear from history |
| **Observations** | Areas with no prior art (novel ground); prior art that the plan correctly builds on; pattern of repeated refactors in the target area |

---

## Structured Result Emission (`--dispatch` only)

After Step 5, emit a single markdown document with YAML frontmatter as the FINAL output. No text before or after this document.

**Format:** Follow the canonical schema at `skills/_shared/contracts/lens-result-contract.md`. That contract is the single source of truth for all lens skill `--dispatch` output.

For this skill, set `lens: precedent-check` in frontmatter. All other fields, severity vocabulary, body sections (Blockers/Risks/Gaps/Questions/Observations), concern area values, and blocked/failed output shape are defined in the contract.

---

## Interactive Mode (no `--dispatch`)

When invoked without `--dispatch`, this skill is an **advisor**, not a report generator.

**Enter Plan Mode.** Call `EnterPlanMode`. All analysis is read-only.

Execute Steps 1-5 above, then present findings as an advisory conversation:

### Advisory Format

Lead with a precedent summary table showing what was found for each plan topic. Then present each concern with options and leans.

For each finding, present:

1. **The precedent** — what was tried before, with a reference (PR number, commit SHA, plan doc path).
2. **The concern** — how the current plan relates to the precedent (repeats it, ignores it, builds on it).
3. **Options** — 2-3 ways the plan could address the concern (including "keep as-is" when the plan already accounts for the history).
4. **Lean** — which option you'd pick and why, in one sentence.
5. **Rationale** — the reasoning, grounded in what the history reveals.

### Example Advisory Output

```
## Precedent Check: [Plan Title]

### Prior Art Summary

| Plan Topic | Precedents Found | Most Relevant |
|-----------|-----------------|---------------|
| Auth middleware rewrite | 3 PRs, 1 reverted | PR #87 (reverted — broke session persistence) |
| Rate-limit config | 1 merged PR | PR #102 (active, ships current approach) |
| API versioning | None | Novel ground |

### Concerns

**Concern:** PR #87 attempted the same auth middleware rewrite and was reverted because it broke session persistence under load. The current plan does not reference this failure.
- **(a)** Add a phase addressing session persistence explicitly, informed by PR #87's failure mode
- **(b)** Add a validation step that tests session persistence under load before merge
- **(c)** Keep as-is — the plan uses a fundamentally different approach that avoids PR #87's architecture
- **Lean:** (a) — the plan uses the same middleware pattern as PR #87; without explicitly addressing session persistence, it risks the same failure

**Concern:** The rate-limit config in Phase 3 overlaps with the approach already shipped in PR #102.
- **(a)** Extend PR #102's config rather than building a new one (consolidate)
- **(b)** Replace PR #102's approach with the new design (acknowledge and supersede)
- **Lean:** (a) — PR #102 is active and working; extending it avoids a parallel path

### Novel Ground
API versioning has no prior art in this repo. Other lenses (first-principles, extension-check) carry more weight for this area.

### Summary
[2-3 sentences. Key takeaway: does the plan learn from history, or does it risk repeating it?]
```

Use one heading per concern. Precedents that the plan correctly acknowledges need only their summary table row.

---

## Codebase Access Strategy

This skill requires access to the target repository's history, not just the plan document.

**In `--dispatch` mode (fleet orchestration):**
- The working directory context or the PR URL in the source frontmatter identifies the target repo.
- Use `gh pr view` to determine the repo if a `pr_url` is available in the source frontmatter.
- Clone or navigate to the repo as needed. If already in the repo's working directory, use it directly.
- Use Explore subagents for all history searches to keep the main context lean.

**In interactive mode:**
- Prompt for the repo path if not obvious from the current working directory.
- Use Explore subagents for history searches.

---

## Relationship to `/adversarial-review`

`/adversarial-review` includes an "Alternatives" lens that may touch on prior approaches. This standalone skill deepens that into a systematic history search with git log, `gh` CLI, and planning archives, giving precedent analysis a full context window and structured per-topic output. The overlap is intentional — general checkup vs. specialist appointment.

---

## Red Flags — You Are Doing This Wrong

| Symptom | Problem |
|---------|---------|
| You searched only by exact component name | Prior art often lives under different names. Search by domain, problem description, and affected paths — not just the names the current plan uses. |
| You listed commits without assessing their relevance | A commit that touches the same file is not automatically a precedent. Assess whether it addresses the same problem or just the same code. |
| You blocked because `gh` CLI is unavailable | `gh` is a nice-to-have. Git history and local file searches still provide substantial value. Proceed with reduced coverage and note it. |
| You found a reverted PR but did not check why it was reverted | The revert reason is the whole point. A revert without context is trivia; a revert with context is a finding. Read the revert commit message and the PR discussion. |
| Every finding is `info` severity | You are cataloguing history, not reviewing a plan against it. Push harder on 3c — does the plan learn from this precedent or ignore it? |
| You flagged novel ground as a risk | No prior art is not inherently risky. It means other lenses matter more for that area. Novel ground is an Observation, not a Risk. |
| You did not check for active open PRs | An open PR in the same area is a potential conflict, not just a precedent. Flag it as a Blocker or Risk depending on overlap. |
| You ignored the 12-month default and searched all-time for every keyword | Step 2a defaults to recent history for a reason. Extend to full history only when recent yields no hits or when a churn pattern emerges. |
