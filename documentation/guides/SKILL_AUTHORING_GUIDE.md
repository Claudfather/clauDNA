# Skill Authoring Guide

How to write, test, and submit a skill for clauDNA. This guide takes you from idea to merged PR.

For the binding rules enforced by CI, see [SKILL_CONTRACT.md](../../SKILL_CONTRACT.md). For the contribution workflow (branching, PRs, changelogs), see [CONTRIBUTING.md](../../CONTRIBUTING.md). This guide focuses on _how to write a good skill_ — the craft, not just the contract.

## What Makes a Good Skill

A skill is a markdown file that teaches Claude how to do something specific, on demand, via a slash command. The best skills share three traits:

**1. Clear trigger.** A reader should know _exactly_ when to reach for this skill. The `description` field starts with "Use when..." and draws a sharp boundary. If you can't finish the sentence "Use when you need to..." in one clause, the skill might be too broad.

**2. Procedural, not referential.** A skill is a _procedure_ — steps the agent executes. It's not a reference document, a style guide, or a collection of tips. If the content reads like documentation rather than instructions, it's better as a knowledge file or an agent definition.

**3. Standalone.** A skill should work without depending on a running server, a database connection, or another skill having run first. It can _use_ external tools (git, gh, npm) and _call_ subagents, but it shouldn't require setup beyond what Claude Code already provides.

### Should This Be a Skill or an Agent?

| Skill | Agent |
|-------|-------|
| User invokes via `/claudna:<name>` | Invoked by name in conversation ("use code-reviewer to...") |
| Procedural: numbered steps, gates, output | Persona: tone, expertise, evaluation lens |
| Runs once, produces output, done | Persistent identity across a conversation |
| Examples: `audit`, `review-work`, `quick-commit` | Examples: `snowflake-analyst`, `code-reviewer`, `dbt-engineer` |

If your contribution defines _who_ the agent is (expertise, judgment criteria, personality), it's an agent. If it defines _what_ to do (steps, gates, output format), it's a skill.

## Step-by-Step: Your First Skill

### 1. Pick a Name

Skill names are `kebab-case`: lowercase letters, digits, hyphens. The name becomes both the directory name and the slash command (`/claudna:<name>`).

Conventions:
- Action verbs for workflow skills: `quick-commit`, `review-work`, `implement-plan`
- Bare tool name for infrastructure engines: `modal`, `railway`, `vercel`, `neon` — one engine with verb modes per `skills/_shared/infra-cli-contract.md`, never a `<tool>-<verb>` skill
- Audit capabilities are lenses of `/audit`, not standalone skills — a new audit concern is a new lens directory (see SKILL_CONTRACT §4)

### 2. Create the Directory

```bash
mkdir skills/your-skill-name
```

### 3. Write SKILL.md

Create `skills/your-skill-name/SKILL.md`. Every SKILL.md has two parts: YAML frontmatter and a markdown body.

#### Frontmatter

```yaml
---
name: your-skill-name
description: "Use when you need to do X after Y happens in the codebase."
---
```

That's the minimum. The full field reference:

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `name` | Yes | string | Must match the directory name exactly. `kebab-case`. |
| `description` | Yes | string | 20-500 characters. The routing surface the model reads when picking a skill — see "Writing the description" below. |
| `allowed-tools` | No | string or list | Restricts which tools the skill can use. Omit to allow all tools. Use when the skill runs dangerous commands and you want to whitelist specific patterns. |
| `argument-hint` | No | string | Shown when the user types `/claudna:<name>`. Convention: `[--flag] [positional-arg]`. Required if the skill accepts arguments (SKILL_CONTRACT §2). |
| `requires` | No | list | External runtime dependencies — each entry has exactly one of `cli` or `env`, plus an optional `reason`. See [SKILL_CONTRACT.md](../../SKILL_CONTRACT.md) for the schema. |
| `user-invocable` | No | boolean | Defaults to `true`. Set to `false` for context-only skills loaded by reference, not invoked as a slash command. |

The validator rejects unknown fields. Only the six fields listed above are accepted in frontmatter.

#### Writing the description

The `description` is the highest-leverage line in the skill: it is what the model reads when deciding which skill to load, and a description that misfires means the skill never runs (or runs when it shouldn't). The grammar is contract-bound ([SKILL_CONTRACT.md §2.1](../../SKILL_CONTRACT.md)) and validator-enforced. The craft version:

- **Lead with the trigger, not the topic.** "Use when a frontend page has performance symptoms — flickering, slow loads, janky scroll" beats "Frontend performance analysis." Temporal anchors ("Use when a PR has been merged…", "Use before starting substantive work…") tell the model *at which moment* to reach for the skill.
- **Describe the situation, never the procedure.** A description that summarizes the workflow ("dispatches lenses, folds findings, checks convergence") becomes a shortcut: the model follows the one-line summary instead of reading the body it abbreviates. State when; let the body say how.
- **Keep flags out.** `Supports --output github and --auto` is argument documentation, not a trigger — it lives in `argument-hint`. The validator hard-errors on any `--flag` token in a description.
- **Route away from confusable siblings.** If a user intent could plausibly land on two skills, partition it inside the descriptions: `/quick-commit` ends with "For the full commit-push-PR flow, use /claudna:commit-push-pr" and `/commit-push-pr` points back. The picker then cannot land wrong. Every `/claudna:<name>` reference is CI-checked to resolve.
- **Use words the model would match on.** Symptoms ("flaky", "stale", "janky scroll"), quoted trigger phrases ("Option A vs B"), and concrete nouns outrank abstractions.
- **Leave a breadcrumb on renames.** If the skill replaces older ones, end with `Replaces /old-name.` so old muscle memory still resolves.

**`allowed-tools` examples:**

String form (comma-separated):
```yaml
allowed-tools: Bash(git *), Bash(gh *), Read, Grep, Glob
```

List form (YAML array):
```yaml
allowed-tools:
  - Bash(git *)
  - Bash(gh *)
  - Read
  - Write
  - Edit
  - Grep
  - Glob
```

Both are equivalent. Use the canonical `Bash(cmd *)` pattern — the colon syntax `Bash(cmd:*)` is deprecated and validator-rejected.

**`argument-hint` examples:**

```yaml
# Simple positional
argument-hint: "[PR number or URL]"

# Flags and positionals
argument-hint: "[--auto] [--output github|session] [focus-area]"

# Source flag
argument-hint: "[--source github [number]] [file-path-or-directory]"
```

#### Body

The body is markdown. Start writing below the closing `---` of the frontmatter.

**Lead line.** Open with a one-sentence restatement of what the skill does. The agent reads this first when the skill is loaded.

**Procedure heading.** Use `## Procedure` for the main steps. Number them sequentially.

**Example skeleton:**

```markdown
---
name: your-skill-name
description: "Use when you need to audit configuration files for drift."
---

Audit configuration files for drift between declared and actual state.

## Procedure

1. Identify configuration files in the repository (look for `*.yaml`, `*.json`, `*.toml` in standard locations).

2. For each config file, compare declared values against the running environment.

3. Present findings grouped by severity:
   - **Drift detected** — declared value differs from actual
   - **Missing** — declared but not present in environment
   - **Undeclared** — present in environment but not in config

4. Ask the user which drifts to fix, then generate patches.
```

### 4. Validate

```bash
python3 scripts/validate-skills.py
```

Fix any violations. The validator checks frontmatter fields, name matching, description length, body length (minimum 200 characters), and stale hardcoded paths.

### 4b. Bump Version and Validate Manifest

Bump `version` in `.claude-plugin/plugin.json` — marketplace users only receive updates on version bumps. Then verify the manifest is valid:

```bash
python3 scripts/validate-manifest.py
```

### 5. Test Locally

```bash
claude --plugin-dir /path/to/clauDNA
```

This loads your local checkout as the plugin for one session. Invoke your skill (`/claudna:your-skill-name`) and verify it behaves as intended.

### 6. Submit

Follow the workflow in [CONTRIBUTING.md](../../CONTRIBUTING.md): branch, CHANGELOG entry, PR.

## Body Conventions

These patterns recur across the canonical skill set. They aren't validator-enforced, but they work.

### Numbered Steps

When ordering matters (most skills), use numbered steps under `## Procedure`. Each step is a discrete action. The agent executes them in order.

```markdown
## Procedure

1. Read the PR diff using `gh pr diff`.

2. Analyze each changed file for correctness, style, and potential issues.

3. Present a structured review with specific line references.
```

### Reference Files

For skills with substantial supporting material (checklists, question matrices, severity definitions), put that content in separate files in the skill directory rather than inlining it.

```
skills/review-work/
  SKILL.md                      # The engine: mode dispatch
  pr.md / changes.md / multi-pr.md   # Per-mode procedures
  review-dimensions.md          # 10 evaluation dimensions
  severity-categories.md        # Blocker/Suggestion/Nit/Question definitions
  red-flags-and-rationalizations.md  # Anti-patterns table
```

Reference them from SKILL.md:

```markdown
3. Evaluate the PR against each dimension in `review-dimensions.md` in this skill directory.
```

This keeps SKILL.md scannable while preserving depth. The agent reads the reference file at runtime when it reaches that step.

### HARD-GATE Pattern

A HARD-GATE is a non-negotiable blocking point — the skill must not proceed past it until a condition is met. Use `<HARD-GATE>` markers:

```markdown
4. **Gate check.**

<HARD-GATE>
Do NOT write any code until the challenge round in Step 3 is complete and the user
has confirmed the approach. If the user said "skip" or "looks good" without engaging
with the questions, re-present the top 3 concerns before proceeding.
</HARD-GATE>
```

HARD-GATEs appear in skills where the cost of skipping a step is high: `implement-plan` gates code writing behind a challenge round, `review-work` gates approval behind checklist verification. Use them sparingly — one or two per skill at most.

### User Confirmation Gates

Before irreversible actions (posting a review, creating issues, pushing code), ask the user:

```markdown
5. Present the review to the user. Ask: "Want me to post this review to the PR, or would you like to adjust anything first?"
```

This is a convention, not a HARD-GATE. The agent should respect the user's answer but doesn't need XML markers.

### Red Flags and Rationalizations Tables

For skills where the agent might rationalize skipping steps, include a table mapping common excuses to counter-arguments:

```markdown
## Red Flags

| Excuse | Reality |
|--------|---------|
| "This is a small change, doesn't need a full review" | Small changes cause big outages. Review proportionally, but review. |
| "The tests pass so it's fine" | Tests verify what was tested. Review covers what wasn't. |
```

These tables are surprisingly effective at preventing the agent from taking shortcuts.

## Common Patterns

### Subagent Delegation

For skills that need to analyze a large codebase, delegate to Explore subagents rather than reading everything in the main context:

```markdown
2. Use Explore subagents to scan the codebase for relevant files:
   - Search for configuration files matching common patterns
   - Identify which modules depend on the configuration
   - Check for environment-specific overrides
```

Subagents run in their own context, keeping the main skill's context clean. Use them for read-heavy scout work before the skill's critical decision points.

### Output Modes

Skills that produce substantial output can support multiple delivery targets via an `--output` flag:

```markdown
argument-hint: "[--output github|session] [focus-area]"
```

The three common modes:

| Mode | Behavior |
|------|----------|
| `--output github` | Create GitHub issues for each finding |
| `--output session` | Print findings in the chat (no file/issue creation) |
| Default (no flag) | Write findings to documentation files |

Implement this by checking the argument early and branching the output step:

```markdown
7. Deliver findings based on the output mode:
   - If `--output github`: create one GitHub issue per finding using `gh issue create`
   - If `--output session`: present findings in chat, organized by severity
   - Otherwise: write a findings document to `docs/` or the project's documentation directory
```

### Plan Mode

Skills that need a deliberation phase before execution can use Plan Mode. This is a Claude Code feature that restricts the agent to read-only tools during planning:

```markdown
2. Enter Plan Mode to analyze the codebase without making changes.

3. Draft the remediation plan. Present it to the user for review.

4. Exit Plan Mode. Begin implementation.
```

Use Plan Mode when the skill has a distinct "analyze, then act" structure and you want to prevent premature execution.

### Autonomous Mode

Some skills support a `--auto` flag that skips user confirmations for low-risk actions:

```markdown
argument-hint: "[--auto] [--output github|session]"
```

In autonomous mode, the skill proceeds through steps without asking for confirmation at each gate. Reserve this for skills where the actions are safe to auto-execute (generating reports, creating draft PRs) — not for skills that delete, push, or post externally.

## Anti-Patterns

### Skills That Should Be Agents

If the content defines judgment criteria, evaluation dimensions, or a persistent persona rather than a procedure with steps, it's an agent definition. Write it as an agent file in `agents/` instead.

**Symptom:** the "skill" has no numbered steps and reads like "You are an expert in X who evaluates Y by considering Z."

### Skills That Depend on Hosted Services

Skills should work with tools available in a standard Claude Code session: git, gh, npm/npx, standard CLI tools. Don't write a skill that requires a running database, a specific API endpoint, or a custom server.

**Exception:** skills for managed platforms (Vercel, Railway, Modal, Neon) where the CLI tool handles authentication and the user has already set up credentials. These are platform-specific by design.

### Over-Long Skills

If SKILL.md exceeds ~500 lines, the agent's context fills up just loading the skill. Split the content:

- Move checklists, question matrices, and reference tables to separate `.md` files in the skill directory
- Keep SKILL.md focused on the procedure
- Reference supporting files by name: "See `checklist.md` in this skill directory"

### Hardcoded Paths

Never reference `~/.claude/skills/`, `~/.claude/commands/`, or `~/.claude/agents/` — those are legacy install paths. The plugin system handles file discovery. The validator catches this in SKILL.md bodies, agent files, and `_shared/` files; skill support files (templates and other non-SKILL.md files in a skill directory) are not yet scanned.

### Duplicate Functionality

Before writing a new skill, check the existing skills in `skills/`. If an existing skill does 80% of what you want, consider improving it rather than creating a parallel one.

## Worked Example 1: Simple Skill

A skill that audits a repo's license compliance.

```
skills/license-audit/SKILL.md
```

```markdown
---
name: license-audit
description: "Use when you want to check that all project dependencies have compatible licenses and no problematic licenses slipped in."
---

Audit project dependencies for license compatibility issues.

## Procedure

1. Identify the project's package manager by checking for `package.json`, `requirements.txt`,
   `Cargo.toml`, `go.mod`, or `pyproject.toml` at the repo root.

2. List all direct and transitive dependencies with their licenses:
   - Node: `npx license-checker --json`
   - Python: `pip-licenses --format=json` (suggest install if missing)
   - Go: `go-licenses report ./...` (suggest install if missing)
   - Rust: `cargo license --json`

3. Flag dependencies with problematic licenses:
   - **Blockers:** GPL-3.0, AGPL-3.0 (copyleft — may require open-sourcing the project)
   - **Warnings:** LGPL, MPL (copyleft with linking exceptions — review usage)
   - **Unknown:** packages with no detected license (manual review needed)

4. Present findings grouped by severity. For each flagged dependency, show:
   - Package name and version
   - Detected license
   - Why it's flagged
   - Suggested action (replace, verify, accept risk)

5. Ask the user if they want a `LICENSE_AUDIT.md` report written to the repo root.

## Red Flags

| Excuse | Reality |
|--------|---------|
| "It's just a dev dependency" | Dev deps can still trigger copyleft if they generate output included in the build. |
| "We're open source anyway" | Open source doesn't mean GPL-compatible. MIT projects can't absorb AGPL deps. |
```

**What makes this work:** clear trigger, linear procedure, concrete tool commands, severity grouping, user confirmation before file creation, and a red flags table.

## Worked Example 2: Skill With Subagents and Output Modes

A skill that finds unused exports across a TypeScript codebase.

```
skills/unused-exports/
  SKILL.md
  severity-rules.md
```

`SKILL.md`:

```markdown
---
name: unused-exports
description: "Use when you want to find exported functions, types, and constants that are never imported anywhere in the codebase. Supports --output github to file issues."
argument-hint: "[--output github|session] [directory]"
allowed-tools: Bash(git *), Bash(gh *), Read, Grep, Glob
---

Find exported symbols that are never imported — dead code that inflates bundle size and
confuses contributors.

## Procedure

1. Determine the scan scope:
   - If the user provided a directory argument, scope to that directory
   - Otherwise, scan `src/` or the project root

2. Use Explore subagents to build the export inventory:
   - Find all files matching `*.ts`, `*.tsx` (exclude `node_modules/`, `dist/`, `*.test.*`, `*.spec.*`)
   - Extract every `export` declaration (named exports, default exports, re-exports)
   - Record: file path, symbol name, export type (function, type, const, class)

3. Use Explore subagents to build the import map:
   - For each exported symbol, search the codebase for imports of that symbol
   - Check both named imports (`import { X }`) and namespace imports (`import * as Y`)
   - Check re-exports from barrel files (`index.ts`)

4. Cross-reference: any export with zero imports outside its own file is a candidate.

5. Apply severity rules from `severity-rules.md` in this skill directory:
   - **High:** exported function with zero imports (dead code)
   - **Medium:** exported type with zero imports (dead type — less urgent)
   - **Low:** exported constant with zero imports (may be used at runtime via string reference)

6. Present findings sorted by severity, grouped by directory.

<HARD-GATE>
Do NOT suggest deleting any export until the full scan is complete. Partial results
lead to false positives — barrel file re-exports can make a symbol appear unused
when it is actually consumed downstream.
</HARD-GATE>

7. Deliver results based on output mode:
   - If `--output github`: create one issue per high-severity finding, batch medium/low into a single issue
   - If `--output session`: print the full report in chat
   - Otherwise: write `UNUSED_EXPORTS.md` to the repo root

8. Summarize: total exports scanned, unused found, breakdown by severity.
```

`severity-rules.md`:

```markdown
# Severity Rules for Unused Exports

## High — Exported Functions

An exported function with zero external imports is almost certainly dead code.
Functions have clear call sites; if nothing calls it, it's unused.

Exception: entry points (main, handler, middleware registered by framework convention).
If the function name matches common entry-point patterns, downgrade to Medium.

## Medium — Exported Types

An exported type with zero imports may be dead, or may be used indirectly via
type inference. TypeScript can propagate types without explicit imports.

Flag but don't auto-suggest deletion without verifying no runtime impact.

## Low — Exported Constants

Constants may be consumed at runtime via dynamic access (`config[key]`),
environment-conditional imports, or framework conventions.

Report but recommend manual review rather than deletion.
```

**What makes this work:** subagent delegation for heavy scanning, HARD-GATE preventing premature deletion suggestions, output modes for different workflows, reference file for severity rules, and `allowed-tools` restricting the skill to read-only operations plus git/gh.

## Submission Checklist

Before opening your PR:

- [ ] `python3 scripts/validate-skills.py` passes
- [ ] `python3 scripts/validate-manifest.py` passes
- [ ] Skill tested locally with `claude --plugin-dir /path/to/clauDNA`
- [ ] `name` in frontmatter matches directory name
- [ ] `description` begins with `Use ` (when/at/before/after/to — SKILL_CONTRACT §2.1 rule 1) and is 20-500 characters
- [ ] Body is at least 200 characters
- [ ] No hardcoded paths to `~/.claude/skills/`, `~/.claude/commands/`, or `~/.claude/agents/`
- [ ] No duplicate of an existing skill (checked the skills in `skills/`)
- [ ] CHANGELOG.md entry added under `[Unreleased]`
- [ ] Version bumped in `.claude-plugin/plugin.json`
- [ ] PR template filled out

Welcome to clauDNA.
