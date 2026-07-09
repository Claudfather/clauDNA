Invoked by /claudna:session in checkpoint mode — a mid-session save without the full handoff ceremony. New in the engine (no standalone predecessor): use it before risky work, before a compaction, or whenever losing the last hour would hurt — without ending the session.

**What checkpoint deliberately does NOT do**: no reaper pass, no full live scan, no `.gitignore` management, no user approval round — the ceremony `handoff` runs — and no legacy-path import, which lives in `resume`. It appends and refreshes — the ceremony stays with `handoff`.

Target: under 20 seconds.

## Steps

### 1. Read existing handoff (if any)

Read `<cwd>/.claude/session.md` if it exists. If absent, this becomes a first-write — the checkpoint creates the file with only this session's items.

### 2. Capture new items since the last write

From the session conversation, identify new **Activity**, **Decisions**, **Open Questions**, and **Next Steps** that are not already in the file (case-insensitive substring dedup, same rule as handoff step 6). Each new item gets the current ISO-8601 UTC timestamp. Existing items are left exactly as they are — no reaping, no pruning, no rewriting.

Capture silently — no approval round in either mode.

### 3. Refresh State only

Run `git status --porcelain` and `git branch --show-current` (parallel, separate calls). Regenerate only the `State` section's `branch` and `working_tree` fields; leave `stashes`/`open_prs`/`in_flight_branches` as they were (the full scan is handoff's job — stale values there are acceptable between handoffs).

### 4. Write atomically

Ensure `<cwd>/.claude/` exists (`mkdir -p <cwd>/.claude`). Use the format in `templates.md` in this skill directory. Write to `<cwd>/.claude/session.md.tmp`, then `mv` into place.

### 5. Confirm

- **Without `--auto`:** one line — "Checkpoint saved (<N> new items). Full handoff still recommended at session end."
- **With `--auto`:** emit the §10.C structured result from `_shared/orchestration-guide.md §10.C` as the final output — nothing after it:

```json
{
  "skill": "session",
  "outcome": "completed",
  "artifacts": {
    "mode": "checkpoint",
    "handoff_path": "<absolute path to <cwd>/.claude/session.md>",
    "branch": "<current branch>",
    "items_added": <N>
  },
  "summary": "Checkpoint saved to <path>. <N> new items.",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

Outcomes: `completed` (written) · `blocked` (could not write — filesystem error; set `blocker_description`). There is no `partial` — checkpoint has no optional steps.

## Rules

- **Checkpoint never reaps.** A checkpoint must never make the file smaller — it only adds and refreshes `branch`/`working_tree`.
- **Not a substitute for handoff.** The reaper and full scan run at session end; a session that only checkpoints accumulates until the next `handoff` or `resume` reaps it.
- **Atomic write, no `~/.claude/` writes** — engine conventions apply.
