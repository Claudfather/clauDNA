---
name: plan-health-audit
description: "Use when you want to check whether a /forge plan document is structurally complete, internally consistent, and ready for implementation. Catches missing sections, incomplete frontmatter, unsized phases, vague validation criteria, undocumented decision forks, and cross-reference gaps."
argument-hint: "[plan-file-path] [--dispatch]"
---

# Plan Health Audit

Structural completeness check for `/forge` plan documents. Is the plan well-formed, internally consistent, and ready for implementation? This skill is the convergence gate for `/ironclad` -- a plan that fails structural health cannot proceed to implementation regardless of what other lenses say.

**This is a plan-only lens.** It reads the plan document and checks its structure. It does not read the target codebase (that is `/extension-check`'s job). It does not assess whether the plan is a good idea (that is `/first-principles`' job). It answers one question: is this document structurally ready to implement?

Most checks in this skill are deterministic -- section presence, frontmatter completeness, effort size coverage, fork field presence. An LLM adds value in two areas: judging whether validation criteria are objectively testable (vs. vague), and assessing whether phase descriptions reference concrete deliverables (vs. hand-wavy goals). The skill marks where each check type applies.

## Arguments

Parse `$ARGUMENTS` at invocation:

- **First positional arg:** Path to the plan document. If omitted, prompt for it.
- `--dispatch`: Non-interactive mode for fleet orchestration. Suppresses all interactive elements (no Plan Mode, no AskUserQuestion). Emits a single markdown document with YAML frontmatter per `skills/_shared/contracts/lens-result-contract.md`. Use this when invoked by `/ironclad` or another orchestrator.

---

## `--dispatch` Mode

When `--dispatch` is passed:

- **Do NOT call `EnterPlanMode`.** The dispatcher owns the lifecycle.
- **Do NOT call `AskUserQuestion`.** No human is present.
- **Do NOT prompt for clarification.** If the plan is unreadable or not a markdown document, emit `status: blocked` with a description of what is wrong.
- Execute the procedure below silently.
- Emit the structured markdown result as the FINAL output and stop. No text after the result document.

When `--dispatch` is NOT passed, follow the interactive procedure (see Interactive Mode below).

---

## Procedure

### Step 1: Read the Plan

Read the full plan document. Determine whether it is a `/forge`-style plan by checking for the expected structure (YAML frontmatter + markdown body with section headings). If the document is not recognizable as a plan (e.g., it is code, a README, or an empty file), stop. In `--dispatch` mode, emit `status: blocked`. In interactive mode, tell the user this skill applies to `/forge` plan documents.

### Step 2: Frontmatter Completeness

**Check type: deterministic.**

Parse the YAML frontmatter. Check for all mandatory fields:

| Field | Required Value |
|-------|---------------|
| `title` | Non-empty string |
| `type` | Must be `plan` |
| `status` | One of: `draft`, `review`, `approved`, `active`, `completed`, `superseded` |
| `owner` | Non-empty string |
| `tags` | Non-empty list |
| `created` | Valid date (YYYY-MM-DD) |
| `updated` | Valid date (YYYY-MM-DD), not earlier than `created` |

Missing or malformed fields are findings. A plan with no frontmatter at all is a `critical` finding.

### Step 3: Mandatory Section Presence

**Check type: deterministic.**

Every `/forge` plan must contain these sections (matched by heading text, case-insensitive):

1. **Goal** -- problem statement and why the plan matters
2. **Current State** -- what exists today
3. **Architecture** -- target state design
4. **Phases** -- breakdown of work into sequential phases
5. **Decision Forks** -- explicit choice points (may contain "None identified")
6. **Companion Plans** -- cross-references (may contain "None identified")
7. **Dependencies** -- external and internal dependencies
8. **Risks** -- risk table with impact and mitigation
9. **Validation Strategy** -- how to verify the plan worked
10. **Complexity and Sequencing** -- phase sizing, ordering, parallelism

Scan the document's headings (H2 level: `## <Section Name>`). For each mandatory section:
- **Present:** continue to content checks in later steps.
- **Missing:** emit a finding. A single missing section is `major`. Three or more missing sections is `critical` (the plan is structurally incomplete).

### Step 4: Phase Health

**Check type: mixed (deterministic structure + LLM judgment on content).**

For each phase defined under `## Phases`:

#### 4a. Effort Sizing (deterministic)

Check that the phase appears in the Complexity and Sequencing table with an effort size (S, M, L, or XL). A phase without a size cannot be scheduled or parallelized.

#### 4b. Numbering Consistency (deterministic)

Check that phases are numbered sequentially and that sub-deliverable labels match their parent phase (e.g., Phase 2's sub-deliverables are 2a, 2b, 2c -- not 1a or 3a). Numbering gaps or mismatches are `minor` findings.

#### 4c. Concrete Deliverables (LLM judgment)

Each phase should reference specific deliverables -- files to create, endpoints to add, schemas to define, scripts to write. Flag phases whose descriptions are entirely abstract ("Build the integration layer", "Implement the feature") without naming any concrete artifact. This is a `major` finding -- a phase without concrete deliverables cannot be implemented by someone who didn't write the plan.

#### 4d. Complexity and Sequencing Table Match (deterministic)

Verify the Complexity and Sequencing table matches the phases defined in the Phases section:
- Every phase in the Phases section appears in the table.
- Every entry in the table corresponds to a phase in the Phases section.
- The "Depends on" and "Parallel with" columns reference valid phase identifiers.

Mismatches are `major` findings -- the table and the phases have drifted.

### Step 5: Decision Fork Health

**Check type: deterministic.**

**Purpose:** Validate that each fork has the structural fields needed for the decision-fork-lifecycle protocol. A locked fork with all fields present is the desired end state -- it means the decision was made. Do NOT generate findings for well-formed forks regardless of their status. Only emit findings when fields are genuinely missing.

The standard `/forge` fork format is:

```markdown
### Fork F1: <Title>
- **Context:** <Why this fork exists>
- **Options:**
  - **(a)** <Option A> — <trade-off>
  - **(b)** <Option B> — <trade-off>
- **Lean:** <Recommended option and why>
- **Ratifier:** <Who locks this>
- **Status:** open | locked
- **Evidence:** <Link to analysis or lock comment> (optional for open forks)
```

For each decision fork defined under `## Decision Forks`, check that these structural fields are present:

| Field | Required | Finding if Missing |
|-------|----------|-------------------|
| Fork ID (F1, F2, ...) | Yes | `minor` -- can't be referenced in discussions |
| Context | Yes | `major` -- reviewers can't understand the fork without context |
| Options (at least 2) | Yes | `critical` -- a fork with fewer than 2 listed options is not a fork |
| Lean | Yes | `major` -- the plan must express a recommendation |
| Ratifier | Yes | `major` -- unratified forks block convergence |
| Status (open/locked) | Yes | `minor` -- defaults to open, but should be explicit |

A fork that has all six fields present generates **zero findings** -- it is structurally complete. This is true whether the fork is open or locked. Locked forks with complete structure are healthy; do not flag them.

Also count (for the Health Summary):
- Total forks
- Open vs. locked forks
- Forks missing any of the above fields

### Step 6: Risk Coverage

**Check type: deterministic.**

For each risk in the `## Risks` section:

- Does it have an **impact level** (or equivalent severity indicator)?
- Does it have a **mitigation** (or "no mitigation identified" for open risks)?

A risk without an impact level is `minor` (can't prioritize). A risk without any mitigation is `minor` (acknowledged but unaddressed). A Risks section with zero entries is `major` -- every plan has risks, and zero means the author skipped the analysis.

### Step 7: Validation Criteria Testability

**Check type: LLM judgment.**

For each criterion in the `## Validation Strategy` section:

- Is it **objectively testable**? Could someone who didn't write the plan verify it unambiguously?
- Does it describe a specific, observable outcome?

Flag vague criteria. Examples:

| Vague (finding) | Testable (not a finding) |
|-----------------|--------------------------|
| "Works correctly" | "Returns 200 with valid JSON matching schema X" |
| "Performs well" | "P95 latency under 200ms at 100 RPS" |
| "Code is clean" | "Passes `scripts/validate-skills.py` with zero errors" |
| "Users can use it" | "Invoke `/skill --dispatch` on the Phase 1 plan doc; verify frontmatter fields and body structure" |
| "No regressions" | "Full test suite passes (`pytest`, exit code 0)" |

Each vague criterion is a `major` finding -- vague validation criteria cannot gate convergence.

### Step 8: Cross-Reference Integrity

**Check type: deterministic (existence checks).**

Scan the plan for references to other documents:

- **Companion plan references** (`## Companion Plans`) -- do the referenced files exist at the paths stated? Use `Read` or `Glob` to verify.
- **Dependency references** (`## Dependencies`) -- are referenced PRs, issues, or files identifiable? (URLs don't need validation, but file paths do.)
- **In-body file path references** -- any path mentioned in the plan body (e.g., `skills/foo/SKILL.md`, `documentation/planning/bar.md`) should exist if the plan claims it exists. Flag references to nonexistent files as `minor` (they may be planned deliverables -- check context).

Count total references checked and broken references for the health summary.

**Note:** These are filesystem checks on companion plans, shared docs, and planning files -- not target codebase reads. The "plan-only" scope means this skill does not read the repo the plan proposes to modify; it does read the filesystem to verify that referenced documents exist.

**Scope boundary:** This skill verifies that references point to things that exist. It does not verify that the referenced content is accurate or up-to-date -- that is `/extension-check`'s job for codebase references and `/precedent-check`'s job for historical references.

### Step 9: None-Identified Density

**Check type: deterministic.**

Count mandatory sections (from Step 3) whose entire body — all content between this section's heading and the next H2 — consists solely of a dismissive placeholder. A section counts as "none-identified" if its body, after trimming whitespace, matches any of these exact phrases (case-insensitive):

- "None identified"
- "None"
- "N/A"
- "Not applicable"
- "TBD"

A section with ANY additional text beyond the placeholder (e.g., "None identified — will revisit in Phase 2") does NOT count. It has real content, even if thin.

- 0-2 sections: normal. Some plans genuinely have no companion plans or no decision forks.
- 3+ sections: `major` finding. The plan is likely undercooked -- the author skimmed rather than researched. This echoes `/forge`'s own self-audit check.

### Step 10: Compute Health Summary

Aggregate all findings and compute a health verdict:

| Verdict | Criteria |
|---------|----------|
| `ready` | Zero `critical` and zero `major` findings. The plan is structurally sound. |
| `needs-work` | Zero `critical` but one or more `major` findings. Addressable without restructuring. |
| `blocked` | One or more `critical` findings. The plan has structural problems that prevent implementation. |

Include the health verdict in the output (both `--dispatch` and interactive modes).

### Step 11: Emit Findings

Assemble the findings classified in Steps 2-9 into the output format. Severity assignments from each step are final -- do not re-evaluate them here. Use the severity vocabulary defined in `skills/_shared/contracts/lens-result-contract.md` (`critical` > `major` > `minor` > `info`).

Tag each finding with a concern area. This skill's primary concern area is `scope` (missing sections, incomplete coverage). Secondary: `architecture` (when structural issues reflect design gaps, e.g., phases without concrete deliverables suggest the architecture isn't thought through).

Map findings to body sections:

| Section | Typical findings |
|---------|-----------------|
| **Blockers** | No frontmatter; 3+ mandatory sections missing; fork with one option |
| **Risks** | Missing effort sizes; vague validation criteria; zero-risk Risks section; phases without concrete deliverables |
| **Gaps** | Missing fork fields (context, lean, ratifier); risks without impact/mitigation; broken cross-references |
| **Questions** | Ambiguous section that could be interpreted as present or absent; phases that might be concrete enough depending on context |
| **Observations** | None-identified density below threshold; minor numbering inconsistencies; health verdict summary |

---

## Structured Result Emission (`--dispatch` only)

After Step 11, emit a single markdown document with YAML frontmatter as the FINAL output. No text before or after this document.

**Format:** Follow the canonical schema at `skills/_shared/contracts/lens-result-contract.md`. That contract is the single source of truth for all lens skill `--dispatch` output.

For this skill, set `lens: plan-health-audit` in frontmatter. All other fields, severity vocabulary, body sections (Blockers/Risks/Gaps/Questions/Observations), concern area values, and blocked/failed output shape are defined in the contract.

**Lens-specific extension:** This skill appends a `## Health Summary` section after the contract's standard sections (Blockers through Observations). This is a declared extension -- it does not replace or modify any contract section. Other lens skills should not parse or depend on it.

```markdown
## Health Summary

**Verdict:** ready | needs-work | blocked
**Sections present:** N/10
**Phases sized:** N/N
**Forks documented:** N (M open, K locked)
**Risks covered:** N/N with mitigation
**Validation criteria testable:** N/N
```

---

## Interactive Mode (no `--dispatch`)

When invoked without `--dispatch`, this skill is an **advisor**, not a report generator.

**Enter Plan Mode.** Call `EnterPlanMode`. All analysis is read-only.

Execute Steps 1-10 above, then present findings as an advisory conversation:

### Advisory Format

Lead with the health score, then walk through each check that produced findings:

```
## Plan Health Audit: [Plan Title]

### Health Score: [ready | needs-work | blocked]

**Sections:** N/10 present
**Phases:** N sized, N with concrete deliverables
**Forks:** N total (M open, K locked), N fully documented
**Risks:** N total, N with mitigation
**Validation:** N/N criteria testable
**Cross-references:** N checked, N broken

### [Check Name]

**Finding:** [Concrete description of the structural issue]

- **(a)** [Fix option: e.g., add the missing Companion Plans section with cross-references to X and Y]
- **(b)** [Alternative: e.g., write "None identified" if genuinely standalone]
- **Lean:** (a) -- [one-sentence reason]

### Summary

[1-2 sentences: overall structural health and the single most important fix to make the plan implementation-ready]
```

Group findings by check. For each finding, include options and a lean. Not every check will produce a finding -- checks that pass get a one-line confirmation ("Frontmatter complete. All 7 fields present.") and move on.

---

## Scope Boundary

This skill checks the plan **document**, not the plan's **content quality**:

| This skill checks | Other skills check |
|-------------------|--------------------|
| Are all mandatory sections present? | Is the Goal the right problem? (`/first-principles`) |
| Do phases have effort sizes? | Are effort sizes accurate? (`/cost-benefit`) |
| Do forks have options, leans, ratifiers? | Are the fork options the right ones? (`/adversarial-review`) |
| Do validation criteria have testable language? | Do validation criteria cover the right things? (`/adversarial-review`) |
| Do cross-references point to existing files? | Does the referenced code match the plan's claims? (`/extension-check`) |
| Is the document structurally complete? | Is the plan aligned with the mission? (`/align-to-mission`) |

This separation is intentional. Structural health is a prerequisite for content review -- a plan missing its Risks section can't be meaningfully risk-reviewed.

---

## Red Flags — You Are Doing This Wrong

| Symptom | Problem |
|---------|---------|
| You are evaluating whether the plan is a good idea | That is `/first-principles` or `/adversarial-review`. This skill checks structure, not strategy. |
| You are reading the target codebase to verify claims | That is `/extension-check`. This skill reads only the plan document. |
| Every finding is `info` severity | You are cataloguing, not auditing. Missing sections and vague validation criteria are `major`, not `info`. |
| You flagged a section as missing when it exists under a different heading | Match headings case-insensitively and allow reasonable synonyms (e.g., "Validation" for "Validation Strategy", "Sizing" for "Complexity and Sequencing"). |
| You marked "None identified" content as a missing section | "None identified" is valid content -- the section is present. Only flag it under the none-identified density check (Step 9). |
| You invented validation criteria testability judgments without examples | Cite a specific vague phrase from the plan and show what a testable version would look like. |
| You are assessing risk quality, not risk coverage | Whether the mitigations are good is `/adversarial-review`'s job. Whether they exist is yours. |
