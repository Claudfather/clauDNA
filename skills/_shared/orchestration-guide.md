# Shared Orchestration Guide

Shared reference for skills that use subagent orchestration to produce design documents. This file is not a skill — it has no `SKILL.md` and does not appear in skill listings. Skills reference it by telling subagents to read it from disk at `skills/_shared/orchestration-guide.md`.

---

## 1. Scratch Directory

At orchestration start, define a scratch directory path for this session:

```
/tmp/<skill-name>-<timestamp>/research/
```

- `<skill-name>` is the slash command name (e.g., `product-enhance`, `security-audit`)
- `<timestamp>` is `YYYY-MM-DD_HHMMSS`
- Research subagents write research files here (use `general-purpose` subagents — Explore agents lack the Write tool)
- Plan agents read research from here

Example: `/tmp/product-enhance-2026-02-17_143022/research/`

**Permissions note:** Do NOT use Bash `mkdir` to create this directory. The Write tool creates parent directories automatically. The first subagent's Write call to this path will create the directory. This avoids any Bash permission prompts — the entire disk-write workflow uses only Read and Write tools, which are blanket-allowed via the `claude-workflow` permission category.

**Subagent type note:** Explore agents (`subagent_type: "Explore"`) do NOT have the Write tool — they are read-only. For the disk-write pattern, use `general-purpose` subagents (`subagent_type: "general-purpose"`) which have access to all tools including Write. Use Explore agents only when you need fast, read-only codebase searches that don't need to persist results to disk.

---

## 2. Research Agent → Disk Pattern

Research subagents (`general-purpose` type) write structured research to disk and return only a short summary to the orchestrator.

### What research agents write to disk

Each research subagent writes a research file to:

```
/tmp/<skill-name>-<timestamp>/research/<slug>.md
```

Research file template:

```markdown
# <Research Topic>

## Summary
<2-3 sentence overview of findings>

## Affected Files
- `path/to/file.ext:line` — description of what's here
- `path/to/file.ext:line` — description of what's here

## Findings
<Detailed analysis, evidence, code snippets with file:line references, root causes>

## Severity
<Assessment relevant to the skill's domain — e.g., CRITICAL/HIGH/MEDIUM/LOW>
```

### What research agents return to the orchestrator

Return ONLY a 2-4 line summary. Example:

```
Scanned authentication flow. Found 3 issues:
- JWT secret hardcoded (src/auth.ts:12) — CRITICAL
- No rate limiting on login endpoint — HIGH
- Session cookies missing secure flag — MEDIUM
Full research: /tmp/security-audit-2026-02-17_143022/research/auth-flow.md
```

**The orchestrator MUST NOT read the full research files into its context.** The orchestrator uses these summaries for user-facing presentation tables only.

---

## 3. Plan Agent → Disk Pattern

Plan agents read research from disk, read this guide for quality standards, and write final docs directly to the output directory.

### Launch prompt template for Plan agents

The orchestrator constructs a prompt for each Plan agent that includes:

```
## Setup

1. Read skills/_shared/orchestration-guide.md — follow Section 4
   (Quality Standards) and Section 5 (Phase Doc Structure) exactly.
2. Read the research file(s) at: /tmp/<skill>-<timestamp>/research/<slug>.md
3. [Any skill-specific quality requirements, inlined by the calling skill]

## Task

Write a phase document for: <enhancement title>
Output path: documentation/planning/<subdirectory>/<session>/<NN>_<slug>.md

## When done

Return ONLY a metadata summary in this format:
- Wrote: <output file path>
- PR title: <concise title>
- Effort: <Low/Medium/High> (<estimate>)
- Risk: <Low/Medium/High>
- Files modified: N | Files created: N
- Dependencies: <phase numbers or "None">
- Unlocks: <phase numbers or "None">

Do NOT return the full document content.
```

### What the orchestrator MUST NOT do

- **MUST NOT write docs itself** — it does not have the research context or quality standards to produce adequate output. Always delegate to Plan subagents.
- **MUST NOT collect full doc content** from Plan agents into its context.
- **MUST NOT read finished docs** into its context (except the first 15-20 lines for header metadata if needed for the overview doc).

---

## 4. Quality Standards

These plans will be handed off to a **junior engineering team for implementation**. The plans are the sole artifact for knowledge transfer — the junior team will not have access to the original author for clarification. Therefore:

- **Extreme attention to detail is mandatory.** Every file path, every function name, every import statement must be explicit. Never say "update the imports" without showing exactly which imports change and how.
- **Reference code explicitly.** Don't describe changes abstractly — show the exact code that exists today and the exact code it should become.
- **Eliminate ambiguity.** If there are two ways to do something, pick one and explain why. Don't leave decisions to the implementer.
- **Ensure separation of concerns.** Each PR should touch a distinct set of files. Verify that no two phases modify the same files unless there is an explicit dependency between them.
- **Prevent parallel conflicts.** Identify which phases can safely run in parallel (touch disjoint files) and which must be sequential. Document this clearly.
- **Include context generously.** Explain *why* each change is being made, not just *what* to change. The junior team needs to understand the reasoning to make good judgment calls during implementation.

**Note:** Individual skills may specify additional domain-specific quality requirements. Plan agents must follow BOTH these shared standards AND any skill-specific additions provided in their launch prompt.

---

## 5. Phase Doc Structure

Each phase doc represents **exactly 1 PR** and must include, at minimum, these sections:

1. **Header** — PR title, risk level, estimated effort, files created/modified/deleted
2. **Context** — Why this change matters. Link back to user intent and the gap it addresses.
3. **Dependencies** — Which phases must be completed first, and which phases this unlocks
4. **Detailed Implementation Plan**
   - Explicit code references: file paths, line numbers, function names, class names
   - Before/after code examples showing exact changes
   - Step-by-step instructions leaving zero ambiguity
   - New files to create with their full initial content or detailed skeleton
5. **Test Plan**
   - New tests to write (with descriptions of what they verify)
   - Existing tests to modify
   - Coverage expectations
   - Manual verification steps
6. **Documentation Updates**
   - README changes
   - API doc changes
   - Inline comment updates
   - User-facing documentation (if applicable)
7. **Stress Testing & Edge Cases**
   - Edge cases to handle
   - Load/performance considerations (if relevant)
   - Error scenarios and expected behavior
8. **Verification Checklist** — tests to run, commands to execute, things to manually check
9. **"What NOT To Do" Section** — common pitfalls, anti-patterns, things that look right but are wrong

**Note:** Some skills have domain-specific sections that replace or augment items above (e.g., Visual Specification and Accessibility Checklist for design-review, or Root Cause Explanation and cascade diagrams for frontend-performance-audit). When a skill specifies custom sections, Plan agents should use those in place of or in addition to the defaults.

---

## 6. Context Window Management

The orchestrator session is long-running and must stay within context limits. These rules prevent context blow-up:

### Launching Plan agents

- Launch ALL Plan agents in parallel using `run_in_background: true`
- Each Plan agent writes its output directly to disk via the Write tool
- Collect Plan agent completions via TaskOutput one at a time
- Each TaskOutput response contains only the metadata summary (not the full doc)
- After all agents complete, present the summary table to the user

### What NEVER enters orchestrator context

- Full research files from research subagents (they stay on disk)
- Full phase/remediation docs from Plan agents (they stay on disk)
- If the orchestrator needs to verify a doc was written correctly, read only the first 15-20 lines (the header/metadata section)

### Sequential collection pattern

Even with the disk-write pattern, collect agent completions ONE AT A TIME:

1. Launch all Plan agents in parallel with `run_in_background: true`
2. Collect agent 1 completion via TaskOutput (receives metadata only)
3. Collect agent 2 completion via TaskOutput (receives metadata only)
4. Repeat for each agent — one at a time, sequentially
5. Never collect multiple agent outputs in the same message

---

## 7. Permissions & Tool Usage

The disk-write workflow is designed to use **only Read and Write tools** for all file I/O — no Bash commands. This means:

- **No `mkdir` calls** — Write tool creates parent directories automatically
- **No `cp` or `mv` calls** — all file creation goes through the Write tool
- **No `cat` or `head`/`tail` calls** — all file reading goes through the Read tool (use `limit` and `offset` parameters for partial reads)
- **No `find` calls** — use the Glob tool for file discovery by pattern
- **No `grep` calls** — use the Grep tool for content search (supports regex, glob filters, output modes, and `head_limit`)

Both Read and Write are blanket-allowed via the `claude-workflow` permission category (default in clauDNA). This means:

- Research subagents writing research to `/tmp/` → **no permission prompt**
- Plan agents reading research from `/tmp/` → **no permission prompt**
- Plan agents reading this guide from `skills/_shared/` → **no permission prompt**
- Plan agents writing docs to `documentation/planning/` → **no permission prompt**

Subagents launched via the Task tool inherit the parent session's permissions. No additional permission grants are needed.

### Shell operator restriction

Shell operators (`&&`, `||`, `;`, `|`, `2>&1`) in Bash commands break `allowed-tools` permission pattern matching. A command like `source venv/bin/activate && pytest` cannot match any wildcard pattern — the user gets prompted for manual approval on every invocation.

Rules for all skills:
- **Never chain commands with `&&` or `;`.** Make separate parallel Bash tool calls instead.
- **Never pipe output with `|`.** Run the command bare and read the result.
- **For Python virtual environments:** Use the venv's python directly — `./venv/bin/python -m pytest` not `source venv/bin/activate && pytest`.
- **For `cd`:** Use absolute paths — `python /path/to/app.py` not `cd /path/to && python app.py`.

**No exceptions.** Previous versions of this guide listed `source .env &&` and `cd <worktree> &&` as accepted. Both have clean alternatives — see below.

### Environment variables from `.env`

Skills that need credentials or config from `.env` must NOT use `source .env && command`. Instead:

1. **Read** `.env` (and `.env.local` if it exists) using the Read tool
2. **Discover** the needed variable — don't hardcode a specific name. For database URLs, look for `DATABASE_URL`, `NEON_PROD_URL`, `POSTGRES_URL`, `PG_URL`, etc. For API keys, look for common patterns.
3. **Pass the value inline** in the command: `psql "postgres://discovered-url" -c "SELECT 1"`

This eliminates the `&&` operator AND makes skills portable across projects that use different variable names.

### Working directory for worktrees/subagents

`cd` persists between Bash calls within a session. Run `cd /path/to/worktree` as the first Bash call, then all subsequent commands run from that directory. No `cd <path> && command` chaining needed.

For Python virtual environments, use the venv binary directly: `./venv/bin/python -m pytest` — never `source venv/bin/activate && pytest`.

---

## 8. Archive Convention

Output directories follow this pattern per skill:

```
documentation/planning/<subdirectory>/<session_name>_<YYYY-MM-DD>/
```

Where `<subdirectory>` varies by skill:
- product-enhance, product-vision, design-review: `phases/`
- frontend-performance-audit: `performance/`
- security-audit: `security/`
- tech-debt: `tech_debt/`

When all phases are complete, the session directory moves to:

```
documentation/archive/<session_name>_<YYYY-MM-DD>/
```

via `git mv`. This is handled by `/claudna:implement-plan` — planning skills only generate plans, never archive them.

---

## 9. Subagent Workflow Reference for Skills

When a skill's doc generation step (typically the final step) delegates to Plan subagents, include this reference instead of inlining the full workflow:

> **Follow the subagent workflow defined in the orchestration guide (`skills/_shared/orchestration-guide.md`):**
> - Plan Agent → Disk pattern (Section 3)
> - Quality standards (Section 4)
> - Phase doc structure (Section 5)
> - Context window management (Section 6)
> - Archive convention (Section 8)
>
> Plan agents read research from the session's scratch directory, write docs directly to the output directory, and return only a metadata summary.
>
> **The orchestrator MUST NOT write docs itself.** Always delegate to Plan subagents.

Skills that have domain-specific quality requirements or custom phase doc sections should specify those AFTER this reference block. The shared standards always apply; skill-specific additions layer on top.

### Alternative Output Targets

Skills support `--output github` and `--output session` in addition to the default `docs` target. When `--output github` is active, the skill runs the full analysis and plan generation pipeline (no phases are skipped), then writes output as GitHub Issues instead of planning docs. When `--output session` is active, findings are presented in chat only with no persistence.

Follow the output guide at `skills/_shared/output-guide.md` for target-specific formatting, deduplication, labels, and subagent workflow details.

---

## 10. Autonomous Mode (`--auto`)

Planning skills that support `--auto` can run fully non-interactively — no user gates, no questions, no confirmations. This enables rolling automated audits, scheduled reviews, and headless operation.

### What `--auto` means

When `$ARGUMENTS` contains `--auto`:

1. **Implies `--output github`.** Findings always go to GitHub Issues, never to planning docs. The planning doc workflow requires user decisions (session naming, scope confirmation, selection) that can't happen without a human.
2. **Skip all user gates.** Do not ask for confirmation, scope selection, or approval. Proceed with sensible defaults.
3. **Scope from arguments.** The focus area must come from `$ARGUMENTS` (e.g., a directory path). If no scope is provided, scan the full codebase but limit findings to the top 10 most impactful.
4. **No Plan Mode.** Skip `EnterPlanMode`/`ExitPlanMode` — there's no deliberation phase when running autonomously. Go straight to scan → findings → issues.
5. **Bail gracefully.** If the skill genuinely cannot proceed without user input (e.g., deployed URL required for design-review), write what you have to the handoff file and stop. Do not block.

### Default behavior changes with `--auto`

| Interactive (default) | `--auto` |
|---|---|
| Ask user for scope | Use scope from `$ARGUMENTS`, or full codebase |
| Present findings, wait for confirmation | Create issues immediately |
| Ask which findings to act on | Act on all findings above LOW severity |
| Write planning docs (`--output docs`) | Create GitHub Issues (`--output github`) |
| Multiple user gates between phases | Zero interaction |

### How skills should reference this

Skills that support `--auto` should add to their Arguments section:

```
- `--auto`: Fully non-interactive. Implies `--output github`. Scans, creates issues, returns summary. See orchestration guide Section 10.
```

And at the end of their procedure, add an "Autonomous Mode" section:

```
## Autonomous Mode (--auto)

When `--auto` is set (see orchestration guide Section 10):
1. Skip [specific user gates in this skill]
2. [Any skill-specific auto defaults]
3. Create GitHub Issues per the output guide (`--output github`)
4. Return structured summary for audit tracking
```

### Skills that support `--auto`

| Skill | Auto-viable? | Notes |
|---|---|---|
| `/claudna:tech-debt` | ✅ Yes | Scan + issue creation, no user input needed |
| `/claudna:security-audit` | ✅ Yes | Scan + issue creation, no user input needed |
| `/claudna:product-enhance` | ✅ Yes | Uses triage path (skip discovery/interview) |
| `/claudna:frontend-performance-audit` | ✅ Yes | Requires page/flow in arguments |
| `/claudna:docs-review` | ✅ Yes | Global review mode, auto-fix stale docs |
| `/claudna:access-path-audit` | ✅ Yes | Scan + issue creation, no user input needed |
| `/claudna:product-vision` | ⚠️ Limited | Vision without user input produces generic ideas. Use only with tight scope. |
| `/claudna:design-review` | ❌ No | Requires screenshots, deployed URL, visual judgment |
| `/claudna:session-handoff` | ✅ Yes | Already implemented |

---

## 11. Shared Skill Reminders

The following rules apply to ALL orchestration skills. Skills should reference this section rather than restating these individually:

- **One PR per doc.** Each phase/remediation/fix doc maps to exactly one PR when implemented via `/claudna:implement-plan`.
- **This skill produces plans, not code.** Implementation is always handled by `/claudna:implement-plan`, which provides its own challenge round, verification, and PR workflow. Do NOT build, branch, or create PRs from planning skills.
- **Testing is non-negotiable.** Every phase doc must include a test plan. Implementations without tests are incomplete.
- **Documentation is non-negotiable.** Every phase doc must specify documentation updates. Code without docs is incomplete.
- **Respect existing architecture.** Enhancements and fixes should work *with* the system's existing patterns, not introduce alien abstractions.

---

## 12. Context Efficiency — Why These Patterns Work

Reference for skill authors. Understanding the "why" helps you make good decisions in situations these patterns don't explicitly cover.

### Prefix caching

The API caches the prompt by prefix — everything from the start of the request to each breakpoint. Order matters: **static content first, dynamic content last.** The actual order is: system prompt & tool definitions (globally cached) → CLAUDE.md (cached per-project) → session context (cached per-session) → conversation messages. Every pattern in this guide preserves that prefix.

### Model stability

Prompt caches are per-model. Switching models mid-session rebuilds the entire cache. Subagents launched via Task inherit the parent model automatically — this is correct behavior. Never recommend `/model` mid-session. If different-model work is needed, use a Task subagent (separate cache).

### Tool set stability

Tool definitions are part of the cached prefix. Adding or removing tools mid-session invalidates the cache for the entire conversation. Use `EnterPlanMode`/`ExitPlanMode` as tools (not tool swapping). For MCP tools, use `defer_loading: true` stubs — full schemas load on demand via `ToolSearch`.

### Compaction awareness

Long orchestration sessions can trigger compaction (automatic context summarization). The disk-write pattern defends against this: research and docs stay on disk, so the orchestrator context stays lean. Rules:
- Orchestrator must not read full research files or finished docs into its context.
- Research subagents return 2-4 line summaries; Plan agents return metadata only.
- If you need to verify a doc, read only the first 15-20 lines (header/metadata).

### Redundant reads

CLAUDE.md and MEMORY.md are already in the system prompt — the orchestrator must NOT re-read them. Subagents (Task tool) run in separate sessions and do NOT inherit the parent's system prompt content, so they DO need to read shared references from disk (e.g., this guide, CLAUDE.md if relevant).

---

## 13. Skill Priority Ordering

When multiple skills could apply to a task, invoke them in tier order. Process skills determine HOW to approach a problem. Planning skills determine WHAT to build. Implementation skills execute. Deployment skills ship. Skipping tiers leads to building the wrong thing or shipping unverified work.

### Priority tiers

| Tier | Category | Skills | Purpose |
|------|----------|--------|---------|
| 1 | **Process** | review-self, investigate-app, verify-completion | Establish approach, verify assumptions, gather evidence, debug |
| 2 | **Planning** | product-enhance, product-vision, design-review, security-audit, tech-debt, frontend-performance-audit | Analyze what to build, identify gaps, produce design docs |
| 3 | **Implementation** | implement-plan, review-changes, review-pr, quick-commit, commit-push-pr | Execute plans, review code, commit and ship PRs |
| 4 | **Deployment & Ops** | railway-deploy, vercel-deploy, modal-deploy, railway-status, vercel-status, modal-status, railway-logs, vercel-logs, modal-logs, dbt, neon-branch, neon-info, neon-query | Deploy, monitor, query infrastructure |

**Utility skills** (context-resume, session-handoff, lessons, notes, find-skills, cache-audit, docs-review, repo-health, worktree, notifications) are not tiered -- they are invoked on demand for session management, not as part of a build workflow.

### Rules

- **Higher tiers first.** When a task could benefit from skills in multiple tiers, start with the lowest-numbered tier. Example: a bug report should invoke investigate-app (Tier 1) before implement-plan (Tier 3).
- **Within a tier, order does not matter.** Tier 1 skills can run in any order relative to each other.
- **Skipping tiers is allowed when inapplicable.** Not every task needs all four tiers. A simple deploy needs only Tier 4. A code review needs only Tier 3. The rule is: do not skip a tier that IS applicable.
- **Review-self is always first.** When present in a workflow, review-self precedes all other skills regardless of tier.
