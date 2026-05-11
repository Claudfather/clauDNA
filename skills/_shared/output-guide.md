# Output Guide

Shared reference for planning skills that support `--output <target>`. Skills reference this file at `skills/_shared/output-guide.md`.

---

## 1. Overview

Planning skills support three output targets. The target controls **where** results are written, not **what** is produced — all targets receive the same level of detail.

| Target | Flag | Behavior |
|---|---|---|
| `docs` | (default, no flag needed) | Write phased planning docs to `documentation/planning/` |
| `github` | `--output github` | Write full plans as GitHub Issue bodies |
| `session` | `--output session` | Present in chat only, no persistence |

**All targets use Plan Mode** for the deliberation phase. The target only affects where the final artifact lands.

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
2. **Produce implementation-ready detail.** Every finding must include: before/after code examples, step-by-step instructions, verification checklist, and "What NOT To Do" guidance. See orchestration guide Section 5 for the full phase doc structure.
3. **Use Plan Mode for deliberation.** Enter Plan Mode before analysis begins. Exit Plan Mode when transitioning to output writing.

The output target is a persistence decision, not a quality decision.

---

## 3. Target: `docs` (Default)

Write phased planning documents to the project's `documentation/planning/` directory. This is the current default behavior — no changes from existing skill workflows.

**Session directory structure:**
```
documentation/planning/<subdirectory>/<session_name>_<YYYY-MM-DD>/
├── 00_OVERVIEW.md (or 00_TECH_DEBT.md, etc.)
├── 01_<phase-slug>.md
├── 02_<phase-slug>.md
└── ...
```

**References:**
- Phase doc structure: orchestration guide Section 5
- Archive convention: orchestration guide Section 8
- Subdirectory per skill: orchestration guide Section 8

**Subagent workflow:** Follow the Plan Agent → Disk pattern in orchestration guide Section 3. Plan agents write docs directly to the output directory.

---

## 4. Target: `github`

Write full implementation plans as GitHub Issue bodies. Each issue maps to one phase (one PR's worth of work), matching the "one PR per doc" convention.

### 4.1. Issue Body Format

The issue body uses a **structured format** that maps 1:1 to the phase doc structure (orchestration guide Section 5). This structure is a contract — it must be parseable by `--source github` in `/claudna:implement-plan`.

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

**Important:** The `## Implementation Plan` section with its `### Steps` subsection is what distinguishes a full-detail issue from a findings-only issue. When `/claudna:implement-plan --source github` reads an issue, it checks for this section to determine whether the issue is implementation-ready.

### 4.2. Issue Title

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

### 4.3. Labels

Apply these labels (create if they don't exist):

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

Skills that use severity systems map to issue priority:

| Severity | Issue Priority | Action |
|----------|---------------|--------|
| CRITICAL | `priority:critical` | Create issue immediately, flag to user |
| HIGH | `priority:high` | Create issue |
| MEDIUM | `priority:medium` | Create issue |
| LOW | `priority:low` | Create issue (may batch with related findings) |
| INFO | — | Skip unless particularly noteworthy |

### 4.5. Deduplication — Check Before Creating

**Before creating any issue, search for duplicates.** This is mandatory.

Use `gh` CLI:
```
gh issue list --repo <owner>/<repo> --search "<key terms>" --state open --limit 20
```

Search for:
- The specific file or function name involved
- The category of finding (e.g., "tech debt", "SQL injection", "N+1 query")
- Key symptoms or error messages

**Decision rules:**
- **Exact match** (same file, same finding): Skip. Do not create a duplicate.
- **Related but different** (same area, different finding): Create new issue and reference the related one with "Related: #NNN".
- **Similar pattern, different location** (e.g., same vulnerability in different files): Create one umbrella issue listing all locations, OR add a comment to an existing umbrella issue if one exists.
- **Previously closed**: If a closed issue covers the same finding, check if it was actually fixed. If the problem recurred, reopen with a comment explaining the recurrence. If it's a new instance, create a new issue referencing the old one.

### 4.6. Batch Creation Pattern

When creating multiple issues from a single audit:

1. **Create issues sequentially**, not in parallel — this avoids race conditions in dupe checking
2. **Log each created issue** — collect issue numbers and URLs for the summary
3. **Create a summary comment or issue** at the end linking all created issues:

```markdown
## Audit Summary: <skill-name> — <area> (<date>)

Created <N> issues from this audit:

- #101 [tech-debt] Duplicated validation logic
- #102 [tech-debt] Dead code in legacy handler
- #103 [tech-debt] Missing test coverage for auth module

Skipped <M> findings (duplicates of existing issues).
```

4. **Return the summary** to the orchestrator for user presentation and audit tracking

### 4.7. Subagent Workflow for `--output github`

When using subagents to generate plans:

1. **Research agents** work identically to the `docs` path — write research to scratch directory, return summaries.
2. **Plan agents** write their output to the scratch directory as temporary files (same structure as phase docs).
3. **The orchestrator** reads Plan agent metadata summaries, then creates GitHub issues from the temporary files using `gh issue create`.

This preserves the context window management benefits (orchestrator never reads full docs) while routing output to GitHub instead of `documentation/planning/`.

### 4.8. Error Handling

- If `gh` is not authenticated or the repo is not accessible, fall back to presenting findings in chat and ask the user to create issues manually.
- If label creation fails (permissions), create the issue without labels and note this in the summary.
- If issue creation fails for any reason, log the failure and continue with remaining issues. Present failures in the summary.

---

## 5. Target: `session`

Present findings and plans in the chat session only. No files or issues are created.

**Behavior:**
- The skill runs its full analysis pipeline (identical to other targets)
- Findings are presented in chat with the same level of detail
- Plan Mode remains active throughout — the skill does NOT exit Plan Mode to write output
- The session ends with a summary of findings and recommendations

**When to use:** "Think with me" sessions where the user wants analysis without creating artifacts. Useful for exploratory audits, second opinions, or scoping exercises before committing to a full remediation effort.

**Limitation:** `--output session` is incompatible with `--auto` (auto requires non-interactive output).

---

## 6. Integration with Audit Tracker

When running in automated/rolling audit mode (`--auto`), after creating issues:

1. Collect all created issue URLs
2. Return them to the calling workflow for logging in the local audit tracker
3. The audit tracker records: repo, directory, audit type, date, issue URLs, summary

This enables the "stale area" detection that drives the rolling audit rotation.

---

## 7. How Skills Should Reference This Guide

In the skill's Arguments section:
```
- `--output github`: Write findings and plans as GitHub Issues. See output guide (`skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Default (no flag): Write planning docs to `documentation/planning/`.
```

In the skill's output section (replacing "Alternative: GitHub Issues Output"):
```
## Output Targets

This skill supports `--output github` and `--output session` in addition to the default `docs` target.

Follow the output guide at `skills/_shared/output-guide.md`:
- For `github`: use the structured issue body format (Section 4), check for duplicates (Section 4.5), apply labels (Section 4.3)
- For `session`: present findings in chat, stay in Plan Mode (Section 5)
- For `docs` (default): follow the subagent workflow in the orchestration guide

[Skill-specific output notes, if any]
```
