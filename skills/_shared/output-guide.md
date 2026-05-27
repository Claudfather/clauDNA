# Output Guide

Shared reference for planning skills that support `--output <target>`. Skills reference this file at `skills/_shared/output-guide.md`.

**Author writes content → `/claudna:publish` enforces + routes.** Skills are *authors*: they run their analysis and produce a markdown doc with valid frontmatter and the house-style body skeleton (defined below). They never call `gh` themselves. `/claudna:publish` is the *publisher*: it validates the doc against this spec, dedups per-medium, and routes it to the chosen edition. This guide is the canonical house-style spec — skills read it for *what to produce*, and `/claudna:publish` reads it for *what to enforce*.

---

## 1. Overview

Planning skills support three output targets. The target controls **where** the doc lands, not **what** is produced — all targets receive the same doc at the same level of detail.

| Target | Flag | Routing | Behavior |
|---|---|---|---|
| `docs` | (default, no flag needed) | _written directly_ | Write phased planning docs to `documentation/planning/<skill>/<session>_<date>/` (as today) |
| `github` | `--output github` | `/claudna:publish --to github-issue` | Create a GitHub issue from the doc |
| `session` | `--output session` | `/claudna:publish --to session` | Print the doc body back into the chat, no persistence |

**The `github` and `session` targets route through `/claudna:publish`.** The default `docs` target still writes phased planning docs to `documentation/planning/` directly — unifying it through publish's `--to disk` adapter is **deferred**, because publish's disk adapter targets the shared-docs vault (`shared/planning/active/`), a different destination than per-project `documentation/planning/`. Reconciling the two is its own change.

**All targets use Plan Mode** for the deliberation phase.

### Activation

The user activates a non-default target by:
1. Passing `--output github` or `--output session` as an argument
2. Saying "create issues" or "file issues" during the skill flow (implies `--output github`)
3. Automated/rolling audit workflows with `--auto` (implies `--output github`)

### Compatibility

- `--auto` implies `--output github`. Skills that support `--auto` do NOT support `--output session` (contradictory — auto is non-interactive, session is interactive).
- `--output session` is always available for interactive use. It produces the same analysis quality as other targets.

---

## 2. Common Requirements — All Targets

Regardless of output target, every skill must:

1. **Run the full analysis pipeline.** No phases are skipped based on output target. The scan, analysis, and plan generation phases all execute identically.
2. **Produce a publishable doc.** Each unit of output is a markdown file with the frontmatter (Section 3) and the body skeleton (Section 4) below. Every finding includes before/after code examples, step-by-step instructions, a verification checklist, and "What NOT To Do" guidance.
3. **Delegate GitHub/session output to `/claudna:publish`.** Never run `gh issue create` / `gh pr create` directly. For `--output github` or `--output session`, invoke `/claudna:publish <file> --to <edition>` (mapping in Section 1) — publish handles validation, dedup, labels, and the destination. For the default `docs` target, write the doc to `documentation/planning/` directly (see Section 1 note).
4. **Use Plan Mode for deliberation.** Enter Plan Mode before analysis begins. Exit Plan Mode when transitioning to writing the doc + publishing.

The output target is a persistence decision, not a quality decision.

---

## 3. The Publishable Doc — Frontmatter

Every doc an author hands to `/claudna:publish` carries YAML frontmatter. Publish validates these (and rejects malformed docs):

| Field | Rule |
|-------|------|
| `title` | Issue/page title. For findings use the format in Section 4.2. |
| `type` | One of: `plan`, `decision`, `knowledge`, `runbook`, `audit`, `review`. Audits/reviews/plans require the body skeleton in Section 4.1. |
| `status` | Valid for the type (`audit`/`review`: `draft`\|`completed`; `plan`: `draft`\|`active`\|`completed`\|`superseded`; etc.) |
| `owner` | The skill or user that produced it. |
| `created` | `YYYY-MM-DD`. |
| `tags` | Labels to apply (github-issue edition maps these → `--label`). Use the taxonomy in Section 4.3. |
| `repos` | Target repo(s); a single value lets the github/disk adapters infer destination. |
| `links` | Publish writes the destination URL back here after publishing. |

---

## 4. House Style for GitHub Issues (`--output github` → `--to github-issue`)

Each issue maps to one phase (one PR's worth of work), matching the "one PR per doc" convention. The author writes the doc; `/claudna:publish --to github-issue` creates the issue from it.

### 4.1. Issue Body Format

The body uses a **structured format** that maps 1:1 to the phase doc structure (orchestration guide Section 5). This structure is a contract — it must be parseable by `--source github` in `/claudna:implement-plan`, and `/claudna:publish` validates its presence for `type: audit|review|plan` before publishing.

```markdown
## Summary

<2-3 sentences: what was found, why it matters, and the intended fix>

## Evidence

<Specific code references with file:line, current behavior, measurements if applicable>

## Implementation Plan

### Dependencies
<Phase/issue numbers that must be completed first, or "None">

### Blocks
<Phase/issue numbers this unlocks, or "None">

### Steps

<Step-by-step implementation instructions with:>
<- Explicit file paths, line numbers, function names>
<- Before/after code examples showing exact changes>
<- New files to create with content or detailed skeleton>
<- Zero ambiguity — a junior engineer can execute without asking questions>

## Test Plan

<- New tests to write (with descriptions of what they verify)>
<- Existing tests to modify>
<- Manual verification steps>

## Verification Checklist

- [ ] <specific check 1>
- [ ] <specific check 2>
- [ ] <specific check N>

## What NOT To Do

<Common pitfalls, anti-patterns, things that look right but are wrong>

## Context

- Source skill: <skill-name>
- Audit date: <YYYY-MM-DD>
- Area: <directory or module>
- Effort: <Low/Medium/High>
- Risk: <Low/Medium/High>
- Priority: <Critical/High/Medium/Low>
- Related issues: #NNN, #NNN (if any)
```

**Important:** The `## Implementation Plan` section with its `### Steps` subsection is what distinguishes a full-detail issue from a findings-only issue. `/claudna:publish` rejects an `audit`/`review`/`plan` doc that lacks it, and `/claudna:implement-plan --source github` checks for it to decide whether an issue is implementation-ready.

### 4.2. Issue Title (the `title:` frontmatter field)

```
[<type>] <concise description> — <file or area>
```

Type prefixes:
- `[tech-debt]` — Technical debt findings
- `[security]` — Security vulnerabilities
- `[perf]` — Performance issues
- `[enhancement]` — Feature/improvement proposals
- `[design]` — Design/UX issues
- `[docs]` — Documentation gaps

### 4.3. Labels (the `tags:` frontmatter field)

Put these in `tags:`; `/claudna:publish` applies them as issue labels (creating any that don't exist):

| Label | When |
|-------|------|
| `auto-audit` | Always — marks issues created by automated review |
| `tech-debt` | Technical debt findings |
| `security` | Security vulnerabilities |
| `performance` | Performance issues |
| `enhancement` | Feature proposals |
| `design` | Design/UX issues |
| `priority:critical` | Exploitable vulnerabilities, data loss risks |
| `priority:high` | Significant impact, should fix soon |
| `priority:medium` | Moderate impact, plan to address |
| `priority:low` | Minor, address when convenient |

### 4.4. Severity-to-Priority Mapping

Skills that use severity systems map severity to a `priority:*` tag:

| Severity | Priority tag | Action |
|----------|--------------|--------|
| CRITICAL | `priority:critical` | Create issue immediately, flag to user |
| HIGH | `priority:high` | Create issue |
| MEDIUM | `priority:medium` | Create issue |
| LOW | `priority:low` | Create issue (may batch with related findings) |
| INFO | — | Skip unless particularly noteworthy |

### 4.5. Deduplication (handled by `/claudna:publish`)

The author does **not** dedup. The `github-issue` adapter of `/claudna:publish` searches for existing open issues before creating, and applies these rules:

- **Exact match** (same file, same finding): Skip; report the existing issue URL.
- **Related but different** (same area, different finding): Create and add `Related: #NNN`.
- **Similar pattern, different location**: Prefer one umbrella issue listing all locations.
- **Previously closed**: If it recurred, reopen with a comment; if a new instance, create referencing the old.

(Disk dedup = compare-and-warn on an existing file; session has no dedup.)

### 4.6. Batch Creation Pattern

When a single audit yields multiple docs:

1. **Publish sequentially**, not in parallel — this lets publish's dedup see prior creations.
2. **Collect each returned URL** for the summary.
3. **Produce a summary doc** at the end linking all created issues and publish it too (or present in session):

```markdown
## Audit Summary: <skill-name> — <area> (<date>)

Created <N> issues from this audit:

- #101 [tech-debt] Duplicated validation logic
- #102 [tech-debt] Dead code in legacy handler
- #103 [tech-debt] Missing test coverage for auth module

Skipped <M> findings (duplicates of existing issues).
```

4. **Return the summary** to the orchestrator for user presentation and audit tracking.

### 4.7. Subagent Workflow

When using subagents to generate plans:

1. **Research agents** write research to a scratch directory and return summaries.
2. **Plan agents** write each doc (frontmatter + skeleton) to the scratch directory.
3. **The orchestrator** invokes `/claudna:publish <scratch-file> --to github-issue --repo <repo>` per doc — it never reads the full doc or calls `gh` itself.

This preserves context-window management (the orchestrator works from metadata summaries) while routing output through the single publisher.

### 4.8. Error Handling

`/claudna:publish` reports adapter errors verbatim (auth failure, missing repo, label-creation failure). If publish reports it cannot reach GitHub, fall back to `--to session` (present the doc in chat) and tell the user to publish later. Continue with remaining docs and surface failures in the summary.

---

## 5. Target: `session` (`--to session`)

Present the doc in the chat session only — no files or issues. The skill runs the full analysis pipeline and produces the same publishable doc as other targets, then hands it to `/claudna:publish <file> --to session`, which prints the body back to chat. Plan Mode remains active throughout (the skill does not exit Plan Mode to persist anything).

**When to use:** "Think with me" sessions — exploratory audits, second opinions, or scoping before committing to remediation.

**Limitation:** incompatible with `--auto` (auto requires non-interactive persistence).

---

## 6. Integration with Audit Tracker

When running in automated/rolling audit mode (`--auto`), after publishing:

1. Collect all issue URLs returned by `/claudna:publish`.
2. Return them to the calling workflow for logging in the local audit tracker.
3. The audit tracker records: repo, directory, audit type, date, issue URLs, summary.

This enables the "stale area" detection that drives the rolling audit rotation.

---

## 7. How Skills Should Reference This Guide

In the skill's Arguments section:
```
- `--output github`: Write findings and plans as GitHub Issues (via /claudna:publish). See output guide (`skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Default (no flag): Write planning docs to disk.
```

In the skill's output section:
```
## Output Targets

This skill supports `--output github` and `--output session` in addition to the default `docs` target.

Produce each unit of output as a markdown doc with frontmatter + the body skeleton in
`skills/_shared/output-guide.md`, then delegate to `/claudna:publish`:
- `--output github` → `/claudna:publish <file> --to github-issue --repo <repo>` (Section 4)
- `--output session` → `/claudna:publish <file> --to session` (Section 5)
- `docs` (default) → write to `documentation/planning/<skill>/<session>_<date>/` directly (publish-disk unification deferred, see Section 1)

Never call `gh` directly for GitHub output — `/claudna:publish` owns validation, dedup, labels, and routing.

[Skill-specific output notes, if any]
```
