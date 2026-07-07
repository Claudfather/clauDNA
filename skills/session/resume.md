Invoked by /claudna:session in resume mode — restore short-burst context fast at the start of a new session. Counterpart to the `handoff` mode.

Target: under 30 seconds. With `--auto` (headless): skip step 7 (the user-focus question); auto-import any legacy file silently.

## Steps

### 1. Read handoff

Read `<cwd>/.claude/session.md`.

If absent, check the legacy path: derive a slug from `git remote get-url origin` (extract `org/repo`, lowercase, replace `/` with `--`); fallback to lowercased dirname. Look for `~/.claude/notes/projects/<slug>/context-resume.md`. If found:

- **With `--auto`:** Import silently. Copy content into `<cwd>/.claude/session.md` (assign the legacy file's `session_date` as the timestamp for every imported bullet — see the migration notes in `templates.md` in this skill directory). Delete the legacy file. Continue.
- **Without `--auto`:** Ask once: "Found a legacy handoff at `<path>` (last touched <date>). Import it? [y/N]". On `y`: import as above. On `n`: leave the legacy file alone and proceed without it.

If neither file exists, run step 2 (live scan), then skip to step 5. Present a brief greeting using the live-scan data only; there is no handoff history.

### 2. Live scan (parallel)

Run in parallel:
- `git status --porcelain`
- `git log --since="30 days ago" --oneline`
- `git branch --list`
- `git stash list`
- `gh pr list --author @me --json number,title,state,updatedAt`
- `gh pr list --review-requested @me --json number,title,updatedAt`
- If `documentation/planning/` exists, run `grep -rE "IN PROGRESS|PENDING|✅ COMPLETE" documentation/planning/ --include="*.md"`

### 3. Reaper pass

Apply the rules in `../_shared/reaper-rules.md` to the loaded content.

### 4. Write back if reaped

If the reaper changed anything, ensure `<cwd>/.claude/` exists first (`mkdir -p <cwd>/.claude`), then write the cleaned content back to `<cwd>/.claude/session.md` (atomic write: `tmp` + `mv`). This is the "read also reaps" half of the contract.

### 5. Present briefing

```
Session Resume: <cwd basename>
═══════════════════════════════════════════════════════════════════════════

  Last handoff:  <last_updated from frontmatter, or "no prior session">

  State:
    <branch> · <clean | dirty: N modified, N untracked, N staged>
    <N stashes>

  Open PRs (yours):
    #N  <title>  (<state>)

  PRs awaiting your review:
    #N  <title>  (from @author)

  In-progress plans:
    <path>  🔧

  Next steps (from handoff):
    - <bullet>

  Open questions:
    - <bullet>

  Recent activity (3 most recent):
    - <bullet>

═══════════════════════════════════════════════════════════════════════════
```

Omit any section with no data. Cap each list at 5.

### 6. Suggest a focus

Prioritize:
1. PR with changes-requested → "PR #N has changes requested. Address those first?"
2. In-progress plan doc → "Phase N is in progress. Continue with `/implement-plan`?"
3. PRs awaiting review → "N PRs waiting for your review. Run `/claudna:review-work pr N`?"
4. Handoff next-step → "Last session suggested: <step>. Pick that up?"
5. Dirty working tree → "Uncommitted changes. Review and commit first?"

### 7. Ask the user

Ask: **"What would you like to focus on?"**

**Skipped under `--auto`.** The agent returns control to its own loop with the briefing in context, then proceeds to step 8.

### 8. Structured-result emission (`--auto` only)

When invoked with `--auto`, emit the §10.C structured result from `_shared/orchestration-guide.md §10.C` as the **final** output — nothing after it. The step 5 briefing still emits as the agent's context payload; the JSON block is appended at the end so orchestrators can parse the outcome.

```json
{
  "skill": "session",
  "outcome": "completed",
  "artifacts": {
    "mode": "resume",
    "handoff_path": "<absolute path to <cwd>/.claude/session.md, or null if none>",
    "handoff_found": true,
    "legacy_imported": false,
    "branch": "<current branch>",
    "items_reaped": <N>
  },
  "summary": "Resumed session at <cwd>. Last handoff <date>. <N> next-step bullets, <M> open PRs.",
  "next": "<top suggested-focus line from step 6, or null>",
  "errors": [],
  "blocker_description": null
}
```

Outcomes:
- `completed` — briefing produced from an existing handoff (with or without legacy import).
- `partial` — no handoff existed, briefing produced from live scan only. Add a note to `errors`.
- `blocked` — couldn't read or scan (e.g., not in a git repo, cwd unreadable). Set `blocker_description`.

Interactive mode (no `--auto`) skips this step entirely.

## Rules

- **Read-only by default.** Only writes are step 4 (write back if reaped) and step 1 legacy import. Never modifies code, never commits.
- **Speed over depth.** Scan, reap, summarize. No deep analysis.
- **Reaper rules in `_shared/`.** Do not duplicate them inline.
- **`--auto` is silent on the prompt.** Briefing and focus suggestion still emit (they are the agent's context payload); only the explicit user-question is suppressed.
- **Legacy import is one-shot per cwd.** Once imported, the legacy file is deleted, so this branch only fires once per project.
