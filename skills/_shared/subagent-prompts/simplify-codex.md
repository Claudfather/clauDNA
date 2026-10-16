# Codex simplification procedure

Use after verification, at the caller's existing diff threshold. This is clauDNA's
procedure; it does not assume a native Codex `/simplify` command. Read
`../../_shared/codex-tools.md` before dispatching.

Record the base revision, current owned file set and clean verification result.
Give each available independent reviewer the exact owned diff plus the following
one lens. Request concrete file:line findings only, preserving observable behavior.
Use real subagent spawn/wait controls. Run lenses sequentially when capacity is
limited; record the execution shape. If independent dispatch is unavailable, label
the pass inline; any separately required independent review remains unsatisfied.

- **Reuse:** Find duplicated logic or existing helpers that remove repetition
  without coupling unrelated responsibilities. Cite the reusable implementation.
- **Simplification:** Find unnecessary branches, state, wrappers or abstractions.
  Propose the smallest equivalent behavior and identify constraints it must preserve.
- **Efficiency:** Find avoidable repeated work, unbounded operations or unnecessary
  allocations in changed paths. Require a concrete trigger; avoid speculative tuning.
- **Altitude:** Check responsibilities and boundaries. Remove implementation detail
  from higher-level policy and keep shared contracts in their owning layer. Do not
  introduce a framework to solve a local problem.

Collect completed reviews, deduplicate overlapping findings and validate each against
the actual source and tests. Apply only justified in-scope changes. Stage explicit
owned paths, inspect the staged diff and commit the simplification separately if
there are edits. Re-run the caller's verification after any edit.

If a simplification regresses behavior, fix forward within the task's authority or
revert only the identified owned simplification commit using `git revert <commit>`
after checking for unrelated/uncommitted edits and conflicts. For uncommitted edits,
reverse only the saved owned patch after confirming it still applies. Preserve other
workers' changes. If neither action is safe, report the concrete conflict; do not
reset the checkout. Reverify after reverting and report any residual failure.

Record lenses, actual reviewer/wait identifiers, findings adopted or rejected,
changed paths, verification and any reverted owned commit in the run's evidence.
