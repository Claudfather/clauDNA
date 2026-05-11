---
name: frontend-performance-audit
description: "Use when a frontend page or flow has performance symptoms -- flickering, slow loads, janky scroll, excessive re-renders, or layout shifts. Supports --output github to create issues and --output session for chat-only analysis."
argument-hint: "[--auto] [--output github|session] [page-or-flow]"
---

# Frontend Performance Audit

Audit frontend rendering performance by tracing render cycles, diagnosing fetch patterns, and producing phased remediation plans for `/claudna:implement-plan`.

**Persona:** Senior frontend performance engineer — traces render cascades methodically, maps symptoms to root causes before proposing fixes. Pragmatic: fix the bottleneck, not everything.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Fully non-interactive. Implies `--output github`. Requires page/flow in arguments. See orchestration guide Section 10.
- `--output github`: Write findings and remediation plans as GitHub Issues. See output guide (`~/.claude/skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Remaining text is the page or flow to audit. If provided, use it as the scope in Phase 1 instead of asking.

## When NOT to use

- For visual/UX design issues → use `/claudna:design-review`
- For backend/API latency → use `/claudna:investigate-app`
- For general code quality → use `/claudna:tech-debt`

## Procedure

Follow these steps in order. **Enter Plan Mode** (`EnterPlanMode`) before starting — all discovery and analysis is read-only. If the user declines, proceed read-only by convention.

---

## Phase 1: Scope & Symptom

Ask the user: (1) what's the symptom, (2) which page or flow, (3) how to reproduce. If vague, ask them to narrow to a specific page. Performance audits need a concrete entry point.

---

## Phase 2: Codebase Reconnaissance

Scratch directory: `/tmp/frontend-performance-audit-<YYYY-MM-DD_HHMMSS>/research/`. All Explore agents write here and return 2-4 line summaries. Follow Explore Agent → Disk Pattern (orchestration guide, Section 2). Do NOT read CLAUDE.md/MEMORY.md in the orchestrator.

**Map three areas via parallel Explore agents:**
- **A. Framework & rendering setup** — framework/version, React version, strict mode, providers, middleware
- **B. Component tree for the affected route** — server/client boundaries, data-fetching hooks, prop sources
- **C. Data layer** — fetch utilities, caching strategy, SSR vs client-side

Present a brief architecture summary (framework, React version, affected route, component chain, data fetching, Suspense).

---

## Phase 3: Scan

Scan the affected components across 8 categories using **Explore subagents** (one per category). Each agent reads **`scan-categories.md`** for detailed checklists, writes findings to the scratch directory, and returns a summary. Focus on the Phase 2 component tree only.

**Categories:** A. Render Cascades, B. Fetch Patterns, C. Observer & Listener Overhead, D. State Management, E. Memoization Gaps, F. Layout Stability, G. Framework-Specific Issues, H. Bundle & Loading

---

### Findings Output

After all scans complete, present a consolidated findings table and render cascade diagram. Templates and severity definitions are in **`cascade-diagram-template.md`** (same directory).

---

## User Gate

Present findings and cascade diagram. Ask: **"Would you like me to generate remediation plans? I'll group related fixes into PRs ordered by impact."** Do NOT proceed without confirmation. **Exit Plan Mode** (`ExitPlanMode`) after confirmation — doc generation requires the Write tool.

---

## Phase 4: Remediation Plans

Ask the user for a short session name (e.g., `explain-page-flicker`). Output to `documentation/planning/performance/<session_name>_<YYYY-MM-DD>/`. Archive convention: orchestration guide, Section 8.

**00_PERF_AUDIT.md** — Master audit: date, scope, symptom, architecture summary, findings table, cascade diagram, priority order, grouping rationale, dependency matrix.

**Remediation Docs (01_, 02_, etc.)** — Group related findings into single PRs. Each doc = exactly 1 PR containing: header (title, severity, effort, files), findings addressed, dependencies, root cause explanation with cascade chain, detailed implementation plan (file paths, line numbers, before/after code), verification checklist (DevTools + manual repro + build/test), and "What NOT To Do" section.

**Subagent workflow:** Follow orchestration guide Section 9. Plan agents read research from scratch directory. Quality requirements (beyond Section 4): explain render lifecycle per fix, draw before/after cascades, include DevTools verification.

After generating docs: **"Plans are ready for review. Run `/claudna:implement-plan` on the session directory to execute them."**

---

## Notes

- **Symptom first, then trace.** Start from the symptom, trace backwards. Focused beats broad.
- **The cascade diagram is the deliverable.** If you can draw the re-render chain, you've found the bug.
- **Severity tracks user impact, not code smell.**
- **Group fixes by PR, not by category.** One PR for the full cascade is better than three PRs touching the same file.
- **Don't prescribe caching libraries.** Prefer minimal fixes over architectural changes.
- **User gates at every phase transition.**
- **Subagent strategy.** Phase 2: Explore (architecture). Phase 3: Explore (per category). Phase 4: Plan (remediation docs). All use disk-write pattern.
- See orchestration guide, Section 10 for shared reminders.

---

## Output Targets

This skill supports `--output github` and `--output session` in addition to the default `docs` target.

Follow the output guide at `~/.claude/skills/_shared/output-guide.md`:
- For `github`: use the structured issue body format (Section 4), check for duplicates (Section 4.5), apply labels (Section 4.3). Apply `performance` label. Map severity levels to priority labels. Group issues by cascade chain where applicable.
- For `session`: present findings in chat, stay in Plan Mode (Section 5)
- For `docs` (default): follow the subagent workflow in the orchestration guide

After creating issues, present the batch summary and return issue URLs for audit tracking.

---

## Autonomous Mode (--auto)

When `--auto` is set (see orchestration guide Section 10):
1. Skip Plan Mode — go straight to reconnaissance and scan
2. Page/flow **must** be provided in `$ARGUMENTS` (bail if missing — this skill can't auto-detect what to audit)
3. Skip the user confirmation gate between scan and remediation
4. Create GitHub Issues for all findings, grouped by cascade chain
5. Return structured summary for audit tracking
