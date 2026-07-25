Panel lens for /claudna:ironclad — checks whether a plan or implementation PR has prior art in the project's history: previous attempts at the same problem, what was tried, what succeeded or failed, and whether the current plan learns from or repeats the past.
Dispatched by the panel (or via /claudna:ironclad --lens precedent-check); emits structured markdown per skills/_shared/contracts/lens-result-contract.md. Not user-invocable.

# Precedent Check

Before building something new, check what came before. Plans that ignore prior art risk repeating mistakes, re-introducing reverted approaches, or duplicating work that already shipped under a different name. This lens searches the project's history — git log, closed PRs, closed issues, planning archives — and surfaces relevant precedents so the plan can build on them rather than around them.

**This is a codebase-dependent lens.** It reads the plan document AND searches the target repository's history using `git log`, `gh` CLI, and Explore subagents. It applies the "consolidate, don't fork" principle across time: if the team solved this problem before, the plan should acknowledge that history.

## Dispatch Rules

Follow the dispatch discipline in `skills/_shared/contracts/lens-result-contract.md` (§ Dispatch Rules): run non-interactively (no `EnterPlanMode`, no `AskUserQuestion`), execute silently, and emit the structured result as the FINAL output with no text after it.

**Blocked condition:** If the plan lacks identifiable topics or scope, emit `status: blocked` with a description of what is missing.

## Procedure

### Step 1: Read the Plan

Read the full plan document. Extract:

- **Key topics** — the domain, subsystem, or feature area the plan addresses (e.g., "auth middleware," "skill validation," "session handoff").
- **Component names** — specific files, classes, modules, endpoints, or tools the plan proposes to create or modify.
- **The problem being solved** — what the plan claims to fix, replace, or build.
- **Approach** — the high-level strategy (refactor, rewrite, extend, greenfield).

Build a list of **search terms** from these extractions: component names, domain keywords, problem descriptions. These drive the history searches in Step 2.

If the plan lacks identifiable topics (no goal, no component names, no domain references), stop and emit `status: blocked` with a description of what is missing.

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

Novel ground is not a finding. It is context: the plan cannot learn from history in these areas, so other lenses — the first-principles panel lens (lenses/first-principles.md) and the extension-check panel lens (lenses/extension-check.md) — carry more weight there. Note novel areas briefly in Observations.

### Step 5: Emit Findings

Classify each finding using the severity vocabulary defined in `skills/_shared/contracts/lens-result-contract.md` (`critical` > `major` > `minor` > `info`).

Tag each finding with a concern area. This lens's primary concern areas are `architecture` and `scope`. Secondary: `compatibility` (when prior art reveals that a previous approach was abandoned due to migration or compatibility barriers). Use the closest match from the canonical set in the contract.

Map findings to body sections:

| Section | Typical findings |
|---------|-----------------|
| **Blockers** | Plan repeats a previously reverted approach without addressing the revert reason; active open PR conflicts with the plan's scope |
| **Risks** | Plan ignores a failed prior attempt at the same problem; residual code from an abandoned approach creates hidden interaction |
| **Gaps** | Plan does not reference relevant prior art that exists; prior decision record constrains the plan's approach but is not acknowledged |
| **Questions** | Ambiguous whether the plan's approach differs enough from a prior attempt; prior art outcome unclear from history |
| **Observations** | Areas with no prior art (novel ground); prior art that the plan correctly builds on; pattern of repeated refactors in the target area |

## Structured Result Emission

**Format:** Follow the canonical schema at `skills/_shared/contracts/lens-result-contract.md`. That contract is the single source of truth for all panel lens output.

For this lens, set `lens: precedent-check` in frontmatter. All other fields, severity vocabulary, body sections (Blockers/Risks/Gaps/Questions/Observations), concern area values, and blocked/failed output shape are defined in the contract.

## Codebase Access Strategy

This lens requires access to the target repository's history, not just the plan document.

- The working directory context or the PR URL in the source frontmatter identifies the target repo.
- Use `gh pr view` to determine the repo if a `pr_url` is available in the source frontmatter.
- Clone or navigate to the repo as needed. If already in the repo's working directory, use it directly.
- Use Explore subagents for all history searches to keep the main context lean.

## Relationship to `/adversarial-review`

`/adversarial-review` includes an "Alternatives" lens that may touch on prior approaches. This lens deepens that into a systematic history search with git log, `gh` CLI, and planning archives, giving precedent analysis a full context window and structured per-topic output. The overlap is intentional — general checkup vs. specialist appointment.

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
