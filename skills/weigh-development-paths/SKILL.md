---
name: weigh-development-paths
user-invocable: true
description: "Use when at a development junction with multiple viable approaches — architecture choices, refactoring strategies, where to put new code, or which pattern to follow. Triggers on 'which approach', 'how should I', 'Option A vs B', or any point where the next step isn't obvious and the wrong choice creates rework. Supports --output github to create issues and --output session for chat-only analysis."
argument-hint: "[--output github|session] [junction-description]"
---

# Weigh Development Paths

Structured multi-dimensional evaluation for development junctions.

**Enter Plan Mode.** Call `EnterPlanMode` to enter deliberation mode. All analysis is read-only — plan mode enforces this. If the user declines plan mode, proceed normally.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--output github`: Write findings and plans as GitHub Issues. See output guide (`skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Remaining text is the junction description or context.

Default (no flag): Present analysis in chat (session-only by default).

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

This skill supports `--output github` and `--output session` in addition to the default `session` target.

Follow the output guide at `skills/_shared/output-guide.md`:
- For `github`: use the structured issue body format (Section 4), check for duplicates (Section 4.5), apply labels (Section 4.3). Create one issue documenting the junction analysis — include the comparison matrix, holistic assessment, and recommendation. Label with `auto-audit` and `enhancement`.
- For `session` (default): present findings in chat, stay in Plan Mode (Section 5)
- For `docs`: write the full analysis to `documentation/planning/decisions/<session_name>_<YYYY-MM-DD>/`

---

## When NOT to Use This

- One option is clearly correct — just do it
- The decision is trivial (naming, formatting, minor placement)
- You are procrastinating instead of building — if the analysis feels like stalling, it probably is
