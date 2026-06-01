---
name: access-path-audit
user-invocable: true
description: "Use when you want to evaluate whether a system's interfaces (API, CLI, Slack, MCP, SDK, workers) consistently enforce cross-cutting concerns and whether those concerns live at the correct architectural layer. Supports --output github to create issues and --output session for chat-only analysis."
argument-hint: "[--auto] [--output github|session] [focus-area]"
---

# Access Path Audit

Audit whether a system's access paths consistently enforce cross-cutting concerns — and whether those concerns are placed at the correct architectural layer (transport vs. domain core).

**Persona:** Senior platform architect who evaluates systems holistically. Evidence-driven — every finding cites specific code paths. Distinguishes between genuine inconsistencies and appropriate per-transport differences.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Fully non-interactive. Implies `--output github`. Scans, creates issues, returns summary. See orchestration guide Section 10.
- `--output github`: Write findings and remediation plans as GitHub Issues. See output guide (`skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Remaining text is the focus area (e.g., `auth`, `validation`, `api/`). If provided, scope the audit to that area.

## When NOT to use

- For security vulnerabilities (injection, secrets, OWASP) → use `/claudna:security-audit`
- For general code quality / tech debt → use `/claudna:tech-debt`
- For production outages or broken behavior → use `/claudna:investigate-app`
- For frontend performance → use `/claudna:frontend-performance-audit`

## The Key Insight

Not every difference across access paths is a bug. A CLI having no auth is correct — it's a local operator tool. The real questions are:

1. **Shared invariants:** Which concerns MUST hold regardless of access path? (e.g., input validation, SQL injection prevention)
2. **Concern placement:** Is each concern enforced at the right layer? Transport-specific concerns (auth, rate limiting) belong at the edge. Universal concerns (validation, error sanitization) belong in the domain core.
3. **Genuine gaps:** Where does one path enforce something that another path should but doesn't?

## Quick Reference

| Phase | Steps | What happens | User gate? |
|-------|-------|-------------|------------|
| **1: Scan** | Steps 1–5 | Detect paths, parallel discovery, convergence analysis, classify findings, present summary | No |
| **Gate** | — | User confirms whether to generate remediation plans | **Yes** |
| **2: Remediation** | — | Generate per-PR planning docs grouped by related findings | No |
| **3: Summary** | — | Present final summary, hand off to `/claudna:implement-plan` | No |

## Procedure

Follow these steps exactly in order.

**Enter Plan Mode.** Call `EnterPlanMode` to enter deliberation mode. All discovery, analysis, and proposal steps are read-only — plan mode enforces this by disabling write tools. If the user declines plan mode, proceed normally — the deliberation steps are still read-only by convention.

Do NOT read CLAUDE.md or MEMORY.md — already in system prompt.

---

## Phase 1: Scan

### Step 1: Scope & Stack Detection

If no focus area was provided in `$ARGUMENTS`, ask: **"Any specific concern or access path to focus on?"** Default to full system scan if no scope given.

Detect the system's framework and access patterns. Run in parallel:

- Glob `**/routes/**/*.py`, `**/api/**/*.py`, `**/controllers/**/*.{ts,js,py,rb,go}` (HTTP frameworks)
- Grep `@app\.(get|post|put|delete|patch)|@router\.|@Controller|@RequestMapping|app\.(get|post|use)\(` in source files
- Grep `click\.command|typer\.command|argparse|Commander|cobra\.Command` (CLI frameworks)
- Grep `slack_bolt|slack_sdk|SlackBot|Bolt\(` (Slack integrations)
- Grep `FastMCP|McpServer|mcp\.tool|@mcp_tool` (MCP servers)
- Grep `celery|dramatiq|huey|rq\.job|@task|BackgroundTasks` (background workers)
- Grep `WebSocket|socket\.io|ws\.on` (WebSocket handlers)
- Grep `GraphQL|@Query|@Mutation|type Query` (GraphQL endpoints)

If fewer than 2 access paths found, tell the user: "This system appears to have a single access path — this audit is most valuable for systems with 2+ interfaces to the same core logic."

### Step 2: Parallel Discovery

**Scratch directory:** `/tmp/access-path-audit-<YYYY-MM-DD_HHMMSS>/research/`

Launch two `general-purpose` subagents in parallel (Agent tool, `subagent_type: "general-purpose"`). Each writes findings to scratch dir, returns 2-4 line summary. Orchestrator does NOT read full research files.

- **Subagent A: Access Path Inventory** — every access path, transport, entry point, auth, domain services called. Writes to `research/path-inventory.md`.
- **Subagent B: Cross-Cutting Concern Mapping** — for each concern in `scan-categories.md`, maps enforcement across every access path. Writes to `research/concern-mapping.md`.

**Full subagent prompts and research file formats:** See `subagent-prompts.md` in this skill directory.

### Step 3: Convergence — Concern Placement Analysis

Launch a third `general-purpose` subagent that reads both research files and builds the concern placement map. This is the core analytical step.

The convergence subagent must:

1. **Classify each concern** as transport-appropriate or domain-core:
   - **Transport-layer concerns** (correctly vary per path): authentication, rate limiting, request/response serialization, protocol-specific headers, connection management
   - **Domain-core concerns** (must be consistent): input validation, business rule enforcement, error sanitization, audit logging of domain events, authorization (beyond "is authenticated")
   - **Hybrid concerns** (enforced at both layers): some validation at transport for fast-fail, authoritative validation in domain

2. **Trace a representative operation** (e.g., "search", "query") through each access path, noting exactly where each concern is applied

3. **Build the consistency matrix**: for each domain-core concern, is it enforced in the domain layer (shared) or only in some transport adapters (inconsistent)?

4. **Identify shared code vs. duplicated logic**: which cross-cutting implementations are shared (good) vs. copy-pasted across paths (maintenance risk)?

Writes to `research/convergence.md`. Returns 2-4 line summary.

**Full convergence subagent prompt:** See `subagent-prompts.md`.

### Step 4: Findings Classification

Using the convergence summary, classify findings into four categories:

**Category A: Genuine Gaps** — domain concern missing from a path. Fix: push concern into domain core.

**Category B: Misplaced Concerns** — right concern, wrong layer. Fix: move to correct layer.

**Category C: Appropriate Differences** — paths correctly differ (transport-specific). Not a bug — list to show thoroughness.

**Category D: Duplication Risk** — shared logic copy-pasted. Fix: extract to shared module.

**Severity for categories A and B:**

| Severity | Definition |
|----------|------------|
| **CRITICAL** | Exploitable security gap or data integrity risk across paths |
| **HIGH** | Inconsistency that causes incorrect behavior under normal use |
| **MEDIUM** | Inconsistency that causes issues under edge cases or load |
| **LOW** | Maintenance risk or minor inconsistency with no immediate impact |

Category C findings are not bugs — list them to show the audit was thorough. Category D findings are always MEDIUM or LOW.

### Step 5: Present Findings Summary

Present to the user:

1. **Architecture summary** — how many paths, what pattern, overall health
2. **Concern placement map** — table showing where each concern is enforced per path (use the legend: `MW` = middleware, `Route!` = route-only should be domain, `None!` = missing gap, `None*` = correctly absent, `Leaks!` = present but broken)
3. **Ranked findings table** — all findings sorted by severity with category, concern, and one-line summary
4. **Architectural recommendation** — one paragraph on highest-leverage structural change

---

## User Gate

Present the findings and ask:

**"Here are the access path audit findings. Would you like me to generate remediation plans? I'll group related fixes into PRs."**

Do NOT proceed to Phase 2 without explicit confirmation.

**Exit Plan Mode.** Call `ExitPlanMode` to transition to execution mode. The deliberation phase is complete — doc generation requires the Write tool.

---

## Phase 2: Remediation Plans

**Output location:**
```
documentation/planning/access-paths/<session_name>_<YYYY-MM-DD>/
├── 00_ACCESS_PATH_AUDIT.md
├── 01_<remediation-slug>.md
├── 02_<remediation-slug>.md
└── ...
```

> **Archive convention:** See orchestration guide, Section 8.

Ask the user for a short session name, or derive one (e.g., `domain-boundary`, `full-audit`).

### 00_ACCESS_PATH_AUDIT.md

Master audit document containing:
- Audit date and scope
- System architecture summary (paths, pattern, domain core)
- Concern placement map (the full table)
- Full findings table with severity, category, concern, location
- Remediation priority order (CRITICAL first, then HIGH, etc.)
- Grouping rationale (which findings are addressed together)
- Operation traces (the traced operations showing where concerns apply per path)
- Category C listing (appropriate differences — proves audit thoroughness)

### Remediation Docs (01_, 02_, etc.)

**Group related findings into single PRs where sensible.** For example:
- All validation extraction → one "domain validation" PR
- All search deduplication → one "search service extraction" PR
- All error sanitization → one "error handling" PR

Each doc represents **exactly 1 PR** and must include:

1. **Header** — PR title, severity of findings addressed, effort, files modified
2. **Findings Addressed** — list of finding numbers from the audit table
3. **Dependencies** — which phases must complete first
4. **Detailed Implementation Plan**
   - Explicit code references: file paths, line numbers, function names
   - Before/after code examples showing exact changes
   - Step-by-step instructions leaving zero ambiguity
5. **Verification Checklist**
   - How to verify each finding is actually fixed
   - Tests to run
   - Manual checks
6. **"What NOT To Do" Section** — common mistakes when fixing this class of issue

#### Subagent Workflow

Follow Section 9 of the orchestration guide (`skills/_shared/orchestration-guide.md`). Plan agents must also read `skills/_shared/planning-standard.md` for quality standards and phase doc structure. Scratch directory: `/tmp/access-path-audit-<YYYY-MM-DD_HHMMSS>/research/`.

---

## Output Targets

This skill supports `--output github` and `--output session` in addition to the default `docs` target.

Follow the output guide at `skills/_shared/output-guide.md`:
- For `github`: write each finding as a doc (frontmatter + the Section 4 body skeleton) and delegate to `/claudna:publish <file> --to github-issue --repo <repo>` — publish validates, dedups, and applies labels from `tags:`. Map Category A/B → `priority:critical`/`priority:high`, Category C → `priority:medium`, Category D → `priority:low`.
- For `session`: produce the doc, then `/claudna:publish <file> --to session` prints it to chat (Section 5)
- For `docs` (default): follow the subagent workflow in the orchestration guide

After creating issues, present the batch summary and return issue URLs for audit tracking.

---

## Phase 2.5: Adversarial Review Pass

Follow `skills/_shared/pre-handoff-checklist.md` for the full procedure. Run on each remediation doc in `documentation/planning/access-paths/<session>/<NN>_*.md` and `00_ACCESS_PATH_AUDIT.md`.

### Access-path-specific concern areas

Prioritize these `concern_area` values:
- `architecture` — does the fix move a concern to the correct layer (transport vs. domain)?
- `compatibility` — does pushing a concern into the domain core break any access path that depended on transport-layer behavior?
- `security` — does the refactor weaken or strengthen the security posture per-path?

---

## Phase 3: Summary & Handoff

After generating all remediation docs, present a final summary:

```
Access Path Audit Summary
═══════════════════════════════════════════════════════════════════════════
  Session:          [name]
  Date:             [date]
  Scope:            [what was audited]

  Architecture:     [pattern] with [N] access paths
  Domain Core:      [key shared modules]

  Findings:         [total] ([critical] critical, [high] high, [medium] medium, [low] low)
  Appropriate Diffs: [count] (not bugs — transport-specific)

  Remediation Plans:
    01  [title]    [CRITICAL]   [effort]
    02  [title]    [HIGH]       [effort]
    03  [title]    [MEDIUM]     [effort]

  Ongoing Recommendations:
    - Schedule periodic re-audit when new access paths are added
    - New access paths should go through domain core, not duplicate transport logic
    - Domain-core concerns should raise domain exceptions, not HTTP exceptions

  Audit docs: documentation/planning/access-paths/<session>/
═══════════════════════════════════════════════════════════════════════════
```

Then tell the user:

**"Plans are ready. Run `/claudna:implement-plan documentation/planning/access-paths/<session>/` to start building — it will handle challenge review, branching, implementation, and PRs for each phase doc."**

**This skill produces plans, not code.** Implementation is always handled by `/claudna:implement-plan`, which provides its own challenge round, verification, and PR workflow. Do NOT build, branch, or create PRs from this skill.

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Treating every cross-path difference as a bug | Use Category C — transport-specific differences (CLI has no auth, HTTP has CORS) are correct. List them to prove thoroughness. |
| Tracing only middleware stacks | Trace at function-call depth — entry point → middleware → domain service → data layer. Middleware-only traces miss gaps in business logic. |
| Missing mounted sub-apps in dual mode | Sub-apps (e.g., MCP on FastAPI) inherit parent middleware in HTTP mode but NOT in stdio/standalone. Always check both deployment modes. |
| Missing LLM-mediated paths | Slack → ChatService → LLM → ToolExecutor is an indirect access path. Trace concerns through the full chain including the dispatch layer, not just the outer entry point. |
| Shallow "access path" definition | Any code path that can invoke domain logic with different cross-cutting behavior counts. Internal dispatch layers (tool executors, job runners) count if they have their own validation/error handling distinct from their caller. |
| Claiming definitive findings for graceful degradation | Scan category I is best audited through code review of error handling and timeout configs. Flag areas of concern for follow-up runtime testing rather than making definitive claims from static analysis alone. |
| Including secrets in findings | Never include connection strings or credentials verbatim — file:line references only. |

## Notes

- **Subagent pattern.** Disk-write pattern per `skills/_shared/orchestration-guide.md` Sections 2 & 6. Three subagents in Phase 1 (two parallel, one sequential). Phase 2 uses Plan agents per Section 9. Orchestrator coordinates only.
- **Pass focus area** from Step 1 into both Step 2 subagent prompts.
- **Technology-agnostic.** The scan categories cover common patterns across Python, Node.js, Go, Ruby, and Java. The subagent prompts adapt to whatever stack is detected.
- **User gates at every phase transition.** Scan → confirm → plan. Do not generate remediation docs without user confirmation.
- See orchestration guide, Section 11 for shared reminders (one PR per doc, testing, plans-not-code).

---

## Autonomous Mode (--auto)

When `--auto` is set (see orchestration guide Section 10):
1. Skip Plan Mode — go straight to Phase 1 scan
2. Skip the user confirmation gate between Phase 1 and Phase 2
3. Use focus area from `$ARGUMENTS` as scope. If none provided, scan full system.
4. Create GitHub Issues for all Category A and B findings (CRITICAL and HIGH immediately, MEDIUM batched)
5. Skip Category C (appropriate differences) and Category D at LOW severity
6. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "access-path-audit",
  "outcome": "completed",
  "artifacts": {
    "issues_created": ["..."],
    "findings_by_category": {"A": 1, "B": 2, "C": 4, "D": 1},
    "paths_analyzed": ["HTTP", "CLI", "MCP"],
    "session_dir": "documentation/planning/access-paths/<session>/"
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `blocked` if fewer than 2 access paths exist (skill bails per existing rule).
- Category C ("appropriate differences") count is included in artifacts even though no issues are filed for them, to demonstrate audit thoroughness.
