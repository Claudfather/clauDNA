---
name: weigh-development-paths
user-invocable: true
description: "Use when at a development junction with multiple viable approaches — architecture choices, refactoring strategies, where to put new code, or which pattern to follow. Triggers on 'which approach', 'how should I', 'Option A vs B', or any point where the next step isn't obvious and the wrong choice creates rework."
argument-hint: "[--auto] [--output github|session] [junction-description-or-bundle-path]"
---

# Weigh Development Paths

Structured multi-dimensional evaluation for development junctions.

**Enter Plan Mode.** Call `EnterPlanMode` to enter deliberation mode. All analysis is read-only — plan mode enforces this. If the user declines plan mode, proceed normally.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Non-interactive synthesis mode. Suppresses Plan Mode and all interactive user-question gates. Requires a context bundle path or inline bundle in `$ARGUMENTS`. Emits the structured-result shape from `skills/_shared/orchestration-guide.md` §10.C with a refined plan in `artifacts.refined_plan`. See "Autonomous Mode" section below.
- `--output github`: Write findings and plans as GitHub Issues. See output guide (`skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Remaining text: the junction description (interactive mode) or path to a context bundle file (--auto mode).

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
- For `github`: write each finding as a doc (frontmatter + the Section 4 body skeleton) and delegate to `/claudna:publish <file> --to github-issue --repo <repo>` — publish validates, dedups, and applies labels from `tags:`. Create one issue documenting the junction analysis — include the comparison matrix, holistic assessment, and recommendation. Label with `auto-audit` and `enhancement`.
- For `session` (default): produce the doc, then `/claudna:publish <file> --to session` prints it to chat (Section 5)
- For `docs`: author the full analysis as a publishable doc in scratch with `type: decision` (knowledge-tier validation — no §4.1 skeleton gate; a junction analysis is a decision record, not an implementation plan), then `/claudna:publish <file> --to docs --dir documentation/planning/decisions/<session_name>_<YYYY-MM-DD>/`

---

## When NOT to Use This

- One option is clearly correct — just do it
- The decision is trivial (naming, formatting, minor placement)
- You are procrastinating instead of building — if the analysis feels like stalling, it probably is

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
2. **Do NOT issue interactive user-question prompts.** Synthesize machine recommendations directly. Any tool that would halt for user input is forbidden in this mode.
3. Parse the bundle.
4. For each open finding AND each open matrix decision, treat it as a junction:
   - Generate candidate options (from the bundle when provided; synthesize otherwise).
   - Run the 7-dimensional analysis from the interactive procedure (do not skip dimensions).
   - Synthesize a recommendation. Capture a "Synthesis Rationale" stating which dimensions drove the choice.
5. Assemble a refined plan: take the original plan body and replace/augment each ambiguous section with the synthesis result. Mark each formerly-open item as RESOLVED with the rationale inline.
6. If any decision genuinely cannot be resolved without human input (insufficient evidence in any dimension), do NOT guess. List it as unresolved and exit `outcome: blocked` with that list in `blocker_description`.

### Output (structured result)

The canonical schema for this output is `skills/_shared/contracts/synthesis-contract.md`. When this skill is invoked as the synthesis producer (typically by `/claudna:implement-plan --auto`), the consumer parses against that contract. If you change the shape here, update `skills/_shared/contracts/synthesis-contract.md` in the same commit.

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
