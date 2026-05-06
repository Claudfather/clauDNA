---
name: design-review
description: "Use when you want a visual and UX audit of a deployed application to find design gaps and plan improvements. Supports --output github to create issues and --output session for chat-only analysis."
argument-hint: "[--output github|session] [deployed-url]"
allowed-tools:
  - "Bash(which *)"
  - "Bash(test *)"
  - "Bash(curl *)"
  - "Bash(lsof *)"
  - "Bash(npm run *)"
  - "Bash(pnpm *)"
  - "Bash(yarn *)"
  - "Bash(/Applications/Google*)"
  - "Bash(\"/Applications/Google*)"
  - "Bash(google-chrome*)"
  - "Bash(chromium*)"
  - "Read(*)"
  - "Write(*)"
  - "Glob(*)"
  - "Grep(*)"
  - "Task(*)"
  - "Agent(*)"
  - "EnterPlanMode"
  - "ExitPlanMode"
---

# Design Review & UI/UX Enhancement Planner

Design-literate PM bridging visual polish and engineering. Audit a deployed app, find design/UX gaps, produce phased PR-ready design docs.

## Arguments

Parse `$ARGUMENTS` at invocation:
- If it contains `--output github`: activate GitHub Issues output mode. See output guide (`~/.claude/skills/_shared/output-guide.md`).
- If it contains `--output session`: present findings in chat only, no persistence.
- Remaining text is the deployed URL or focus area. If provided, skip asking in Step 1.

## When NOT to use

- For frontend performance (flickering, slow loads, re-renders) → use `/frontend-performance-audit`
- For code quality/tech debt → use `/tech-debt`
- For product feature gaps → use `/product-enhance`

## Procedure

**Enter Plan Mode** (`EnterPlanMode`). Steps 1-5 are read-only. If declined, proceed by convention.

---

### Step 1: Scope & Context Gathering

Ask: (1) deployed URL, (2) focus area, (3) anything to skip, (4) front-end stack. Scratch dir: `/tmp/design-review-<YYYY-MM-DD_HHMMSS>/research/`.

Parallel: **A.** Explore subagents (disk-write pattern, orchestration guide Section 2) for front-end structure, styling, state, APIs, tokens, components. **B.** Begin Step 2.

Present codebase context summary. Confirm with user.

---

### Step 2: Visual Audit — Screenshot Capture

Detect Chrome (`which google-chrome`, `which chromium`, `test -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"` in parallel). Prefer local dev server -- check `package.json` for port, `lsof` if running, `curl` to verify; fall back to deployed URL.

Capture each page at `1440,900` / `768,1024` / `375,812`. **One screenshot per Bash call. No shell operators.**

Classify pages: **MARKETING** (hero-driven), **APP UI** (data-dense), **HYBRID** (per-section rules). See `design-hard-rules.md`.

**DOM Extraction (optional, claude-in-chrome MCP -- skip if unavailable):**

**Fonts:** `JSON.stringify([...new Set([...document.querySelectorAll('*')].slice(0,500).map(e => getComputedStyle(e).fontFamily))])`

**Colors:** `JSON.stringify([...new Set([...document.querySelectorAll('*')].slice(0,500).flatMap(e => [getComputedStyle(e).color, getComputedStyle(e).backgroundColor]).filter(c => c !== 'rgba(0, 0, 0, 0)'))])`

**Headings:** `JSON.stringify([...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h => ({tag:h.tagName, text:h.textContent.trim().slice(0,50), size:getComputedStyle(h).fontSize, weight:getComputedStyle(h).fontWeight})))`

**Touch targets:** `JSON.stringify([...document.querySelectorAll('a,button,input,[role=button]')].filter(e => {const r=e.getBoundingClientRect(); return r.width>0 && (r.width<44||r.height<44)}).map(e => ({tag:e.tagName, text:(e.textContent||'').trim().slice(0,30), w:Math.round(e.getBoundingClientRect().width), h:Math.round(e.getBoundingClientRect().height)})).slice(0,20))`

Ask: **"Here's what I see. Anything I should look at more closely?"**

---

### Step 3: Design Intent Interview

Ask these one group at a time, waiting for answers:

- **Brand & Identity** — desired feeling, brand guides/Figma, target users
- **Pain Points** — visual annoyances, user complaints, pages that feel "off"
- **Aspirations** — admired apps, snap-fix wish, desired patterns

---

### Step 4: Design Gap Analysis

Compare intent (Step 3) vs. observations (Step 2) vs. code (Step 1). Explore subagents for targeted digs.

Subagents read from this directory: `audit-checklist.md`, `ai-slop-blacklist.md`, `font-knowledge.md`, `design-hard-rules.md`. Calibrate by page-type. Present gap analysis with dual scores (Design + AI Slop), referencing screenshots and code.

Ask: **"Does this match your experience? Anything I missed or got wrong?"**

---

### Step 5: Enhancement Proposals


Propose enhancements scored on Impact, Effort, Risk. Classify as **SAFE** (baseline fix users expect) or **RISK** (differentiation -- explain upside and downside). SAFE first, ranked by impact-to-effort. Reference screenshots, Step 3 intent, code.

Ask: **"Which would you like me to design? Pick by number or adjust."** Wait for selection. Call `ExitPlanMode`.

---

### Step 6: Generate Phased Design Docs

Output to `documentation/planning/phases/<session_name>_<YYYY-MM-DD>/`. Overview + numbered docs (1 PR each). Orchestration guide Section 9.

Phase docs include: header, context + screenshots, visual spec (exact before/after), dependencies, implementation plan, responsive behavior, accessibility checklist, test plan, verification, "What NOT To Do."

Tell user: **"Run `/implement-plan` on the phase directory to start building."** This skill produces plans, not code.

---

## Notes

- **User gates** at every step -- never auto-proceed.
- **Screenshots are evidence** -- every observation references one.
- **Subagents:** Steps 1/4 Explore, Step 6 Plan. Disk-write pattern per orchestration guide.
- **Critique format:** "I notice..." / "I wonder..." / "What if..." / "I think... because..."
- **Respect existing design system.** Accessibility non-negotiable. Orchestration guide Section 10.

---

## Output Targets

This skill supports `--output github` and `--output session` in addition to the default `docs` target.

Follow the output guide at `~/.claude/skills/_shared/output-guide.md`:
- For `github`: use the structured issue body format (Section 4), check for duplicates (Section 4.5), apply labels (Section 4.3). Apply `design` label. Include SAFE vs RISK classification in issue body.
- For `session`: present findings in chat, stay in Plan Mode (Section 5)
- For `docs` (default): follow the subagent workflow in the orchestration guide

After creating issues, present the batch summary and return issue URLs for audit tracking.

