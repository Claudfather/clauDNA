Invoked by /claudna:audit in frontend-perf mode — audits a frontend page or flow with performance symptoms: flickering, slow loads, janky scroll, excessive re-renders, or layout shifts.

Audit frontend rendering performance by tracing render cycles, diagnosing fetch patterns, and producing phased remediation plans for `/claudna:implement-plan`.

**Persona:** Senior frontend performance engineer — traces render cascades methodically, maps symptoms to root causes before proposing fixes. Pragmatic: fix the bottleneck, not everything.

## Lens arguments (beyond contract §2)

Shared argument semantics live in `skills/_shared/audit-lens-contract.md` §2. Lens-specific:

- `[focus]` — the page or flow to audit. If provided, use it as the scope in Phase 1 instead of asking.
- `--auto` — implies `--output github` and **requires** the page/flow in the arguments; this lens cannot auto-detect what to audit. See Autonomous Mode below.

## When NOT to use

- For visual/UX design issues → use `/claudna:audit design`
- For backend/API latency → use `/claudna:investigate-app`
- For general code quality → use `/claudna:audit tech-debt`

## Procedure

Follow these steps in order. **Enter Plan Mode** (`EnterPlanMode`) before starting — all discovery and analysis is read-only. If the user declines, proceed read-only by convention.

---

## Phase 1: Scope & Symptom

Ask the user: (1) what's the symptom, (2) which page or flow, (3) how to reproduce. If vague, ask them to narrow to a specific page. Performance audits need a concrete entry point. If `[focus]` supplied the page or flow, use it as the scope instead of asking.

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

Scan the affected components across 8 categories using **Explore subagents** (one per category). Each agent reads **`scan-categories.md`** (same directory as this file) for detailed checklists, writes findings to the scratch directory, and returns a summary. Focus on the Phase 2 component tree only.

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

**Subagent workflow:** Follow orchestration guide Section 9. Plan agents must also read `skills/_shared/planning-standard.md`. Quality requirements beyond the shared standard: explain render lifecycle per fix, draw before/after cascades, include DevTools verification.

After generating docs: **"Plans are ready for review. Run `/claudna:implement-plan` on the session directory to execute them."**

---

## Phase 4.5: Adversarial Review Pass

Follow `skills/_shared/pre-handoff-checklist.md` for the full procedure. Run on each phase doc in `documentation/planning/performance/<session>/<NN>_*.md` and `00_PERF_AUDIT.md`.

### Performance-specific concern areas

Prioritize these `concern_area` values:
- `performance` — does the proposed fix actually address the measured bottleneck, or is it speculative?
- `compatibility` — does the fix break any framework guarantees (e.g., Suspense boundaries, React 18 transitions)?
- `architecture` — does the fix introduce architectural changes (e.g., new caching layers) that should be split into a separate plan?

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

Follow the output guide at `skills/_shared/output-guide.md`. Beyond the shared `--output github|session` surface (contract §2), this lens supports a `docs` target — the Phase 4 remediation plan docs:

- For `github`: write each finding as a doc (frontmatter + the Section 4 body skeleton) and delegate to `/claudna:publish <file> --to github-issue --repo <repo>` — publish validates, dedups, and applies labels from `tags:`. Apply `performance` label. Map severity levels to priority labels. Group issues by cascade chain where applicable.
- For `session` (engine default): produce the doc, then `/claudna:publish <file> --to session` prints it to chat (Section 5)
- For `docs`: follow the subagent workflow in the orchestration guide

After creating issues, present the batch summary and return issue URLs for audit tracking.

---

## Autonomous Mode (--auto)

When `--auto` is set (see orchestration guide Section 10):
1. Skip Plan Mode — go straight to reconnaissance and scan
2. Page/flow **must** be provided in the arguments (bail if missing — this lens can't auto-detect what to audit)
3. Skip the user confirmation gate between scan and remediation
4. Create GitHub Issues for all findings, grouped by cascade chain
5. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after, `skill: "audit"` with the lens inside `artifacts` (contract §4):

```json
{
  "skill": "audit",
  "outcome": "completed",
  "artifacts": {
    "lens": "frontend-perf",
    "issues_created": ["..."],
    "cascade_chains_found": 2,
    "page_audited": "<route or flow>",
    "session_dir": "documentation/planning/performance/<session>/"
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `blocked` if the page/flow wasn't provided (this lens cannot auto-detect; see rule 2 above).
