---
name: align-to-mission
description: "Use when you want to check whether every phase in a plan serves the project's stated mission. Catches scope creep, tangential work, misaligned success metrics, and aggregate drift from the north star."
argument-hint: "[plan-file-path] [--dispatch]"
---

# Align to Mission

Check whether every phase and deliverable in a plan serves the project's north star. Plans accumulate scope naturally — individually-reasonable phases can drift from the mission in aggregate. This skill compares each phase against the mission and flags misalignment before resources are committed.

**This is a plan-only lens.** It reads the plan document and the project's mission source. It does not read the target codebase (that is `/extension-check`'s job).

## Arguments

Parse `$ARGUMENTS` at invocation:

- **First positional arg:** Path to the plan document. If omitted, prompt for it.
- `--dispatch`: Non-interactive mode for fleet orchestration. Suppresses all interactive elements (no Plan Mode, no AskUserQuestion). Emits a single markdown document with YAML frontmatter per `skills/_shared/contracts/lens-result-contract.md`. Use this when invoked by `/ironclad` or another orchestrator.

---

## `--dispatch` Mode

When `--dispatch` is passed:

- **Do NOT call `EnterPlanMode`.** The dispatcher owns the lifecycle.
- **Do NOT call `AskUserQuestion`.** No human is present.
- **Do NOT prompt for clarification.** If the plan lacks phases or is too ambiguous to assess, emit `status: blocked` with a description of what is missing.
- Execute the procedure below silently.
- Emit the structured markdown result as the FINAL output and stop. No text after the result document.

When `--dispatch` is NOT passed, follow the interactive procedure (see Interactive Mode below).

---

## Procedure

### Step 1: Read the Plan

Read the full plan document. Identify:

- **Goal / Problem Statement** — what the plan claims to solve.
- **Phases** — the breakdown of work. Each phase is assessed individually.
- **Decision Forks** — choices that may affect alignment.
- **Validation Strategy** — success criteria the plan defines for itself.

If the plan lacks identifiable phases, stop. In `--dispatch` mode, emit `status: blocked`. In interactive mode, tell the user the plan needs a phased breakdown before alignment analysis is meaningful.

### Step 2: Locate the Mission

Find the project's north-star statement using this fallback hierarchy:

1. **`PROJECT_MISSION.md`** in the repo root — the canonical source.
2. **`README.md`** mission/purpose section — extract the north-star statement.
3. **GitHub repo description** — the one-liner from the repo settings (if accessible).
4. **`CLAUDE.md`** purpose/description section — the repo's self-description for Claude Code.

Use the **first source that yields a usable mission statement** — a concrete statement of what the project exists to achieve, not a list of features or technical description.

If none of these yield a usable mission statement, do NOT block. Instead:
- Emit an `info`-severity finding recommending the team create a `PROJECT_MISSION.md`.
- Infer the mission from the plan's own Goal section and proceed with that as the working mission. Note explicitly that you are using the plan's goal as a proxy — this weakens the analysis because the plan is being compared against itself.

### Step 3: Per-Phase Alignment Assessment

For each phase or deliverable in the plan, assess:

#### 3a: Does This Phase Serve the Mission?

Classify each phase into one of three categories:

- **Aligned** — directly advances the north star. The phase would not exist without the mission.
- **Tangential** — useful work, but not mission-critical. Could be deferred or cut without harming the mission. Examples: documentation cleanup, nice-to-have tooling, speculative features.
- **Misaligned** — actively pulls away from the mission. Introduces scope, dependencies, or complexity that does not serve the north star. Rare but high-impact when found.

#### 3b: Are Success Metrics Aligned?

If the plan defines validation criteria or success metrics for a phase:
- Do those metrics measure progress toward the mission, or do they measure something else?
- Could a phase pass its own validation criteria while failing to advance the mission?

#### 3c: Is the Phase Proportionate?

- Does the effort size (S/M/L/XL) match the mission importance of the deliverable?
- A large phase for a tangential deliverable is a signal — the plan may be over-investing in non-mission work.

### Step 4: Aggregate Drift Check

After assessing individual phases, step back and check the plan as a whole:

- **Ratio check:** What fraction of the plan's phases are tangential or misaligned? A plan where most phases are aligned but one is tangential is healthy. A plan where half the phases are tangential has drifted.
- **Cumulative scope:** Do the individually-tangential phases add up to a significant scope commitment? Three small tangential phases may collectively represent more effort than the core mission work.
- **Mission coverage:** Does the plan address the mission comprehensively, or does it leave mission-critical areas untouched while investing in adjacent concerns?
- **Metric alignment:** Do the plan's aggregate validation criteria, taken together, confirm the mission will be advanced? Or could all criteria pass while the mission remains unserved?

### Step 5: Emit Findings

Classify each finding using the severity vocabulary defined in `skills/_shared/contracts/lens-result-contract.md` (`critical` > `major` > `minor` > `info`).

Tag each finding with a concern area. This skill's primary concern area is `scope`. Secondary: `architecture` (when misalignment stems from structural choices). Use the closest match from the canonical set in the contract.

Map findings to body sections:

| Section | Typical findings |
|---------|-----------------|
| **Blockers** | Phase actively misaligned with mission; plan's success criteria could pass while mission fails |
| **Risks** | Aggregate drift — most effort goes to tangential work; mission-critical areas left unaddressed |
| **Gaps** | Mission coverage holes — areas the mission demands that the plan does not touch |
| **Questions** | Ambiguous alignment — phase could serve the mission depending on interpretation |
| **Observations** | Tangential phases that could be deferred; no mission source found (suggest creating one) |

---

## Structured Result Emission (`--dispatch` only)

After Step 5, emit a single markdown document with YAML frontmatter as the FINAL output. No text before or after this document.

**Format:** Follow the canonical schema at `skills/_shared/contracts/lens-result-contract.md`. That contract is the single source of truth for all lens skill `--dispatch` output.

For this skill, set `lens: align-to-mission` in frontmatter. All other fields, severity vocabulary, body sections (Blockers/Risks/Gaps/Questions/Observations), concern area values, and blocked/failed output shape are defined in the contract.

---

## Interactive Mode (no `--dispatch`)

When invoked without `--dispatch`, this skill is an **advisor**, not a report generator.

**Enter Plan Mode.** Call `EnterPlanMode`. All analysis is read-only.

Execute Steps 1-5 above, then present findings as an advisory conversation:

### Advisory Format

Lead with the mission statement (Step 2) and a per-phase alignment summary table. Then present each concern with options and leans.

For each finding, present:

1. **The concern** — what the assessment revealed, stated concretely.
2. **Options** — 2-3 ways the plan could address the concern (including "keep as-is" when the concern is minor).
3. **Lean** — which option you'd pick and why, in one sentence.
4. **Rationale** — the reasoning behind the lean, grounded in the mission.

### Example Advisory Output

```
## Mission Alignment Review: [Plan Title]

### Mission
[The north-star statement, with source noted]

### Phase Alignment Summary

| Phase | Alignment | Notes |
|-------|-----------|-------|
| 2a. [name] | Aligned | Directly serves [mission aspect] |
| 2b. [name] | Tangential | Useful but not mission-critical |
| 2c. [name] | Aligned | ... |

### Aggregate Assessment
[Does the plan as a whole advance the mission? Ratio of aligned/tangential/misaligned.]

### Concerns

**Concern:** Phase 2b is tangential — [explanation]
- **(a)** Defer to a follow-up plan
- **(b)** Keep but reduce scope to [specific cut]
- **(c)** Keep as-is — the tangential work enables future mission-critical work
- **Lean:** (a) — [one-sentence reason grounded in mission]
```

Use one heading per concern. Phases that are cleanly aligned need only their summary table row — no separate section.

---

## Relationship to `/adversarial-review`

`/adversarial-review` touches mission alignment tangentially across its seven lenses but does not dedicate a full pass to it. This standalone skill gives mission alignment a full context window and structured per-phase assessment for independent fleet dispatch by `/ironclad`.

---

## Red Flags — You Are Doing This Wrong

| Symptom | Problem |
|---------|---------|
| Every phase is "aligned" | You are pattern-matching on topic similarity, not assessing mission criticality. A phase about the same domain is not automatically mission-aligned. |
| You assessed alignment without stating the mission first | The mission is the anchor. Without it, alignment is opinion. Go back to Step 2. |
| You flagged a phase as misaligned but cannot explain what mission it pulls away from | Misaligned requires a direction — away from what? Restate the conflict concretely. |
| You skipped the aggregate drift check | Individual phases can each look reasonable while the sum drifts. Step 4 is mandatory. |
| You are evaluating implementation quality, not mission alignment | This lens checks *what* the plan builds, not *how well* it builds it. Implementation quality is other lenses' job. |
| You blocked on missing PROJECT_MISSION.md | Missing mission source is info-severity, not a blocker. Use the fallback hierarchy or infer from the plan's Goal. |
