# Synthesis contract — `weigh-development-paths --auto` → `build --auto`

The machine handoff for the **synthesis pass**: when `build --auto` hits a plan with *open* decisions (unresolved adversarial findings or undecided matrix junctions), it delegates the resolution to `weigh-development-paths --auto` instead of skipping the challenge round. This file is the contract between the two — the producer (`weigh`) and the consumer (`build`) both adhere to it, and both point here rather than restating the shape inline.

Producer: `weigh-development-paths --auto <bundle-path>`. Consumer: `build --auto` Step 3-AUTO.

## The input bundle (consumer → producer)

`build` writes a scratch bundle (a markdown file under the run's scratch dir, per `orchestration-guide.md` §1) and passes its path to `weigh --auto`. The bundle carries everything `weigh` needs to resolve the junctions **without a human or codebase round-trip of its own**:

```
# Synthesis bundle — <plan title>

## Open decisions
<one block per junction needing resolution>
### D<n>: <junction title>
- Options: <A / B / C, with the plan's framing>
- Source: <"adversarial finding" | "matrix decision point" | "plan fork F<n>">
- Context: <the plan text + why it's open>

## Codebase-comparison artifacts
<the Step-2 findings: what exists, relevant patterns, constraints — so weigh's
"Existing Patterns" / "Extension" dimensions are grounded, not guessed>

## Plan
<the full upstream plan body, so weigh resolves in-context>
```

A junction enters the bundle only if it is genuinely **open** — an adversarial finding still flagged, or a fork/matrix cell the plan left undecided. A fully-decided plan produces an **empty** `## Open decisions` section, and the consumer skips synthesis entirely (trust-the-plan still applies when there's nothing to resolve).

## The output (producer → consumer)

`weigh --auto` emits **one** `orchestration-guide.md` §10.C structured-result block, with `skill: "weigh-development-paths"` and the synthesis payload under `artifacts`:

```json
{
  "skill": "weigh-development-paths",
  "outcome": "completed | needs-input | blocked",
  "artifacts": {
    "refined_plan": "<the plan body with every resolved decision substituted in-line>",
    "decisions_resolved": [
      {
        "junction": "D1: where the dedup helper lives",
        "choice": "extend skills/neon/branch.md",
        "rationale": "<1-2 lines — the holistic synthesis across the 7 dimensions>"
      }
    ],
    "decisions_unresolved": [
      {
        "junction": "D3: two-key bot vs personal key",
        "why": "requires a human policy call (identity/security) the matrix can't settle"
      }
    ],
    "synthesis_rationales": {
      "D1": "<the per-dimension reasoning, Elegance…Plan Alignment, behind the choice>"
    }
  },
  "summary": "<2-4 lines: how many junctions resolved / left open>",
  "next": null,
  "errors": [],
  "blocker_description": "<required when outcome != completed; names the unresolved junctions>"
}
```

- **`refined_plan`** — the upstream plan with every `decisions_resolved` choice woven in (the decision is now stated, not a fork). This is what the consumer implements.
- **`decisions_resolved`** — one entry per junction the synthesis settled; `rationale` is the holistic call, `synthesis_rationales[junction-id]` holds the full 7-dimension reasoning (audit trail).
- **`decisions_unresolved`** — junctions the matrix *cannot* settle headlessly (they hinge on a human value/policy/security call, not a technical comparison). Non-empty ⇒ producer `outcome: "needs-input"`.

## Producer outcomes

| `weigh --auto` outcome | When | `decisions_unresolved` |
|---|---|---|
| `completed` | every open junction resolved by the 7-dimension synthesis | empty |
| `needs-input` | one or more junctions need a human call (not a technical tie — a value/policy/security decision) | non-empty |
| `blocked` | the bundle was malformed/unreadable, or no junctions were supplied | n/a (a contract error, not a decision gap) |

A genuine technical tie is **not** `needs-input` — `weigh` must still pick (its Step 5 names what's lost). `needs-input` is reserved for decisions that aren't the matrix's to make.

## The remap (consumer)

`build` Step 3-AUTO maps the producer's outcome to its own:

| producer (`weigh`) | consumer (`build`) | consumer action |
|---|---|---|
| `completed` | continues to Step 4 | substitute `refined_plan`, flip the resolved adversarial findings to closed, proceed |
| `needs-input` | **`needs-input`** | stop; emit the §10.C block with `blocker_description` listing the `decisions_unresolved` junctions; leave a note on the source issue |
| `blocked` | **`needs-input`** | a synthesis it cannot run is a decision it cannot make headlessly — surface for a human, don't silently fall back to trust-the-plan (that would implement *unresolved* decisions) |

The `blocked → needs-input` remap is deliberate: the consumer never silently proceeds past an open decision it failed to resolve. Either synthesis settled it, or a human is asked — never "implement it anyway".

## Stability

This contract is the integration surface between two skills. Changes are breaking:

- Adding a new REQUIRED field is a breaking change for producers (must add) and consumers (must read).
- Removing or renaming any field is a breaking change for both.
- Adding an OPTIONAL field is non-breaking — consumers MUST ignore unknown fields.

When changing this file, update both `skills/weigh-development-paths/SKILL.md` and `skills/build/SKILL.md` in the same commit.

## Related

- `skills/_shared/orchestration-guide.md` §10.C — the structured-result envelope this nests in.
- `skills/weigh-development-paths/SKILL.md` — the producer (7-dimension synthesis).
- `skills/build/SKILL.md` — the consumer (Step 3-AUTO).
