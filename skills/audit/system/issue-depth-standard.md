# Junior-executable issue-depth standard

The system lens files issues for a **more junior implementer who did not do this review**. The house body contract is output-guide §4.1 — `/claudna:publish` validates it and `/claudna:implement-plan --source github` parses it. This file is the *depth* each §4.1 section must reach for a system-review issue. It does not replace §4.1; it raises the bar inside it.

The depth this standard requires — ordered implementation steps, acceptance criteria, exact test commands — is depth a thorough review can already reach on its own; that is the part to preserve. What such a review typically lacks is the tracker reconciliation (system.md Phase 5) and the §4.1 frontmatter/skeleton — this standard bolts the depth onto the house contract so both survive.

## The mapping — §4.1 section → depth required

| §4.1 section | System-review depth bar |
|---|---|
| `## Summary` | 2-3 sentences: the problem, why it matters, the intended fix. Name the failure mode, not just the area. |
| `## Evidence` | `file:line` for every claim. Current behavior quoted from source. A `Confirmed \| Likely \| Hypothesis` label carried over from the sweep. If Hypothesis: what would confirm or falsify it. |
| `## Implementation Plan → Dependencies / Blocks` | Real issue/phase numbers from the Phase 5 partition (`extends #N`, `regressed #N`), or "None". Sequencing constraints stated (e.g., "backfill column X before enforcing the scope filter, or the pool reads empty"). |
| `## Implementation Plan → Steps` | Ordered, file-by-file, with function/symbol names and before/after sketches. Zero ambiguity — the implementer never has to reverse-engineer intent. New files: give the skeleton. |
| `## Test Plan` | **Exact commands** (`./venv/bin/python -m pytest tests/x -k y`), not "run the tests". New tests named with what they assert. Manual checks where automation can't reach. |
| `## Verification Checklist` | Main case fixed; edge cases enumerated; tests added/updated; existing tests still pass; logging/metrics/docs updated if applicable; no secret exposed. |
| `## What NOT To Do` | The specific wrong turn for *this* fix — the call-site that looks unrelated but breaks, the "behavior-preserving" refactor that isn't, the tenant/scope filter that silently empties a result set. |
| `## Context` | Source skill `audit (system lens)`; date; area; effort; risk; priority; related issues from the partition. |

## Rules

- **Rollout & backout for anything touching data or a running job.** State risk level, rollout notes, and a backout plan. A migration or a scheduler change without a backout plan is not junior-executable.
- **Non-goals are load-bearing.** State what NOT to change, so a junior implementer doesn't expand a scoped fix into a refactor. The baseline review that over-reaches is a real failure mode.
- **One issue = one PR's worth of work.** De-fragment (three near-identical findings → one umbrella) and split (one finding that is two unrelated fixes → two issues) at Phase 5, before authoring. Do not bundle unrelated fixes because they share a file.
- **Priority is explicit and honest.** Map sweep severity → `priority:*` per output-guide §4.4 (`CRITICAL → priority:critical` … `LOW → priority:low`). Do not inflate a MEDIUM to draw attention or deflate a CRITICAL to avoid alarm.
- **Frontmatter comes from the house contract.** `type: audit` (or `review`), `status: draft`, `title` per §4.2 (`[<type>] <desc> — <area>`), `tags:` from the §4.3 taxonomy plus `auto-audit`. The §4.2 prefixes and §4.3 labels are conventions publish *extends* — it creates any label that doesn't exist (§4.3) — not a closed set, so map each sweep lane to the nearest fit: correctness & reliability → `[bug]` + `bug`; backend-perf → `[perf]` + `performance`; data-quality → `[data-quality]` + `data-quality`; security → `[security]` + `security`; maintainability → `[tech-debt]` + `tech-debt`. Publish rejects a doc missing the §4.1 skeleton — author it complete.
