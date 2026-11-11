# Reaper Rules — the `/claudna:session` engine

The reaper runs in memory on handoff preparation and resume reads (`/claudna:session`; checkpoint deliberately never reaps). It prunes the selected predecessor's content for briefing or uses the current session's existing content when preparing a write. A predecessor is immutable: resume never writes reaped content back to that predecessor. New writes belong only to the verified current native session at `R/sessions/<native-sid>/handoff.md`.

## Inputs

- The selected handoff content returned by scoped continuity resolution, or the current native session's own `handoff.md`
- A live scan of the current cwd:
  - `git status`, `git log --since="30 days ago"` (covers the longest TTL window — Decisions at 30d), `git stash list`, `git branch --list`
  - `gh pr list --author @me --json number,title,state,updatedAt`
  - File-presence checks for any path mentioned in handoff items
  - `documentation/planning/` status markers (`IN PROGRESS`, `PENDING`, `✅ COMPLETE`)
- The current ISO-8601 UTC timestamp

## Per-section rules

| Section | Rule | Action |
|---|---|---|
| `State` | Never reaped — always overwritten from live scan | n/a |
| `Activity` | Item timestamp > 7d old | hard drop |
| `Activity` | Item references a PR/branch that no longer exists | hard drop |
| `Open Questions` | Item timestamp > 14d old | soft — see "LLM judgment" below; default to drop if no current signal |
| `Open Questions` | Item references a closed PR or merged plan phase | hard drop |
| `Decisions` | Item timestamp > 30d old | soft — see "LLM judgment" below; default to drop if no current signal |
| `Decisions` | Referenced verbatim by a current Next Step | never auto-drop (overrides the TTL soft rule) |
| `Next Steps` | Commit message since last handoff references the step as done | hard drop, move to Activity with the commit timestamp |
| `Next Steps` | Plan phase referenced is now `✅ COMPLETE`, unless the item is a documentation flag that handoff step 4 rebuilds (its text after the timestamp starts with `Archive (documentation-standard §6):` or `Set terminal statuses (documentation-standard §6):`) | hard drop |
| `Next Steps` | Pure timestamp | never drop by TTL alone |
| Any of `Activity` / `Decisions` / `Open Questions` / `Next Steps` | Section exceeds 10 bullets after other rules apply | drop oldest-first until ≤ 10 bullets remain (capacity cap, regardless of TTL) |

## "Soft" rules — LLM judgment criteria

**Definition:** "current Next Step" means any bullet in the file's `## Next Steps` section that has not itself been dropped by this reaper pass.

When a soft rule fires, evaluate the item against current state. Drop if **all** are true:

1. No recent commit, PR, or plan-doc activity references the item's content
2. No current Next Step depends on the item
3. The item's content is not flagged with explicit "keep" intent (e.g., "[pin]" suffix)

Otherwise: keep with a `(stale-flagged YYYY-MM-DD)` suffix appended once. If the suffix is already present and conditions still match for drop, drop on the next pass.

## Output

The reaper returns a new in-memory representation with stale items removed and survivors preserved. Handoff may persist a new document only to the current session through the atomic session-store writer. Resume does not write back to the predecessor. Checkpoint does not invoke the reaper.

## Determinism

Hard drops are mechanical. Soft drops involve LLM judgment, but the criteria above must be applied consistently — do not improvise. Treat the criteria as a checklist.
