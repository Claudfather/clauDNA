# Mechanical Verification Checklist

Reference material for the `/claudna:audit data-model-redesign` lens — run in Step 8, after the deliverables exist and **before anything is presented or published**, in every output mode. Mechanical means each check is a command or a list-diff with a binary outcome, not a judgment call: an evaluation that cites files that don't exist, references issues that don't resolve, or ships placeholder text fails at the credibility layer no matter how good the reasoning is.

Run every check over every deliverable (`research/*.md` that will be presented, `docs/00_*`, `docs/NN_*`). Report the results as a PASS/FAIL table appended to the run summary. **Any FAIL blocks the handoff until fixed** — fix the artifact, or cut the claim that cannot be verified.

---

## 1. Referenced files exist

Extract every repo path cited in the deliverables (`file`, `file:line`, schema/migration identifiers) and verify each resolves in the audited repo at the audited revision — Glob for the path, Read to confirm a `file:line` citation's line number is within the file. A citation that doesn't resolve is fixed (the path moved, the line drifted) or the claim it supports is cut or downgraded to `Hypothesis` — a claim without a live citation is an assertion, not evidence.

## 2. Referenced issues exist

Extract every tracker reference (`#N`, issue/PR URLs, foreign-tracker IDs) and verify each resolves — `gh issue view <N>` / `gh pr view <N>` (or the equivalent for the repo's tracker). Verify the resolved title is plausibly the thing being cited, not just that the number exists. A wrong-number reference is worse than none: fix it or drop it.

## 3. Placeholder scan

Grep every deliverable for unfilled-template debris:

- `{{` or `}}` — unfilled template variables
- `TODO`, `TBD`, `FIXME`, `XXX`
- `<placeholder`, `<fill`, `<YYYY`, `<name>`-style angle-bracket stubs outside fenced example blocks
- `lorem`
- `NN_` appearing *inside* a doc body (an unresolved stage-doc cross-reference; the literal filenames in the scratch dir are fine)
- `...` as the sole content of a table cell

Every hit is filled or removed. This catches the failure mode where a protocol section shipped as its own template.

## 4. Tracker reconciliation

Reconcile every Part 4 finding and every Part 7 migration stage against the live tracker before filing or presenting — a targeted `gh issue list --repo <owner/repo> --search "<key terms>" --state all --limit 50` per item (`--state all` is mandatory: `gh issue list` defaults to open-only, and a *closed* match means the work landed or the problem regressed). Bucket each item:

| Bucket | Fate |
|---|---|
| **net-new** | Keep |
| **extends #N** | Keep, add `Related: #N` to the doc |
| **regressed #N** | Keep, reference #N as the recurrence |
| **duplicate of #N** | Drop from the deliverable; report the `#N` in the summary |
| **already landed (#N closed)** | The plan must not re-plan landed work — cut the stage step or rebase it on what shipped |

If the repo has no reachable tracker, say so in the summary and reconcile against whatever exists (`documentation/`, a TODO file) — never silently skip. `--output github` additionally gets `/claudna:publish`'s per-medium dedup; this reconciliation runs in **every** output mode regardless.

## 5. Internal consistency

List-diffs and structural checks against the protocol's own requirements:

- Part 5 carries **three or more** candidates, and one of them is incremental repair of the current model.
- The criteria matrix scores every candidate on the same criteria — no column with a blank or extra row.
- Part 6's recommendation cites only evidence present in Parts 1–5 (no new findings introduced at recommendation time).
- Every consumer in Part 1's inventory appears in Part 7's consumer × stage matrix — diff the two lists both ways (a matrix row with no inventory entry is as wrong as a missing row).
- Every migration stage doc carries a rollback entry (trigger, mechanism, blast radius) — and any skipped or collapsed stage is named with its justification.
- The deliverable's headings cover all seven protocol parts for the parts that ran — nothing silently dropped.
