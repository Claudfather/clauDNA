---
name: tech-debt
user-invocable: true
description: "Use when you want to find and plan remediation of technical debt in the codebase. Supports --output github to create issues and --output session for chat-only analysis."
argument-hint: "[--auto] [--output github|session] [focus-area]"
requires:
  - cli: gh
    reason: "GitHub CLI for issue creation (--output github mode)"
---

# Tech Debt Finder & Remediation Planner

Find, report, and plan remediation of technical debt in the current codebase.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Fully non-interactive. Implies `--output github`. Scans, creates issues, returns summary. See orchestration guide Section 10.
- `--output github`: Write findings and plans as GitHub Issues. See output guide (`skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Remaining text is the focus area (e.g., `src/api/` or `auth module`). If provided, scope the scan to that area instead of the full codebase.

## When NOT to use

- For security-specific vulnerabilities → use `/claudna:security-audit`
- For frontend performance issues → use `/claudna:frontend-performance-audit`
- For product feature gaps → use `/claudna:product-enhance`

**Enter Plan Mode.** Call `EnterPlanMode` to enter deliberation mode. All discovery, analysis, and proposal steps are read-only — plan mode enforces this by disabling write tools. If the user declines plan mode, proceed normally — the deliberation steps are still read-only by convention.

## Constraints

These constraints arbitrate every cleanup decision. When in doubt, defer to them in this order:

1. **No functionality regression.** Cleanup must preserve behavior. The test suite must pass before AND after each change. If a refactor would change observable behavior — even subtly — it's out of scope of this skill: flag it as a separate issue and skip. The whole point of `/claudna:tech-debt` is to ship cleaner code with the same semantics; any uncertainty about preservation is reason to bail on the change.

2. **Call-site check on every edited surface.** Renaming a symbol, extracting a function, decomposing a file, or relocating a constant all change the surface that callers reach. Before merging any cleanup PR, grep every caller of the edited surface (function name, type, exported constant, file path, route handler) and verify each still resolves. Run tests on the touching surfaces specifically. A missed call-site is the most common form of "behavior-preserving" refactor that quietly breaks production — guard against it explicitly.

3. **Idiomatic to the codebase ("when in rome").** Don't introduce patterns the codebase doesn't already use. If the codebase is imperative, don't bolt on FP. If it uses one ORM or one HTTP client, don't add another. If it's class-based, don't pivot to closures. The cleanup respects existing conventions; it doesn't import outside style. A cleaner abstraction that fights the codebase's grain is worse than the duplication it was trying to remove.

4. **Reference frame.** Channel the lessons of Michael Feathers (*Working Effectively with Legacy Code* — characterization tests, seams, dependency-breaking) and Robert C. Martin (*Clean Code* — meaningful names, small functions, single responsibility, KISS). These set the bar for what "good" looks like, but Constraint 3 always wins over a Martin-aligned pattern that fights the codebase's grain. Use them as inspiration, not as a checklist applied dogmatically.

## Phase 1: Scan & Report

Scan the codebase across two tiers: **quality axes** (the cleanup vectors that change how the code reads and composes) and **hygiene checks** (objective debt that builds up over time).

Do NOT read CLAUDE.md or MEMORY.md directly — Claude already has both in its system prompt. Use the system prompt context for project understanding; focus scan effort on code patterns and structure.

### Quality axes — five vectors that shape readability and composition

#### 1. DRY violations (duplicated code, logic, config, strings)

Detect the project language from the codebase (look at file extensions, `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod`, etc.). Use the Glob tool with appropriate patterns (e.g., `**/*.py`, `**/*.ts`, `**/*.go`).

Look for:
- Copy-pasted functions
- Similar logic in multiple places (especially across files that share a domain)
- Repeated patterns that could be abstracted IF the abstraction is idiomatic per Constraint 3
- Repeated string/regex/path literals that should be a single named constant
- Three-or-more recurrences of the same shape (two recurrences are not duplication; they're coincidence — wait for the third before extracting)

Bias against premature abstraction. Three similar lines is often better than a leaky abstraction that fights the codebase.

#### 2. Magic numbers and strings

Find hardcoded literals that obscure intent:
- Numbers used in business logic without a named constant (`if score > 0.85` → `if score > MIN_QUALITY_THRESHOLD`)
- Hardcoded strings that recur or carry meaning (`"admin"` role checks, route paths, env-var names, status enum values)
- Inline regexes that should be a named pattern
- Magic timeouts, retry counts, batch sizes — anything tunable without context

Each finding: name a candidate constant + suggest the right place for it (module-level, config file, types file). Do NOT extract single-use literals where the context already makes the meaning obvious (e.g., `pi = 3.14159` in a math file; `port = 8080` in a one-off script).

#### 3. Naming clarity (clear, unambiguous names)

Find names that obscure intent:
- Single-letter or generic variables (`x`, `data`, `item`, `tmp`) where the surrounding context doesn't make their role obvious
- Function names that don't say what they return or what side-effect they perform (`process()`, `handle()`, `run()`)
- Type/class names that describe shape but not purpose (`UserData` when the type is `Author`)
- Boolean variables phrased as nouns (`status` should be `is_active`, `flag` should be `should_retry`)
- File names that don't reflect contents

For each finding: propose a clearer name. Reject renames that "add information" by trading one ambiguity for another (e.g., `data` → `info` is not a fix).

#### 4. Single Responsibility violations (function and file scope)

A function or file does too much when it can be described only with "and": "this function fetches the user AND validates the role AND writes the audit log."

Function scope — flag:
- Functions with deep nesting (>3 levels)
- Functions with many parameters (>5) — often a sign of mixed concerns
- Functions whose docstring/comment lists multiple unrelated steps
- Functions over ~50 lines (rough heuristic; defer to language convention)

File/module scope — flag:
- Files mixing route handlers, business logic, and DB queries when the codebase elsewhere separates them
- Files with unrelated exports (utils.ts dumping ground)
- Files that fight the directory structure (a `auth/` file that contains logging logic)

Splitting recommendations should NOT proliferate files. The right pattern is "extract this responsibility to a sibling file that already exists, or to a new file IF the codebase has precedent for that scope of file."

#### 5. KISS — simplicity and human readability

Find code that is more complex than the problem warrants:
- Over-abstracted utilities consumed once (an `IUserService` interface with one impl)
- Clever one-liners that obscure linear logic (`reduce` chains better expressed as a `for` loop in this codebase)
- Premature performance optimizations that have no measured impact
- Generic-typed functions where concrete types would read cleaner
- Multi-level inheritance hierarchies where composition or a switch would suffice
- Comment-explaining-code-instead-of-clarifying-code situations (the comment is a tell that the code is too complex)

For each: propose a simpler shape. The simplification must respect Constraint 3 (idiomatic to codebase) — don't strip a useful abstraction just because it's "clever."

### Hygiene checks — objective debt that accumulates over time

#### 6. TODO/FIXME comments

Use the Grep tool with pattern `TODO|FIXME|HACK|XXX`, glob `*.{py,js,ts}`, `output_mode: content`, and `head_limit: 30`.

#### 7. Large files

Use the Glob tool with the detected language patterns to find source files, then run `wc -l` on the results to identify large files. Files over 300 lines may need splitting (see SRP at #4 above for the reasoning).

#### 8. Missing tests

Compare source files to test files — flag untested modules.

#### 9. Outdated dependencies

Detect the package manager and run the appropriate command:
- Python: `pip list --outdated`
- Node: `npm outdated` or check `package.json`
- Rust: `cargo outdated` (if installed)
- Go: check `go.mod` for old versions

Skip gracefully if the tool isn't installed.

#### 10. Dead code

Find code that is no longer reached or referenced:
- Unused imports
- Unreachable code paths
- Commented-out code blocks
- Functions/types/constants with zero call-sites (verify via grep — false positives happen with dynamic dispatch, reflection, or test-only callers)
- Feature-flag code paths whose flag has been off for >6 months
- Old migration helpers / scaffolding code that the surrounding system has outgrown

The call-site check from Constraint 2 cuts both ways here: a careful grep is the difference between "cleanup that ships" and "production breakage when the dynamic dispatch finally fires."

### Scan Output

Provide a prioritized list:
1. **High Priority** - Bugs waiting to happen, security issues
2. **Medium Priority** - Maintainability concerns, duplication
3. **Low Priority** - Style issues, minor improvements

For each item, suggest a specific fix.

---

## Phase 2: Generate Remediation Plans

After presenting the scan results, **ask the user to confirm** whether they want to generate the full tech debt documentation and phased remediation plans. Do NOT proceed without explicit confirmation.

Ask: "Would you like me to generate detailed tech debt documentation and phased remediation plans?"

**Exit Plan Mode.** Call `ExitPlanMode` to transition to execution mode. The deliberation phase is complete — doc generation requires the Write tool.

If yes, ask the user for a **short session name** (e.g., `api-cleanup`, `db-layer`) or derive one from the focus area. All output goes into:

```
documentation/planning/tech_debt/<session_name>_<YYYY-MM-DD>/
├── 00_TECH_DEBT.md
├── 01_<remediation-slug>.md
├── 02_<remediation-slug>.md
└── ...
```

> **Archive convention:** See orchestration guide, Section 8.

### If the user confirms, generate the following:

#### A. Master Tech Debt Document

Create `00_TECH_DEBT.md` in the session directory containing:
- Complete inventory of all findings from Phase 1
- Severity scoring (blast radius, complexity, risk)
- Prioritized remediation order
- Dependency matrix showing which work blocks other work

#### B. Phased Enhancement Plans

Create individual plan documents prefixed by execution order: `01-*.md`, `02-*.md`, etc.

Each plan document represents **exactly 1 PR** and must include:

1. **PR title, risk level, estimated effort, files modified**
2. **Dependencies** (which phases must be completed first) and **blocks** (which phases this unlocks)
3. **Explicit code references** - file paths, line numbers, function names, class names
4. **Before/after code examples** showing exact changes to make
5. **Step-by-step implementation instructions** leaving zero ambiguity
6. **Verification checklist** (tests to run, commands to execute, things to manually check)
7. **"What NOT To Do" section** - common pitfalls and anti-patterns to avoid
8. **Behavior preservation gate** (load-bearing per Constraints 1 + 2). Each PR must list explicitly:
   - Pre-change baseline: full test suite passes locally on the branch's parent commit (capture command + result).
   - Post-change verification: same test suite passes after the change (capture command + result).
   - Call-site audit: for every renamed/extracted/moved surface, list the grep command used to find callers and confirm each was updated. If a caller resists trivial migration, abort the change — it's a sign the refactor is changing more than the surface.
   - Manual smoke (where applicable): UI changes get a dual-mode visual smoke; API changes get a representative curl/HTTP probe; data-layer changes get a sample query.
   - If any item above can't be filled in honestly, the PR is OUT of scope for `/claudna:tech-debt` — split or skip.

#### C. Subagent Workflow

Follow Section 9 of the orchestration guide (`skills/_shared/orchestration-guide.md`). Scratch directory: `/tmp/tech-debt-<YYYY-MM-DD_HHMMSS>/research/`. Plan agents read research from this directory.

---

## Phase 2.5: Adversarial Review Pass

After Plan agents return with their metadata summaries (and the master `00_TECH_DEBT.md` doc is written), run adversarial review on each generated doc to stress-test the remediation plans before publishing/handoff. Apply in both `--output docs` and `--output github` (where each issue body is treated as a plan doc) and in `--auto` mode.

### Procedure

For each phase doc generated by Phase 2 (path: `documentation/planning/tech_debt/<session>/<NN>_*.md`), and for the master `00_TECH_DEBT.md`:

1. Dispatch a `general-purpose` subagent using the prompt template in `skills/_shared/subagent-prompts/adversarial-chain.md`. Substitute `<DOC_PATH>` with the phase doc's filesystem path.

2. Collect the subagent's structured-result JSON block. If `outcome` is `completed`, parse `artifacts.findings`.

3. Use the Edit tool to append an `## Adversarial Review Findings` section to the phase doc with the findings as markdown checkbox bullets (format per `skills/_shared/subagent-prompts/adversarial-chain.md`).

4. If `outcome` is `blocked` or `errors` is non-empty, log a note in the orchestrator session but proceed with the next doc — adversarial-review failure does not block plan publishing.

### Parallelism

Launch all adversarial-review subagents in parallel using `run_in_background: true`, then collect via `TaskOutput` one at a time. This mirrors the Plan-agent dispatch pattern in §6 of the orchestration guide.

### `--output github` adaptation

When the planning output is GitHub Issues (not phase docs), run adversarial-review on the proposed issue body BEFORE creating the issue. Pass the body content directly to the subagent (write it to `<scratch>/issue-<N>-body.md` as a temporary file, run adversarial-review against that path, fold findings into the body, then create the issue with the augmented body).

### Skipping in degenerate cases

If Phase 2 produced zero phase docs (no findings worth a plan), skip Phase 2.5 entirely. No phase docs = nothing to review.

---

## Output Targets

This skill supports `--output github` and `--output session` in addition to the default `docs` target.

Follow the output guide at `skills/_shared/output-guide.md`:
- For `github`: write each finding as a doc (frontmatter + the Section 4 body skeleton) and delegate to `/claudna:publish <file> --to github-issue --repo <repo>` — publish validates, dedups, and applies labels from `tags:`. Map scan priorities: High → `priority:high`, Medium → `priority:medium`, Low → `priority:low`.
- For `session`: produce the doc, then `/claudna:publish <file> --to session` prints it to chat (Section 5)
- For `docs` (default): follow the subagent workflow in the orchestration guide

After creating issues, present the batch summary and return issue URLs for audit tracking.

---

## Autonomous Mode (--auto)

When `--auto` is set (see orchestration guide Section 10):
1. Skip Plan Mode — go straight to Phase 1 scan
2. Skip the user confirmation gate between Phase 1 and Phase 2
3. Implies `--output github`
4. Use focus area from `$ARGUMENTS` as scope. If none provided, scan full codebase but limit to top 10 findings.
5. Create GitHub Issues per the output guide (`--output github`) for all findings above LOW severity
6. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "tech-debt",
  "outcome": "completed",
  "artifacts": {
    "issues_created": ["https://github.com/org/repo/issues/123", "..."],
    "session_dir": "documentation/planning/tech_debt/<session>/",
    "files_changed": 0
  },
  "summary": "<2-3 line digest of N findings, M issues filed>",
  "next": "<follow-up hint or null>",
  "errors": [],
  "blocker_description": null
}
```

- `outcome` should be `completed` on a successful run, `partial` if some issues failed to create (gh CLI errors), `blocked` if the scan couldn't run (e.g., no git repo).
- `next` may suggest follow-up like `"Apply /claudna:implement-plan --source github <#> --auto to highest-severity issue"`.
