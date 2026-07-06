---
name: extension-check
description: "Use when you want to verify that a plan or implementation PR isn't duplicating existing codebase abstractions — parallel implementations, redundant patterns, naming drift, sprawl where an existing component should have been extended. Runs standalone or as a lens in the /claudna:ironclad review panel."
argument-hint: "[plan-or-source-path] [--dispatch]"
---

# Extension Check

For every new component a plan or PR proposes, check whether an existing abstraction already covers the need. Catches parallel implementations, duplicate patterns, naming convention drift, and codebase sprawl before they happen.

**This is a codebase-dependent lens.** It reads the plan or PR source AND searches the target codebase using Explore subagents. It applies the "consolidate, don't fork" principle: when the team owns a surface, one path is better than two.

## Arguments

Parse `$ARGUMENTS` at invocation:

- **First positional arg:** Path to the plan document or PR source file. If omitted, prompt for it.
- `--dispatch`: Non-interactive mode for fleet orchestration. Suppresses all interactive elements (no Plan Mode, no AskUserQuestion). Emits a single markdown document with YAML frontmatter per `skills/_shared/contracts/lens-result-contract.md`. Use this when invoked by `/ironclad` or another orchestrator.

---

## `--dispatch` Mode

When `--dispatch` is passed:

- **Do NOT call `EnterPlanMode`.** The dispatcher owns the lifecycle.
- **Do NOT call `AskUserQuestion`.** No human is present.
- **Do NOT prompt for clarification.** If the source lacks identifiable proposed components, emit `status: blocked` with a description of what is missing.
- Execute the procedure below silently.
- Emit the structured markdown result as the FINAL output and stop. No text after the result document.

When `--dispatch` is NOT passed, follow the interactive procedure (see Interactive Mode below).

---

## Procedure

### Step 1: Read the Source

Read the plan document or PR source. The source may be:

- **A plan document** (markdown with phases, proposed components, architecture sections). Extract every new component the plan proposes to create.
- **A PR diff** (unified diff from an implementation PR). Extract every new file, class, module, function, endpoint, or schema the PR introduces.

If the source is a PR diff (implementation review), the source file's frontmatter `pr_type` field will be `implementation` or `mixed`. Use the diff itself and the PR body to identify proposed components.

Identify every **proposed new component**:

- New files or directories
- New classes, structs, or interfaces
- New modules or packages
- New API endpoints or routes
- New database tables or schemas
- New configuration surfaces (env vars, config keys, CLI flags)
- New shared abstractions (factories, registries, base classes, protocols)

If zero proposed components are identified, emit a `completed` result with a single Observation: "No new components identified in the source. Nothing to check against the codebase."

### Step 2: Explore the Codebase

Launch **Explore subagents** to search the codebase. Use subagents aggressively to keep the main context lean. Batch related components by locality — if three proposed classes live in the same package, search that package once rather than launching three separate subagents.

Each subagent should search for:

1. **Existing abstractions that cover the same need:**
   - Classes, modules, or functions with similar names or responsibilities
   - Factories, registries, or base classes that the new component could extend
   - Shared utilities that already implement the proposed logic

2. **Same-level duplicates:**
   - Code that solves the same problem at the same layer (not a base class to extend, but a parallel implementation)
   - Near-duplicates with slight variation (different names, same shape)

3. **Naming convention patterns:**
   - How are similar components named in adjacent files? (grep sibling files, not the whole repo)
   - Does the proposed name follow the established convention or introduce a new one?

Scope searches to the relevant layer (routes directory for endpoints, models directory for schemas, utils for helpers). Don't grep the entire repo for every component.

### Step 3: Analyze Findings

For each proposed component, evaluate the search results:

#### Check 1: Vertical Reuse (extend an existing abstraction)

Is there a base class, factory, registry, or shared interface the new component should extend or plug into?

- Does the codebase already have an abstraction at a higher level that this component fits under?
- Would extending it be simpler than creating a new standalone component?
- If the existing abstraction doesn't quite fit, is it cheaper to widen it than to build a new one?

#### Check 2: Horizontal Duplication (consolidate same-level parallels)

Does the proposal introduce a second implementation at the same level where one could serve both needs?

- Is there an existing component with the same responsibility but a different name?
- Would consolidating be cheaper long-term than maintaining two paths?
- Does the "consolidate, don't fork" principle apply? (Exception: external API contracts, public endpoints, semver public libs.)

#### Check 3: Naming Conventions

Does the proposed name follow existing codebase patterns?

- Check adjacent files and sibling components for naming patterns
- Flag names that break established conventions (e.g., `UserManager` when everything else uses `UserService`)
- Flag names that collide or confuse (e.g., `Config` when `Configuration` already exists with different semantics)

#### Check 4: Abstraction Level

Is the proposed component at the right level of abstraction?

- Is it too fine-grained? (Could it be a method on an existing class instead of a new class?)
- Is it too coarse? (Does it combine unrelated responsibilities that should be separate per existing patterns?)
- Does it match the granularity of similar components in the codebase?

### Step 4: Emit Findings

Classify each finding using the severity vocabulary defined in `skills/_shared/contracts/lens-result-contract.md` (`critical` > `major` > `minor` > `info`).

Tag each finding with a concern area. This skill's primary concern areas are `architecture` and `compatibility`. Secondary: `scope`, `dependencies`.

Map findings to body sections:

| Section | Typical findings |
|---------|-----------------|
| **Blockers** | New component directly duplicates an existing one with no justification; introduces a second path that will diverge |
| **Risks** | Existing abstraction is close but needs extension; proposed name conflicts with existing conventions |
| **Gaps** | Missing consolidation opportunity; existing pattern not referenced in the plan |
| **Questions** | Ambiguous whether the proposed component overlaps with an existing one; needs author clarification |
| **Observations** | Naming convention notes; minor reuse opportunities; cases where the new component is genuinely novel |

---

## Structured Result Emission (`--dispatch` only)

After Step 4, emit a single markdown document with YAML frontmatter as the FINAL output. No text before or after this document.

**Format:** Follow the canonical schema at `skills/_shared/contracts/lens-result-contract.md`. That contract is the single source of truth for all lens skill `--dispatch` output.

For this skill, set `lens: extension-check` in frontmatter. All other fields, severity vocabulary, body sections (Blockers/Risks/Gaps/Questions/Observations), concern area values, and blocked/failed output shape are defined in the contract.

---

## Interactive Mode (no `--dispatch`)

When invoked without `--dispatch`, this skill is an **advisor**, not a report generator.

**Enter Plan Mode.** Call `EnterPlanMode`. All analysis is read-only.

Execute Steps 1-4 above, then present findings as an advisory conversation:

### Advisory Format

For each proposed component where findings exist, present:

1. **The proposed component** — name, type, and what it does.
2. **What exists** — the existing abstraction, parallel path, or naming pattern found in the codebase.
3. **Options** — 2-3 ways to address the overlap (including "keep as-is" when the overlap is minor or justified).
4. **Lean** — which option you'd pick and why, in one sentence.
5. **Rationale** — the reasoning, grounded in what the codebase search revealed.

Group findings by proposed component. Lead with a summary of how many proposed components were checked and how many have findings.

### Example Advisory Output

```
## Extension Check: [Plan/PR Title]

**Components checked:** 7
**Findings:** 3 components have existing overlap

### `SkillValidator` (new class in `scripts/`)

**Existing:** `scripts/validate-skills.py` already validates SKILL_CONTRACT.md compliance,
frontmatter checks, and CI integration.

- **(a)** Extend `validate-skills.py` with the new validation rules
- **(b)** Replace `validate-skills.py` with the new `SkillValidator` class (consolidate into one)
- **(c)** Keep both — `validate-skills.py` for CI, `SkillValidator` for runtime
- **Lean:** (a) — the existing script handles the same domain; extending it avoids a parallel path

### `EventBus` (new module in `lib/`)

**Existing:** No event bus pattern found in the codebase. This is genuinely novel.

No concerns. The codebase doesn't have an eventing abstraction — this fills a real gap.

### Summary

2 of 7 proposed components overlap with existing abstractions. 1 is a direct parallel path
(SkillValidator) that should be consolidated. 1 has a naming convention mismatch.
```

---

## Codebase Access Strategy

This skill requires access to the target codebase, not just the plan or PR source.

**In `--dispatch` mode (fleet orchestration):**
- The working directory context or the PR URL in the source frontmatter identifies the target repo.
- Use `gh pr view` to determine the repo if a `pr_url` is available in the source frontmatter.
- Clone or navigate to the repo as needed. If already in the repo's working directory, use it directly.
- Use Explore subagents for all codebase search to keep the main context lean.

**In interactive mode:**
- Prompt for the repo path if not obvious from the current working directory.
- Use Explore subagents for codebase search.

---

## Relationship to `/adversarial-review`

`/adversarial-review` includes an "Alternatives" lens that touches on existing-pattern reuse. This standalone skill deepens that into a systematic codebase search with Explore subagents, giving extension checking a full context window and structured per-component output. The overlap is intentional — general checkup vs. specialist appointment.

---

## Red Flags — You Are Doing This Wrong

| Symptom | Problem |
|---------|---------|
| You flagged every new component as overlapping | You are pattern-matching on names, not responsibilities. Check what the existing code actually does. |
| You didn't use Explore subagents for codebase search | You are consuming context budget on search results. Delegate to subagents. |
| Your search was limited to exact name matches | Search by responsibility, not just name. A `UserService` might overlap with a `UserManager` or a `handle_user()` function. |
| You found overlap but didn't check if extending is feasible | "There's an existing X" is not a finding. "Existing X covers this need and should be extended because Y" is. |
| You recommended keeping parallel paths without justifying it | The default is consolidation. Parallel paths need a justification (external API contract, different lifecycle, genuinely different domain). |
| You flagged naming issues without checking the local convention | A name is only wrong relative to its neighbors. Check adjacent files, not abstract naming rules. |
| Every finding is `info` severity | You are cataloguing, not reviewing. Push harder on Checks 1-2 — parallel paths are usually `major`. |
