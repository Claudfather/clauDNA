# Lens Result Contract

Canonical schema for the structured markdown result emitted by every panel lens and consumed by `/claudna:ironclad` for plan-hardening synthesis. All lens sources MUST reference this file rather than inlining their own format. (`/ironclad` migrated from claudlobby into clauDNA in 0.6.0; any fleet deployment consumes lenses through this plugin via the compositor-injected `fleet-dispatch-capability` override.)

## Producer

Any panel lens dispatched by `/claudna:ironclad` — the panel-internal lens files under `skills/ironclad/lenses/` and the `adversarial-review` skill in `--dispatch` mode.

## Consumer

`/claudna:ironclad` — reads `result.md` files from the scratch directory, parses YAML frontmatter and markdown body, aggregates findings across lenses, and posts to the target Issue or PR. A fleet override (compositor-injected) substitutes the dispatch step only; lens addressing post-P6 is by panel-file path (`skills/ironclad/lenses/<name>.md`), not skill name — an *absent* protocol (or `FLEET_STATE_PATH` set with no protocol) degrades safely to subagent mode with the loud mode indicator; a present-but-stale protocol runs in fleet mode and recovers per-lens via the Phase-6 retry.

## Dispatch Rules

Every panel lens runs dispatched, non-interactively. The dispatcher provides the source (plan document path or PR URL/source file) and the result path; the lens then follows the discipline below. Lens files reference this section rather than restating it, carrying only their own blocked condition.

- **Do NOT call `EnterPlanMode`.** The dispatcher owns the lifecycle.
- **Do NOT call `AskUserQuestion`.** No human is present.
- **Do NOT prompt for clarification.** If the source is too incomplete to assess, emit `status: blocked` with a description of what is missing. Each lens declares its own blocked condition (see the lens file).
- Execute the lens procedure silently.
- Emit the structured markdown result as the FINAL output and stop. No text after the result document.

## Emission Rules (Producer Side)

- The producer writes a single markdown file with YAML frontmatter to the path specified by the dispatcher (typically `RESULT_PATH`).
- No text outside the frontmatter + body structure defined below.
- Frontmatter MUST be valid YAML between `---` delimiters.
- The file is the ONLY output artifact. Producers MUST NOT post to the GitHub PR, create GitHub issues, or write to any other path. The consumer owns all external interaction.

## Format

````markdown
---
lens: <skill-name>
worker: <bot-id>
pr_url: <PR URL or null>
plan-path: <filesystem path or URL that was reviewed>
started: <ISO 8601 UTC, e.g. 2026-06-02T14:30:00Z>
completed: <ISO 8601 UTC>
status: completed | failed | blocked
severity: <highest severity across all findings: critical | major | minor | info | null>
---

## Blockers

- **[critical] <concern_area>**: <finding summary>
  - **Recommendation:** <action>

## Risks

- **[major] <concern_area>**: <finding summary>
  - **Recommendation:** <action>

## Gaps

- **[minor] <concern_area>**: <finding summary>
  - **Recommendation:** <action>

## Questions

- **[minor] <concern_area>**: <ambiguity that needs clarification>

## Observations

- **[info] <concern_area>**: <non-blocking note>
````

## Frontmatter Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `lens` | yes | string | Lens name of the producer (e.g., `adversarial-review`, `first-principles`) |
| `worker` | yes | string | Bot ID of the worker that produced this result |
| `pr_url` | no | string \| null | PR URL if reviewing a PR-linked plan, otherwise `null` |
| `plan-path` | yes | string | Filesystem path or URL of the plan that was reviewed |
| `started` | yes | string | ISO 8601 UTC timestamp of when the review started |
| `completed` | yes | string | ISO 8601 UTC timestamp of when the review completed |
| `status` | yes | enum | One of: `completed`, `failed`, `blocked` |
| `severity` | yes | enum \| null | Highest severity across all findings. `null` when `status` is `blocked` or `failed` with no findings |

### Status Semantics

- **`completed`** — Review finished. Findings (if any) are in the body. `severity` reflects the highest finding.
- **`failed`** — Review could not complete due to an error (e.g., plan unreadable, context overflow). Body contains a description of the failure.
- **`blocked`** — Review cannot proceed without external input (e.g., missing PROJECT_MISSION.md for align-to-mission). Body contains a description of what's needed.

## Severity Vocabulary

`critical` > `major` > `minor` > `info`

One severity tag per finding. If a finding spans two levels, use the higher one.

| Severity | Meaning | Blocks convergence? |
|----------|---------|---------------------|
| `critical` | Plan cannot proceed without addressing this | Yes |
| `major` | Significant gap that weakens the plan | Yes |
| `minor` | Improvement opportunity, not blocking | No |
| `info` | Observation or context, no action needed | No |

## Body Sections

Sections: Blockers, Risks, Gaps, Questions, Observations — in that order.

Each finding is a bullet with a `[severity]` tag and `concern_area` prefix. Include a `**Recommendation:**` sub-bullet for Blockers, Risks, and Gaps.

**Omit empty sections.** If every section is empty (zero findings), write a single line: "No findings surfaced by this lens."

### Concern Area Values

Use these where possible so downstream skills (e.g., `/implement-plan` challenge round) can categorize findings consistently:

`architecture`, `testing`, `dependencies`, `error-handling`, `performance`, `security`, `data-integrity`, `compatibility`, `observability`, `scope`

Lens-specific concern areas are permitted when none of the above fit, but prefer the canonical set.

## Blocked / Failed Output

When `status` is `blocked` or `failed`, the body is a plain description (no finding sections):

```markdown
---
lens: adversarial-review
worker: alex
pr_url: null
plan-path: /path/to/plan.md
started: 2026-06-02T14:30:00Z
completed: 2026-06-02T14:30:05Z
status: blocked
severity: null
---

Review could not proceed: plan body lacks a Goal section. The plan must define the problem being solved before it can be reviewed.
```

## Consumer Expectations

Consumers (currently `/ironclad`) MUST:

1. Parse the YAML frontmatter to identify the lens, worker, and status.
2. On `status: completed`: parse the markdown body for findings by section header and severity tag.
3. On `status: failed` or `blocked`: record the failure and optionally retry on a different worker.
4. Ignore unknown frontmatter fields (forward compatibility).
5. Aggregate findings across multiple lens results, deduplicating by concern area and finding summary.

## Stability

This contract is the integration surface between the panel lenses and `/claudna:ironclad` (including any fleet override). Changes are breaking:

- Adding a new REQUIRED frontmatter field is breaking for producers.
- Removing, renaming, or changing the type of any field is breaking for both sides.
- Adding an OPTIONAL field is non-breaking — consumers MUST ignore unknown fields.
- Changing the severity vocabulary or section names is breaking for consumers.

When changing this file, update every panel lens that references it and coordinate with any external fleet compositor that injects a dispatch override.

## Related

- Consumer: `/claudna:ironclad` (`skills/ironclad/SKILL.md`); producers: `skills/ironclad/lenses/*.md` + `skills/adversarial-review/`
- Severity vocabulary: shared with `pr-comment-hygiene` protocol (claudlobby)
- Concern area vocabulary: `skills/implement-plan/challenge-round-questions.md`
- Sibling contract: `skills/_shared/contracts/synthesis-contract.md` (weigh-development-paths <-> implement-plan)
- General structured-result shape: `skills/_shared/orchestration-guide.md` §10.C
