Invoked by /claudna:audit in frontend-perf mode — audits a frontend page or flow with performance symptoms: flickering, slow loads, janky scroll, excessive re-renders, or layout shifts.

Audit frontend rendering performance by tracing render cycles, diagnosing fetch patterns, and producing phased remediation plans for `/claudna:build`.

**Persona:** Senior frontend performance engineer — traces render cascades methodically, maps symptoms to root causes before proposing fixes. Pragmatic: fix the bottleneck, not everything.

## Lens arguments (beyond contract §2)

Shared argument semantics live in `../../_shared/audit-lens-contract.md` §2. Lens-specific:

- `[focus]` — the page or flow to audit. If provided, use it as the scope in Phase 1 instead of asking.
- `--auto` — defaults to canonical `artifacts` output and **requires** the page/flow in the arguments; this lens cannot auto-detect what to audit. GitHub filing requires explicit `--output github`. See Autonomous Mode below.

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

Scratch directory: `<scratch>/research/`, under the exact current-session scratch path resolved through `../../_shared/orchestration-guide.md` §1. Resolve the actual SID/provider and exact paths before dispatch; never use OS temp or a guessed replacement. All general-purpose research agents write here and return 2-4 line summaries. Follow Research Agent → Disk Pattern (orchestration guide, Section 2). Do NOT read CLAUDE.md/MEMORY.md in the orchestrator.

For explicit `--output session`, perform discovery inline and keep findings in context; create no scratch files. The disk-writing subagent workflow below applies to persisted-output runs.

**Map three areas via parallel general-purpose research agents:**
- **A. Framework & rendering setup** — framework/version, React version, strict mode, providers, middleware
- **B. Component tree for the affected route** — server/client boundaries, data-fetching hooks, prop sources
- **C. Data layer** — fetch utilities, caching strategy, SSR vs client-side

Present a brief architecture summary (framework, React version, affected route, component chain, data fetching, Suspense).

---

## Phase 3: Scan

Scan the affected components across 8 categories using **general-purpose research subagents** (one per category). Each agent reads **`scan-categories.md`** (same directory as this file) for detailed checklists, writes findings to the scratch directory, and returns a summary. Focus on the Phase 2 component tree only.

**Categories:** A. Render Cascades, B. Fetch Patterns, C. Observer & Listener Overhead, D. State Management, E. Memoization Gaps, F. Layout Stability, G. Framework-Specific Issues, H. Bundle & Loading

---

### Findings Output

After all scans complete, present a consolidated findings table and render cascade diagram. Templates and severity definitions are in **`cascade-diagram-template.md`** (same directory).

---

## User Gate

Present findings and cascade diagram. Ask: **"Would you like me to generate remediation plans? I'll group related fixes into PRs ordered by impact."** Do NOT proceed without confirmation. **Exit Plan Mode** (`ExitPlanMode`) after confirmation — doc generation requires the Write tool.

---

## Phase 4: Remediation Plans

Ask the user for a short session name (e.g., `explain-page-flicker`). By default, Plan agents write the final family to `<artifacts>/frontend-perf/`; keep research and intermediate inputs in `<scratch>`. For explicit `--output docs`, export the selected canonical family with `/claudna:publish <artifacts>/frontend-perf/ --to docs --dir documentation/planning/performance/<session_name>_<YYYY-MM-DD>/` and retain the source. Archive convention: orchestration guide, Section 8.

**00_PERF_AUDIT.md** — Master audit: date, scope, symptom, architecture summary, findings table, cascade diagram, priority order, grouping rationale, dependency matrix.

**Remediation Docs (01_, 02_, etc.)** — Group related findings into single PRs. Each doc = exactly 1 PR containing: header (title, severity, effort, files), findings addressed, dependencies, root cause explanation with cascade chain, detailed implementation plan (file paths, line numbers, before/after code), verification checklist (DevTools + manual repro + build/test), and "What NOT To Do" section.

**Subagent workflow:** Follow orchestration guide Section 9. Plan agents must also read `../../_shared/planning-standard.md`. Quality requirements beyond the shared standard: explain render lifecycle per fix, draw before/after cascades, include DevTools verification.

After generating docs: **"Plans are ready for review. Run `/claudna:build` on the session directory to execute them."**

---

## Phase 4.5: Adversarial Review Pass

Follow `../../_shared/pre-handoff-checklist.md` for the full procedure. Run on each phase doc (`<NN>_*.md`) and `00_PERF_AUDIT.md` under `<artifacts>` before presentation or export. For explicit chat-only `session`, keep review input and findings in context and create no files.

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
- **Subagent strategy.** Phase 2: general-purpose research (architecture). Phase 3: general-purpose research (per category). Phase 4: general-purpose planning (remediation docs). All use disk-write pattern.
- See orchestration guide, Section 10 for shared reminders.

---

## Output Targets

Follow the output guide at `../../_shared/output-guide.md`. This lens defaults to `artifacts` and supports explicit `session`, `github`, and `docs` targets — the latter exports the Phase 4 remediation plan docs:

- For `github`: write selected issue docs under `<artifacts>/frontend-perf/` (frontmatter + the Section 4 body skeleton), then delegate to `/claudna:publish <artifact-file> --to github-issue --repo <repo>` — publish validates, dedups, and applies labels from `tags:`. Keep each canonical source. Apply `performance` label. Map severity levels to priority labels. Group issues by cascade chain where applicable.
- For `artifacts` (default): retain the final report and selected plan family with `/claudna:publish <artifacts>/frontend-perf/ --to artifacts`.
- For `session`: present results in chat only; create no files.
- For `docs`: explicitly export the selected canonical family from `<artifacts>/frontend-perf/` to `documentation/planning/performance/<session_name>_<YYYY-MM-DD>/`; retain the source.

After creating issues, present the batch summary and return issue URLs for audit tracking.

---

## Autonomous Mode (--auto)

When `--auto` is set (see orchestration guide Section 10), retain the report and plan family under `<artifacts>/frontend-perf/` by default. Only explicit `--output github` files issues:
1. Skip Plan Mode — go straight to reconnaissance and scan
2. Page/flow **must** be provided in the arguments (bail if missing — this lens can't auto-detect what to audit)
3. Skip the user confirmation gate between scan and remediation
4. With explicit `--output github`, create issues for all findings, grouped by cascade chain
5. **Emit the structured-result shape** per `../../_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "audit",
  "outcome": "completed",
  "artifacts": {
    "lens": "frontend-perf",
    "issues_created": ["..."],
    "cascade_chains_found": 2,
    "page_audited": "<route or flow>",
    "session_dir": "<artifacts>/frontend-perf/"
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `blocked` if the page/flow wasn't provided (this lens cannot auto-detect; see rule 2 above).
