---
title: Phase 1 — clauDNA Contract & Structured Result Shape
type: plan
status: draft
owner: chrisrogers37
created: 2026-05-17
tags: [autonomous-mode, phase-1, contract, structured-result]
repos: [clauDNA]
links: []
---

# Phase 1 Implementation Plan — clauDNA Contract & Structured Result Shape

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the shared autonomous-mode contract to cover Tier-3 (implementation) skills, define a uniform machine-readable result shape, normalize all existing `--auto` skills to emit it, and add the discipline modes to `/claudna:adversarial-review` and `/claudna:weigh-development-paths` that downstream phases depend on.

**Architecture:** Edits live in (a) one shared doc (`skills/_shared/orchestration-guide.md`), (b) 9 existing `--auto` skill bodies, and (c) two skill bodies that gain new non-interactive modes. No code changes; only skill markdown and one optional validator extension. Each skill edit is independent and can be parallelized after the shared doc is updated.

**Tech Stack:** Markdown only. Python only if the optional validator extension is chosen.

**Repo:** clauDNA (`/path/to/clauDNA`)

**Prerequisites:** Read the design spec at `documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md` end-to-end before starting. Especially §5.1, §5.2, §5.6, §5.7.

---

## Audit Status (2026-07-06)

**Overall: ✅ COMPLETE.** All 16 tasks below shipped in PR #85 ("Phase 1: Autonomous-mode contract & structured result shape", commit `d46699c`, merged **2026-05-18** — one day after this plan was authored). This audit re-verified every task against the codebase at HEAD (`feat/frameworks-not-skus-phase1`, 2026-07-06), roughly 7 weeks and many commits later, after Phase 2 (#86, same day), Phase 3 (#87, 2026-05-18), the session-handoff redesign (#88, 2026-05-18), the `/claudna:publish` output-routing consolidation (#115, 2026-05-27), and the forge/ironclad unification (#130, #132, 2026-06-02, and later) all landed on top of it.

Headline findings:
- Tasks 2, 3, 5, 6-14, 15, 16 are intact and still match this plan's specified text/shape almost verbatim — confirmed by `grep`/`git log` against each target file.
- Task 4 is **✅ COMPLETE but superseded in shape**: `/claudna:adversarial-review --dispatch` no longer emits the §10.C JSON block this plan specifies. PR #130 (2026-06-02) changed it to emit markdown+YAML frontmatter per the newer `skills/_shared/contracts/lens-result-contract.md`, built to feed `/claudna:ironclad`'s multi-lens convergence loop — a consumer that didn't exist yet when this plan was written. CHANGELOG.md's own entry for that change notes: "The generic `--auto` JSON shape in orchestration-guide.md §10.C is unchanged" — i.e. a deliberate, scoped divergence for one consumer, not a regression of the general contract.
- The §10.C JSON contract this phase defined has since been adopted by skills built *after* this plan shipped (`/claudna:forge`, `/claudna:ironclad --auto`) — evidence the contract succeeded as a durable convention rather than a one-off.

Per-task detail and file:line citations are marked inline below.

---

## File Structure

Files modified or created in this phase:

| File | Action | Notes | Status (2026-07-06) |
|---|---|---|---|
| `skills/_shared/orchestration-guide.md` | Modify | Extend §10 with Tier-3 sub-section + structured-result shape | ✅ COMPLETE |
| `skills/adversarial-review/SKILL.md` | Modify | Make `--dispatch` imply non-interactive; emit structured findings | ✅ COMPLETE but superseded — non-interactive behavior intact, but `--dispatch` output is now markdown+frontmatter (`lens-result-contract.md`), not §10.C JSON |
| `skills/weigh-development-paths/SKILL.md` | Modify | Add `--auto` mode; emit refined-plan structured result | ✅ COMPLETE |
| `skills/tech-debt/SKILL.md` | Modify | Append structured-result emission to "Autonomous Mode" section | ✅ COMPLETE |
| `skills/security-audit/SKILL.md` | Modify | Same | ✅ COMPLETE |
| `skills/product-enhance/SKILL.md` | Modify | Same | ✅ COMPLETE |
| `skills/frontend-performance-audit/SKILL.md` | Modify | Same | ✅ COMPLETE |
| `skills/docs-review/SKILL.md` | Modify | Same | ✅ COMPLETE |
| `skills/access-path-audit/SKILL.md` | Modify | Same | ✅ COMPLETE |
| `skills/product-vision/SKILL.md` | Modify | Same | ✅ COMPLETE |
| `skills/session-handoff/SKILL.md` | Modify | Same (no "--auto" section today, but has --auto behavior throughout) | ✅ COMPLETE — re-homed into a numbered step by the #88 redesign, same shape |
| `skills/visual-crawl/SKILL.md` | Modify | Same | ✅ COMPLETE |
| `scripts/validate-skills.py` (optional) | Modify | Add a check: skills declaring `--auto` must have a "Structured Result Emission" section | ✅ COMPLETE — done, not skipped; live in CI today |
| `CHANGELOG.md` | Modify | Add an entry summarizing the Phase 1 changes | ✅ COMPLETE — now under the dated `[0.4.0]` release, not `[Unreleased]` |

---

## Conventions for this phase

- **All edits to skill markdown anchor by heading text**, not line numbers. Use the Edit tool with `old_string` containing a unique heading line + surrounding context.
- **The exact YAML and prose to insert is given inline below.** Copy verbatim except where the task explicitly says to adapt to the skill (e.g., the `skill` field in the JSON example takes the current skill's name).
- **After each skill is edited, run `python3 scripts/validate-skills.py`** to confirm no regressions.
- **Each task ends with a commit.** Conventional commit format. Do not batch.

---

## Task 1: Read all source files

> **Status: ✅ COMPLETE (implicit).** Read-only orientation task with no on-disk deliverable to verify directly. Confirmed by outcome: every downstream task (2-16) matches this plan's specified text, which would not be possible without this reading having happened.

**Files:**
- Read: `documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md`
- Read: `skills/_shared/orchestration-guide.md`
- Read: `skills/_shared/output-guide.md`
- Read: `skills/adversarial-review/SKILL.md`
- Read: `skills/weigh-development-paths/SKILL.md`
- Read: `skills/tech-debt/SKILL.md`
- Read: `skills/security-audit/SKILL.md`
- Read: `skills/product-enhance/SKILL.md`
- Read: `skills/frontend-performance-audit/SKILL.md`
- Read: `skills/docs-review/SKILL.md`
- Read: `skills/access-path-audit/SKILL.md`
- Read: `skills/product-vision/SKILL.md`
- Read: `skills/session-handoff/SKILL.md`
- Read: `skills/visual-crawl/SKILL.md`
- Read: `scripts/validate-skills.py`
- Read: `SKILL_CONTRACT.md`
- Read: `CLAUDE.md`

- [ ] **Step 1: Read the design spec end-to-end**

Read the full design spec. Pay particular attention to §5.1 (orchestration-guide extension), §5.2 (structured result shape), §5.6 (`/weigh-development-paths --auto`), §5.7 (normalize existing --auto skills).

Expected: you understand the contract being added, the JSON shape every `--auto` skill must emit, and which 9 skills need normalization.

- [ ] **Step 2: Read the current orchestration guide**

Read `skills/_shared/orchestration-guide.md`. Note especially:
- §10 "Autonomous Mode (`--auto`)" — this is the section being extended
- §13 "Skill Priority Ordering" — defines tiers; Phase 1 adds Tier-3 to the §10 compatibility matrix

Expected: you can quote the current §10 rules and know which skills are listed in the compatibility matrix.

- [ ] **Step 3: Read the 9 target skills**

Read each of the 9 skills that currently support `--auto`. For each, locate its `## Autonomous Mode (--auto)` section (or its equivalent for `session-handoff`, which interleaves `--auto` behavior throughout).

Expected: you have a mental map of where each skill's autonomous-mode section sits so you can append the structured-result emission cleanly.

- [ ] **Step 4: Read adversarial-review and weigh-development-paths**

Both skills currently use Plan Mode and (in some flows) AskUserQuestion. Note:
- `adversarial-review` has a `--dispatch` flag for parallel-critic mode that currently doesn't suppress interactive elements.
- `weigh-development-paths` has no `--auto` mode; the entire skill enters Plan Mode by default.

Expected: you understand which interactive elements need to be suppressed in the new non-interactive modes.

- [ ] **Step 5: Read the validator**

Read `scripts/validate-skills.py` and `SKILL_CONTRACT.md`. Note which fields the validator checks (name, description, length, regex on names). The validator extension in Task 13 will follow this pattern.

No commit for Task 1 — it's a read-only orientation task.

---

## Task 2: Extend `orchestration-guide.md §10` with Tier-3 sub-section

**Files:**
- Modify: `skills/_shared/orchestration-guide.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/_shared/orchestration-guide.md:304-321` — "### For implementation skills (Tier 3)" sub-section present, text matches this plan almost verbatim. Compatibility matrix rows added at lines 386-388 (`/claudna:implement-plan`, `/claudna:weigh-development-paths`, `/claudna:adversarial-review`). Shipped in PR #85 (2026-05-17); unchanged as of 2026-07-06 through several later refactors (#121 extracted `planning-standard.md`/`pre-handoff-checklist.md` from this same file without touching §10).

- [ ] **Step 1: Locate the existing §10 structure**

Open `skills/_shared/orchestration-guide.md`. Find the heading `## 10. Autonomous Mode (`--auto`)`. The current section has these sub-headings in order:
1. `### What --auto means`
2. `### Default behavior changes with --auto`
3. `### How skills should reference this`
4. `### Skills that support --auto`

The work adds new sub-sections between §10 and §11.

- [ ] **Step 2: Add a sub-section "For implementation skills (Tier 3)"**

Use the Edit tool. Find this text:

```
### Skills that support `--auto`

| Skill | Auto-viable? | Notes |
```

Replace with this text (which prepends a new sub-section and keeps the existing table heading):

```
### For implementation skills (Tier 3)

The rules above describe planning skills that produce GitHub Issues. Implementation skills (Tier 3 per §13: `/claudna:implement-plan`, and any future skill that produces PRs from existing plans) follow a parallel `--auto` contract with these differences:

- **Implies producing a PR, not an issue.** Does NOT imply `--output github`. The terminal artifact is an open PR on the work item's source branch.
- **Never merges.** The merge gate is unconditionally skipped in `--auto`. A human ratifies the PR.
- **Requires a target work item.** `--auto` MUST be invoked with `--source github <#>` or an explicit plan path. Picker / browse modes are disallowed.
- **Trusts the caller has vetted the plan.** Interactive challenge rounds are replaced by either (a) trust (the upstream planning skill ran adversarial-review at creation time per §5.3 of the design) or (b) machine synthesis via `/claudna:weigh-development-paths --auto` per design §5.5.2. The skill does not stop to ask the user.
- **"Feels wrong" exits with `outcome: blocked`** with a populated `blocker_description` field, instead of stopping for user discussion.
- **Emits the structured result shape (§10.C below)** at the end of the run.

Skills MUST add to their Arguments section:

```
- `--auto`: Fully non-interactive mode. Required target work item via `--source github <#>` or explicit plan path. Never merges. See orchestration guide §10 (Tier-3 sub-section).
```

And add an "Autonomous Mode (--auto)" section at the end of their procedure mirroring planning-skill structure but documenting the Tier-3 specifics.

### Skills that support `--auto`

| Skill | Auto-viable? | Notes |
```

- [ ] **Step 3: Update the compatibility matrix to add Tier-3 entries**

The compatibility matrix table currently lists Tier-2 planning skills plus `session-handoff`. Find the row for `session-handoff` and add new rows below it before the closing `---` separator. Use Edit with this `old_string`:

```
| `/claudna:session-handoff` | ✅ Yes | Already implemented |

---
```

And this `new_string`:

```
| `/claudna:session-handoff` | ✅ Yes | Already implemented |
| `/claudna:implement-plan` | ✅ Yes | **Tier 3.** Phase 3 of the autonomous-mode rollout. Consumes plans/issues, produces PRs, never merges. |
| `/claudna:weigh-development-paths` | ✅ Yes | **Composable.** Phase 1 adds `--auto` for chained use from `/implement-plan --auto`. Returns refined plan. |
| `/claudna:adversarial-review` | ✅ Yes | **Composable.** `--dispatch` mode is non-interactive when invoked from another skill. Returns structured critique findings. |

---
```

- [ ] **Step 4: Verify the edit**

Run:

```bash
grep -n "implement-plan" /path/to/clauDNA/skills/_shared/orchestration-guide.md | head -5
```

Expected: `implement-plan` appears in the compatibility matrix row, alongside the new sub-section above.

Run:

```bash
python3 /path/to/clauDNA/scripts/validate-skills.py
```

Expected: `OK: N skills validated, no violations` (orchestration-guide.md is in `_shared/`, which the validator only lint-checks for stale paths — should still pass).

- [ ] **Step 5: Commit**

```bash
cd /path/to/clauDNA
git add skills/_shared/orchestration-guide.md
git commit -m "$(cat <<'EOF'
docs: extend orchestration-guide §10 with Tier-3 sub-section

Adds a sub-section to the Autonomous Mode contract covering implementation
skills (Tier 3). Differentiates from planning-skill --auto: produces a PR,
never merges, requires explicit work item, replaces interactive challenge
rounds with trust or machine synthesis. Updates the compatibility matrix
to list /implement-plan, /weigh-development-paths, and /adversarial-review.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 3: Add §10.C structured result shape to orchestration-guide

**Files:**
- Modify: `skills/_shared/orchestration-guide.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/_shared/orchestration-guide.md:323-371` — "### Structured Result Shape" sub-section present with the exact JSON schema, field rules, outcome-semantics table, and emission rules specified here. This is the shape still referenced as canonical by `skills/_shared/contracts/synthesis-contract.md` ("General structured-result shape: `skills/_shared/orchestration-guide.md` §10.C") and by newer skills built after this plan shipped (`/claudna:forge`, `/claudna:ironclad --auto`). Shipped in PR #85 (2026-05-17).

- [ ] **Step 1: Append the structured-result shape sub-section**

Find this heading line:

```
### Skills that support `--auto`
```

Insert a new sub-section *before* it. Use Edit with the `old_string`:

```
### Skills that support `--auto`
```

And the `new_string`:

````
### Structured Result Shape

Every `--auto` run emits a single fenced JSON block as its final output (the last content before the run ends). The orchestrator (e.g., claudlobby's `autonomous-runner` skill) parses this block. Skills must NOT print anything after it.

```json
{
  "skill": "<skill name, e.g. 'implement-plan'>",
  "outcome": "completed | bypassed | needs-input | blocked | partial",
  "artifacts": {
    "issues_created": ["https://github.com/org/repo/issues/123"],
    "pr_url": "https://github.com/org/repo/pull/456",
    "files_changed": 3,
    "lines_added": 47,
    "lines_removed": 12,
    "branch": "implement/some-slug"
  },
  "summary": "<2-4 line human-readable summary for Telegram report-back>",
  "next": "<orchestrator hint for what to schedule next, or null>",
  "errors": [],
  "blocker_description": null
}
```

#### Field rules

- `skill` (required): the skill's name as it appears in frontmatter.
- `outcome` (required): exactly one of the five values listed. Skills MUST NOT invent new outcome strings.
- `artifacts` (required): an object. Keys are skill-dependent — planning skills include `issues_created`; implementation skills include `pr_url`. Both are optional fields within `artifacts`. Skills SHOULD include `files_changed`, `lines_added`, `lines_removed`, `branch` when they touch code.
- `summary` (required): 2-4 lines of plain text. No markdown. For Telegram report-back.
- `next` (optional, may be null): a one-sentence hint for the orchestrator.
- `errors` (required, may be empty): array of strings describing non-fatal issues encountered during the run.
- `blocker_description` (required when outcome is `blocked` or `needs-input`, null otherwise): one or two sentences explaining what blocks the work and what would unblock it.

#### Outcome semantics

| Outcome | Meaning | Retry safe? |
|---|---|---|
| `completed` | Work landed; PR or issues exist as expected. | n/a (don't retry) |
| `bypassed` | Explicit decision not to work this item (heavy-refactor tripwire, scope-exceeded). | No — needs policy change |
| `needs-input` | Cannot proceed without a human decision (ambiguous design, conflicting plans). A comment was posted on the source. | No — needs human action first |
| `blocked` | Attempted work but couldn't complete due to environment failure or unresolved internal contradiction. | Yes in principle, but treat as suspect until investigated |
| `partial` | Some progress made, but not the full outcome. | Yes — followup needed |

#### Emission rules

- The JSON block MUST be the final output of the `--auto` run. No text after.
- The JSON block MUST be valid (parseable by `json.loads`).
- The block MUST be fenced with ```` ```json ```` (the language hint matters — orchestrators key off it).
- The skill SHOULD log the block to stdout, not to a side-channel.

#### Reference: minimal emission template

For a skill body adding `--auto` support, this is the minimal template for the final emission step (substitute the skill's name and outcome computation):

````markdown
Emit the structured result block as the final output of the run:

```json
{
  "skill": "tech-debt",
  "outcome": "completed",
  "artifacts": {
    "issues_created": ["..."],
    "files_changed": 0
  },
  "summary": "...",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```
````

### Skills that support `--auto`
````

- [ ] **Step 2: Verify the edit**

Run:

```bash
grep -n "Structured Result Shape" /path/to/clauDNA/skills/_shared/orchestration-guide.md
```

Expected: one match showing the new heading.

Run:

```bash
python3 /path/to/clauDNA/scripts/validate-skills.py
```

Expected: no violations.

- [ ] **Step 3: Commit**

```bash
cd /path/to/clauDNA
git add skills/_shared/orchestration-guide.md
git commit -m "$(cat <<'EOF'
docs: define structured-result shape in orchestration-guide §10.C

Every --auto skill now emits a fenced JSON block as its final output with
a uniform shape: skill, outcome, artifacts, summary, next, errors,
blocker_description. Defines outcome semantics (completed, bypassed,
needs-input, blocked, partial) and emission rules. Orchestrators parse
this single contract regardless of which skill ran.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 4: Update `/claudna:adversarial-review` for non-interactive `--dispatch`

**Files:**
- Modify: `skills/adversarial-review/SKILL.md`

**Goal:** When `--dispatch` is set, the skill MUST suppress Plan Mode entry, suppress AskUserQuestion calls, and emit the structured-result shape with critique findings. Without `--dispatch`, current interactive behavior is preserved.

> **Status: ✅ COMPLETE but superseded (output shape changed).** The non-interactive-suppression half of this task is intact and unchanged: `skills/adversarial-review/SKILL.md:24-35` ("## --dispatch (non-interactive) mode") still says "Do NOT call `EnterPlanMode`" / "Do NOT call `AskUserQuestion`" / exit `outcome: blocked` on ambiguity, verbatim to what this task specified. **But the structured-result format it emits has changed.** As shipped here (PR #85), `--dispatch` emitted the §10.C JSON block with `artifacts.findings`. PR #130 (2026-06-02, "adversarial-review --dispatch emits markdown with frontmatter") replaced that with a markdown+YAML-frontmatter document per `skills/_shared/contracts/lens-result-contract.md` (see `skills/adversarial-review/SKILL.md:343-351`, "## Structured Result Emission (`--dispatch` only)") — built so `/claudna:ironclad` can aggregate findings from multiple lens skills in one pass. `CHANGELOG.md` documents this as a deliberate, scoped change: "The generic `--auto` JSON shape in orchestration-guide.md §10.C is unchanged." Net: the *behavioral* contract (non-interactive, structured, no user gates) this task wanted is fully honored; the *wire format* is not what this plan specifies — superseded by a richer consumer-specific contract that didn't exist yet in May.

- [ ] **Step 1: Update the Arguments section to clarify `--dispatch` semantics**

Find this text in `skills/adversarial-review/SKILL.md`:

```
- `--dispatch`: Multi-reviewer mode — spawn parallel subagents with different review angles (see Phase 3). Without this flag, perform a single consolidated review.
```

Replace with:

```
- `--dispatch`: Multi-reviewer mode AND non-interactive mode. Spawns parallel subagents with different review angles AND suppresses all interactive elements (no Plan Mode, no AskUserQuestion). Returns the structured-result shape from §10.C of `skills/_shared/orchestration-guide.md` with critique findings in `artifacts.findings`. Use this mode when invoking adversarial-review from another skill or from an orchestrator. Without this flag, perform a single consolidated review interactively.
```

- [ ] **Step 2: Add a non-interactive-mode preamble to the procedure**

Find the heading `## Phase 1: Understand the Plan` (the first procedural phase). Insert a new sub-section *immediately before* it, using Edit with the `old_string`:

```
## Phase 1: Understand the Plan
```

And the `new_string`:

```
## --dispatch (non-interactive) mode

When `--dispatch` is passed (typically when invoked as a subagent from another skill or an orchestrator):

- **Do NOT call `EnterPlanMode`.** The caller has its own Plan Mode lifecycle.
- **Do NOT call `AskUserQuestion`.** The caller is not a human; questions cannot be answered.
- **Do NOT prompt for clarification.** If the plan is too ambiguous to review, exit `outcome: blocked` with a populated `blocker_description`.
- Spawn parallel critic subagents per Phase 3.
- Aggregate critic findings into the structured-result shape.
- Emit the structured-result JSON block as the final output and stop.

When `--dispatch` is NOT passed, follow the full interactive procedure below (Plan Mode, single consolidated review, user-facing presentation).

## Phase 1: Understand the Plan
```

- [ ] **Step 3: Add a "Structured Result Emission" section at the end of the procedure**

Find the last heading of the procedure (likely "Phase 3" or "Output"). Append a new section at the very end of the procedure (before any trailing notes). Use Edit with the `old_string` being the file's final non-trailing line + one line of trailing context, and `new_string` adding the new section before that trailing line.

The section to add:

````markdown

---

## Structured Result Emission (`--dispatch` only)

After Phase 3 aggregation, emit a single fenced JSON block as the FINAL output. No text after this block. Format per `skills/_shared/orchestration-guide.md` §10.C:

```json
{
  "skill": "adversarial-review",
  "outcome": "completed",
  "artifacts": {
    "findings_count": 5,
    "findings": [
      {
        "concern_area": "error-handling",
        "severity": "high",
        "summary": "Plan doesn't account for the 429 retry case in the upstream API.",
        "recommendation": "Add explicit retry-with-backoff to Step 4."
      }
    ],
    "plan_path": "<path or issue URL that was reviewed>"
  },
  "summary": "<2-3 line digest of findings>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

If review cannot proceed (e.g., plan body is empty or unreadable), emit `outcome: blocked` with `blocker_description` explaining what would unblock it (e.g., "plan body lacks an Implementation Plan section; run a planning skill to populate it first").

`concern_area` values should align with the matrix categories in `skills/implement-plan/challenge-round-questions.md` where possible (architecture, testing, dependencies, error-handling, etc.) so downstream skills can fold findings into the challenge round.
````

- [ ] **Step 4: Verify the edit**

Run:

```bash
grep -n "## --dispatch" /path/to/clauDNA/skills/adversarial-review/SKILL.md
grep -n "Structured Result Emission" /path/to/clauDNA/skills/adversarial-review/SKILL.md
```

Expected: both grep commands return one match each.

Run:

```bash
python3 /path/to/clauDNA/scripts/validate-skills.py
```

Expected: no violations.

- [ ] **Step 5: Commit**

```bash
cd /path/to/clauDNA
git add skills/adversarial-review/SKILL.md
git commit -m "$(cat <<'EOF'
feat(adversarial-review): make --dispatch non-interactive and emit structured result

--dispatch now suppresses Plan Mode and AskUserQuestion calls and emits
the §10.C structured-result shape with findings in artifacts.findings.
Plain (no --dispatch) interactive behavior preserved.

Enables chaining adversarial-review from planning skills and from
/implement-plan --auto without per-skill prompt customization.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 5: Add `--auto` mode to `/claudna:weigh-development-paths`

**Files:**
- Modify: `skills/weigh-development-paths/SKILL.md`

**Goal:** Add a new `--auto` argument that takes a context bundle (open findings + matrix concerns + plan + codebase artifacts) and returns a refined plan via the structured-result shape. Suppresses Plan Mode and AskUserQuestion. Interactive mode unchanged.

> **Status: ✅ COMPLETE.** Verified live at `skills/weigh-development-paths/SKILL.md:14-20` (Arguments) and `:123-198` ("## Autonomous Mode (`--auto`)" — input contract, procedure, output). Still emits the exact JSON shape this plan specifies (`refined_plan_path`, `refined_plan`, `decisions_resolved`, `decisions_unresolved`, `synthesis_rationales`). PR #132 (2026-06-02) extracted this shape into a standalone canonical file, `skills/_shared/contracts/synthesis-contract.md`, which this SKILL.md now points to as the source of truth (line 163) — a refactor, not a behavior change; the schema is unchanged. Consumed by `/claudna:implement-plan --auto` Step 3-AUTO per that contract.

- [ ] **Step 1: Update the frontmatter argument-hint**

Find the YAML frontmatter at the top of the file. Locate the `argument-hint` field. Update it to include `--auto`:

Find this line (or equivalent — match what's actually there):

```yaml
argument-hint: "[junction-description]"
```

If no `argument-hint` exists, add it after `description:`. Replace/add:

```yaml
argument-hint: "[--auto] [junction-description-or-bundle-path]"
```

- [ ] **Step 2: Add an Arguments section if one doesn't exist; otherwise extend it**

Find the heading `## When to Use` (or the first procedural heading). If there is no `## Arguments` section before it, insert one. If there is, extend it with the `--auto` description.

The Arguments section content to insert (or merge):

````markdown
## Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Non-interactive synthesis mode. Suppresses Plan Mode and AskUserQuestion. Requires a context bundle path or inline bundle in `$ARGUMENTS`. Emits the structured-result shape from `skills/_shared/orchestration-guide.md` §10.C with a refined plan in `artifacts.refined_plan`. See "Autonomous Mode" section below.
- Remaining text: the junction description (interactive mode) or path to a context bundle file (--auto mode).

````

- [ ] **Step 3: Add an "Autonomous Mode (--auto)" section at the end of the procedure**

Append at the end of the file (after the last existing section, before any trailing notes if present):

````markdown

---

## Autonomous Mode (`--auto`)

When `--auto` is set, this skill operates as a non-interactive synthesis engine called from another skill (typically `/claudna:implement-plan --auto` per design §5.5.2) or directly from an orchestrator.

### Input contract

`$ARGUMENTS` after the `--auto` flag MUST contain a path to a context bundle file OR the bundle content inline. The bundle is a markdown document with these sections:

```markdown
## Plan
<the plan body being refined>

## Open Adversarial Findings
- [<concern_area>][<severity>] <finding summary> — <recommendation>
- ...

## Open Matrix Decisions
- [<category>] <question> — Options: A) ..., B) ..., C) ...
- ...

## Codebase Comparison Artifacts (optional)
<file paths, function names, dependency notes from Step 2 of implement-plan>
```

### Procedure

When `--auto` is active:

1. **Do NOT call `EnterPlanMode`.** The caller manages mode.
2. **Do NOT call `AskUserQuestion`.** Synthesize machine recommendations directly.
3. Parse the bundle.
4. For each open finding AND each open matrix decision, treat it as a junction:
   - Generate candidate options (from the bundle when provided; synthesize otherwise).
   - Run the 7-dimensional analysis from the interactive procedure (do not skip dimensions).
   - Synthesize a recommendation. Capture a "Synthesis Rationale" stating which dimensions drove the choice.
5. Assemble a refined plan: take the original plan body and replace/augment each ambiguous section with the synthesis result. Mark each formerly-open item as RESOLVED with the rationale inline.
6. If any decision genuinely cannot be resolved without human input (insufficient evidence in any dimension), do NOT guess. List it as unresolved and exit `outcome: blocked` with that list in `blocker_description`.

### Output (structured result)

Emit a single fenced JSON block as the FINAL output. Format:

```json
{
  "skill": "weigh-development-paths",
  "outcome": "completed",
  "artifacts": {
    "refined_plan_path": "<path written to disk, or null if inline only>",
    "refined_plan": "<full markdown body of the refined plan>",
    "decisions_resolved": 5,
    "decisions_unresolved": 0,
    "synthesis_rationales": [
      {
        "decision": "<original open question or finding>",
        "chosen_option": "<the synthesized choice>",
        "dimensions": ["<dim that drove it>", "..."]
      }
    ]
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

If outcome is `blocked`, `decisions_unresolved` > 0 and `blocker_description` lists the unresolvable decisions.

### Restrictions in `--auto` mode

- Do NOT write to the original plan file unless explicitly given a write path in the bundle.
- Do NOT open Plan Mode.
- Do NOT ask questions.
- Do NOT print anything after the JSON block.
````

- [ ] **Step 4: Verify the edit**

Run:

```bash
grep -n "## Autonomous Mode" /path/to/clauDNA/skills/weigh-development-paths/SKILL.md
grep -n "argument-hint" /path/to/clauDNA/skills/weigh-development-paths/SKILL.md
```

Expected: each returns at least one match.

Run:

```bash
python3 /path/to/clauDNA/scripts/validate-skills.py
```

Expected: no violations.

- [ ] **Step 5: Commit**

```bash
cd /path/to/clauDNA
git add skills/weigh-development-paths/SKILL.md
git commit -m "$(cat <<'EOF'
feat(weigh-development-paths): add --auto synthesis mode

Adds a non-interactive --auto mode that accepts a context bundle (plan +
open adversarial findings + open matrix decisions + codebase artifacts)
and synthesizes a refined plan by running the 7-dimensional analysis on
each open question. Emits the §10.C structured-result shape with the
refined plan and per-decision synthesis rationales.

Required by /implement-plan --auto Step 3 synthesis pass (design §5.5.2).

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 6: Add structured-result emission to `tech-debt`

**Files:**
- Modify: `skills/tech-debt/SKILL.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/tech-debt/SKILL.md:236-262` — "## Autonomous Mode (--auto)" section step 6 emits the §10.C JSON block verbatim as specified. Unchanged through Phase 2 (#86), the `/claudna:publish` routing consolidation (#115), and the recent description-grammar pass (#165, 2026-07-05) that touched this file's frontmatter but not this section.

- [ ] **Step 1: Append a structured-result emission step to the Autonomous Mode section**

Find the existing section heading:

```
## Autonomous Mode (--auto)
```

The current Autonomous Mode section ends with this bullet (or equivalent):

```
6. Return structured summary for audit tracking
```

Replace that closing bullet with the explicit emission instruction. Use Edit with `old_string`:

```
6. Return structured summary for audit tracking
```

And `new_string`:

````
6. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "tech-debt",
  "outcome": "completed",
  "artifacts": {
    "issues_created": ["https://github.com/org/repo/issues/123", "..."],
    "session_dir": "documentation/planning/tech_debt/<session>/",
    "files_changed": 0
  },
  "summary": "<2-3 line digest of N findings, M issues filed>",
  "next": "<follow-up hint or null>",
  "errors": [],
  "blocker_description": null
}
```

- `outcome` should be `completed` on a successful run, `partial` if some issues failed to create (gh CLI errors), `blocked` if the scan couldn't run (e.g., no git repo).
- `next` may suggest follow-up like `"Apply /claudna:implement-plan --source github <#> --auto to highest-severity issue"`.
````

- [ ] **Step 2: Verify the edit**

Run:

```bash
grep -n "Emit the structured-result shape" /path/to/clauDNA/skills/tech-debt/SKILL.md
```

Expected: one match.

Run:

```bash
python3 /path/to/clauDNA/scripts/validate-skills.py
```

Expected: no violations.

- [ ] **Step 3: Commit**

```bash
cd /path/to/clauDNA
git add skills/tech-debt/SKILL.md
git commit -m "feat(tech-debt): emit §10.C structured result in --auto mode"
```

---

## Task 7: Add structured-result emission to `security-audit`

**Files:**
- Modify: `skills/security-audit/SKILL.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/security-audit/SKILL.md:184-212` — emission step 8 present with the §10.C shape (`findings_by_severity`, masked-secrets rule preserved). Unchanged since PR #85.

- [ ] **Step 1: Append emission step to the Autonomous Mode section**

Find the existing closing bullet of the Autonomous Mode section in `skills/security-audit/SKILL.md`. It currently reads:

```
7. **Security-specific:** Never include actual secret values in issue bodies. Mask as `sk-****`.
```

Use Edit. The `old_string`:

```
7. **Security-specific:** Never include actual secret values in issue bodies. Mask as `sk-****`.
```

The `new_string`:

````
7. **Security-specific:** Never include actual secret values in issue bodies. Mask as `sk-****`.
8. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "security-audit",
  "outcome": "completed",
  "artifacts": {
    "issues_created": ["https://github.com/org/repo/issues/123", "..."],
    "findings_by_severity": {"critical": 0, "high": 2, "medium": 5, "low": 3},
    "session_dir": "documentation/planning/security/<session>/"
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `partial` if some issue creates failed, `blocked` if the scan couldn't run.
- Secret values MUST remain masked in `summary` and all artifact fields.
````

- [ ] **Step 2: Verify the edit and commit**

Run:

```bash
grep -n "Emit the structured-result shape" /path/to/clauDNA/skills/security-audit/SKILL.md
python3 /path/to/clauDNA/scripts/validate-skills.py
```

Expected: one grep match, validator passes.

```bash
cd /path/to/clauDNA
git add skills/security-audit/SKILL.md
git commit -m "feat(security-audit): emit §10.C structured result in --auto mode"
```

---

## Task 8: Add structured-result emission to `product-enhance`

**Files:**
- Modify: `skills/product-enhance/SKILL.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/product-enhance/SKILL.md:163-188` — emission step 5 present with the §10.C shape (`proposals_ranked`, etc.). Unchanged since PR #85.

- [ ] **Step 1: Append emission step**

Find the closing bullet of the Autonomous Mode section in `skills/product-enhance/SKILL.md`. It currently reads:

```
5. Return structured summary for audit tracking
```

Use Edit with `old_string`:

```
5. Return structured summary for audit tracking
```

`new_string`:

````
5. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "product-enhance",
  "outcome": "completed",
  "artifacts": {
    "issues_created": ["https://github.com/org/repo/issues/123", "..."],
    "proposals_ranked": 8,
    "session_dir": "documentation/planning/phases/<session>/"
  },
  "summary": "<2-3 line digest of proposals filed>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `blocked` if codebase reconnaissance can't run.
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Emit the structured-result shape" /path/to/clauDNA/skills/product-enhance/SKILL.md
python3 /path/to/clauDNA/scripts/validate-skills.py
```

```bash
cd /path/to/clauDNA
git add skills/product-enhance/SKILL.md
git commit -m "feat(product-enhance): emit §10.C structured result in --auto mode"
```

---

## Task 9: Add structured-result emission to `frontend-performance-audit`

**Files:**
- Modify: `skills/frontend-performance-audit/SKILL.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/frontend-performance-audit/SKILL.md:126-152` — emission step 5 present with the §10.C shape (`cascade_chains_found`, `page_audited`). Unchanged since PR #85.

- [ ] **Step 1: Append emission step**

Find the closing bullet in the Autonomous Mode section. It currently reads:

```
5. Return structured summary for audit tracking
```

Use Edit. `old_string`:

```
5. Return structured summary for audit tracking
```

`new_string`:

````
5. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "frontend-performance-audit",
  "outcome": "completed",
  "artifacts": {
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

- `outcome` is `completed` on success, `blocked` if the page/flow wasn't provided (this skill cannot auto-detect; see existing rule #2 in Autonomous Mode).
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Emit the structured-result shape" /path/to/clauDNA/skills/frontend-performance-audit/SKILL.md
python3 /path/to/clauDNA/scripts/validate-skills.py
```

```bash
cd /path/to/clauDNA
git add skills/frontend-performance-audit/SKILL.md
git commit -m "feat(frontend-performance-audit): emit §10.C structured result in --auto mode"
```

---

## Task 10: Add structured-result emission to `docs-review`

**Files:**
- Modify: `skills/docs-review/SKILL.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/docs-review/SKILL.md:197-231` — emission step 7 present with the dual-artifact shape this task calls for (`auto_fixes_committed` + `gaps_filed_as_issues`). A separate reference to §10.C at line 142 shows Phase 2's adversarial-review chain (added later, #86) folds its summary into the same structured result — the two phases composed cleanly. Unchanged since.

- [ ] **Step 1: Append emission step**

`docs-review --auto` is unique: it both auto-fixes inline AND files issues for gaps. The artifacts must reflect both.

Find the closing bullet of the Autonomous Mode section:

```
7. Return structured summary for audit tracking
```

Use Edit. `old_string`:

```
7. Return structured summary for audit tracking
```

`new_string`:

````
7. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "docs-review",
  "outcome": "completed",
  "artifacts": {
    "issues_created": ["https://github.com/org/repo/issues/789", "..."],
    "files_changed": 3,
    "lines_added": 12,
    "lines_removed": 5,
    "branch": "<branch if commits were pushed, or null>",
    "auto_fixes_committed": ["docs/architecture.md", "README.md"],
    "gaps_filed_as_issues": 2,
    "plans_archived": 1
  },
  "summary": "<2-3 line digest of fixes and gaps>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- Inline auto-fixes are reflected in `files_changed`, `lines_added`, `lines_removed`, `auto_fixes_committed`.
- Gaps that needed human judgment are reflected in `issues_created` and `gaps_filed_as_issues`.
- `outcome` is `completed` on full success; `partial` if some auto-fixes were attempted but failed (record in `errors`).
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Emit the structured-result shape" /path/to/clauDNA/skills/docs-review/SKILL.md
python3 /path/to/clauDNA/scripts/validate-skills.py
```

```bash
cd /path/to/clauDNA
git add skills/docs-review/SKILL.md
git commit -m "feat(docs-review): emit §10.C structured result in --auto mode"
```

---

## Task 11: Add structured-result emission to `access-path-audit`

**Files:**
- Modify: `skills/access-path-audit/SKILL.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/access-path-audit/SKILL.md:295-322` — emission step 6 present with the §10.C shape (`findings_by_category`, `paths_analyzed`). Unchanged since PR #85.

- [ ] **Step 1: Append emission step**

Find the closing bullet of the Autonomous Mode section:

```
6. Return structured summary for audit tracking
```

Use Edit. `old_string`:

```
6. Return structured summary for audit tracking
```

`new_string`:

````
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
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Emit the structured-result shape" /path/to/clauDNA/skills/access-path-audit/SKILL.md
python3 /path/to/clauDNA/scripts/validate-skills.py
```

```bash
cd /path/to/clauDNA
git add skills/access-path-audit/SKILL.md
git commit -m "feat(access-path-audit): emit §10.C structured result in --auto mode"
```

---

## Task 12: Add structured-result emission to `product-vision`

**Files:**
- Modify: `skills/product-vision/SKILL.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/product-vision/SKILL.md:165-196` — emission step 7 present with the §10.C shape (`compound_plays_identified`, `mission_proposed`). Unchanged since PR #85.

- [ ] **Step 1: Append emission step**

Find the closing bullet of the Autonomous Mode section:

```
7. Return structured summary for tracking
```

Use Edit. `old_string`:

```
7. Return structured summary for tracking
```

`new_string`:

````
7. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "product-vision",
  "outcome": "completed",
  "artifacts": {
    "issues_created": ["..."],
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

- `mission_proposed` is `true` when no PROJECT_MISSION.md existed and one was synthesized; the proposed text remains in chat per existing rule (not written to disk in --auto).
- `outcome` is `completed` on success.
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Emit the structured-result shape" /path/to/clauDNA/skills/product-vision/SKILL.md
python3 /path/to/clauDNA/scripts/validate-skills.py
```

```bash
cd /path/to/clauDNA
git add skills/product-vision/SKILL.md
git commit -m "feat(product-vision): emit §10.C structured result in --auto mode"
```

---

## Task 13: Add structured-result emission to `session-handoff`

**Files:**
- Modify: `skills/session-handoff/SKILL.md`

**Note:** `session-handoff` doesn't have a single "Autonomous Mode" section — its `--auto` behavior is woven throughout. Add a new closing section.

> **Status: ✅ COMPLETE, later re-homed by a redesign.** Shipped as its own closing section in PR #85. PR #88 (2026-05-18, "Redesign /session-handoff + /session-resume: per-cwd, reaper-driven") restructured the whole skill into numbered steps; the emission logic now lives at `skills/session-handoff/SKILL.md:98-119` as "### 10. Structured-result emission (`--auto` only)" — same §10.C JSON shape (`handoff_path`, `items_reaped`, `items_added`), just moved to fit the new step-based procedure. Explicitly called out as consumed by `/restart`'s pre-stop check to confirm the handoff landed.

- [ ] **Step 1: Append a Structured Result section at the end of the procedure**

Find the closing section of the file. It currently ends with the "Rules" section. Use Edit. `old_string`:

```
- **Handoff file is ephemeral.** Not a log. Overwritten each session.
```

`new_string`:

````
- **Handoff file is ephemeral.** Not a log. Overwritten each session.

---

## Structured Result Emission (`--auto` only)

When `--auto` is set, emit the structured-result shape per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "session-handoff",
  "outcome": "completed",
  "artifacts": {
    "handoff_path": "~/.claude/notes/projects/<slug>/claudna:context-resume.md",
    "memories_pruned": 2,
    "memories_updated": 1,
    "learnings_saved": 3,
    "changelog_entries_added": 0,
    "plans_archived": 0
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success; `partial` if any step failed (record in `errors`).
- `handoff_path` is required (it's the skill's primary artifact).

Interactive mode (no `--auto`) does NOT emit the JSON block — it presents human-readable confirmation messages as today.
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Structured Result Emission" /path/to/clauDNA/skills/session-handoff/SKILL.md
python3 /path/to/clauDNA/scripts/validate-skills.py
```

```bash
cd /path/to/clauDNA
git add skills/session-handoff/SKILL.md
git commit -m "feat(session-handoff): emit §10.C structured result in --auto mode"
```

---

## Task 14: Add structured-result emission to `visual-crawl`

**Files:**
- Modify: `skills/visual-crawl/SKILL.md`

> **Status: ✅ COMPLETE.** Verified live at `skills/visual-crawl/SKILL.md:489-520` — emission step 6 present with the §10.C shape (`routes_crawled`, `design_token_violations`, etc.). Unchanged since PR #85.

- [ ] **Step 1: Append emission step to the Autonomous Mode section**

Find the closing bullet of the Autonomous Mode section in `skills/visual-crawl/SKILL.md`:

```
6. Return structured summary for tracking
```

Use Edit. `old_string`:

```
6. Return structured summary for tracking
```

`new_string`:

````
6. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "visual-crawl",
  "outcome": "completed",
  "artifacts": {
    "issues_created": ["..."],
    "routes_crawled": 12,
    "screenshots_taken": 36,
    "console_errors": 3,
    "dead_links": 1,
    "interaction_failures": 0,
    "design_token_violations": 5,
    "scratch_dir": "/tmp/visual-crawl-<timestamp>/"
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `blocked` if base URL is unreachable or no routes were discovered.
- `--deep` mode produces additional artifacts; if --deep was used, add `deep_findings: N` to artifacts.
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Emit the structured-result shape" /path/to/clauDNA/skills/visual-crawl/SKILL.md
python3 /path/to/clauDNA/scripts/validate-skills.py
```

```bash
cd /path/to/clauDNA
git add skills/visual-crawl/SKILL.md
git commit -m "feat(visual-crawl): emit §10.C structured result in --auto mode"
```

---

## Task 15 (Optional): Extend `validate-skills.py` with a structured-result check

**Files:**
- Modify: `scripts/validate-skills.py` (and possibly `scripts/skill_checks.py`)
- Test: `scripts/test_skill_checks.py` (create if it doesn't exist)

This task is OPTIONAL but recommended. It prevents future skills from claiming `--auto` support without emitting the structured result shape.

> **Status: ✅ COMPLETE (the optional task was done, not skipped).** `check_structured_result_emission()` lives at `scripts/skill_checks.py:254-274`, wired as a hard-error check into `validate_skill_md` (`scripts/skill_checks.py:509`), alongside the two pre-existing behavioral checks (`check_output_github_reference`, `check_auto_no_ask_user`). `scripts/test_skill_checks.py` has unit tests for it. Confirmed live during this audit: `python3 scripts/validate-skills.py` reports "OK: 61 skills validated, no blocking violations" — the check runs clean against all 9 normalized skills plus every skill added since (including `/claudna:forge`, `/claudna:ironclad`).

- [ ] **Step 1: Inspect the existing `skill_checks` module**

Run:

```bash
ls /path/to/clauDNA/scripts/
cat /path/to/clauDNA/scripts/skill_checks.py | head -100
```

Note the existing check functions and the conventions for adding a new check.

- [ ] **Step 2: Write a failing test**

Create or extend `scripts/test_skill_checks.py`:

```python
"""Test the structured-result emission check."""
import pytest
from pathlib import Path
from skill_checks import has_auto_arg, has_structured_result_emission


def test_skill_with_auto_must_have_structured_result(tmp_path):
    """A skill that documents --auto in argument-hint must mention structured-result emission."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("""---
name: test-skill
description: Test
argument-hint: "[--auto]"
---

# Test Skill

## Autonomous Mode (--auto)

Skip Plan Mode and do things.
""")
    assert has_auto_arg(skill_md) is True
    assert has_structured_result_emission(skill_md) is False


def test_skill_without_auto_doesnt_require_structured_result(tmp_path):
    """A skill that doesn't claim --auto support doesn't need to emit structured result."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("""---
name: test-skill
description: Test
argument-hint: "[scope-path]"
---

# Test Skill
""")
    assert has_auto_arg(skill_md) is False


def test_skill_with_auto_and_emission_passes(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("""---
name: test-skill
description: Test
argument-hint: "[--auto]"
---

# Test Skill

## Autonomous Mode (--auto)

Skip stuff.

Emit the structured-result shape per skills/_shared/orchestration-guide.md §10.C.
""")
    assert has_auto_arg(skill_md) is True
    assert has_structured_result_emission(skill_md) is True
```

Run the tests:

```bash
cd /path/to/clauDNA
python3 -m pytest scripts/test_skill_checks.py -v
```

Expected: import failure or test failures because `has_auto_arg` and `has_structured_result_emission` don't exist yet. This is the failing test (RED).

- [ ] **Step 3: Implement the checks in `skill_checks.py`**

Add these functions to `scripts/skill_checks.py` (location: after the existing parse_frontmatter or similar utility):

```python
import re

_AUTO_ARG_PATTERNS = [
    re.compile(r"argument-hint:.*--auto", re.IGNORECASE),
    re.compile(r"^\s*-\s*`--auto`", re.MULTILINE),
]

_STRUCTURED_RESULT_PATTERN = re.compile(
    r"structured.{0,10}result|orchestration-guide.{0,30}§10\.C",
    re.IGNORECASE,
)


def has_auto_arg(skill_md_path) -> bool:
    """True if the SKILL.md declares --auto support (in frontmatter argument-hint or Arguments section)."""
    if not skill_md_path.is_file():
        return False
    text = skill_md_path.read_text()
    return any(p.search(text) for p in _AUTO_ARG_PATTERNS)


def has_structured_result_emission(skill_md_path) -> bool:
    """True if the SKILL.md mentions emitting the structured-result shape."""
    if not skill_md_path.is_file():
        return False
    text = skill_md_path.read_text()
    return bool(_STRUCTURED_RESULT_PATTERN.search(text))
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd /path/to/clauDNA
python3 -m pytest scripts/test_skill_checks.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Wire the new check into the validator**

Edit `scripts/validate-skills.py` to incorporate the check. Find this block (or equivalent):

```python
errors = validate_skill(skill_dir)
```

Below it, add a structured-result check:

```python
        # Phase 1 contract: skills declaring --auto must emit structured result
        if has_auto_arg(skill_md):
            if not has_structured_result_emission(skill_md):
                errors.append(
                    "declares --auto support but does not mention structured-result emission "
                    "(see skills/_shared/orchestration-guide.md §10.C)"
                )
```

And add to the imports at the top:

```python
from skill_checks import (
    STALE_PATH_RE,
    has_auto_arg,
    has_structured_result_emission,
    parse_frontmatter,
    validate_skill_md,
    warn_skill_md,
)
```

- [ ] **Step 6: Run the full validator against the repo**

```bash
cd /path/to/clauDNA
python3 scripts/validate-skills.py
```

Expected: all 9 `--auto` skills pass (because Tasks 6-14 added the emission). If any fail, return to the corresponding task and fix.

- [ ] **Step 7: Commit**

```bash
cd /path/to/clauDNA
git add scripts/validate-skills.py scripts/skill_checks.py scripts/test_skill_checks.py
git commit -m "$(cat <<'EOF'
test: add validator check for structured-result emission

Skills declaring --auto support must mention emitting the §10.C
structured-result shape. Includes unit tests for the new check
functions in skill_checks.py.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 16: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

> **Status: ✅ COMPLETE.** Entry landed and has since aged out of "Unreleased" into a dated release: `CHANGELOG.md` §`[0.4.0] - 2026-05-18` (around lines 94-99, 109-110): "Autonomous-mode contract — Phase 1 of the autonomous-mode-and-orchestration rollout... Claudfather/clauDNA#82." More detailed than the plan's minimal template — documents every sub-change with file references, including the later Phase 3 entry immediately below it in the same release.

- [ ] **Step 1: Add an Unreleased entry**

Find the existing `## [Unreleased]` section (or add one at the top under the title if missing). Add a bulleted entry summarizing Phase 1:

```markdown
### Added
- Autonomous-mode contract extended in `skills/_shared/orchestration-guide.md`:
  - New Tier-3 (implementation skill) sub-section in §10
  - Standardized structured-result shape (§10.C) emitted by every `--auto` run
- `/claudna:adversarial-review`: `--dispatch` now implies non-interactive mode (suppresses Plan Mode and AskUserQuestion) and emits the structured-result shape with critique findings
- `/claudna:weigh-development-paths`: new `--auto` synthesis mode for chained use from other skills
- Structured-result emission added to all 9 existing `--auto` skills: tech-debt, security-audit, product-enhance, frontend-performance-audit, docs-review, access-path-audit, product-vision, session-handoff, visual-crawl
- `scripts/validate-skills.py`: new check that skills declaring `--auto` support must emit the structured-result shape (optional; only if Task 15 was completed)
```

- [ ] **Step 2: Commit**

```bash
cd /path/to/clauDNA
git add CHANGELOG.md
git commit -m "docs(changelog): record Phase 1 autonomous-mode contract changes"
```

---

## Phase 1 Verification

After all tasks complete, run end-to-end verification.

> **Status: ✅ COMPLETE.** Re-ran this verification during this audit (2026-07-06): `python3 scripts/validate-skills.py` → "OK: 61 skills validated, no blocking violations." §10 of `orchestration-guide.md` confirmed intact top-to-bottom (Tier-3 sub-section, Structured Result Shape sub-section, compatibility matrix rows all present). The real PR that shipped this phase was literally titled "Phase 1: Autonomous-mode contract & structured result shape (#85)" — matching the title this plan's Step 5 script proposes almost exactly.

- [ ] **Step 1: Run the full validator**

```bash
cd /path/to/clauDNA
python3 scripts/validate-skills.py
```

Expected: `OK: N skills validated, no violations`.

- [ ] **Step 2: Manually inspect §10 of orchestration-guide.md**

Open `skills/_shared/orchestration-guide.md` and read §10 top-to-bottom. Confirm:
- Original §10 content is intact
- "For implementation skills (Tier 3)" sub-section appears before the compatibility matrix
- "Structured Result Shape" sub-section appears before the compatibility matrix
- Compatibility matrix now includes `/implement-plan`, `/weigh-development-paths`, `/adversarial-review`

- [ ] **Step 3: Smoke-test one updated skill (read-only)**

Pick `/claudna:tech-debt`. Open `skills/tech-debt/SKILL.md` and confirm:
- The Autonomous Mode section includes the structured-result emission step with a JSON example
- The JSON example mentions `outcome`, `artifacts`, `summary`, `next`, `errors`, `blocker_description`

Do the same spot-check for `/claudna:adversarial-review` (confirm `--dispatch` non-interactive section is present) and `/claudna:weigh-development-paths` (confirm Autonomous Mode section is present).

- [ ] **Step 4: Run the validator with the optional structured-result check if Task 15 was implemented**

```bash
cd /path/to/clauDNA
python3 scripts/validate-skills.py
```

Expected: still passes (all 9 skills emit the structured result now).

- [ ] **Step 5: Push for review**

```bash
cd /path/to/clauDNA
git push -u origin <branch-name>
gh pr create --title "Phase 1: Autonomous-mode contract & structured result shape" \
  --body "$(cat <<'EOF'
## Summary

Implements Phase 1 of the autonomous-mode-and-orchestration design (spec: `documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md`).

- Extends `orchestration-guide.md §10` with a Tier-3 (implementation skill) sub-section
- Defines the structured-result shape (§10.C) emitted by every `--auto` skill
- Adds `--dispatch` non-interactive mode to `/claudna:adversarial-review`
- Adds `--auto` synthesis mode to `/claudna:weigh-development-paths`
- Normalizes 9 existing `--auto` skills to emit the structured-result shape
- Adds validator check (if Task 15 done) preventing future skills from claiming `--auto` without emission

Downstream phases consume the contract: Phase 2 chains adversarial-review from planning skills; Phase 3 invokes weigh-development-paths from /implement-plan --auto; Phase 4's claudlobby wrapper parses the structured result.

## Test plan

- [ ] `python3 scripts/validate-skills.py` passes
- [ ] Manual read-through of `skills/_shared/orchestration-guide.md §10` confirms new sub-sections present
- [ ] Spot-check 2-3 of the 9 normalized skills to confirm emission step is present
- [ ] Confirm CHANGELOG.md updated

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Common Mistakes for this Phase

| Mistake | Fix |
|---|---|
| Editing skill files by line number — line numbers drift between commits | Anchor edits by unique heading text or full quoted prose using `old_string` |
| Forgetting to fence the JSON example with ```` ```json ```` | Orchestrators parse based on the language hint; always use `json` |
| Adding text after the JSON block in the Autonomous Mode section examples | The example shows what the skill emits; describing it elsewhere in the section is fine, but the actual emission must be the final output of the run |
| Trying to make `--auto` imply non-interactive across all skill types in §10's main rules | The Tier-3 sub-section is intentionally separate. The main §10 rules still describe planning-skill behavior |
| Mass find-and-replace across all 9 skill files | Each skill has a slightly different artifacts shape (because the skill does different things). Apply per-skill; don't homogenize |
| Skipping CHANGELOG.md | Every release requires a changelog entry per project convention |
| Running `--no-verify` if pre-commit fails | Fix the underlying issue; never skip hooks |

---

## What this phase does NOT do

These belong to later phases — do NOT do them here even if tempting:

- Adding adversarial-review chain to planning skills → Phase 2
- Adding /simplify Step 6.5 to /implement-plan → Phase 2
- Adding --auto to /implement-plan → Phase 3
- Building the claudlobby autonomous-runner skill → Phase 4

If any of those feel necessary to "complete" Phase 1, stop and re-read the design spec. Phase 1 is intentionally the contract layer only.
