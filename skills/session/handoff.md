Invoked by /claudna:session in handoff mode — write the short-burst continuity tattoo at the end of a session. Counterpart to the `resume` mode.

Target: under 60 seconds with `--auto`, under 2 minutes interactive. With `--auto`: fully non-interactive — never ask the user anything; the reaper is the only pruning mechanism; silent on success.

## Steps

### 1. Read existing handoff (if any)

Read `<cwd>/.claude/session.md` if it exists. If absent, this is a first-write — skip to step 3.

### 2. Live scan (parallel)

Run in parallel:
- `git status --porcelain`
- `git log --since="30 days ago" --oneline`
- `git stash list`
- `git branch --list`
- `gh pr list --author @me --json number,title,state,updatedAt`
- If `documentation/planning/` exists, run `grep -rE "IN PROGRESS|PENDING|✅ COMPLETE" documentation/planning/ --include="*.md"`

### 3. Reaper pass

Apply the rules in `../_shared/reaper-rules.md` to the existing content. Items survive, drop, or get `(stale-flagged YYYY-MM-DD)`.

### 4. Capture this session's new items

From the session conversation, identify new:
- **Activity** — what was done (commits already covered by git log; add session-level work that didn't land in a commit)
- **Decisions** — choices made and rationale
- **Open Questions** — blockers, unknowns, pending inputs
- **Next Steps** — what the next session should start with

Each item gets the current ISO-8601 UTC timestamp.

**With `--auto`:** Capture silently. No user approval round.

**Without `--auto`:** Present captured items in one numbered list. Ask once: "Drop any? Pick numbers, edit, or accept all."

### 5. Regenerate State

The `State` section is regenerated from the live scan, fully overwriting any prior `State`:

```yaml
branch: <current branch>
working_tree: <clean | dirty: N modified, N untracked, N staged>
stashes: <count>
open_prs: ["#N <title> (<state>)", ...]
in_flight_branches: [<non-main feature branches>]
```

### 6. Merge

Combine reaped survivors (from step 3) + new items (from step 4). Dedupe by content (case-insensitive substring match — if a new Activity entry is a substring of an existing one, keep the existing). Preserve original timestamps on survivors.

### 7. Write `<cwd>/.claude/session.md`

Ensure `<cwd>/.claude/` exists first (`mkdir -p <cwd>/.claude`). Use the format in `templates.md` in this skill directory. Write atomically: write to `<cwd>/.claude/session.md.tmp` then `mv` to `<cwd>/.claude/session.md`.

### 8. Manage `.gitignore`

First, verify we are inside a git working tree (`git rev-parse --is-inside-work-tree`). If not, skip this entire step — there is no gitignore to manage.

Detect:
1. Run `git check-ignore <cwd>/.claude/session.md` — if exit 0, the file is already ignored (by any rule, anywhere). Skip.
2. Else if `<cwd>/.gitignore` exists, append `\n.claude/session.md\n` to it.
3. Else create `<cwd>/.claude/.gitignore` with a single line:

   ```
   session.md
   ```

This is idempotent — step 1 catches both "already there" and "ignored by parent dir" (e.g., a runtime tree ignored at its root needs no further action).

### 9. Confirm

- **With `--auto`:** Skip this confirmation — proceed to step 10.
- **Without `--auto`:** "Handoff written to `<cwd>/.claude/session.md`. Use `/claudna:session resume` next session."

### 10. Structured-result emission (`--auto` only)

When invoked with `--auto`, emit the §10.C structured result from `_shared/orchestration-guide.md §10.C` as the **final** output — nothing after it. Orchestrators (and `/restart`'s pre-stop check) key off this to confirm the handoff landed instead of inferring it from file mtime.

```json
{
  "skill": "session",
  "outcome": "completed",
  "artifacts": {
    "mode": "handoff",
    "handoff_path": "<absolute path to <cwd>/.claude/session.md>",
    "branch": "<current branch>",
    "items_reaped": <N>,
    "items_added": <N>
  },
  "summary": "Handoff written to <path>. <N> new items, <M> reaped.",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

Outcomes:
- `completed` — file written successfully.
- `partial` — file written but a non-fatal step failed (e.g., `.gitignore` step skipped because not in a git tree). Add a one-line note to `errors`.
- `blocked` — could not write the file (filesystem error, permission denied). Include the error in `errors` and set `blocker_description`.

Interactive mode (no `--auto`) skips this step entirely.

## Rules

- **Speed over thoroughness.** Reap, scan, write. Not a documentation exercise.
- **Reaper rules in `_shared/`.** Do not duplicate them inline. Read `../_shared/reaper-rules.md` and apply.
- **`State` is always regenerated.** Never reaped, never merged with prior State.
- **`--auto` means silent.** Reaper is the only pruning mechanism in `--auto`; user-driven pruning is interactive-only.
