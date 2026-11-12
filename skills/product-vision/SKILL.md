---
name: product-vision
user-invocable: true
description: "Use when you want to explore what a codebase could become — candidate features one or two hops from existing infrastructure, compound plays, and a trajectory aligned to the project mission. For triaging known issues in an existing product, use /claudna:product-enhance. For discovery gated on an active piece of creative work, needing user approval before implementation, use /claudna:kindle instead. Replaces /product-brainstorm."
argument-hint: "[--auto] [--output artifacts|docs|github|vault|notion|session] [focus-area]"
---

# Product Vision — Architecture-Grounded Feature Exploration

> **Codex:** Read `../_shared/codex-tools.md` before following this skill. Apply its tool, root and dispatch mappings throughout.

Act as a product strategist with deep technical fluency. Unlike generic brainstorming, this skill is **grounded in the actual codebase** — every idea must trace back to existing infrastructure that makes it feasible. The goal is to find what's **1-2 hops away** from what already exists, group ideas into **compound plays** that are greater than the sum of their parts, and align everything to a **project mission**.

## Working files and output

Follow `../_shared/orchestration-guide.md` §1 for native session allocation and exact-owner cleanup. Exploration and intermediate notes stay in `<scratch>`; the sanitized capability map, scored ideas, vision report, and generated plan docs default to `<artifacts>`. `--output artifacts` is the explicit spelling of that default; `--auto` uses the same default unless an output target was explicitly supplied. Explicit `--output docs|github|vault|notion` publishes retained canonical artifacts and records actual outcomes in the current session's private receipt (`docs` → `--to docs`, `github` → `--to github-issue --repo <repo>`, `vault` → `--to vault`, `notion` → `--to notion`). `--output session` is chat-only and performs no allocation or writes; skip disk-writing subagent steps in this mode. Missing/conflicting/unverified identity or ordinary-permission denial stops persistence without cwd, operation-ID, or OS-temp fallback. Preserve user-authored project source/config as project-owned.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Fully non-interactive. Defaults to canonical session artifacts; an explicit `--output docs|github|vault|notion` selects an export. Explore, analyze, and return a summary. See Section: Autonomous Mode.
- `--output artifacts`: Keep sanitized reports and any generated plan docs in current-session artifacts (default).
- `--output docs|github|vault|notion`: Explicitly export the canonical revision through `/claudna:publish` using the matching adapter (`github` maps to `--to github-issue --repo <repo>`), retaining the source and recording the actual result.
- `--output github`: Write findings as GitHub Issues. See output guide (`../_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Remaining text is a focus area or constraint. If provided, scope exploration to that area.

## When NOT to use

- For specific known issues or bug triage → use `/claudna:product-enhance`
- For code quality/tech debt → use `/claudna:audit tech-debt`
- For design/UX problems → use `/claudna:audit design`
- For security vulnerabilities → use `/claudna:audit security`

**Enter Plan Mode.** Call `EnterPlanMode`. All discovery and analysis steps are read-only. If declined, proceed by convention.

---

## Phase 1: Understand What Exists

### Step 1: Project Mission Check

Look for `PROJECT_MISSION.md` in the repo root. This file contains the project's north star — what it's trying to become, who it serves, and what success looks like.

- **If found:** Read it. Use it to score and prioritize ideas in later phases.
- **If not found:** Note this. You'll propose one at the end based on what you discover.

### Step 2: Deep Codebase Exploration

Launch **Explore subagents** in parallel (disk-write pattern, scratch dir: `<scratch>/research/`, allocated per `../_shared/orchestration-guide.md` §1). Each subagent writes private findings there and returns only a summary.

Subagent assignments:
1. **Architecture & capabilities** — what does this system do today? Map every major module, service, API endpoint, and user-facing feature.
2. **Data & state** — what data does the system collect, store, or have access to? What is being collected but NOT surfaced to users?
3. **Integration surface** — what external systems does it connect to? What APIs does it call? What could it connect to that it doesn't?
4. **User flows** — trace the primary user journeys end-to-end. Where do they start? Where do they end? Where are the friction points?
5. **Extensibility patterns** — what does the architecture suggest it was designed to support that isn't built yet? Config-driven patterns, plugin systems, unused abstractions.

Also check:
- Existing GitHub Issues (open) — what do users/developers already want?
- Git log (last 30 days) — what direction is the project moving?
- CLAUDE.md / README — stated goals and context

### Step 3: Capability Map

Present a concise **Capability Map**:
- **Core capabilities** — the main things this product does today
- **Underutilized assets** — data, infrastructure, or integrations that exist but aren't fully leveraged
- **Architectural affordances** — patterns that suggest the system was designed for more

Ask user to confirm the map is accurate (skip in `--auto` mode).

---

## Phase 2: Explore What's Possible

### Step 4: Feature Discovery

For each idea, determine feasibility using Explore subagents that read from the scratch directory.

Generate ideas across these dimensions:

**ONE HOP** (build this week on existing infrastructure):
- What existing data could be surfaced in new ways?
- What manual steps could be automated with current capabilities?
- What features are 80% built but missing the last mile (UI, API endpoint, etc.)?
- What error paths or edge cases could become features?

**TWO HOPS** (needs some new infrastructure but builds on what exists):
- What adjacent capabilities would make the core product 10x more valuable?
- What integrations would compound existing value?
- What would shift this from "useful tool" to "can't work without it"?
- What would make the product proactive instead of reactive (push vs pull)?

**DEPRECATION CANDIDATES** (what to stop doing):
- Features that add complexity but aren't used
- Patterns that the codebase has outgrown
- Technical approaches that should be replaced

### Step 5: Compound Plays

This is the most important step. Group related ideas into **compound plays** — themes where 2-3 features together create something much more valuable than any single feature.

Format:
```
COMPOUND PLAY: [Theme Name]
Features: [Feature A] + [Feature B] + [Feature C]
Together they become: [What this combination creates]
Why it compounds: [Why the whole is greater than the sum]
```

Example: "Data Reliability Platform" = freshness monitoring + anomaly alerts + entity health scorecard. Individually they're nice-to-haves. Together they're the reason you open the tool every morning.

### Step 6: Impact × Effort Scoring

Score each idea and compound play:

| Idea | Hop | Impact | Effort | Score | Mission Alignment |
|------|-----|--------|--------|-------|-------------------|
| ... | 1 | High | Low | 🟢 | Strong |

Impact: How much does this change the user's experience?
Effort: How much new code/infrastructure vs reusing existing?
Mission Alignment: Does this move the project toward its north star? (Skip if no mission doc)

Present the scored table. User selects which to pursue (skip in `--auto` mode — select all with Score 🟢 or 🟡).

---

## Phase 3: Crystallize

### Step 7: Mission Synthesis (if no PROJECT_MISSION.md)

If the project doesn't have a mission doc, propose one based on what you discovered:

```markdown
# Project Mission — [Project Name]

## What this project is
[One paragraph — what it does today and who it serves]

## What it's becoming
[One paragraph — the trajectory based on recent development and compound plays]

## North star
[One sentence — the ultimate value proposition]

## Guiding principles
[3-5 bullets — what to prioritize when making tradeoffs]
```

Present conversationally for the user to edit. **Do not write the file in `--auto` mode** — just include the proposed mission in the output.

### Step 8: Output

**Exit Plan Mode.** Call `ExitPlanMode`.

Create GitHub Issues only when `--output github` is explicitly selected:
- One issue per feature idea (tagged with `product-vision`, hop count, compound play if applicable)
- One issue per compound play (meta-issue linking the component features)
- Cross-reference against existing open issues to avoid duplicates
- Apply labels: `enhancement`, `product-vision`, `one-hop` or `two-hop`

Present summary:
- Capability map (what exists)
- Top compound plays (what to build toward)
- Scored feature table (what to build next)
- Proposed mission (if no mission doc existed)
- Deprecation candidates (what to stop)

---

## Autonomous Mode (--auto)

When `--auto` is set:
1. Skip Plan Mode — go straight to exploration
2. Skip user confirmation gates
3. Defaults to `--output artifacts`; explicit `--output docs|github|vault|notion` selects that export.
4. Use focus area from `$ARGUMENTS` as scope. If none, explore full codebase.
5. For explicit `session`, return the report and ideas in context with no files; otherwise write the sanitized vision report and idea set to `<artifacts>`. Create GitHub Issues for ideas scored 🟢 or 🟡 only when `--output github` was explicitly selected; retain canonical artifacts and record actual URLs/status privately.
6. Do NOT write PROJECT_MISSION.md — just include proposed mission in summary
7. **Emit the structured-result shape** per `../_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "product-vision",
  "outcome": "completed",
  "artifacts": {
    "issues_created": [],
    "canonical_report": "<artifacts>/VISION.md",
    "compound_plays_identified": 3,
    "one_hop_features": 7,
    "two_hop_features": 4,
    "deprecation_candidates": 2,
    "mission_proposed": false
  },
  "summary": "<2-3 line digest of compound plays and top features>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `mission_proposed` is `true` when no PROJECT_MISSION.md existed and one was synthesized; the proposed mission text remains in the summary, while the generated vision report is canonical under `<artifacts>`.
- `outcome` is `completed` on success.

---

## Output Targets

Follow the output guide at `../_shared/output-guide.md`:
- For `artifacts` (default): write the sanitized vision report and any planning-doc family under `<artifacts>/product-vision/<session_name>_<YYYY-MM-DD>/`; private exploration remains in scratch.
- For explicit `github`: retain canonical reports, then publish selected findings/plays as issues; record actual URLs/status in the private receipt.
- GitHub issue documents retain output-guide frontmatter and Section 4 body skeleton, with `product-vision`, hop-count, and compound-play tags. Publish one issue per selected feature idea and one linking meta-issue per selected compound play; cross-reference existing open issues and apply `enhancement`, `product-vision`, and `one-hop` or `two-hop` labels.
- For explicit `docs`: retain the canonical family, then publish `00_VISION.md` as the publishable family master (presence-only validation); publish implementation-ready compound-play or feature docs individually only when GitHub output is selected.
- For explicit `session`: present sanitized results in chat without allocation or file writes; do not run disk-writing subagent steps.
- For explicit `docs`, `vault`, or `notion`: retain canonical reports and use the selected publisher adapter, recording its actual result.

---

## Pre-Handoff

Before presenting output (all modes), run the adversarial review gate per `../_shared/pre-handoff-checklist.md` on each generated doc. Plan output must meet the quality standard in `../_shared/planning-standard.md`.

---

## Notes

- **Architecture-grounded, not blue-sky.** Every idea must trace to existing code that makes it feasible.
- **Compound plays are the star.** Individual features are useful. Themes that compound are transformative.
- **Mission emerges from exploration.** Don't force a mission upfront — let it crystallize from what you find.
- **Deprecation is vision too.** What you choose NOT to build is as important as what you do.
- **Subagents for everything.** Keep the orchestrator lean. Push all codebase reads to Explore subagents.
- Orchestration guide Section 10 for shared reminders.
