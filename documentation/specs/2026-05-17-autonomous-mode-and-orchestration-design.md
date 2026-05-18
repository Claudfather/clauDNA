---
title: Autonomous Mode & Orchestration Design
date: 2026-05-17
status: draft
authors: [chrisrogers37]
repos: [claudna, claudlobby]
---

# Autonomous Mode & Orchestration Design

## 1. Problem

A user-authored `/loop 1 hour` prompt has been driving autonomous GitHub-issue resolution by stacking three jobs into one custom prompt: (1) a loop driver, (2) per-issue craft (adversarial-review, /weigh-development-paths, /simplify, factuality checks), and (3) domain rules. This works but reinvents primitives that belong elsewhere, doesn't compose with other skills, and has no machine-readable result an orchestrator can consume.

Three concrete gaps surfaced during audit:

1. The `--auto` convention exists in clauDNA (`skills/_shared/orchestration-guide.md §10`) but is biased toward Tier-2 planning skills that produce GitHub Issues. Tier-3 implementation skills (notably `/implement-plan`) have no `--auto` mode and cannot conform to the current contract (they produce a PR, not an issue).
2. The six existing `--auto` skills emit different summary shapes. Any orchestrator wanting to act on their output needs per-skill parsers.
3. Three quality disciplines that *should* run every time — adversarial-review on plans, `/simplify` on non-trivial diffs, force-expand sparse issues into evidence-backed plans — currently live only in custom prompts or as user-offered options.

## 2. Goals

1. Every clauDNA procedural skill is invocable from headless orchestration with a uniform contract.
2. One structured-result shape across all `--auto` skills (the DRY artifact the orchestrator parses).
3. Quality discipline lives in clauDNA at natural workflow homes — not duplicated in orchestration prompts.
4. claudlobby provides a single configurable wrapper skill that turns any clauDNA procedural skill into a bot's continuous work pattern.

## 3. Non-goals

- Multi-bot dispatch (already covered by claudlobby's existing dispatch protocol).
- Domain-specific knowledge in the wrapper (lives in `library/expertise/` per existing claudlobby contract).
- Auto-merge. The contract is hard: implementation `--auto` runs always stop at PR-opened.
- Replacing `/implement-plan`, `/tech-debt`, etc. — augmenting them.

## 4. Architectural rule

Two layers, strictly separated:

- **clauDNA**: 1:1 workflows. Each skill does one job end-to-end. No skill orchestrates other skills as a continuous policy. `--auto` is a *thin* mode that removes user-input requirements; it does not add new workflow steps.
- **claudlobby**: orchestration. Discipline composition, inter-skill choreography, mission filtering, cadence, quota awareness, report-back. The wrapper skill is configurable per bot via fleet.yaml.

Exception: a clauDNA skill may chain another clauDNA skill *as part of its own natural workflow* when that chained step is universally applicable (e.g., `/simplify` after implementation is universally a quality polish; `/adversarial-review` at end of planning is universally a stress-test). It may NOT chain a skill conditionally based on orchestration policy — that's claudlobby's job.

If a discipline added to claudlobby's wrapper proves universally valuable in 1:1 human-driven sessions, it graduates up into the relevant clauDNA skill.

---

## 5. clauDNA changes

### 5.1 Extend `orchestration-guide.md §10`

Add a Tier-3 (implementation) sub-section to the existing Autonomous Mode contract. Define how `--auto` behaves for implementation skills:

- Implies producing a PR (not an issue). Does NOT imply `--output github`.
- Never merges. PR-opened is the terminal artifact.
- Skips all user gates. Replaces interactive challenge rounds with "trust the caller has vetted the plan" — the upstream planning skill is responsible for adversarial review.
- Requires a target work item via `--source github <#>` or a plan path. No "browse" / picker mode in `--auto`.
- "Feels wrong" exits return `outcome: blocked` with a `blocker_description` field rather than stopping for user discussion.
- Emits the structured result (§5.2) at the end of the run.

Also update the §10 compatibility matrix to include `/implement-plan` (Tier 3: ✅ with auto).

### 5.2 Structured result shape

Every `--auto` run, regardless of tier or skill, emits a single fenced JSON block as its final output:

```json
{
  "skill": "implement-plan",
  "outcome": "completed | bypassed | needs-input | blocked | partial",
  "artifacts": {
    "issues_created": ["https://github.com/org/repo/issues/123"],
    "pr_url": "https://github.com/org/repo/pull/456",
    "files_changed": 3,
    "lines_added": 47,
    "lines_removed": 12,
    "branch": "implement/some-slug"
  },
  "summary": "Resolved dedup at staging layer per QUALIFY pattern. PR includes verification evidence.",
  "next": "Apply same pattern to stg_protocols if confirmed working.",
  "errors": [],
  "blocker_description": null
}
```

Field rules:
- `outcome` is required and constrained to the five values above.
- `artifacts` keys are optional — only those relevant to this skill's output appear. `pr_url` for implementation skills; `issues_created` for planning skills; both for skills that do both (e.g., `docs-review --auto` auto-fixes some things in a commit AND files issues for others).
- `summary` is 2-4 lines of human-readable for Telegram report-back.
- `next` is the orchestrator's hint for what to schedule after this run, or `null`.
- `blocker_description` is non-null only when `outcome == "blocked"` or `outcome == "needs-input"`.

`outcome` semantics:
- `completed` — work landed; PR or issues exist as expected.
- `bypassed` — explicit decision not to work this item (heavy-refactor tripwire, scope-exceeded, etc.). The orchestrator should not retry without policy change.
- `needs-input` — work cannot proceed without a human decision (ambiguous design, conflicting plans). A comment was posted; the orchestrator may surface to a human.
- `blocked` — work attempted but couldn't complete due to environment or unresolved internal contradiction. Retryable in principle, but the orchestrator should treat it as suspect until investigated.
- `partial` — some progress made, but not the full outcome (e.g., 3 of 5 issues filed; or implementation reached but verification regressed). Followup needed.

### 5.3 Adversarial-review at end of planning skills

Add to each planning skill (`tech-debt`, `security-audit`, `product-enhance`, `frontend-performance-audit`, `docs-review`, `access-path-audit`) a step at the end of plan generation that invokes:

```
Task(subagent_type: general-purpose,
     prompt: "Read /claudna:adversarial-review skill body. Apply with --dispatch mode to the plan at <plan-path>. Return structured critique findings only. Do not enter Plan Mode. Do not invoke AskUserQuestion.")
```

The planning skill folds the returned critique into the plan body (new "Adversarial Review Findings" section, or inline annotations against specific recommendations) before publishing.

Applies in **all modes** — interactive and `--auto`. The interactive user gets a vetted plan; the orchestrator gets a vetted plan downstream.

Update `/claudna:adversarial-review` itself: when invoked with `--dispatch`, suppress Plan Mode entry and AskUserQuestion calls. Return structured findings via stdout (matching §5.2 shape, with `outcome: completed` and findings in `summary` and an `artifacts.findings_count`). Without `--dispatch`, current interactive behavior preserved.

### 5.4 /simplify chain in /implement-plan

Add Step 6.5 to `/implement-plan` between current Steps 6 (Verify) and 7 (PR):

> **Step 6.5: Simplification pass.** If the diff at this point exceeds 50 LOC *or* touches 2+ files, invoke `/simplify` as a subagent on the changed files. Then re-run Step 6 verification.
>
> If post-simplify verification fails:
> - **Interactive mode**: present the regression to the user and ask whether to fix-forward or revert the simplify commit.
> - **`--auto` mode**: revert the simplify commit (`git reset --hard HEAD~1` if it was its own commit; or `git checkout` the affected files from pre-simplify state). Note the revert in the PR body. Proceed to Step 7.

Applies in **all modes**. No flag needed.

`/simplify` itself is unchanged — it already operates non-interactively against a working tree and reshapes the recent changes.

### 5.5 /implement-plan --auto

New argument: `--auto` (alias: `--autonomous`).

Step-by-step behavior changes:

| Step | Interactive | `--auto` |
|---|---|---|
| 1: Receive plan | Path/issue picker as today | Requires `--source github <#>` or explicit path; no picker |
| 1.5: Plan-detail check | Offers to expand findings-only issues | **Refuses** sparse issues: exits with `outcome: blocked`, `blocker_description: "issue lacks ## Implementation Plan section; run a planning skill to generate one"` |
| 2: Codebase comparison | Same | Same |
| 2.5: Scope-expansion tripwire | n/a (challenge round catches design issues) | **New** — if Step 2 reveals scope significantly larger than the plan describes (e.g., 3-file plan touches 15 files in actual dependency graph), exit with `outcome: bypassed`, `blocker_description: "scope exceeded plan: <details>"`. This is a *surprise* tripwire, not a size threshold — fires when reality contradicts the plan, not when reality is "large." |
| 3: Challenge round | **Revised** — see §5.5.1. Open adversarial findings seed the round; full matrix runs after. | **Replaced by synthesis pass** — see §5.5.2. Open adversarial findings + matrix concerns packaged and handed to `/claudna:weigh-development-paths --auto` to synthesize a final refined plan. |
| 4: Mark in-progress | Same | Same |
| 5: Branch + implement | "Feels wrong → stop and discuss" | "Feels wrong" → exit with `outcome: blocked`, `blocker_description: <specifics>` |
| 6: Verify | Fix-and-retry on failure | Same; persistent failure → `outcome: partial` with details |
| 6.5: Simplify | Ask user on regression | Revert simplify on regression, proceed |
| 7: PR | Open PR | Open PR |
| 8: Merge gate | Offer merge/stop | **Skipped entirely** |
| 9: Summary | Human-readable | Structured result per §5.2 |

The scope-expansion tripwire (Step 2.5) is `--auto` only. Interactive users can ratify scope changes via the challenge round and continue.

Queue mode (multi-issue) is disallowed in `--auto`: the orchestrator picks one work item per invocation. If invoked with `--auto` and an ambiguous source (e.g., directory of plans), exit with `outcome: blocked`, `blocker_description: "ambiguous source in --auto; specify single plan"`.

#### 5.5.1 Interactive Step 3 — adversarial findings seed the round

When the plan body contains an `## Adversarial Review Findings` section with OPEN items (not yet marked resolved):

1. First AskUserQuestion presents the open findings as items to address:
   *"Adversarial review flagged these unresolved concerns: A, B, C. Which to dig into?"*
   Options: each finding + "All" + "None — ready to build".
2. For each picked finding, drive matrix questions from `challenge-round-questions.md` scoped to that finding's concern area (architecture, testing, error handling, etc.).
3. As findings are addressed, update them in the plan body from OPEN to RESOLVED, recording the user's decision inline.
4. After all picked findings are addressed (or user declined to dig into any), run the full matrix-driven flow as today — even if every finding was resolved. The matrix may surface concerns adversarial-review didn't think to raise; an extra pass costs little and catches real issues.
5. Final "Ready to build?" gate as today.

When the plan body has no Adversarial Review Findings section (ad-hoc plan), the matrix-driven flow runs unchanged from today's behavior.

#### 5.5.2 --auto Step 3 — synthesis pass via /weigh-development-paths

In `--auto` mode, Step 3's human steering is replaced by machine synthesis:

1. **Extract OPEN adversarial findings** from the plan body.
2. **Generate machine-form matrix concerns** — read `challenge-round-questions.md`, produce the matrix questions relevant to this plan (architecture, testing, dependencies, error handling, etc.) as a list of decision points with concrete options drawn from the codebase comparison done in Step 2.
3. **Package context bundle** — the plan body + open findings + matrix decision points + Step 2 codebase-comparison artifacts.
4. **Invoke `/claudna:weigh-development-paths --auto`** (see §5.7) as a subagent with the bundle. The skill applies its 7-dimensional analysis to each open question, synthesizes recommendations, and returns a refined plan that resolves every open finding and matrix decision point.
5. **Adopt the refined plan** — write the refined plan back to the plan body (or comment on the source issue), marking findings RESOLVED with the synthesized rationale. The refined plan is what Steps 4+ implement.

If synthesis fails (e.g., `/weigh-development-paths --auto` returns `outcome: blocked` because a decision genuinely requires human input), exit `/implement-plan --auto` with `outcome: needs-input` and `blocker_description` containing the unresolvable decision points.

This makes `--auto` mode genuinely autonomous on well-formed plans while preserving the safety net of structured analysis — every open question is consciously resolved with rationale, not skipped.

### 5.6 /weigh-development-paths --auto

Add `--auto` mode to `/claudna:weigh-development-paths`. Behavior changes when `--auto` is set:

- Skip `EnterPlanMode` / `ExitPlanMode`.
- Skip any AskUserQuestion gates.
- Accept the context bundle from §5.5.2 as input (open findings + matrix decision points + plan + codebase artifacts).
- For each decision point in the bundle, run the 7-dimensional evaluation as today, but synthesize the recommendation directly (no human pick).
- Output: a refined plan document (or refined sections) that resolves every decision point, with a "Synthesis Rationale" block per resolution explaining which dimensions drove the choice.
- Emit structured result per §5.2: `outcome: completed` with the refined plan path/content in `artifacts.refined_plan`. If any decision is genuinely unresolvable without human input (insufficient evidence in any dimension), exit `outcome: blocked` with the unresolvable points listed.

Interactive mode is unchanged.

This makes `/weigh-development-paths` chainable from `/implement-plan --auto` and from any future skill that needs autonomous decision synthesis.

### 5.7 Normalize existing --auto skills

For each skill currently supporting `--auto` — `tech-debt`, `security-audit`, `product-enhance`, `frontend-performance-audit`, `docs-review`, `access-path-audit`, `product-vision`, `session-handoff`, `visual-crawl` — append the §5.2 structured result emission at the end of the `--auto` path. Existing behavior preserved; only the closing output changes.

For `docs-review --auto` specifically (which already does both auto-fix and issue-file): `artifacts.issues_created` lists the gaps filed as issues; `artifacts.files_changed` reflects the inline fixes committed.

---

## 6. claudlobby changes

### 6.1 New skill: `library/skills/autonomous-runner`

A single composable wrapper skill. Bots include it in fleet.yaml; the compositor bakes the relevant config into the bot's CLAUDE.md.

#### Configuration via fleet.yaml

```yaml
bots:
  - name: dbt-eng-bot
    expertise: data-engineering
    skills:
      - autonomous-runner:
          skill: /claudna:implement-plan
          cadence: 1h
          target_repo: artemis-xyz/dbt
          picker:
            type: github_issues
            label: claudna-eligible
            state: open
            score_by: mission_alignment   # | recency | priority_label
          bypass:
            risk_classifier: structural_vs_mechanical   # see §6.1.1
            block_on: [structural]                       # which risk classes trigger bypass
            on_bypass: comment_and_label                 # | comment_only | exit_silent
          pre_hooks: []
          post_hooks: []
          on_outcome:
            completed: report
            bypassed: report
            needs_input: report_and_pause
            blocked: report_and_pause
            partial: report
```

Other supported `skill` targets: any clauDNA procedural skill that supports `--auto`. The wrapper is skill-agnostic — `cadence`, `picker`, `bypass`, and `on_outcome` mean the same thing regardless of which clauDNA skill is being run.

For non-implementation skills (e.g., `skill: /claudna:tech-debt`), the `picker` block is optional — those skills scan their target repo without needing a pre-picked work item. `target_repo` always supplies the scope.

For arguments beyond what the picker supplies, the wrapper accepts a free-form `args:` block, appended verbatim to the skill invocation:

```yaml
autonomous-runner:
  skill: /claudna:tech-debt
  cadence: 6h
  target_repo: artemis-xyz/dbt
  args: "--scope models/ --output github"   # appended after --auto
```

`--auto` is always added by the wrapper; do not include it in `args`.

For `score_by: mission_alignment`, the wrapper reads `PROJECT_MISSION.md` from the target repo's default branch and uses its north star + guiding principles to score open issues. If the file is missing, falls back to `score_by: recency`.

#### Procedure

When the bot fires (per cadence):

1. **Idle check.** If a previous invocation is still running, exit. No overlap.
2. **Quota check.** Query Anthropic quota state via existing fleet-state mechanism. If near limit, beacon to Telegram per `continuous-autonomous-mode.md`, exit.
3. **Pick work item** (if `picker` configured). For `github_issues`: `gh issue list --repo <target_repo> --label <label> --state <state>`, score per `score_by`, take top one. If no eligible item, beacon "no work" and exit.
4. **Risk classification (qualitative bypass).** Dispatch a classifier subagent with the issue body + a read-only scan of the affected area. The classifier returns one of three classes (see §6.1.1). If the class is in `bypass.block_on`, execute `on_bypass`:
   - `comment_and_label`: post a comment summarizing why this change is risky for headless work, add `needs-input` label, return.
   - `comment_only`: post comment, no label.
   - `exit_silent`: log locally only.
   Exit without invoking the main skill.

   This is a *qualitative* check, not a size threshold. A 100-file mechanical rename is fine. A 3-file change that flips an abstraction is not. Size doesn't decide risk; structure does.
5. **Pre-hooks.** For each configured pre_hook, invoke as subagent. (Empty by default.)
6. **Invoke main skill.** Dispatch via Task subagent:
   ```
   Task(prompt: "/claudna:<skill> --source github <#> --auto" + skill-specific args)
   ```
7. **Parse structured result.** Read the fenced JSON block from the subagent's final output. Validate against §5.2 shape. On parse failure, treat as `outcome: blocked` with `blocker_description: "result parse failed"`.
8. **Post-hooks.** For each configured post_hook, invoke as subagent.
9. **Apply `on_outcome` policy.** `report` posts the summary to Telegram. `report_and_pause` posts to Telegram and additionally sets the bot to paused state (waits for human ratification before next cadence fire).
10. **Update fleet-state.** Append outcome, PR URL, issue URL, timestamp.

#### 6.1.1 Risk classifier — `structural_vs_mechanical`

The default `risk_classifier`. Reads the picked issue body, scans the files referenced, and outputs one of:

| Class | Examples | Headless-safe? |
|---|---|---|
| `mechanical` | Rename, reformat, dep-bump, doc fix, lint cleanup, codemod-style sweep | ✅ Yes — size doesn't matter |
| `localized` | Single-purpose feature/fix bounded within one module, single layer of the stack | ✅ Yes — within reason |
| `structural` | Cross-cutting refactor, API/contract change, abstraction shift, schema migration, anything that changes how callers must use the code | ⚠️ Default block — too easy to get wrong without human ratification |

The classifier is implemented as a subagent prompt that takes the issue body + a sample of affected files and emits one of the three labels with a one-line justification. The justification is posted in the bypass comment so the human reviewer sees the reasoning.

Bots can override `block_on` to be permissive (`block_on: []` — never bypass) or strict (`block_on: [structural, localized]` — only run pure mechanical changes).

The skill-side tripwire in `/implement-plan --auto` Step 2.5 is a *complementary* safety net: even if the wrapper classified the change as `localized` based on the issue text, Step 2's codebase comparison may reveal the change is actually structural in scope (e.g., the named function has 30 callers across the codebase). In that case, the skill exits with `outcome: bypassed`. Defense-in-depth without duplication: the wrapper assesses *intent*, the skill verifies *reality*.

#### Behavior the wrapper deliberately does NOT do

- Run adversarial-review on plans — that happens inside the planning skill that generated the plan (§5.3).
- Run /simplify on the diff — that happens inside `/implement-plan` (§5.4).
- Enforce factuality (test runs, type checks) — that happens inside `/implement-plan` Step 6.
- Make merge decisions — `--auto` skills never merge.
- Apply domain rules (e.g., dbt anti-patterns) — those live in `library/expertise/data-engineering.md` and are composed into the bot's CLAUDE.md.

The wrapper is a *thin coordinator* of policy: when to fire, what to pick, when to bypass, how to report. The discipline lives in the skills.

### 6.2 Documentation and bot archetype

Add a new bot archetype entry to `docs/bot-archetypes.md`: "Autonomous Worker" — describes the wrapper skill, common config patterns, and example fleet.yaml blocks for typical use cases (issue-resolver, rolling tech-debt-auditor, rolling security-auditor).

---

## 7. Migration plan

Each phase is independently shippable.

### Phase 1 — clauDNA contract (prerequisite)
1. Update `skills/_shared/orchestration-guide.md §10` per §5.1 + §5.2 (Tier-3 sub-section + structured result shape).
2. Update `/claudna:adversarial-review` per §5.3 (`--dispatch` implies non-interactive, structured findings output).
3. Add §5.2 structured-result emission to all existing `--auto` skills per §5.7.
4. Add `--auto` to `/claudna:weigh-development-paths` per §5.6.

### Phase 2 — clauDNA discipline chains
5. Add adversarial-review chain to each planning skill per §5.3.
6. Add `/simplify` Step 6.5 to `/implement-plan` per §5.4.
7. Revise interactive Step 3 in `/implement-plan` per §5.5.1 (open findings seed; full matrix runs after).

### Phase 3 — `/implement-plan --auto`
8. Add `--auto` to `/implement-plan` per §5.5, including the §5.5.2 synthesis pass that invokes `/weigh-development-paths --auto`.
9. Add Step 1.5 (sparse-issue refusal) and Step 2.5 (scope-expansion tripwire) per §5.5.

### Phase 4 — claudlobby wrapper
10. Build `library/skills/autonomous-runner` in claudlobby per §6.1.
11. Implement the `structural_vs_mechanical` risk classifier subagent per §6.1.1.
12. Wire fleet.yaml schema (update `claudlobby/validator.py`, `claudlobby/loader.py`).
13. Add bot archetype docs per §6.2.
14. Compose a single-bot fleet using `autonomous-runner` against `artemis-xyz/dbt` as the validation deployment.

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Implement-plan `--auto` produces low-quality PRs because the challenge round was skipped | Adversarial review at planning time (§5.3) is now mandatory upstream. Plans reaching implement-plan are pre-vetted. For ad-hoc human-written plans, run `/adversarial-review` manually before `/implement-plan --auto`. |
| Structured-result shape doesn't fit a future skill | The shape is permissive (`artifacts` is open-ended). Add new fields backward-compatibly. |
| Sub-skill subagent dispatches blow up orchestrator context | All sub-skill invocations follow the existing disk-write subagent pattern (§3 of orchestration guide). Subagents return summaries; full output stays on disk. |
| Wrapper config schema drifts from clauDNA `--auto` argument shapes | The wrapper's `skill:` field references the clauDNA skill name only; per-skill args go in a free-form `args:` block or are constructed by the wrapper from picker output. CI test: `autonomous-runner` against each supported skill name resolves cleanly. |
| `/simplify` post-implementation regresses verification in `--auto`, gets reverted silently, masks real bugs | Revert is logged in the PR body. Reviewer sees "Simplify pass attempted; reverted due to regression: <details>." Treated as a signal for follow-up, not failure. |
| Heavy-refactor bypass tripwire produces false positives, wastes bot cycles | Threshold is per-bot config. Start conservative (high thresholds, few bypasses); tune based on telemetry. |
| Two skills both want to chain a third skill, leading to nested subagent depth | Document the depth limit (1 level of sub-skill chaining per skill body). If a chain wants more, lift the chain to claudlobby's wrapper. |

---

## 9. Open questions

1. **Sub-skill argument passing.** When a planning skill chains adversarial-review, how does it pass the plan path? Today `/adversarial-review` takes a positional plan-file-path arg. The subagent dispatch prompt template should be standardized.
2. **`--auto` for skills not yet on the §10 compatibility matrix.** `/visual-crawl` and `/product-vision` partly support `--auto` already with different semantics. Confirm their normalized result shapes match §5.2 exactly during Phase 1.
3. **Fleet-state.json schema extension.** The wrapper needs to write outcome history per bot. Confirm the existing fleet-state ledger has room or needs a `runs:` sub-tree.
4. **What happens if `/implement-plan --auto` succeeds but the PR is closed by a human without merging?** Out of scope for v1 — the wrapper doesn't poll PR status. Could become a follow-up signal (re-trigger if PR closed without merge).

---

## 10. Outcomes

- A claudlobby bot is assigned a single procedural skill, a target repo, and a cadence — and runs that skill autonomously with full quality discipline already inside the skill.
- A human invoking any clauDNA skill interactively gets the same discipline as the bot (adversarial-review on plans, /simplify on diffs, factuality enforcement).
- A future skill that wants to chain `/adversarial-review` or `/simplify` does so via the established subagent-dispatch pattern with no per-skill special handling.
- One parser in claudlobby reads any clauDNA `--auto` skill's result via the §5.2 contract.
- The user's hand-rolled `/loop` prompt is replaced by a ~10-line `fleet.yaml` block.
