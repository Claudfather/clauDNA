---
name: session-handoff
user-invocable: true
description: "Use at the end of a session to validate persisted state, prune stale items, capture session context, and write a handoff file for /claudna:context-resume. Supports --auto for fully non-interactive operation."
allowed-tools: Bash(git *), Bash(gh *), Bash(ls *), Bash(wc *), Bash(date *), Read, Write, Edit, Glob, Grep
argument-hint: "[--auto]"
---

# Session Handoff

Validate, prune, capture, and write. Counterpart to `/claudna:context-resume`.

Target: 2-3 minutes interactive, under 1 minute with `--auto`.

## Arguments

Parse `$ARGUMENTS`:
- `--auto`: Fully non-interactive. Never ask the user anything. Auto-fix verifiable issues, silently skip ambiguous ones, auto-save learnings, auto-write handoff.

## Step 0: Validate Persisted State

**This step runs first, before capturing anything new.** Review what's currently saved and prune stale or incorrect items.

### 0A. Memory Validation

Read the project's `MEMORY.md` (at `~/.claude/projects/<project-path>/memory/MEMORY.md`). For each memory entry:

1. **Read the memory file** it points to
2. **Verify against current state** — check if the memory's claims are still true:
   - File paths mentioned → Glob/Read to confirm they exist
   - Function/class names → Grep to confirm they exist
   - Configuration claims → Read the config file to verify
   - Project state claims (e.g., "using X library", "deployed on Y") → check package.json/requirements.txt/git history
   - Process/workflow claims → verify against current tooling
3. **Classify each memory:**
   - **Verified** — claims confirmed against code/config. Keep as-is.
   - **Stale** — claims contradicted by current state. Update or remove.
   - **Unverifiable** — can't confirm or deny from code alone (e.g., user preferences, external system references). Keep as-is.

**With `--auto`:** Silently update or remove stale memories. Keep unverifiable ones. No user interaction.

**Without `--auto`:** Present stale items and proposed fixes. Ask once: "Update these? Pick numbers, edit, or skip."

### 0B. Handoff File Validation

If a previous handoff file exists at `~/.claude/notes/projects/<slug>/claudna:context-resume.md`:
- Check if open PRs listed are still open (via `gh pr view`)
- Check if branches listed still exist
- Check if "next steps" are still relevant (were they completed this session?)

This informs Step 4 — the new handoff overwrites the old one, but knowing what changed helps write better next steps.

### 0C. Notes Validation

If `~/.claude/notes/` contains project-scoped notes or lessons, scan for:
- References to deleted files or renamed functions
- Outdated patterns (e.g., "use X" when X was replaced by Y)

**With `--auto`:** Silently remove or update verifiably stale notes.

**Without `--auto`:** Flag stale notes and ask once.

---

## Step 1: Scan Session

Gather everything automatically — no user interaction needed.

**Run in parallel:**
- `git log --oneline --since="8 hours ago"` (adjust if user specifies a timeframe)
- `git diff --stat` + `git stash list`
- `gh pr list --author @me --json number,title,state,updatedAt`
- Search `documentation/planning/` for status markers (IN PROGRESS, PENDING, COMPLETE)

Present a brief summary of findings.

**Dirty working tree:**
- **With `--auto`:** Leave uncommitted changes as-is. Note them in the handoff file.
- **Without `--auto`:** Ask once: "Uncommitted changes — commit first or leave them?"

---

## Step 2: Capture Learnings

Review the session for knowledge worth persisting. Look for:
- Patterns, gotchas, debugging insights discovered
- Times the user corrected your approach
- Commands or workflows that worked well

**Scope each item:**
- **Project-scoped** → write to auto-memory at `~/.claude/projects/<project-path>/memory/`
- **Cross-project** → write to `~/.claude/notes/` (use `/claudna:notes` or `/claudna:lessons` conventions)

**With `--auto`:** Auto-save all identified learnings without asking. Classify and write silently. Skip anything ambiguous about scope — default to project-scoped.

**Without `--auto`:** Present all candidates in a numbered list grouped by destination. Ask once: "Add any? Pick numbers, edit, or skip." Do not ask separate rounds for notes vs lessons.

**Size checks (mention only if exceeded):**
- MEMORY.md > 150 lines → nudge to prune (or auto-prune with `--auto` by removing lowest-value entries)
- Global notes > 100 lines → nudge to prune

---

## Step 3: Changelog + Stale Plans (Optional)

**Changelog:** If `CHANGELOG.md` exists, compare session commits against `[Unreleased]`. Flag missing entries.

- **With `--auto`:** Auto-add missing changelog entries.
- **Without `--auto`:** Offer to add them.

If no changelog, skip silently.

**Stale plans:** If `documentation/planning/` exists, check for:
1. **Completed but unarchived** — all phases `✅ COMPLETE` but still in `documentation/planning/`.
2. **Stale and abandoned** — idle 14+ days with incomplete phases.

- **With `--auto`:** Auto-archive completed plans via `git mv`. Flag stale plans in the handoff file for next session's attention.
- **Without `--auto`:** Offer archive/delete/skip.

If none found, skip silently.

---

## Step 4: Write Handoff File

**Location:** `~/.claude/notes/projects/<project-slug>/claudna:context-resume.md`

**Slug derivation:** Git remote `org/repo` with `/` replaced by `--`. Fallback: directory name. Must match what `/claudna:context-resume` uses.

Write tool creates parent directories automatically. See [templates.md](references/templates.md) for the output format.

The handoff file is agent-optimized — structured for machine parsing, not human reading. It is ephemeral and overwritten each session.

After writing:
- **With `--auto`:** Silent. No confirmation message needed.
- **Without `--auto`:** "Handoff written to `~/.claude/notes/projects/<slug>/claudna:context-resume.md`. Use `/claudna:context-resume` next session."

---

## Integration Points

Other skills should trigger `/claudna:session-handoff --auto` at natural end-of-work boundaries:

- `/claudna:commit-push-pr` — after PR is created, suggest or auto-run handoff
- `/claudna:implement-plan` — after final phase is complete
- Pre-restart hooks — before `systemctl restart` or session teardown
- Context compaction — when the system compresses context, trigger a background handoff to capture state before it's summarized away

---

## Rules

- **Speed over thoroughness.** Scan, validate, write. Do not turn this into a documentation exercise.
- **One approval round per step (interactive mode only).** Do not ask multiple rounds of questions within a step.
- **No compound commands.** Never chain commands with `&&`, `||`, or `;`. Make separate parallel tool calls instead — `allowed-tools` patterns only match simple commands, not compound ones.
- **User says skip, you skip.** The handoff file is the only non-optional output.
- **With `--auto`, never ask.** Auto-fix verifiable issues, skip ambiguous ones, save learnings, write handoff. Zero interaction.
- **Validate before capture.** Step 0 always runs before Steps 1-4. Don't save new state on top of stale state.
- **Handoff file is ephemeral.** Not a log. Overwritten each session.

---

## Structured Result Emission (`--auto` only)

When `--auto` is set, emit the structured-result shape per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "session-handoff",
  "outcome": "completed",
  "artifacts": {
    "handoff_path": "~/.claude/notes/projects/<slug>/claudna:context-resume.md",
    "memories_pruned": 2,
    "memories_updated": 1,
    "learnings_saved": 3,
    "changelog_entries_added": 0,
    "plans_archived": 0
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success; `partial` if any step failed (record in `errors`).
- `handoff_path` is required (it's the skill's primary artifact).

Interactive mode (no `--auto`) does NOT emit the JSON block — it presents human-readable confirmation messages as today.
