---
name: session-handoff
user-invocable: true
description: "Use at the end of a session to write a per-cwd handoff file (<cwd>/.claude/session.md) capturing live state, activity, decisions, open questions, and next steps. Reaps stale items on write. Counterpart to /claudna:session-resume."
allowed-tools: Bash(git *), Bash(gh *), Bash(ls *), Bash(wc *), Bash(date *), Bash(grep *), Bash(mv *), Bash(mkdir *), Read, Write, Edit, Glob
argument-hint: "[--auto]"
---

# Session Handoff

Write the short-burst continuity tattoo. Counterpart to `/session-resume`.

**Identity:** This skill is keyed by **cwd**. The handoff lives at `<cwd>/.claude/session.md`. No global slug, no cross-project state.

**Scope:** Session continuity only. Knowledge capture (lessons, durable findings, memory pruning, changelog backfill) is **not** this skill's job — Claudron owns that lane. Use `/lessons` or `/notes` for cross-session knowledge today.

Target: under 60 seconds with `--auto`, under 2 minutes interactive.

## Arguments

Parse `$ARGUMENTS`:
- `--auto`: Fully non-interactive. Never ask the user anything. Reaper runs as the only pruning mechanism. Silent on success.

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

Ensure `<cwd>/.claude/` exists first (`mkdir -p <cwd>/.claude`). Use the format in `references/templates.md`. Write atomically: write to `<cwd>/.claude/session.md.tmp` then `mv` to `<cwd>/.claude/session.md`.

### 8. Manage `.gitignore`

First, verify we are inside a git working tree (`git rev-parse --is-inside-work-tree`). If not, skip this entire step — there is no gitignore to manage.

Detect:
1. Run `git check-ignore <cwd>/.claude/session.md` — if exit 0, the file is already ignored (by any rule, anywhere). Skip.
2. Else if `<cwd>/.gitignore` exists, append `\n.claude/session.md\n` to it.
3. Else create `<cwd>/.claude/.gitignore` with a single line:

   ```
   session.md
   ```

This is idempotent — step 1 catches both "already there" and "ignored by parent dir" (e.g., Claudlobby's `runtime/` is ignored at the Claudlobby root, so individual bot dirs need no further action).

### 9. Confirm

- **With `--auto`:** Skip this confirmation — proceed to step 10.
- **Without `--auto`:** "Handoff written to `<cwd>/.claude/session.md`. Use `/session-resume` next session."

### 10. Structured-result emission (`--auto` only)

When invoked with `--auto`, emit the §10.C structured result from `_shared/orchestration-guide.md §10.C` as the **final** output — nothing after it. Orchestrators (and `/restart`'s pre-stop check) key off this to confirm the handoff landed instead of inferring it from file mtime.

```json
{
  "skill": "session-handoff",
  "outcome": "completed",
  "artifacts": {
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
- **No writes to `~/.claude/`.** This skill stays out of the user-config tree entirely.
- **No compound commands.** Make separate parallel tool calls — `allowed-tools` patterns only match simple commands.
- **`State` is always regenerated.** Never reaped, never merged with prior State.
- **`--auto` means silent.** Reaper is the only pruning mechanism in `--auto`; user-driven pruning is interactive-only.
- **Atomic write.** `tmp` + `mv` so a concurrent reader (e.g., a bot mid-task) never sees a half-written file.
