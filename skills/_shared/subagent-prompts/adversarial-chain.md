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

Return ONLY the structured markdown document per the adversarial-review SKILL.md "Structured Result Emission" section. Format:

---
lens: adversarial-review
severity: <highest severity across findings: critical/major/minor/info>
pr: null
plan-path: "<DOC_PATH>"
timestamp: <ISO 8601 UTC>
outcome: completed
---

## Blockers

- **[<severity>] <concern_area>**: <summary>
  - **Recommendation:** <recommendation>

## Risks
...

## Gaps
...

## Questions
...

## Observations
...

Omit empty sections. If the plan body cannot be reviewed (empty, malformed), emit outcome: blocked with the reason in the body.
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

1. Parses the markdown output — reads YAML frontmatter for `outcome` and `severity`, then extracts findings from the body sections (Blockers, Risks, Gaps, Questions, Observations).
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

Findings sorted by severity (critical → major → minor → info).

4. The section becomes part of the plan body. Downstream consumers (interactive `/implement-plan` Step 3A, or `--auto` synthesis pass) read it and resolve items.

## When this chain runs

- **All planning skills, all modes.** Interactive and `--auto`. The chain is part of the planning skill's natural workflow, not a mode-specific addition.
- **Per phase doc**, not per session. A session may produce 1-N phase docs; the chain runs once per doc.
- **After Plan agents return**, before the planning skill's final summary/handoff section.
