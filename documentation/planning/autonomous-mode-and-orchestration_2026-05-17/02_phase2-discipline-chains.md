---
title: Phase 2 — clauDNA Discipline Chains
type: plan
status: draft
owner: chrisrogers37
created: 2026-05-17
tags: [autonomous-mode, phase-2, adversarial-review, simplify, discipline-chains]
repos: [clauDNA]
links: []
---

# Phase 2 Implementation Plan — clauDNA Discipline Chains

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chain `/claudna:adversarial-review` into the end of every clauDNA planning skill so generated plans arrive at downstream consumers already stress-tested. Add a `/simplify` quality pass to `/claudna:implement-plan` (Step 6.5). Revise `/implement-plan` interactive Step 3 so open adversarial findings seed the challenge round before the full matrix runs.

**Architecture:** A single shared subagent dispatch prompt template lives in `skills/_shared/subagent-prompts/adversarial-chain.md`. Each of 6 planning skills gets a new section (consistent shape across all 6) invoking that template against the generated plan docs. `/implement-plan` gets two new step descriptions (3A and 6.5). All changes are skill-body markdown — no code changes.

**Tech Stack:** Markdown only.

**Repo:** clauDNA (`/Users/chris/Projects/claudna`)

**Prerequisites:**
- Phase 1 must be merged. The structured-result shape and `/claudna:adversarial-review --dispatch` non-interactive mode are required.
- Read `documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md` §5.3, §5.4, §5.5.1.

---

## File Structure

| File | Action | Notes |
|---|---|---|
| `skills/_shared/subagent-prompts/adversarial-chain.md` | Create | Shared dispatch prompt template |
| `skills/_shared/subagent-prompts/simplify-chain.md` | Create | Shared dispatch prompt template for /simplify |
| `skills/tech-debt/SKILL.md` | Modify | Add adversarial-review pass after Phase 2 |
| `skills/security-audit/SKILL.md` | Modify | Same |
| `skills/product-enhance/SKILL.md` | Modify | Same — at end of Step 5 |
| `skills/frontend-performance-audit/SKILL.md` | Modify | Same — at end of Phase 4 |
| `skills/docs-review/SKILL.md` | Modify | Add adversarial pass at end of Step 5 (Gap Analysis) before applying changes |
| `skills/access-path-audit/SKILL.md` | Modify | Same |
| `skills/implement-plan/SKILL.md` | Modify | Revise Step 3 (3A/3B split); add Step 6.5 (simplification pass) |
| `skills/implement-plan/challenge-round-questions.md` | Modify (light) | Add a note that question categories align with adversarial-review concern-area labels |
| `CHANGELOG.md` | Modify | Phase 2 entry |

---

## Conventions

- Same as Phase 1: anchor by heading text, one task = one commit, run `python3 scripts/validate-skills.py` after each skill edit.
- Each planning skill's adversarial-chain section uses the same prose pattern (copy from Task 3's template, adapt only the phase numbering and the path that the chain reviews).

---

## Task 1: Read source files

**Files:**
- Read: All Phase 2 files listed above (current state)
- Read: `skills/_shared/orchestration-guide.md` (Phase 1 just updated it — review the §10.C structured result shape)
- Read: `skills/adversarial-review/SKILL.md` (Phase 1 added the non-interactive --dispatch section — review its emission contract)
- Read: `skills/implement-plan/challenge-round-questions.md`
- Read: `documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md` (§5.3, §5.4, §5.5.1)

- [ ] **Step 1: Read the design spec sections**

Specifically §5.3 (adversarial-review chain), §5.4 (/simplify chain in implement-plan), §5.5.1 (interactive Step 3 with open findings seed).

- [ ] **Step 2: Read adversarial-review's emission contract (set in Phase 1)**

In `skills/adversarial-review/SKILL.md`, find the "Structured Result Emission (--dispatch only)" section. Note the exact `artifacts.findings` shape — each finding has `concern_area`, `severity`, `summary`, `recommendation`. Phase 2 tasks consume this shape.

- [ ] **Step 3: Read the 6 planning skills' phase boundaries**

For each planning skill, identify the section where Plan agents return their summaries OR where the skill finalizes its plan output. The adversarial pass will be inserted after that boundary. Note the section number/heading for each — you'll reference it precisely in each task below.

| Skill | Boundary section to anchor on |
|---|---|
| tech-debt | After "Generate Remediation Plans" Phase 2; before "Output Targets" section |
| security-audit | After Phase 2 "Remediation Plans" section; before Phase 3 "Summary & Handoff" |
| product-enhance | After Step 5 "Generate Phased Design Docs"; before "Notes" |
| frontend-performance-audit | After Phase 4 "Remediation Plans"; before "Notes" |
| docs-review | After Step 5 "Gap Analysis", before Step 6 "Summary Report" — pass runs on gap-fix proposals before they're applied |
| access-path-audit | After Phase 2 "Remediation Plans"; before Phase 3 "Summary & Handoff" |

- [ ] **Step 4: Read `/claudna:implement-plan` current Step 3 and Step 6/7**

You'll be revising Step 3 (split into 3A/3B) and inserting Step 6.5 between current Steps 6 and 7. Read those sections carefully in their current form.

No commit for Task 1.

---

## Task 2: Create the shared adversarial-chain dispatch prompt

**Files:**
- Create: `skills/_shared/subagent-prompts/adversarial-chain.md`

- [ ] **Step 1: Create the directory and file**

The directory `skills/_shared/subagent-prompts/` does not exist yet. Use the Write tool — parent directories are created automatically.

Create `skills/_shared/subagent-prompts/adversarial-chain.md` with this content:

````markdown
# Adversarial-Review Chain — Subagent Dispatch Prompt

Used by planning skills to chain `/claudna:adversarial-review` at the end of plan generation. This file is the source of truth for the dispatch prompt; planning skills reference it rather than inlining the prompt.

## Subagent dispatch prompt template

When a planning skill needs to run adversarial review on a generated plan document, it dispatches a `general-purpose` subagent (NOT `Explore` — that type lacks the tools adversarial-review needs) with this prompt:

```
Read the skill body at skills/adversarial-review/SKILL.md.

Apply the skill with --dispatch mode to the plan document at: <DOC_PATH>

Operate non-interactively per the skill's `--dispatch` mode rules:
- Do NOT call EnterPlanMode
- Do NOT call AskUserQuestion
- Do NOT prompt for clarification

Spawn parallel critic subagents per the skill's Phase 3 dispatch procedure.

Return ONLY the structured-result JSON block per skills/_shared/orchestration-guide.md §10.C. Format:

{
  "skill": "adversarial-review",
  "outcome": "completed",
  "artifacts": {
    "findings_count": <N>,
    "findings": [
      {"concern_area": "...", "severity": "...", "summary": "...", "recommendation": "..."},
      ...
    ],
    "plan_path": "<DOC_PATH>"
  },
  "summary": "<digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}

If the plan body cannot be reviewed (empty, malformed), emit outcome: blocked with blocker_description.
```

Substitute `<DOC_PATH>` with the actual filesystem path or issue URL.

## Concern area vocabulary

When critics label findings, use these `concern_area` values where possible (aligns with `skills/implement-plan/challenge-round-questions.md` matrix categories so downstream consumers can route findings to the right matrix questions):

- `architecture` — module boundaries, layering, placement decisions
- `testing` — test coverage, test design, missing scenarios
- `dependencies` — new dependencies introduced, version constraints
- `error-handling` — failure modes, retries, fallbacks
- `performance` — measured cost, scaling assumptions
- `security` — auth, validation, secret handling
- `data-integrity` — invariants, idempotency, transaction boundaries
- `compatibility` — backward compat, breaking changes
- `observability` — logging, metrics, debugging
- `scope` — over- or under-scoped changes

Use one value per finding (the dominant area). If a finding spans two areas, pick the higher-priority one and mention the secondary in `summary`.

## Folding findings into the plan body

After the subagent returns, the calling planning skill:

1. Parses `artifacts.findings`.
2. If `outcome` is not `completed`, log the issue and skip folding for that doc.
3. Uses the Edit tool to append (or create) an `## Adversarial Review Findings` section in the plan doc. The section format:

```markdown
## Adversarial Review Findings

These concerns were raised by /claudna:adversarial-review at plan-creation time. Items are OPEN until resolved during implementation challenge round or by `--auto` synthesis pass.

- [ ] **[<severity>] <concern_area>**: <summary>
  - **Recommendation:** <recommendation>

- [ ] **[<severity>] <concern_area>**: <summary>
  - **Recommendation:** <recommendation>
```

Findings sorted by severity (critical → high → medium → low → info).

4. The section becomes part of the plan body. Downstream consumers (interactive `/implement-plan` Step 3A, or `--auto` synthesis pass) read it and resolve items.

## When this chain runs

- **All planning skills, all modes.** Interactive and `--auto`. The chain is part of the planning skill's natural workflow, not a mode-specific addition.
- **Per phase doc**, not per session. A session may produce 1-N phase docs; the chain runs once per doc.
- **After Plan agents return**, before the planning skill's final summary/handoff section.
````

- [ ] **Step 2: Verify the file is well-formed**

```bash
ls -la /Users/chris/Projects/claudna/skills/_shared/subagent-prompts/
wc -l /Users/chris/Projects/claudna/skills/_shared/subagent-prompts/adversarial-chain.md
```

Expected: file exists, ~80 lines.

Run the validator:

```bash
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

Expected: no violations. The `_shared/` directory is lint-checked for stale paths only.

- [ ] **Step 3: Commit**

```bash
cd /Users/chris/Projects/claudna
git add skills/_shared/subagent-prompts/adversarial-chain.md
git commit -m "$(cat <<'EOF'
docs: add shared adversarial-chain subagent dispatch prompt

New shared file at skills/_shared/subagent-prompts/adversarial-chain.md
that planning skills reference when chaining /claudna:adversarial-review
at the end of plan generation. Single source of truth for the dispatch
prompt and findings-folding pattern.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 3: Create the shared simplify-chain dispatch prompt

**Files:**
- Create: `skills/_shared/subagent-prompts/simplify-chain.md`

- [ ] **Step 1: Create the file**

Create `skills/_shared/subagent-prompts/simplify-chain.md`:

````markdown
# /simplify Chain — Subagent Dispatch Prompt

Used by `/claudna:implement-plan` (Step 6.5) to run `/simplify` against changed files after verification passes. /simplify operates non-interactively on the working tree by design — this file documents the chain pattern so other skills can adopt it later if needed.

## When this chain runs

In `/claudna:implement-plan` Step 6.5, AFTER Step 6 verification passes. Triggered when the diff exceeds a size threshold (>50 LOC OR >2 files changed).

## Procedure

1. Compute the diff size:

```bash
git diff --stat <base-branch>...HEAD
```

Parse the output for total lines changed and file count.

2. If diff size is below the trigger threshold, skip /simplify entirely. Proceed to Step 7.

3. Run /simplify. The skill operates against the current working tree non-interactively:

```
Invoke: /simplify
```

(/simplify does not require arguments. It reviews recently changed files and reshapes them in place.)

4. Stage and commit /simplify's edits if any were made:

```bash
git status --short
git add -u  # or specific files /simplify edited
git commit -m "refactor: simplify pass (post-verify)"
```

5. Re-run the Step 6 verification checklist (tests, lint, types). If verification passes, proceed to Step 7.

6. **If verification fails after /simplify:**
   - **Interactive mode:** Present the regression to the user via AskUserQuestion. Options: "Fix forward (debug the regression)", "Revert /simplify's commit", "Abort". Process the user's choice.
   - **`--auto` mode:** Revert /simplify's commit unconditionally:

```bash
git reset --hard HEAD~1
```

  Add a note to the eventual PR body (Step 7): "Simplification pass attempted; reverted due to verification regression: <error summary>". Proceed to Step 7 with the pre-simplify diff.

## Why a separate commit for /simplify

Having /simplify's edits in their own commit makes revert trivial (`git reset --hard HEAD~1`) and makes the PR's history clear: implementation commits, then simplification commit. Reviewers can quickly see what /simplify changed.

## What /simplify does NOT do

- It does not change test code (unless tests themselves are simplifiable — uncommon).
- It does not introduce new abstractions; it removes incidental complexity.
- It does not change observable behavior. If verification regresses, that's the trigger to revert.
````

- [ ] **Step 2: Verify and commit**

```bash
ls -la /Users/chris/Projects/claudna/skills/_shared/subagent-prompts/
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

```bash
cd /Users/chris/Projects/claudna
git add skills/_shared/subagent-prompts/simplify-chain.md
git commit -m "docs: add shared simplify-chain dispatch prompt"
```

---

## Task 4: Add adversarial-review chain to `tech-debt`

**Files:**
- Modify: `skills/tech-debt/SKILL.md`

- [ ] **Step 1: Insert the chain section after Phase 2**

Find the existing transition from Phase 2 to the next section. In `tech-debt/SKILL.md`, Phase 2 ends and the next major section is "Output Targets" (the `## Output Targets` heading). The adversarial chain runs between them.

Use Edit. `old_string`:

```
---

## Output Targets
```

`new_string`:

````
---

## Phase 2.5: Adversarial Review Pass

After Plan agents return with their metadata summaries (and the master `00_TECH_DEBT.md` doc is written), run adversarial review on each generated doc to stress-test the remediation plans before publishing/handoff. Apply in both `--output docs` and `--output github` (where each issue body is treated as a plan doc) and in `--auto` mode.

### Procedure

For each phase doc generated by Phase 2 (path: `documentation/planning/tech_debt/<session>/<NN>_*.md`), and for the master `00_TECH_DEBT.md`:

1. Dispatch a `general-purpose` subagent using the prompt template in `skills/_shared/subagent-prompts/adversarial-chain.md`. Substitute `<DOC_PATH>` with the phase doc's filesystem path.

2. Collect the subagent's structured-result JSON block. If `outcome` is `completed`, parse `artifacts.findings`.

3. Use the Edit tool to append an `## Adversarial Review Findings` section to the phase doc with the findings as markdown checkbox bullets (format per `skills/_shared/subagent-prompts/adversarial-chain.md`).

4. If `outcome` is `blocked` or `errors` is non-empty, log a note in the orchestrator session but proceed with the next doc — adversarial-review failure does not block plan publishing.

### Parallelism

Launch all adversarial-review subagents in parallel using `run_in_background: true`, then collect via `TaskOutput` one at a time. This mirrors the Plan-agent dispatch pattern in §6 of the orchestration guide.

### `--output github` adaptation

When the planning output is GitHub Issues (not phase docs), run adversarial-review on the proposed issue body BEFORE creating the issue. Pass the body content directly to the subagent (write it to `<scratch>/issue-<N>-body.md` as a temporary file, run adversarial-review against that path, fold findings into the body, then create the issue with the augmented body).

### Skipping in degenerate cases

If Phase 2 produced zero phase docs (no findings worth a plan), skip Phase 2.5 entirely. No phase docs = nothing to review.

---

## Output Targets
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Phase 2.5: Adversarial Review Pass" /Users/chris/Projects/claudna/skills/tech-debt/SKILL.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

Expected: one match, validator passes.

```bash
cd /Users/chris/Projects/claudna
git add skills/tech-debt/SKILL.md
git commit -m "$(cat <<'EOF'
feat(tech-debt): add adversarial-review chain after plan generation

After Phase 2 plan generation, dispatch /claudna:adversarial-review
--dispatch on each phase doc and the master tech-debt doc. Findings
are folded into the docs as an Adversarial Review Findings section.
Plans arrive at /implement-plan already stress-tested.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 5: Add adversarial-review chain to `security-audit`

**Files:**
- Modify: `skills/security-audit/SKILL.md`

- [ ] **Step 1: Insert the chain section between Phase 2 and Phase 3**

Find this heading in `security-audit/SKILL.md`:

```
## Phase 3: Summary & Handoff
```

The adversarial chain inserts before it. Use Edit. `old_string`:

```
## Phase 3: Summary & Handoff
```

`new_string`:

````
## Phase 2.5: Adversarial Review Pass

After Plan agents return with their metadata summaries (and the master `00_SECURITY_AUDIT.md` doc is written), run adversarial review on each generated remediation doc before publishing/handoff. Apply in all output modes (`docs`, `github`, `session` final review) and in `--auto`.

### Procedure

For each remediation doc generated by Phase 2 (path: `documentation/planning/security/<session>/<NN>_*.md`), and for the master `00_SECURITY_AUDIT.md`:

1. Dispatch a `general-purpose` subagent per `skills/_shared/subagent-prompts/adversarial-chain.md`. Substitute `<DOC_PATH>`.

2. Collect structured-result JSON. Parse `artifacts.findings` if `outcome: completed`.

3. Append `## Adversarial Review Findings` section to the doc.

### Security-specific rules

- The adversarial-review subagent inherits the secret-masking rule: critics MUST NOT reproduce secret values in their findings.
- For each finding, the `concern_area` should be one of: `security`, `data-integrity`, or `error-handling` (most common areas for security remediation plans). Critics may use others if applicable.
- If the adversarial review surfaces a NEW security risk introduced by the remediation plan itself (e.g., "this auth change creates a session-fixation window"), elevate that finding's severity to CRITICAL regardless of the critic's default labeling.

### Parallelism and `--output github`

Same as Phase 1 contract — see `skills/tech-debt/SKILL.md` Phase 2.5 for the parallelism pattern and `--output github` adaptation.

---

## Phase 3: Summary & Handoff
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Phase 2.5: Adversarial Review Pass" /Users/chris/Projects/claudna/skills/security-audit/SKILL.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

```bash
cd /Users/chris/Projects/claudna
git add skills/security-audit/SKILL.md
git commit -m "feat(security-audit): add adversarial-review chain after plan generation"
```

---

## Task 6: Add adversarial-review chain to `product-enhance`

**Files:**
- Modify: `skills/product-enhance/SKILL.md`

- [ ] **Step 1: Insert the chain after Step 5**

Find this heading:

```
### Step 5: Generate Phased Design Docs
```

The chain inserts after Step 5's procedure but before the section ends. In product-enhance, Step 5 is followed by `## Notes`. Use Edit. `old_string`:

```
Present a `Product Enhancement Summary`, then direct user to `/claudna:implement-plan`. **This skill produces plans, not code.**

---

## Notes
```

`new_string`:

````
Present a `Product Enhancement Summary`, then direct user to `/claudna:implement-plan`. **This skill produces plans, not code.**

---

### Step 5.5: Adversarial Review Pass

Before presenting the Product Enhancement Summary, run adversarial review on each generated design doc.

For each phase doc (path: `documentation/planning/phases/<session>/<NN>_*.md`) and `00_OVERVIEW.md`:

1. Dispatch a `general-purpose` subagent per `skills/_shared/subagent-prompts/adversarial-chain.md`. Substitute `<DOC_PATH>`.

2. Collect the structured-result JSON. Append `## Adversarial Review Findings` section to each doc.

Run all dispatches in parallel via `run_in_background: true`; collect via `TaskOutput` one at a time.

Apply in all modes (interactive, `--auto`). Skip only if Phase 5 generated zero docs.

---

## Notes
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Step 5.5: Adversarial Review Pass" /Users/chris/Projects/claudna/skills/product-enhance/SKILL.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

```bash
cd /Users/chris/Projects/claudna
git add skills/product-enhance/SKILL.md
git commit -m "feat(product-enhance): add adversarial-review chain after design doc generation"
```

---

## Task 7: Add adversarial-review chain to `frontend-performance-audit`

**Files:**
- Modify: `skills/frontend-performance-audit/SKILL.md`

- [ ] **Step 1: Insert the chain after Phase 4**

Find this text:

```
After generating docs: **"Plans are ready for review. Run `/claudna:implement-plan` on the session directory to execute them."**

---

## Notes
```

Use Edit. `old_string`:

```
After generating docs: **"Plans are ready for review. Run `/claudna:implement-plan` on the session directory to execute them."**

---

## Notes
```

`new_string`:

````
After generating docs: **"Plans are ready for review. Run `/claudna:implement-plan` on the session directory to execute them."**

---

## Phase 4.5: Adversarial Review Pass

Before handing off to `/implement-plan`, run adversarial review on each remediation doc.

For each phase doc in `documentation/planning/performance/<session>/<NN>_*.md` and `00_PERF_AUDIT.md`:

1. Dispatch a `general-purpose` subagent per `skills/_shared/subagent-prompts/adversarial-chain.md`. Substitute `<DOC_PATH>`.

2. Collect structured-result JSON. Append `## Adversarial Review Findings` section.

### Performance-specific concern areas

For frontend-performance plans, critics SHOULD flag:
- `performance` — does the proposed fix actually address the measured bottleneck, or is it speculative?
- `compatibility` — does the fix break any framework guarantees (e.g., Suspense boundaries, React 18 transitions)?
- `architecture` — does the fix introduce architectural changes (e.g., new caching layers) that should be split into a separate plan?

Parallel dispatch and `--output github` adaptation: same as Phase 1 contract — see `skills/tech-debt/SKILL.md` Phase 2.5.

---

## Notes
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Phase 4.5: Adversarial Review Pass" /Users/chris/Projects/claudna/skills/frontend-performance-audit/SKILL.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

```bash
cd /Users/chris/Projects/claudna
git add skills/frontend-performance-audit/SKILL.md
git commit -m "feat(frontend-performance-audit): add adversarial-review chain after plan generation"
```

---

## Task 8: Add adversarial-review chain to `docs-review`

**Files:**
- Modify: `skills/docs-review/SKILL.md`

**Note:** `docs-review` is structurally different — it doesn't use Plan agents producing phase docs. Instead, Step 5 (Gap Analysis) identifies gaps and proposes new/extended documentation. The adversarial pass runs on the **gap proposals** before they're applied to the codebase.

- [ ] **Step 1: Insert the chain between Step 5 (Gap Analysis) and Step 6 (Summary Report)**

Find this text:

```
Execute the user's choices — create or update docs as requested.

### Step 6: Summary Report
```

Use Edit. `old_string`:

```
Execute the user's choices — create or update docs as requested.

### Step 6: Summary Report
```

`new_string`:

````
Execute the user's choices — create or update docs as requested.

### Step 5.5: Adversarial Review Pass on Gap Proposals

Before executing user choices to create/extend documentation, run adversarial review on each proposed new doc body (or extension content).

For each gap-fix proposal (a new doc to create or an existing doc to extend):

1. Write the proposed content to a temporary scratch file at `/tmp/docs-review-<timestamp>/proposals/<gap-slug>.md`.

2. Dispatch a `general-purpose` subagent per `skills/_shared/subagent-prompts/adversarial-chain.md` against the scratch file.

3. Collect findings. If `outcome: completed` and `artifacts.findings` is non-empty:
   - For each finding, fold the recommendation into the proposed content before applying.
   - Specifically: if a finding's `concern_area` is `compatibility` (e.g., "this onboarding step assumes Python 3.10 but project uses 3.8"), revise the content to match observed code reality.

4. Present the revised proposals to the user via AskUserQuestion (interactive mode) or apply directly (--auto mode).

### `--auto` mode adaptation

In `--auto` mode, adversarial findings are folded silently. The summary report (Step 6 below) MUST mention how many adversarial findings were addressed during gap-proposal generation, in the `summary` field of the structured-result JSON.

### Skipping

If Step 5 identified zero gaps requiring new content, skip Step 5.5.

### Step 6: Summary Report
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Step 5.5: Adversarial Review Pass" /Users/chris/Projects/claudna/skills/docs-review/SKILL.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

```bash
cd /Users/chris/Projects/claudna
git add skills/docs-review/SKILL.md
git commit -m "feat(docs-review): add adversarial-review chain on gap proposals"
```

---

## Task 9: Add adversarial-review chain to `access-path-audit`

**Files:**
- Modify: `skills/access-path-audit/SKILL.md`

- [ ] **Step 1: Insert the chain between Phase 2 and Phase 3**

Find this heading:

```
## Phase 3: Summary & Handoff
```

Use Edit. `old_string`:

```
## Phase 3: Summary & Handoff
```

`new_string`:

````
## Phase 2.5: Adversarial Review Pass

After Plan agents return with their metadata summaries (and `00_ACCESS_PATH_AUDIT.md` is written), run adversarial review on each remediation doc.

For each remediation doc in `documentation/planning/access-paths/<session>/<NN>_*.md` and `00_ACCESS_PATH_AUDIT.md`:

1. Dispatch a `general-purpose` subagent per `skills/_shared/subagent-prompts/adversarial-chain.md`. Substitute `<DOC_PATH>`.

2. Collect structured-result JSON. Append `## Adversarial Review Findings` section.

### Access-path-specific concern areas

For access-path remediation plans, critics SHOULD flag:
- `architecture` — does the fix move a concern to the correct layer (transport vs. domain)?
- `compatibility` — does pushing a concern into the domain core break any access path that depended on transport-layer behavior?
- `security` — does the refactor weaken or strengthen the security posture per-path?

Parallel dispatch and `--output github` adaptation: see `skills/tech-debt/SKILL.md` Phase 2.5.

---

## Phase 3: Summary & Handoff
````

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Phase 2.5: Adversarial Review Pass" /Users/chris/Projects/claudna/skills/access-path-audit/SKILL.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

```bash
cd /Users/chris/Projects/claudna
git add skills/access-path-audit/SKILL.md
git commit -m "feat(access-path-audit): add adversarial-review chain after plan generation"
```

---

## Task 10: Revise `/implement-plan` Step 3 (split into 3A/3B per design §5.5.1)

**Files:**
- Modify: `skills/implement-plan/SKILL.md`

- [ ] **Step 1: Find the existing Step 3 section**

In `skills/implement-plan/SKILL.md`, find the heading:

```
### Step 3: Challenge Round
```

The current section uses an "Adaptive one-at-a-time flow" with the question matrix. The work splits this into 3A (seed with adversarial findings if present) and 3B (run matrix as today).

- [ ] **Step 2: Replace the Step 3 body with the 3A/3B split**

The existing Step 3 body (everything from the heading down through `"Abort — not implementing this"`) is being restructured. Use Edit. `old_string`:

```
### Step 3: Challenge Round

Read `challenge-round-questions.md` for the question matrix and `red-flags-and-rationalizations.md` to guard against rubber-stamping.

**Adaptive one-at-a-time flow using AskUserQuestion:**

1. Analyze the plan against the codebase (Explore subagents — same as before)
2. Generate the first challenge question based on the question matrix categories
3. Present via AskUserQuestion with 2-4 **contextual options** drawn from the codebase — not generic "accept/reject" but concrete alternatives (e.g., "Extend existing Pydantic model" vs "Add new validation layer" vs "Keep both — defense in depth")
4. Process the user's answer. Update the plan document (or issue body) immediately if the answer changes the approach.
5. Generate the next challenge, informed by the previous answer
6. Repeat until:
   - All relevant categories from the question matrix have been probed
   - No more substantive challenges remain
   - User selects "Skip remaining challenges" (always include as an option)
7. Final gate — AskUserQuestion: **"Ready to build?"** with options:
   - "Ready to build" (proceed to Step 4)
   - "I have more concerns" (loop back to Step 3)
   - "Abort — not implementing this"

**The question matrix still guides what to challenge** (architecture, testing, dependencies, error handling, etc.). The delivery mechanism changes — each question gets its own focused AskUserQuestion instead of a batch of 3-5 in chat.
```

`new_string`:

````
### Step 3: Challenge Round

Read `challenge-round-questions.md` for the question matrix and `red-flags-and-rationalizations.md` to guard against rubber-stamping.

Step 3 has two sub-steps: **3A** seeds the round with any open adversarial-review findings from the plan body; **3B** runs the matrix-driven flow. 3A is skipped when no adversarial findings are present (ad-hoc plans, or plans where every finding was already resolved).

#### Step 3A: Seed with open adversarial-review findings

Open the plan body (the plan document or GitHub issue body). Search for a section titled `## Adversarial Review Findings`.

**If the section exists and has OPEN items** (markdown checkboxes `- [ ]` rather than `- [x]`):

1. Use AskUserQuestion. First question: **"Adversarial review flagged these unresolved concerns. Which to dig into?"**

   Options: up to 3 most-severe findings (use the severity label from the bullet) + "All of them" + "None — ready to build".

   If more than 3 findings are open, paginate: after the user picks from the first 3, present the next 3 in another AskUserQuestion turn until all are addressed or the user picks "None — ready to build."

2. For each picked finding:
   - Identify the finding's `concern_area` from the bullet text (e.g., `[high] architecture`).
   - Drive matrix questions from `challenge-round-questions.md` scoped to that concern area. Generate options drawn from the codebase, just as in 3B.
   - Process the user's answer. Update the plan body immediately — both the finding's resolution AND any plan-level changes the user's answer implies.
   - Mark the finding's checkbox as resolved: `- [ ]` → `- [x]`. Add the user's decision as a sub-bullet below the finding.

3. After all picked findings are addressed (or user chose "None — ready to build"), proceed to Step 3B for a full matrix pass.

**If the section exists but has NO open items** (all resolved):

Skip Step 3A. Note in chat: "Plan was reviewed adversarially at creation time; all findings already resolved. Proceeding to matrix challenge." Go to Step 3B.

**If the section does NOT exist** (ad-hoc plan):

Skip Step 3A. Note in chat: "No upstream adversarial review present (ad-hoc plan). Running full matrix challenge from scratch." Go to Step 3B.

#### Step 3B: Matrix-driven challenge round

This is the existing challenge-round flow, run AFTER Step 3A regardless of whether findings were resolved. The matrix may surface concerns adversarial-review didn't think to raise; an extra pass is cheap and catches real issues.

**Adaptive one-at-a-time flow using AskUserQuestion:**

1. Analyze the plan against the codebase (Explore subagents — same as before)
2. Generate the first challenge question based on the question matrix categories
3. Present via AskUserQuestion with 2-4 **contextual options** drawn from the codebase — not generic "accept/reject" but concrete alternatives (e.g., "Extend existing Pydantic model" vs "Add new validation layer" vs "Keep both — defense in depth")
4. Process the user's answer. Update the plan document (or issue body) immediately if the answer changes the approach.
5. Generate the next challenge, informed by the previous answer
6. Repeat until:
   - All relevant categories from the question matrix have been probed
   - No more substantive challenges remain
   - User selects "Skip remaining challenges" (always include as an option)
7. Final gate — AskUserQuestion: **"Ready to build?"** with options:
   - "Ready to build" (proceed to Step 4)
   - "I have more concerns" (loop back to Step 3B)
   - "Abort — not implementing this"

**The question matrix still guides what to challenge** (architecture, testing, dependencies, error handling, etc.). The delivery mechanism is one focused AskUserQuestion per topic.

#### Note for `--auto` mode

In `--auto` mode (added by Phase 3), Step 3 is replaced entirely by a synthesis pass (see §5.5.2 of the design spec). 3A and 3B above describe interactive behavior only.
````

- [ ] **Step 3: Verify and commit**

```bash
grep -n "Step 3A:" /Users/chris/Projects/claudna/skills/implement-plan/SKILL.md
grep -n "Step 3B:" /Users/chris/Projects/claudna/skills/implement-plan/SKILL.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

Expected: both grep commands return one match each, validator passes.

```bash
cd /Users/chris/Projects/claudna
git add skills/implement-plan/SKILL.md
git commit -m "$(cat <<'EOF'
feat(implement-plan): split Step 3 challenge round into 3A (seed) + 3B (matrix)

Step 3A is new: when the plan body contains open adversarial-review
findings, seed the challenge round with them. User picks which to dig
into; matrix questions then drive into the picked concerns.

Step 3B is the existing matrix-driven flow, run AFTER 3A regardless of
whether findings were resolved. The matrix surfaces concerns
adversarial-review may not have raised.

When the plan body has no adversarial findings (ad-hoc plan), 3A is
skipped and 3B runs as today — backward compatible.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 11: Add Step 6.5 (Simplification Pass) to `/implement-plan`

**Files:**
- Modify: `skills/implement-plan/SKILL.md`

- [ ] **Step 1: Locate the boundary between Step 6 and Step 7**

In `skills/implement-plan/SKILL.md`, find the heading sequence:

```
### Step 6: Verify
...
### Step 7: PR & Status Update
```

The simplification pass inserts between them.

- [ ] **Step 2: Insert Step 6.5**

Use Edit. `old_string`:

```
### Step 7: PR & Status Update
```

`new_string`:

````
### Step 6.5: Simplification Pass

After Step 6 verification passes, evaluate whether the diff warrants a simplification pass via `/simplify`. /simplify reshapes recently changed code for clarity and removes incidental complexity. It operates non-interactively on the working tree.

Follow the procedure in `skills/_shared/subagent-prompts/simplify-chain.md`.

**Trigger condition:**

Run:

```bash
git diff --stat <base-branch>...HEAD
```

Parse the output for total lines changed and file count. If EITHER:
- Total lines added or removed > 50, OR
- Files changed > 2

then proceed with /simplify. Otherwise, skip to Step 7.

**Procedure:**

1. Invoke `/simplify` (no arguments — operates against the current working tree).
2. After /simplify completes, stage and commit its edits as a separate commit:

```bash
git add -u
git commit -m "refactor: simplify pass (post-verify)"
```

3. Re-run the Step 6 verification checklist (tests, lint, types).
4. **If verification passes:** /simplify's changes stay. Proceed to Step 7. The PR body will reference both the implementation commit(s) and the simplification commit.
5. **If verification fails (regression introduced by /simplify):**
   - **Interactive mode:** Present the regression to the user via AskUserQuestion with options:
     - "Fix forward — debug the regression" (return to Step 5 to investigate)
     - "Revert /simplify's commit" (run `git reset --hard HEAD~1`, proceed to Step 7 with the pre-simplify diff)
     - "Abort — stop here"
   - **`--auto` mode:** Revert /simplify's commit unconditionally:

```bash
git reset --hard HEAD~1
```

     Add a note for the eventual PR body (Step 7): "Simplification pass attempted; reverted due to verification regression: `<error summary>`." Proceed to Step 7 with the pre-simplify diff.

**Why a separate commit for /simplify:** keeping the simplification in its own commit makes revert trivial and makes the PR history clear: implementation, then quality polish. Reviewers can quickly see what /simplify changed without disentangling it from implementation logic.

**Skipping:** If the diff is below the threshold, the simplification pass is unnecessary — small changes rarely benefit from /simplify, and the runtime cost isn't justified.

### Step 7: PR & Status Update
````

- [ ] **Step 3: Verify and commit**

```bash
grep -n "Step 6.5: Simplification Pass" /Users/chris/Projects/claudna/skills/implement-plan/SKILL.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

```bash
cd /Users/chris/Projects/claudna
git add skills/implement-plan/SKILL.md
git commit -m "$(cat <<'EOF'
feat(implement-plan): add Step 6.5 simplification pass

After Step 6 verification, if the diff exceeds 50 LOC or 2+ files,
invoke /simplify against the working tree, commit its edits as a
separate commit, and re-verify. On regression: interactive mode asks
user to fix-forward or revert; --auto mode reverts unconditionally and
notes in PR body.

Applies in all modes (interactive and --auto).

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 12: Update the implement-plan flowchart for new steps

**Files:**
- Modify: `skills/implement-plan/SKILL.md` (the graphviz Process Flow section)

- [ ] **Step 1: Locate the existing flowchart**

Find the `### Step 5: Branch & Implement` reference in the existing graphviz DOT block at the top of `skills/implement-plan/SKILL.md`. The flowchart describes the procedure's flow.

- [ ] **Step 2: Add the new step nodes**

The existing nodes include `step3 [label="Step 3: Challenge Round..."]` and `commit [label="Commit chunk"]` and `step6a`, `step6b`, `step7`. We need to add:
- A `step3a` node and `step3b` node (replacing the single `step3` reference)
- A `step6_5` node between `step6b` and `step7`

Find the existing node definitions block. Use Edit to update them. The simplest path is to replace the `step3` node and add the new nodes while keeping the rest of the flowchart intact.

Find:

```
    step3 [label="Step 3: Challenge Round\nAdaptive AskUserQuestion" shape=box];
```

Replace with:

```
    step3a [label="Step 3A: Seed with\nadversarial findings\n(if present)" shape=box];
    step3b [label="Step 3B: Matrix\nchallenge round" shape=box];
    step6_5 [label="Step 6.5: Simplify\nif diff > threshold" shape=box];
    simplify_pass [label="Verify\npasses?" shape=diamond];
    simplify_revert [label="Revert simplify\ncommit" shape=box];
```

Then find:

```
    step3 -> update_plan;
    update_plan -> more_challenges;
    more_challenges -> step3 [label="yes"];
    more_challenges -> ready [label="no"];
    ready -> step4 [label="ready"];
    ready -> step3 [label="revise"];
```

Replace with:

```
    next_item -> step2;
    step2 -> blockers;
    blockers -> report_blockers [label="yes"];
    blockers -> step3a [label="no"];
    step3a -> step3b;
    step3b -> update_plan;
    update_plan -> more_challenges;
    more_challenges -> step3b [label="yes"];
    more_challenges -> ready [label="no"];
    ready -> step4 [label="ready"];
    ready -> step3b [label="revise"];
```

Then find the connection from `step6b` (verify) to `step7` (PR):

```
    step6b -> verify_pass;
    verify_pass -> step7 [label="yes"];
    verify_pass -> fix_check [label="no"];
    fix_check -> step6b;
```

Replace with:

```
    step6b -> verify_pass;
    verify_pass -> step6_5 [label="yes"];
    verify_pass -> fix_check [label="no"];
    fix_check -> step6b;
    step6_5 -> simplify_pass;
    simplify_pass -> step7 [label="yes"];
    simplify_pass -> simplify_revert [label="no"];
    simplify_revert -> step7;
```

- [ ] **Step 3: Verify the dot block is well-formed**

```bash
grep -A 1 "step3a" /Users/chris/Projects/claudna/skills/implement-plan/SKILL.md | head -10
grep "step6_5" /Users/chris/Projects/claudna/skills/implement-plan/SKILL.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

Expected: matches found, validator passes.

Optionally render the dot block to visually verify (requires graphviz installed):

```bash
sed -n '/```dot/,/```/p' /Users/chris/Projects/claudna/skills/implement-plan/SKILL.md | sed '1d;$d' > /tmp/implement-plan-flow.dot
dot -Tsvg /tmp/implement-plan-flow.dot -o /tmp/implement-plan-flow.svg
```

Open the SVG in a browser to confirm the flowchart is coherent. If `dot` is not installed, skip — the grep checks above are sufficient.

- [ ] **Step 4: Commit**

```bash
cd /Users/chris/Projects/claudna
git add skills/implement-plan/SKILL.md
git commit -m "docs(implement-plan): update flowchart for Step 3A/3B split and Step 6.5"
```

---

## Task 13: Update `challenge-round-questions.md` with concern-area alignment note

**Files:**
- Modify: `skills/implement-plan/challenge-round-questions.md`

- [ ] **Step 1: Add an introductory note about concern-area alignment**

This is a light touch: the question matrix already exists. We add a brief preamble noting that question categories align with the `concern_area` vocabulary in `skills/_shared/subagent-prompts/adversarial-chain.md` so Step 3A can route findings to the right matrix questions.

Open `skills/implement-plan/challenge-round-questions.md`. Find the first heading after any existing preamble. Insert a new note at the top of the body (after frontmatter if any, before the first matrix category).

Add (use Edit; locate the file's existing first H2 or H3 heading and prepend):

```markdown
## Note: Concern-Area Alignment

The categories in this matrix correspond to the `concern_area` vocabulary used by `/claudna:adversarial-review --dispatch` findings (defined in `skills/_shared/subagent-prompts/adversarial-chain.md`).

When Step 3A of `/claudna:implement-plan` processes an open adversarial finding, it routes questions to the matrix category matching the finding's `concern_area`. For example, a finding with `concern_area: error-handling` triggers questions from this matrix's `error-handling` category.

If a finding's `concern_area` does not have a direct matrix category, fall back to the closest one (e.g., `compatibility` findings often map to `architecture` or `dependencies` matrix questions). Add new matrix categories here as needed when adversarial-review surfaces patterns the matrix doesn't cover.

---
```

(Insert the heading above the first existing H2/H3 in the file.)

- [ ] **Step 2: Verify and commit**

```bash
grep -n "Concern-Area Alignment" /Users/chris/Projects/claudna/skills/implement-plan/challenge-round-questions.md
python3 /Users/chris/Projects/claudna/scripts/validate-skills.py
```

```bash
cd /Users/chris/Projects/claudna
git add skills/implement-plan/challenge-round-questions.md
git commit -m "docs(implement-plan): note concern-area alignment between matrix and adversarial-review"
```

---

## Task 14: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add Phase 2 entries**

Add to the `## [Unreleased]` section (under `### Added` or create as needed):

```markdown
### Added
- Shared subagent dispatch prompt templates at `skills/_shared/subagent-prompts/`:
  - `adversarial-chain.md` — used by planning skills to chain `/claudna:adversarial-review` at the end of plan generation
  - `simplify-chain.md` — used by `/claudna:implement-plan` Step 6.5 to invoke `/simplify`
- Adversarial-review chain added to 6 planning skills: tech-debt (Phase 2.5), security-audit (Phase 2.5), product-enhance (Step 5.5), frontend-performance-audit (Phase 4.5), docs-review (Step 5.5), access-path-audit (Phase 2.5). Generated plan docs now arrive at `/implement-plan` with an `## Adversarial Review Findings` section.
- New Step 6.5 in `/claudna:implement-plan`: simplification pass via `/simplify` when diff > 50 LOC or 2+ files. Auto-reverts on regression in --auto mode; asks user in interactive mode.

### Changed
- `/claudna:implement-plan` Step 3 split into 3A (seed with open adversarial findings, if present) and 3B (matrix-driven challenge round). Ad-hoc plans without adversarial findings run 3B only — backward compatible.
- `skills/implement-plan/challenge-round-questions.md` notes concern-area alignment with adversarial-review's vocabulary.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chris/Projects/claudna
git add CHANGELOG.md
git commit -m "docs(changelog): record Phase 2 discipline chain additions"
```

---

## Phase 2 Verification

- [ ] **Step 1: Run the validator**

```bash
cd /Users/chris/Projects/claudna
python3 scripts/validate-skills.py
```

Expected: `OK: N skills validated, no violations`.

- [ ] **Step 2: Confirm all 6 planning skills have the chain**

```bash
for skill in tech-debt security-audit product-enhance frontend-performance-audit docs-review access-path-audit; do
  echo "=== $skill ==="
  grep -c "Adversarial Review Pass" /Users/chris/Projects/claudna/skills/$skill/SKILL.md
done
```

Expected: each prints `1`.

- [ ] **Step 3: Confirm `/implement-plan` has Step 3A, 3B, and 6.5**

```bash
grep -c "Step 3A:" /Users/chris/Projects/claudna/skills/implement-plan/SKILL.md
grep -c "Step 3B:" /Users/chris/Projects/claudna/skills/implement-plan/SKILL.md
grep -c "Step 6.5:" /Users/chris/Projects/claudna/skills/implement-plan/SKILL.md
```

Expected: each prints `1`.

- [ ] **Step 4: Confirm shared dispatch prompts exist**

```bash
ls /Users/chris/Projects/claudna/skills/_shared/subagent-prompts/
```

Expected: `adversarial-chain.md` and `simplify-chain.md` both present.

- [ ] **Step 5: Push for review**

```bash
cd /Users/chris/Projects/claudna
git push -u origin <branch-name>
gh pr create --title "Phase 2: clauDNA discipline chains (adversarial-review + /simplify)" \
  --body "$(cat <<'EOF'
## Summary

Implements Phase 2 of the autonomous-mode-and-orchestration design (spec: `documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md`).

- Adds adversarial-review chain at end of every planning skill (6 skills): plans arrive at /implement-plan already stress-tested
- Adds Step 6.5 simplification pass to /implement-plan: post-verify quality polish via /simplify when diff > threshold
- Revises interactive Step 3 in /implement-plan: open adversarial findings seed the round (3A), matrix runs after (3B)
- Adds shared subagent dispatch prompts at `skills/_shared/subagent-prompts/`

Backward compatible:
- Ad-hoc plans without adversarial findings work unchanged (3A skipped, 3B runs as today)
- Diffs below the simplify threshold skip Step 6.5
- Adversarial-review failures (subagent blocked) don't block plan publishing

Depends on Phase 1 (structured-result shape, adversarial-review --dispatch non-interactive mode).

## Test plan

- [ ] `python3 scripts/validate-skills.py` passes
- [ ] Each of 6 planning skills has an "Adversarial Review Pass" section
- [ ] /implement-plan has Step 3A, 3B, and 6.5
- [ ] Shared dispatch prompts exist at `skills/_shared/subagent-prompts/`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Common Mistakes for this Phase

| Mistake | Fix |
|---|---|
| Inserting the adversarial chain in the wrong phase boundary | Re-read Task 1 Step 3's anchor table — each skill has a different boundary section |
| Mass-copying the chain section verbatim across all 6 skills | Each skill has subtle adaptations: docs-review runs against gap proposals, security-audit has secret-masking rules, frontend-performance has its own concern areas |
| Making the chain conditional on `--auto` | The chain runs in ALL modes per design §5.3. Interactive users get vetted plans too |
| Forgetting to update the implement-plan flowchart | Task 12 is easy to miss; the DOT block at the top of the skill must reflect the procedure |
| Breaking Step 3 for ad-hoc plans | Step 3A's "section does not exist" branch falls through cleanly to 3B; double-check the prose handles this case |
| Running /simplify INSIDE the same commit as implementation in Step 6.5 | The skill explicitly commits /simplify separately to make revert trivial |
| Auto-reverting in interactive mode if /simplify regresses | Interactive mode asks the user; --auto reverts. Don't homogenize |

---

## What this phase does NOT do

- Add --auto to /implement-plan → Phase 3
- Implement Step 1.5 sparse-issue refusal or Step 2.5 scope tripwire → Phase 3
- Build the claudlobby autonomous-runner → Phase 4
- Modify any of the 6 planning skills beyond inserting the adversarial chain section

If any of those feel necessary to "complete" Phase 2, stop. The phase is the chain layer only.
