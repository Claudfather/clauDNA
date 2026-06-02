# Synthesis Contract

Canonical schema for the structured result emitted by `/claudna:weigh-development-paths --auto` and consumed by `/claudna:implement-plan --auto` (Step 3-AUTO). Both skills MUST reference this file rather than restating the shape inline.

## Producer

`/claudna:weigh-development-paths` running in `--auto` mode.

## Consumer

`/claudna:implement-plan` running in `--auto` mode, specifically Step 3-AUTO (synthesis pass).

## Emission rules (producer side)

- The producer emits exactly one fenced ```json block as the FINAL output of the run.
- No prose, comments, or extra text after the block.
- The block MUST be valid JSON (no trailing commas, all strings quoted).

## Schema

```json
{
  "skill": "weigh-development-paths",
  "outcome": "completed",
  "artifacts": {
    "refined_plan_path": "<absolute path written to disk, or null if inline-only>",
    "refined_plan": "<full markdown body of the refined plan>",
    "decisions_resolved": <integer count>,
    "decisions_unresolved": <integer count>,
    "synthesis_rationales": [
      {
        "decision": "<original open question or finding summary>",
        "chosen_option": "<the synthesized choice>",
        "dimensions": ["<dimension that drove it>", "..."]
      }
    ]
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

### Field requirements

| Field | Required | Type | Notes |
|---|---|---|---|
| `skill` | yes | string | Exactly `"weigh-development-paths"` |
| `outcome` | yes | enum | One of `completed`, `blocked`. See "Outcome semantics" below. |
| `artifacts.refined_plan` | yes (when `completed`) | string | Full markdown body — directly substitutable for the original plan body |
| `artifacts.refined_plan_path` | optional | string \| null | Disk path if the producer chose to persist; null otherwise |
| `artifacts.decisions_resolved` | yes | integer | Count of input decisions/findings the producer resolved |
| `artifacts.decisions_unresolved` | yes | integer | Count the producer could NOT resolve without human input |
| `artifacts.synthesis_rationales` | yes | array | One entry per resolved decision; see element schema above |
| `summary` | yes | string | 2-3 line digest for human/orchestrator scanning |
| `next` | optional | string \| null | Orchestrator hint; usually null for synthesis |
| `errors` | yes | array | Empty on success |
| `blocker_description` | required when `outcome != completed` | string \| null | 1-2 sentences explaining what blocked and what would unblock |

### Outcome semantics

- **`completed`** — All input decisions and adversarial findings resolved. `refined_plan` is substitutable for the original plan body. `decisions_unresolved` is 0.
- **`blocked`** — One or more decisions cannot be resolved without human input (insufficient evidence in any of the 7 dimensions). `decisions_unresolved` > 0. `blocker_description` lists the unresolvable decisions as a checklist a human can complete.

The producer MUST NOT emit any other outcome value. Consumers MAY treat unrecognized outcomes as a synthesis failure (mapping to consumer-side `blocked` with `errors: ["synthesis pass returned outcome: <X>"]`).

## Consumer expectations

Consumers (currently only `/implement-plan --auto` Step 3-AUTO) MUST:

1. Read the producer's final output and parse the JSON block.
2. On `outcome: completed`:
   - Use `artifacts.refined_plan` as the new plan body. Replace the original.
   - For each previously-OPEN adversarial finding present in the original plan, mark its checkbox as resolved (`- [ ]` → `- [x]`) and append a sub-bullet pulling the matching `synthesis_rationales` entry by `decision` text.
   - Record `decisions_resolved` in the consumer's own structured result as `artifacts.synthesis_decisions_resolved`.
3. On `outcome: blocked`:
   - Exit with the consumer's own `outcome: "needs-input"` (mapping: producer-blocked ≠ consumer-blocked; the producer asks for human help, the consumer surfaces that request).
   - Copy the producer's `blocker_description` into the consumer's structured result.
4. On any other outcome (malformed JSON, timeout, missing required fields):
   - Exit with consumer's `outcome: "blocked"`, `errors: ["synthesis pass returned outcome: <value or 'malformed'>"]`.

## Stability

This contract is the integration surface between two skills. Changes are breaking:

- Adding a new REQUIRED field is a breaking change for producers (must add) and consumers (must read).
- Removing or renaming any field is a breaking change for both.
- Adding an OPTIONAL field is non-breaking — consumers MUST ignore unknown fields.

When changing this file, update both `skills/weigh-development-paths/SKILL.md` and `skills/implement-plan/SKILL.md` in the same commit.

## Related

- General structured-result shape: `skills/_shared/orchestration-guide.md` §10.C
- Producer skill: `skills/weigh-development-paths/SKILL.md` "Autonomous Mode (`--auto`)" section
- Consumer skill: `skills/implement-plan/SKILL.md` Step 3-AUTO (Synthesis pass)
