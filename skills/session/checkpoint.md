Invoked by /claudna:session in checkpoint mode — a mid-session save without the full handoff ceremony. New in the engine (no standalone predecessor): use it before risky work, before a compaction, or whenever losing the last hour would hurt — without ending the session.

**What checkpoint deliberately does NOT do**: no reaper pass, no full live scan, no `.gitignore` management, no user approval round, and no legacy-path import, which lives in `resume`. It appends and refreshes — the ceremony stays with `handoff`.

Target: under 20 seconds.

## Steps

### 1. Read existing handoff (if any)

Read only the current native session's `handoff.md` through the session-store CLI. Use the actual verified SID and host; missing/conflicting identity stops the write. If `CLAUDNA_SESSION_STORE=0`, skip background checkpointing; an explicit user-requested manual checkpoint may proceed with verified identity without initializing lifecycle state. If the handoff is absent, this becomes a first-write — the checkpoint creates the file with only this session's items.

### 2. Capture new items since the last write

From the session conversation, identify new **Activity**, **Decisions**, **Open Questions**, and **Next Steps** that are not already in the file (case-insensitive substring dedup, same rule as handoff step 6). Each new item gets the current ISO-8601 UTC timestamp. Existing items are left exactly as they are — no reaping, no pruning, no rewriting.

Capture silently — no approval round in either mode.

### 3. Refresh State only

Run `git status --porcelain` and `git branch --show-current` (parallel, separate calls). Regenerate only the `State` section's `branch` and `working_tree` fields; leave `stashes`/`open_prs`/`in_flight_branches` as they were (the full scan is handoff's job — stale values there are acceptable between handoffs).

### 4. Write atomically

Use the v2 format in [`templates.md`](./templates.md) and submit the complete content to `session-store handoff-write --session <native-sid> --host <host> [--background] --json`. Let the runtime atomically write the current session's handoff. Do not create shell temp files or use `mv`. If an existing scoped pointer belongs to the current owner, retain it; do not advance or replace a predecessor pointer during checkpoint. Publish a current-owner pointer only when this workflow explicitly continues that scope and supplies the existing ref hash for compare-and-swap.

### 5. Confirm

- **Without `--auto`:** one line — "Checkpoint saved (<N> new items). Full handoff still recommended at session end."
- **With `--auto`:** emit the §10.C structured result from `../_shared/orchestration-guide.md §10.C` as the final output — nothing after it:

```json
{
  "skill": "session",
  "outcome": "completed",
  "artifacts": {
    "mode": "checkpoint",
    "handoff_path": "<absolute path returned by the session-store writer, or null>",
    "source_sid": "<verified current native SID, or null>",
    "branch": "<current branch>",
    "items_added": <N>
  },
  "summary": "Checkpoint saved to <path>. <N> new items.",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

Outcomes: `completed` (write and any explicitly required pointer action succeeded) · `partial` (identity/path/write unavailable; use `handoff_path: null`) · `blocked` (required interaction cannot proceed; set `blocker_description`).

## Rules

- **Checkpoint never reaps.** A checkpoint must never make the file smaller — it only adds and refreshes `branch`/`working_tree`.
- **Not a substitute for handoff.** The reaper and full scan run at session end; a session that only checkpoints accumulates until the next `handoff` or `resume` reaps it.
- **Atomic helper only.** No shell temp files, `mv`, `.gitignore` updates, or lifecycle initialization.
