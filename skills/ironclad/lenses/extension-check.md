Panel lens for /claudna:ironclad — verifies that a plan or implementation PR isn't duplicating existing codebase abstractions: parallel implementations, redundant patterns, naming drift, sprawl where an existing component should have been extended.
Dispatched by the panel (or via /claudna:ironclad --lens extension-check); emits structured markdown per skills/_shared/contracts/lens-result-contract.md. Not user-invocable.

# Extension Check

For every new component a plan or PR proposes, check whether an existing abstraction already covers the need. Catches parallel implementations, duplicate patterns, naming convention drift, and codebase sprawl before they happen.

**This is a codebase-dependent lens.** It reads the plan or PR source AND searches the target codebase using Explore subagents. It applies the "consolidate, don't fork" principle: when the team owns a surface, one path is better than two.

**Applies to:** `implementation` and `mixed` targets.

## Dispatch Rules

Follow the dispatch discipline in `skills/_shared/contracts/lens-result-contract.md` (§ Dispatch Rules): run non-interactively (no `EnterPlanMode`, no `AskUserQuestion`), execute silently, and emit the structured result as the FINAL output with no text after it.

**Blocked condition:** If the source lacks identifiable proposed components, emit `status: blocked` with a description of what is missing.

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

Tag each finding with a concern area. This lens's primary concern areas are `architecture` and `compatibility`. Secondary: `scope`, `dependencies`.

Map findings to body sections:

| Section | Typical findings |
|---------|-----------------|
| **Blockers** | New component directly duplicates an existing one with no justification; introduces a second path that will diverge |
| **Risks** | Existing abstraction is close but needs extension; proposed name conflicts with existing conventions |
| **Gaps** | Missing consolidation opportunity; existing pattern not referenced in the plan |
| **Questions** | Ambiguous whether the proposed component overlaps with an existing one; needs author clarification |
| **Observations** | Naming convention notes; minor reuse opportunities; cases where the new component is genuinely novel |

---

## Structured Result Emission

**Format:** Follow the canonical schema at `skills/_shared/contracts/lens-result-contract.md`. That contract is the single source of truth for all panel lens output.

For this lens, set `lens: extension-check` in frontmatter. All other fields, severity vocabulary, body sections (Blockers/Risks/Gaps/Questions/Observations), concern area values, and blocked/failed output shape are defined in the contract.

---

## Codebase Access Strategy

This lens requires access to the target codebase, not just the plan or PR source:

- The working directory context or the PR URL in the source frontmatter identifies the target repo.
- Use `gh pr view` to determine the repo if a `pr_url` is available in the source frontmatter.
- Clone or navigate to the repo as needed. If already in the repo's working directory, use it directly.
- Use Explore subagents for all codebase search to keep the main context lean.

---

## Relationship to `/adversarial-review`

`/adversarial-review` includes an "Alternatives" lens that touches on existing-pattern reuse. This panel lens deepens that into a systematic codebase search with Explore subagents, giving extension checking a full context window and structured per-component output. The overlap is intentional — general checkup vs. specialist appointment.

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
