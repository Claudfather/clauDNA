---
name: weigh-development-paths
user-invocable: true
description: "Use when at a development junction with multiple viable approaches — architecture choices, refactoring strategies, where to put new code, or which pattern to follow. Triggers on 'which approach', 'how should I', 'Option A vs B', or any point where the next step isn't obvious and the wrong choice creates rework."
argument-hint: "[--auto] [--output artifacts|docs|github|vault|notion|session] [junction-description-or-bundle-path]"
---

# Weigh Development Paths

> **Codex:** Read `../_shared/codex-tools.md` before following this skill. Apply its tool, root and dispatch mappings throughout.

Structured multi-dimensional evaluation for development junctions.

Follow `../_shared/orchestration-guide.md` §1 for native session allocation and exact-owner cleanup. Private comparison notes and working bundles stay in `<scratch>`; the sanitized comparison and refined plan default to `<artifacts>`. `--output artifacts` is the explicit spelling of that default, including with `--auto`. Explicit `--output docs|github|vault|notion` exports the canonical revision and records actual outcome in the current session's private receipt (`docs` → `--to docs`, `github` → `--to github-issue --repo <repo>`, `vault` → `--to vault`, `notion` → `--to notion`). `--output session` is chat-only: no allocation or intermediate files. Missing/conflicting/unverified native identity or ordinary-permission denial stops persistence without cwd, operation-ID, or OS-temp fallback.

**Enter Plan Mode.** Call `EnterPlanMode` to enter deliberation mode. All analysis is read-only — plan mode enforces this. If the user declines plan mode, proceed normally.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Non-interactive synthesis mode. Suppresses Plan Mode and all interactive user-question gates. Requires a context bundle path in `$ARGUMENTS`. Defaults to a canonical refined-plan artifact and emits the structured-result shape from `../_shared/orchestration-guide.md` §10.C with the same plan in `artifacts.refined_plan`. See "Autonomous Mode" section below.
- `--output artifacts`: Save the sanitized analysis/refined plan under current-session artifacts (default).
- `--output docs|github|vault|notion`: Explicitly export the retained canonical document through the corresponding adapter (`github` maps to `--to github-issue --repo <repo>`); record actual URL/path/result in the private receipt. When called as a build synthesis producer, return the contract result to the caller and leave external publication to that caller.
- `--output github`: Write findings and plans as GitHub Issues. See output guide (`../_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Remaining text: the junction description (interactive mode) or path to a context bundle file (--auto mode).

Default (no flag): persist the sanitized analysis as a canonical artifact and present its result in chat. Use `--output session` for chat-only work with no disk writes.

## When to Use

You are mid-development — implementing a feature, executing a plan, or refactoring — and you hit a fork:

- "Should this live in module A or module B?"
- "Do we extend the existing pattern or introduce a new one?"
- "There are 3 ways to structure this — which one?"
- A plan step has multiple valid implementation strategies
- A code review surfaces an architectural alternative
- You're about to make a design choice that downstream work depends on

This is for **junctures** — moments where the next step isn't obvious and the wrong choice creates rework. Not for trivial decisions (naming, formatting) or situations where one option is clearly correct.

## The Rule

**Analyze first, recommend second.** You are an analyst presenting all perspectives, not an advocate arguing for a predetermined pick. Evaluate every option against every dimension before synthesizing a recommendation.

## Process

### Step 1: Frame the Junction

State clearly:
- What decision needs to be made
- What options are on the table (minimum 2, identify any the user missed)
- What constraints exist (timeline, existing patterns, team preferences, plan phases)

### Step 2: Evaluate Each Dimension

For **each option**, evaluate against **all 7 dimensions**. Do not skip dimensions. Do not evaluate only your preferred option.

| Dimension | What to Evaluate |
|-----------|-----------------|
| **Elegance** | Simplicity, clarity, minimal moving parts. Does it feel like the natural solution? |
| **Existing Patterns** | Does it leverage code paths, conventions, and architecture already in the codebase? |
| **Extension** | Does it extend current code naturally, or require new abstractions? |
| **DRY** | Does it reduce duplication, or introduce new redundancy? |
| **Separation of Concerns** | Are responsibilities cleanly divided? Does it mix unrelated concerns? |
| **Future-Proofing** | How well does it accommodate likely future changes without over-engineering for unlikely ones? |
| **Plan Alignment** | Does it support upcoming plan phases, or create obstacles for future steps? |

### Step 3: Build the Comparison Matrix

Present a table. Every cell must be filled. No blanks, no "N/A".

```
| Dimension           | Option A        | Option B        | Option C        |
|---------------------|-----------------|-----------------|-----------------|
| Elegance            | [assessment]    | [assessment]    | [assessment]    |
| Existing Patterns   | [assessment]    | [assessment]    | [assessment]    |
| Extension           | [assessment]    | [assessment]    | [assessment]    |
| DRY                 | [assessment]    | [assessment]    | [assessment]    |
| Separation          | [assessment]    | [assessment]    | [assessment]    |
| Future-Proofing     | [assessment]    | [assessment]    | [assessment]    |
| Plan Alignment      | [assessment]    | [assessment]    | [assessment]    |
```

### Step 4: Assess Holistically

For each option, synthesize across dimensions:
- **Behavioral effectiveness** — Does it make the system behave correctly and predictably?
- **Functional completeness** — Does it deliver the needed capability fully?
- **Tech debt trajectory** — Does it reduce, maintain, or increase technical debt?

### Step 5: Recommend

State your recommendation with:
1. Which option wins overall
2. What you lose by not picking the runners-up (tradeoffs are real — name them)
3. Any conditions that would change your recommendation

## Red Flags — You Are Doing This Wrong

- **Jumping to a recommendation before completing the matrix** — The matrix IS the analysis. Fill it out first.
- **Leaving cells blank or writing "N/A"** — Every option has something to say for every dimension. Think harder.
- **Evaluating only your preferred option in depth** — If your non-preferred options get one-sentence assessments while your pick gets paragraphs, you are advocating, not analyzing.
- **Ignoring the codebase** — Read the actual code and plans before filling the matrix. Your assessments must reflect what exists, not what you imagine.
- **Over-engineering in the name of "future-proofing"** — Future-proofing means accommodating *likely* changes, not building for every hypothetical. The most future-proof code is often the simplest.

---

## Output Targets

This skill supports `--output artifacts` (default), explicit `docs|github|vault|notion` exports, and `--output session` (chat only).

Follow the output guide at `../_shared/output-guide.md`:
- For `artifacts` (default): write the sanitized analysis and refined plan to `<artifacts>/weigh-development-paths/<junction>.md`; keep private comparison notes in scratch.
- For explicit `github`: retain the canonical decision document, then publish the selected analysis as an issue with output-guide frontmatter and Section 4 body skeleton, tagged `auto-audit` and `enhancement`; include the comparison matrix, holistic assessment, and recommendation, and record actual URL/status in the private receipt.
- For explicit `session`: present the analysis in chat without allocation or file writes.
- For explicit `docs`: retain the canonical decision document, then publish it with `type: decision` to `documentation/planning/decisions/<session_name>_<YYYY-MM-DD>/`; decision records use knowledge-tier validation, so the Section 4 implementation-plan skeleton gate does not apply. Record the actual result in the private receipt.
- For explicit `vault` or `notion`: retain the canonical decision document, then export through the chosen adapter with a private receipt.

---

## When NOT to Use This

- One option is clearly correct — just do it
- The decision is trivial (naming, formatting, minor placement)
- You are procrastinating instead of building — if the analysis feels like stalling, it probably is

---

## Autonomous Mode (`--auto`)

`weigh-development-paths --auto <bundle-path>` runs the synthesis non-interactively — it's the **synthesis pass** that `build --auto` delegates to when a plan has open decisions. No human, no plan mode, no prompts. Contract: `../_shared/contracts/synthesis-contract.md`.

### Input contract

`$ARGUMENTS` after the `--auto` flag MUST contain a path to a context bundle file — the only argument. The bundle carries `## Open decisions` (one block per junction needing resolution, each with its options, source, and context), `## Codebase-comparison artifacts` (so the Existing-Patterns / Extension / DRY dimensions are grounded — do **not** re-explore the codebase; the consumer already did Step 2 and handed you its findings), and the full `## Plan`. Exact shape: `../_shared/contracts/synthesis-contract.md`.

If the bundle is missing/unreadable or has zero open decisions, emit the §10.C block with `outcome: "blocked"` and stop — an empty synthesis is the consumer's bug, not a resolution.

### Procedure

When `--auto` is active:

1. **Do NOT call `EnterPlanMode`.** The caller manages mode.
2. **Do NOT issue interactive user-question prompts.** Synthesize machine recommendations directly. Any tool that would halt for user input is forbidden in this mode.
3. Parse the bundle.
4. For **each** open junction, run Steps 1–5 exactly as above (frame → 7-dimension evaluation → matrix → holistic → recommend) — but grounded in the bundle, not live exploration. Then resolve:
   - **Technical comparison** (one option wins on the dimensions, even narrowly, or it's a genuine tie) → **resolve it.** A tie is still a pick; Step 5 names what's lost. Goes to `decisions_resolved`.
   - **Not the matrix's call** (the junction hinges on a human value / policy / security / cost decision the dimensions can't settle — e.g. "bot identity vs personal key") → do **not** force a pick. Goes to `decisions_unresolved`.
5. Assemble a refined plan: take the original plan body and replace/augment each ambiguous section with the synthesis result. Mark each formerly-open item as RESOLVED with the rationale inline. By default, save this same refined plan under `<artifacts>/weigh-development-paths/synthesis-<bundle-name>.md` before emitting the structured result; if the caller explicitly selected session output, make no file writes.

### Output (structured result)

The canonical schema for this output is `../_shared/contracts/synthesis-contract.md`. When this skill is invoked as the synthesis producer (typically by `/claudna:build --auto`), the consumer parses against that contract. If you change the shape here, update `../_shared/contracts/synthesis-contract.md` in the same commit.

Emit exactly one fenced ```json §10.C block (the FINAL output, nothing after it), shaped per the synthesis-contract: `skill: "weigh-development-paths"`, `artifacts.refined_plan` (the plan body with every resolved choice woven in), `artifacts.decisions_resolved` / `decisions_unresolved` (junction-keyed arrays, not counts — see the contract), and `artifacts.synthesis_rationales` (the per-dimension reasoning behind each pick, keyed by junction id, as the audit trail).

**Outcome:** `completed` when every junction resolved (`decisions_unresolved` empty); `needs-input` when one or more need a human call (set `blocker_description` to the unresolved junctions); `blocked` for a malformed/empty bundle — a contract error, not a decision gap.

### Restrictions in `--auto` mode

- Do NOT write to the original plan file unless explicitly given a write path in the bundle.
- Do NOT open Plan Mode.
- Do NOT ask questions.
- Do NOT publish externally from a build-synthesis invocation; `--auto` returns the refined plan to its caller in the existing structured-result contract. Its canonical artifact is the same result for durable recovery, not an independently edited copy. For standalone `--auto`, honor an explicit non-session output target and record the actual result.
- Do NOT re-explore the codebase — use the bundle's `## Codebase-comparison artifacts`.
- Do NOT print anything after the JSON block.
