---
name: qa
user-invocable: true
description: "Use for headless-browser QA against a running app — systematic bug-hunting with optional fixes, post-deploy canary monitoring, performance benchmarking, ad-hoc browser interaction, cookie import, or an autonomous full-site visual crawl with per-route findings filed as issues. For a judgment-based design critique, use /claudna:audit design; for static code-level performance analysis, use /claudna:audit frontend-perf. Replaces /visual-crawl."
argument-hint: "[test|report|canary|benchmark|browse|cookies|crawl] [--auto] [--deep] [--output github|session] [--url <base-url>] [--local] [focus-area]"
allowed-tools:
  - "Bash(which *)"
  - "Bash(test *)"
  - "Bash(curl *)"
  - "Bash(lsof *)"
  - "Bash(npm *)"
  - "Bash(npm run *)"
  - "Bash(pnpm *)"
  - "Bash(yarn *)"
  - "Bash(python *)"
  - "Bash(python3 *)"
  - "Bash(pytest *)"
  - "Bash(ruff *)"
  - "Bash(flake8 *)"
  - "Bash(black *)"
  - "Bash(isort *)"
  - "Bash(mypy *)"
  - "Bash(npx *)"
  - "Bash(node *)"
  - "Bash(prettier *)"
  - "Bash(eslint *)"
  - "Bash(tsc *)"
  - "Bash(ls *)"
  - "Bash(mkdir *)"
  - "Bash(cat *)"
  - "Bash(git *)"
  - "Bash(gh *)"
  - "Read(*)"
  - "Write(*)"
  - "Edit(*)"
  - "Glob(*)"
  - "Grep(*)"
  - "Task(*)"
  - "Agent(*)"
  - "EnterPlanMode"
  - "ExitPlanMode"
---

# QA

Browser-automation framework with modes for different QA tasks. Uses a fast headless browser (~100ms per command) for navigating, interacting, screenshotting, and verifying state.

## Mode dispatch

Arguments to dispatch (first token = mode, the rest belong to the mode): $ARGUMENTS

| Token | Mode | When |
|-------|------|------|
| `test` | Test-and-fix | Systematically QA the app, find bugs, fix them, re-verify (iterative loop) |
| `report` | Report-only | Find bugs and produce a structured report; never modify code |
| `canary` | Canary | Post-deploy monitoring; baseline + diff to catch regressions |
| `benchmark` | Benchmark | Performance regression detection (Core Web Vitals, bundle size, load time) |
| `browse` | Browse | General-purpose browser interactions (navigate, click, screenshot, verify) |
| `cookies` | Cookie-setup | Import cookies from real browser for authenticated testing |
| `crawl` | Crawl | Autonomous route discovery + screenshot + per-route checks + findings filed via `publish` |

**No mode token → infer from the natural-language triggers in each mode's own section below** ("qa"/"test this site" → `test`; "canary"/"monitor deploy" → `canary`; etc. — see each mode's **When:** line). **Headless / non-interactive contexts: the mode token is required** — never inferred.

Only **Crawl mode** supports `--auto` (see "Autonomous Mode" below) — the other six modes are interactive-only.

---

## Test-and-fix mode

**When:** user says "qa", "test this site", "find bugs and fix them", "test and fix."

**Process:**

1. **Health baseline.** Snapshot the current state: tests pass/fail, lint clean, type-check clean, build succeeds. Record a score 0-10.
2. **Discover.** Either walk the app's key flows (golden path + top edge cases) OR if a URL is provided, navigate and interact.
3. **Find bugs.** Each bug gets severity (Critical / High / Medium / Cosmetic), repro steps, screenshot, and expected vs. actual.
4. **Fix iteratively.** For each bug, write a failing test → fix → verify pass → commit atomically. One bug → one commit.
5. **Re-verify.** Re-run the QA flow. Did fixes introduce regressions? Repeat.
6. **Report.** Before/after health score, fix evidence, ship-readiness summary.

Three tiers based on user's appetite:
- **Quick** — Critical + High only
- **Standard** — + Medium
- **Exhaustive** — + Cosmetic

---

## Report-only mode

**When:** user says "qa report only", "just check for bugs", "don't fix anything."

Same as test-and-fix but stops at step 3. Deliverable is a structured report (bug list + screenshots + repro). No code changes.

---

## Canary mode

**When:** user says "canary", "monitor deploy", "verify deploy", "watch production."

**Process:**

1. Before deploy, snapshot baseline: key pages' screenshots, Core Web Vitals, console error counts.
2. Deploy (the user handles the deploy; this skill doesn't deploy).
3. After deploy, periodically (every ~2 min) re-capture the same pages.
4. Compare against baseline. Flag anomalies:
   - New console errors
   - LCP / CLS / FID regressions >20%
   - Page load failures
   - Screenshot diff >10% (may indicate layout break)
5. Alert on anomaly; report all-clear after N clean cycles.

---

## Benchmark mode

**When:** user says "benchmark", "performance", "page speed", "check bundle size", "web vitals."

**Process:**

1. Establish baseline (first run OR from a previous commit/deploy).
2. Measure: load time, Core Web Vitals (LCP, FID, CLS), total bundle size per resource type, console errors.
3. Compare to baseline. Flag regressions >5%.
4. Present a before/after table. Suggest specific fixes for regressions.

---

## Browse mode

**When:** user says "open in browser", "screenshot this page", "click this button then verify X", "test this form."

A general-purpose browser automation interface. Navigate, interact with elements, take screenshots, verify assertions, handle dialogs, test forms/uploads.

No process — it's a tool. Agent picks commands based on task.

---

## Cookie-setup mode

**When:** user needs to test authenticated pages.

**Process:**

1. Open a picker UI showing cookie domains from the user's real Chromium browser.
2. User selects which domains to import.
3. Import those cookies into the headless session.
4. Subsequent QA/browse commands are authenticated.

Use before test-and-fix, report-only, canary, or crawl mode if auth is required.

---

## Crawl mode

**When:** user says "visual crawl", "crawl the site", "screenshot every page", "test the whole frontend."

Systematic visual crawl of a frontend application. Discovers routes, screenshots every page at three viewports, tests interactions for errors, compares observed styles against design tokens, and files GitHub issues with screenshot evidence for every finding.

Runs on a real Playwright engine. Three support files in this directory carry the mechanics:
- `deep-crawl.md` — copy-pasteable scripts: screenshot recipe (`device_scale_factor=2`, networkidle, full-page), console-error collector, the `--deep` interactive harness (click ≤30 buttons / fill ≤10 forms with before/after diffs), and the chat-simulation driver.
- `crawl-checklist.md` — the 7 per-route check groups (render / console / link / interaction / responsive / empty-states / a11y) with concrete thresholds (body ≥16px, touch ≥44px, WCAG AA 4.5:1).
- `design-token-rules.md` — token extraction JS + ΔE2000 perceptual color-distance thresholds for drift detection.

### Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Fully non-interactive. Implies `--output github`. Crawl, screenshot, test, file issues, return summary.
- `--deep`: Full interactive testing. Extends the interaction-testing step with: click every button/link and verify result, fill and submit forms, simulate chat conversations with sample queries, screenshot before/after each interaction, report broken flows. Uses Playwright for interaction testing (see `deep-crawl.md`).
- `--output github`: Write findings as GitHub Issues (default). See output guide (`skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- `--url <base-url>`: Crawl a deployed URL (e.g., `--url https://app.example.com`).
- `--local`: Spin up a local dev server from the project directory and crawl it.
- Remaining text is a focus area or constraint (e.g., "only the dashboard pages").

If neither `--url` nor `--local` is specified, ask the user.

### When NOT to use this mode

- For design critique and enhancement proposals → use `/claudna:audit design`
- For frontend performance (flickering, re-renders, layout shifts) → use `/claudna:audit frontend-perf`
- For code quality/tech debt → use `/claudna:audit tech-debt`
- For security vulnerabilities → use `/claudna:audit security`

**Enter Plan Mode.** Call `EnterPlanMode`. All discovery and crawl steps are read-only. If declined, proceed by convention.

### Process

1. **Setup.** Scratch dir: `/tmp/qa-crawl-<YYYY-MM-DD_HHMMSS>/`. Create subdirectories: `screenshots/`, `research/`, `console-logs/`. Detect Chrome/Chromium: `which chromium`, `which google-chrome`, `which chromium-browser` in parallel.

2. **Determine base URL.**
   - **If `--url <base-url>`:** Use directly. Verify reachable with `curl -sI <base-url>`.
   - **If `--local`:** Read `package.json` for start/dev scripts and port; check if already running (`lsof -i :<port>`, `curl -s http://localhost:<port>`); if not, start it in background; poll with curl (max 30s); base URL = `http://localhost:<port>`.
   - **If neither:** Ask the user (skip in `--auto` — error out).

3. **Route discovery.** Launch **Explore subagents** in parallel — one scans for file-based routes (Next.js App/Pages Router, React Router, `routes/`/`views/`), one checks `sitemap.xml`/`robots.txt`/homepage `<a href>` links. Merge into a deduplicated list. Present to user for confirmation (skip in `--auto`).

4. **Screenshot crawl.** Per `deep-crawl.md`'s screenshot recipe: capture desktop (1440×900) / tablet (768×1024) / mobile (375×812) for each route, in parallel per-route, sequential across routes. Collect console errors and page exceptions per route.

5. **Interaction testing.** Per `deep-crawl.md`'s standard interaction pass: enumerate interactive elements, dead-link check, button click test, empty-state detection. If `--deep`: run the deep-crawl harness and chat-simulation driver from `deep-crawl.md`.

6. **Design token comparison.** Per `design-token-rules.md`: extract observed tokens (fonts, colors, sizes, spacing) at desktop viewport; compare against the project's reference tokens (or fallback defaults); flag drift (ΔE2000 > 5 for colors).

7. **Findings compilation.** Classify per `crawl-checklist.md`'s categories and priority mapping (Critical / High / Medium / Low).

8. **Output.** **Exit Plan Mode** (`ExitPlanMode`).
   - **`--output github` or `--auto`:** write each finding as a doc (frontmatter + Section 4 body skeleton; group related findings per `crawl-checklist.md`'s grouping rules), `tags:` including `auto-audit`, `visual-crawl`, a category label, a priority label; delegate each to `/claudna:publish <file> --to github-issue --repo <repo>`. Finish with a batch summary doc (output guide §4.6).
   - **`--output session`:** present findings in chat with inline screenshot references. Stay in Plan Mode.

Return structured summary:
```
Visual Crawl Summary
════════════════════════════════════════════════════
Routes crawled: N
Screenshots taken: N (N routes × 3 viewports)
Console errors found: N
Dead links found: N
Interaction failures: N
Design token violations: N
GitHub issues created: N
════════════════════════════════════════════════════
```

### Autonomous Mode (`--auto`)

Scoped to **Crawl mode only** — the other six modes have no `--auto` contract.

When `--auto` is set:
1. Skip Plan Mode — go straight to crawl
2. Skip user confirmation gates
3. Implies `--output github`
4. Must have `--url` or `--local` (cannot prompt for URL)
5. Create GitHub Issues for all findings at Medium priority or above
6. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "qa",
  "outcome": "completed",
  "artifacts": {
    "mode": "crawl",
    "issues_created": ["..."],
    "routes_crawled": 12,
    "screenshots_taken": 36,
    "console_errors": 3,
    "dead_links": 1,
    "interaction_failures": 0,
    "design_token_violations": 5,
    "scratch_dir": "/tmp/qa-crawl-<timestamp>/"
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `blocked` if base URL is unreachable or no routes were discovered.
- `--deep` mode produces additional artifacts; if `--deep` was used, add `deep_findings: N` to artifacts.

`--auto` and `--deep` can be combined: `--auto --deep --url https://app.example.com` runs a full interactive crawl with issue filing, no human in the loop.

---

## Notes

- **One screenshot per Bash call.** No shell operators (`&&`, `||`, `;`, `|`). Playwright commands are single-shot.
- **Sequential routes, parallel viewports.** Don't open multiple browser instances for different routes simultaneously — sequential keeps memory pressure low and avoids resource exhaustion on constrained hardware.
- **Screenshots are evidence.** Every crawl-mode finding must reference at least one screenshot file.
- **Don't fix code in report-only or crawl mode.** These identify problems. Use `/claudna:build`, test-and-fix mode, or manual fixes afterward.
- **Respect robots.txt.** If a deployed URL has `Disallow` rules, honor them unless the user explicitly overrides.
- **Timeout handling.** If a page doesn't load within 30 seconds, log a finding (possible server issue) and continue to next route.
- **Subagents for research.** Use Explore subagents for route discovery and codebase analysis. Use general-purpose subagents for disk writes. Keep orchestrator context lean.
- `skills/_shared/orchestration-guide.md` §11 for shared reminders.

---

## Output Targets (crawl mode)

Follow the output guide at `skills/_shared/output-guide.md`:
- For `github` (default): write each finding as a doc (frontmatter + Section 4 body skeleton) with `tags:` including `visual-crawl` + a category label, then delegate to `/claudna:publish <file> --to github-issue --repo <repo>` (publish dedups + labels).
- For `session`: produce the doc, then `/claudna:publish <file> --to session` prints it to chat (Section 5)
