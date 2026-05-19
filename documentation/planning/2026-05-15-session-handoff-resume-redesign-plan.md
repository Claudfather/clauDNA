# Session Handoff & Resume Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/session-handoff` + `/context-resume` with a redesigned pair (`/session-handoff` + `/session-resume`) keyed by cwd, writing to `<cwd>/.claude/session.md`, with an evidence + TTL reaper. Shed all knowledge-capture work to Claudron's lane.

**Architecture:** Two skills sharing one reaper rules reference file. New skill writes a per-item-timestamped markdown file inside the project's own `.claude/` dir (gitignored). Reaper runs on every read AND write. `--auto` flag for headless callers (Claudlobby bots).

**Tech Stack:** Markdown SKILL.md files. Bash/git/gh in `allowed-tools`. No code, no test framework — verification is end-to-end manual scenarios.

**Spec:** `documentation/planning/2026-05-15-session-handoff-resume-redesign-design.md` (commit `0848092`)

**Sibling work tracked at:** https://github.com/Claudfather/Claudlobby/issues/223

---

## File structure

**Created:**
- `global/skills/_shared/reaper-rules.md` — single source of truth for the reaper contract, sourced by both skills
- `global/skills/session-resume/SKILL.md` — created by `git mv` from `context-resume/`, then rewritten

**Rewritten:**
- `global/skills/session-handoff/SKILL.md` — full rewrite per spec
- `global/skills/session-handoff/references/templates.md` — new schema (per-item timestamps, schema_version: 2)

**Modified:**
- `global/skills/_shared/orchestration-guide.md` — rename `context-resume` → `session-resume`
- `global/skills/repo-health/SKILL.md` — rename `/context-resume` → `/session-resume` in the suggestion list
- `README.md` — rename references
- `CHANGELOG.md` — breaking-change entry

**Renamed:**
- `global/skills/context-resume/` → `global/skills/session-resume/` (via `git mv`)

**Deleted:**
- `global/skills/session-resume/references/templates.md` — the old briefing template is incorporated inline into the new SKILL.md (single source of truth, no separate file needed)

**Out of scope (deliberately left alone):**
- `global/skills/notes/SKILL.md` — `~/.claude/notes/projects/<project>.md` references are the `/notes` mechanism, not handoff
- `global/skills/dbt/SKILL.md` line 18 — same `/notes` mechanism
- `global/skills/init-project/references/CLAUDE_MD_TEMPLATE.md` line 109 — name mention only, still valid
- `global/skills/cache-audit/cache-checks.md` line 82 — name mention only, still valid
- `global/skills/repo-health/health-checks.md` orphan-check — still valid for cleaning up legacy `~/.claude/notes/projects/` files during the migration window

---

## Task 1: Create the shared reaper rules file

**Files:**
- Create: `global/skills/_shared/reaper-rules.md`

The reaper contract is byte-identical between `/session-handoff` and `/session-resume`. Putting it in `_shared/` (which already houses `orchestration-guide.md`, etc.) prevents drift. Both SKILL.md files reference this file by relative path.

- [ ] **Step 1: Write the file**

Create `global/skills/_shared/reaper-rules.md` with this exact content:

````markdown
# Reaper Rules — `/session-handoff` and `/session-resume`

The reaper runs on every write (in `/session-handoff`) and every read (in `/session-resume`). Its job: prune stale items from `<cwd>/.claude/session.md` so the file stays scoped to live work.

## Inputs

- The current contents of `<cwd>/.claude/session.md` (if it exists)
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
| `Next Steps` | Plan phase referenced is now `✅ COMPLETE` | hard drop |
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

The reaper returns a new in-memory representation of the file with stale items removed and survivors preserved. The caller (handoff or resume) decides whether to write back.

## Determinism

Hard drops are mechanical. Soft drops involve LLM judgment, but the criteria above must be applied consistently — do not improvise. Treat the criteria as a checklist.
````

- [ ] **Step 2: Commit**

```bash
git add global/skills/_shared/reaper-rules.md
git commit -m "feat: shared reaper rules for session handoff/resume"
```

---

## Task 2: Rewrite `/session-handoff` SKILL.md

**Files:**
- Modify: `global/skills/session-handoff/SKILL.md` (full replacement)

The current SKILL.md does memory validation, notes pruning, learnings capture, and changelog backfill — all of which are removed. New SKILL.md is much smaller.

- [ ] **Step 1: Replace SKILL.md with the new content**

Replace `global/skills/session-handoff/SKILL.md` with this exact content:

````markdown
---
name: session-handoff
description: "Use at the end of a session to write a per-cwd handoff file (<cwd>/.claude/session.md) capturing live state, activity, decisions, open questions, and next steps. Reaps stale items on write. Counterpart to /session-resume. --auto for headless callers."
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
3. Else create `<cwd>/.claude/.gitignore` containing `session.md`.

This is idempotent — step 1 catches both "already there" and "ignored by parent dir" (e.g., Claudlobby's `runtime/` is ignored at the Claudlobby root, so individual bot dirs need no further action).

### 9. Confirm

- **With `--auto`:** Silent.
- **Without `--auto`:** "Handoff written to `<cwd>/.claude/session.md`. Use `/session-resume` next session."

## Rules

- **Speed over thoroughness.** Reap, scan, write. Not a documentation exercise.
- **Reaper rules in `_shared/`.** Do not duplicate them inline. Read `../_shared/reaper-rules.md` and apply.
- **No writes to `~/.claude/`.** This skill stays out of the user-config tree entirely.
- **No compound commands.** Make separate parallel tool calls — `allowed-tools` patterns only match simple commands.
- **`State` is always regenerated.** Never reaped, never merged with prior State.
- **`--auto` means silent.** Reaper is the only pruning mechanism in `--auto`; user-driven pruning is interactive-only.
- **Atomic write.** `tmp` + `mv` so a concurrent reader (e.g., a bot mid-task) never sees a half-written file.
````

- [ ] **Step 2: Verify the file is well-formed**

Run: `head -10 global/skills/session-handoff/SKILL.md`
Expected: starts with `---\nname: session-handoff\n...`

- [ ] **Step 3: Commit**

```bash
git add global/skills/session-handoff/SKILL.md
git commit -m "refactor: rewrite /session-handoff to scoped per-cwd handoff"
```

---

## Task 3: Update `/session-handoff` references/templates.md

**Files:**
- Modify: `global/skills/session-handoff/references/templates.md` (full replacement)

The old template wrote to `~/.claude/notes/projects/<slug>/context-resume.md` and had no per-item timestamps. New template matches schema_version: 2.

- [ ] **Step 1: Replace templates.md with the new content**

Replace `global/skills/session-handoff/references/templates.md` with:

````markdown
# Handoff File Format — `<cwd>/.claude/session.md`

Schema version: 2. Written by `/session-handoff`, read by `/session-resume`. Optimized for agent consumption.

```markdown
---
cwd: <absolute path to current working directory>
last_updated: <ISO-8601 UTC, e.g. 2026-05-15T14:30:00Z>
schema_version: 2
---

## State
branch: <current branch>
working_tree: <clean | dirty: N modified, N untracked, N staged>
stashes: <count>
open_prs:
  - "#N <title> (<state>)"
in_flight_branches:
  - <branch-name>

## Activity
- <ISO-8601 UTC> — <one-line summary, prefix with short hash if from a commit>

## Decisions
- <ISO-8601 UTC> — <decision and rationale>

## Open Questions
- <ISO-8601 UTC> — <blocker, unknown, pending input>

## Next Steps
- <ISO-8601 UTC> — <what the next session should start with>
```

## Format rules

- Every bullet under Activity / Decisions / Open Questions / Next Steps starts with an ISO-8601 UTC timestamp followed by ` — ` (em-dash with spaces). The reaper parses on this format.
- `State` is regenerated on every write — never preserves prior content.
- Empty sections may be omitted.
- A bullet may carry a `(stale-flagged YYYY-MM-DD)` suffix added by the reaper. On the next pass, if the soft-drop conditions still hold, the bullet is dropped.
- A bullet may carry a `[pin]` suffix added by the user to opt out of soft drops.
- Maximum 10 bullets per section. If a section grows past 10, the reaper drops oldest-first regardless of TTL.

## Migration from schema_version: 1

Legacy files at `~/.claude/notes/projects/<slug>/context-resume.md` use schema_version: 1 (no per-item timestamps; bullets in plain `- text` form; frontmatter with `session_date` only).

When `/session-resume` imports a v1 file, it assigns the file's `session_date` as the timestamp for every imported item, then runs the reaper. Most v1 items will hard-drop on first reap because they exceed TTL (Activity > 7d, etc.) — which is the correct behavior.
````

- [ ] **Step 2: Commit**

```bash
git add global/skills/session-handoff/references/templates.md
git commit -m "refactor: session.md schema v2 (per-item timestamps, cwd-keyed)"
```

---

## Task 4: Rename `context-resume` → `session-resume`

**Files:**
- Rename: `global/skills/context-resume/` → `global/skills/session-resume/`

- [ ] **Step 1: Rename via git mv**

```bash
git mv global/skills/context-resume global/skills/session-resume
```

- [ ] **Step 2: Verify**

```bash
ls global/skills/session-resume/
```
Expected: `SKILL.md  references`

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: rename /context-resume to /session-resume"
```

---

## Task 5: Rewrite `/session-resume` SKILL.md

**Files:**
- Modify: `global/skills/session-resume/SKILL.md` (full replacement)
- Delete: `global/skills/session-resume/references/templates.md`

The briefing template lived in `references/templates.md` but is short enough to inline. Single-file skill is easier to reason about.

- [ ] **Step 1: Replace SKILL.md with the new content**

Replace `global/skills/session-resume/SKILL.md` with:

````markdown
---
name: session-resume
description: "Use at the start of a new session to read <cwd>/.claude/session.md, reap stale items, scan live state, and brief the agent on where to pick up. Counterpart to /session-handoff. --auto for headless callers (Claudlobby bots)."
allowed-tools: Bash(git *), Bash(gh *), Bash(stat *), Bash(ls *), Bash(grep *), Bash(mv *), Bash(mkdir *), Read, Write, Glob
argument-hint: "[--auto]"
---

# Session Resume

Restore short-burst context fast. Counterpart to `/session-handoff`.

**Identity:** Keyed by **cwd**. Reads `<cwd>/.claude/session.md`.

Target: under 30 seconds.

## Arguments

Parse `$ARGUMENTS`:
- `--auto`: Headless. Skip step 7 (the user-focus question). Auto-import any legacy file silently.

## Steps

### 1. Read handoff

Read `<cwd>/.claude/session.md`.

If absent, check the legacy path: derive a slug from `git remote get-url origin` (extract `org/repo`, lowercase, replace `/` with `--`); fallback to lowercased dirname. Look for `~/.claude/notes/projects/<slug>/context-resume.md`. If found:

- **With `--auto`:** Import silently. Copy content into `<cwd>/.claude/session.md` (assign the legacy file's `session_date` as the timestamp for every imported bullet — see `references/templates.md` migration notes in `/session-handoff`). Delete the legacy file. Continue.
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
3. PRs awaiting review → "N PRs waiting for your review. Run `/review-pr N`?"
4. Handoff next-step → "Last session suggested: <step>. Pick that up?"
5. Dirty working tree → "Uncommitted changes. Review and commit first?"

### 7. Ask the user

Ask: **"What would you like to focus on?"**

**Skipped under `--auto`.** The agent returns control to its own loop with the briefing in context.

## Rules

- **Read-only by default.** Only writes are step 4 (write back if reaped) and step 1 legacy import. Never modifies code, never commits.
- **Speed over depth.** Scan, reap, summarize. No deep analysis.
- **Reaper rules in `_shared/`.** Do not duplicate them inline.
- **No compound commands.** Make separate parallel tool calls.
- **`--auto` is silent on the prompt.** Briefing and focus suggestion still emit (they are the agent's context payload); only the explicit user-question is suppressed.
- **Legacy import is one-shot per cwd.** Once imported, the legacy file is deleted, so this branch only fires once per project.
````

- [ ] **Step 2: Delete the now-redundant templates.md**

```bash
git rm global/skills/session-resume/references/templates.md
```

If `global/skills/session-resume/references/` is now empty:
```bash
rmdir global/skills/session-resume/references
```

- [ ] **Step 3: Verify**

```bash
ls global/skills/session-resume/
```
Expected: `SKILL.md` (and possibly `references/` if other files remain)

- [ ] **Step 4: Commit**

```bash
git add global/skills/session-resume/SKILL.md
git commit -m "refactor: rewrite /session-resume with reaper, --auto, legacy import"
```

---

## Task 6: Update internal references in clauDNA

**Files:**
- Modify: `global/skills/_shared/orchestration-guide.md:408`
- Modify: `global/skills/repo-health/SKILL.md:66`
- Modify: `README.md` (lines 42, 43, 131, 154, 155, 158)

These all reference the old `/context-resume` name. Pure rename.

- [ ] **Step 1: Update orchestration-guide.md**

In `global/skills/_shared/orchestration-guide.md`, change line ~408 from:
```
**Utility skills** (context-resume, session-handoff, lessons, notes, find-skills, ...) are not tiered ...
```
to:
```
**Utility skills** (session-resume, session-handoff, lessons, notes, find-skills, ...) are not tiered ...
```

(Use Edit with the surrounding context for uniqueness.)

- [ ] **Step 2: Update repo-health/SKILL.md**

In `global/skills/repo-health/SKILL.md`, change line ~66 from:
```
Once the user picks a repo, suggest the relevant skill (`/context-resume`, `/review-pr`, `/implement-plan`).
```
to:
```
Once the user picks a repo, suggest the relevant skill (`/session-resume`, `/review-pr`, `/implement-plan`).
```

Leave line 60 ("Orphaned context-resume files") alone — it correctly refers to legacy files in `~/.claude/notes/projects/` that need cleanup during the migration window.

- [ ] **Step 3: Update README.md**

In `README.md`, perform a textual rename of `/context-resume` → `/session-resume` on lines 42, 43, 131, 154, 155, 158. Verify with:

```bash
grep -n "context-resume" README.md
```
Expected after edits: only matches that refer to the *file system path* `~/.claude/notes/projects/<slug>/context-resume.md` (legacy, leave alone), not the skill name.

- [ ] **Step 4: Verify no other references slipped through**

```bash
grep -rn "/context-resume\|context-resume/SKILL\|context-resume/references" \
  --include="*.md" \
  global/ README.md CLAUDE.md SETUP_GUIDE.md CHANGELOG.md \
  documentation/ project-template/ 2>/dev/null
```
Expected: no matches (file-path mentions of the legacy `context-resume.md` filename are OK; what we want zero of is references to the *skill* by its old name).

- [ ] **Step 5: Commit**

```bash
git add global/skills/_shared/orchestration-guide.md global/skills/repo-health/SKILL.md README.md
git commit -m "refactor: update internal references to /session-resume"
```

---

## Task 7: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add a top entry**

Open `CHANGELOG.md`. If there's an `[Unreleased]` section, add to it. Otherwise add a new dated section above the most recent entry.

Add this exact content:

```markdown
## [Unreleased]

### Changed (BREAKING)
- **Renamed `/context-resume` → `/session-resume`.** Sibling change required in any caller (notably Claudlobby's `/restart`, tracked at https://github.com/Claudfather/Claudlobby/issues/223).
- **`/session-handoff` and `/session-resume` redesigned for per-cwd scope.** Handoff now lives at `<cwd>/.claude/session.md` (not `~/.claude/notes/projects/<slug>/context-resume.md`). Identity is the cwd, not a derived slug. Legacy files are imported once on first `/session-resume` in a given cwd and then deleted.
- **`/session-handoff` no longer touches `~/.claude/`.** Memory validation, notes/lessons capture, MEMORY.md pruning, and CHANGELOG backfill are removed. Use `/lessons` and `/notes` for cross-session knowledge until the Claudron-write skill ships.
- **Both skills now accept `--auto`.** Headless mode for Claudlobby bots and any other automated caller.
- **Schema version 2** for `session.md`: per-item ISO-8601 timestamps, regenerated `State` section, evidence + TTL reaper run on every read and write.

### Migration
Legacy `~/.claude/notes/projects/<slug>/context-resume.md` files are imported on first `/session-resume` in their corresponding cwd. Files for projects you never reopen will sit until manually deleted (the `/repo-health` orphan check covers this). 30 days post-release, the legacy import path itself will be removed.

Spec: `documentation/planning/2026-05-15-session-handoff-resume-redesign-design.md`
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entry for session handoff/resume redesign"
```

---

## Task 8: End-to-end verification in this repo

**No file changes — manual scenarios from the spec's Validation section.**

- [ ] **Step 0: Sync the new skills to the live install**

The skills live in `global/` (the source of truth) but are invoked from the user's `~/.claude/skills/` install. Per `CLAUDE.md`, push the changes to local first:

```
/clauDNA-setup
```

Confirm the prompts to install/overwrite `session-handoff/SKILL.md`, `session-resume/SKILL.md` (new dir), `_shared/reaper-rules.md`, and the renamed templates file. **Important:** if the old `~/.claude/skills/context-resume/` directory remains after sync, delete it manually — `/clauDNA-setup` adds files but does not remove the now-orphaned old skill dir. Verify:

```bash
ls ~/.claude/skills/session-resume/    # exists, contains SKILL.md
ls ~/.claude/skills/context-resume/    # should NOT exist
```

If `context-resume/` is still there:
```bash
rm -rf ~/.claude/skills/context-resume
```

- [ ] **Step 1: Run `/session-handoff --auto` in this clauDNA repo**

In a fresh terminal in `/Users/chris/Projects/clauDNA`:
```
/session-handoff --auto
```

Verify:
- File created: `ls -la /Users/chris/Projects/clauDNA/.claude/session.md` → exists
- Schema correct: `head -10 /Users/chris/Projects/clauDNA/.claude/session.md` → has frontmatter with `cwd:`, `last_updated:`, `schema_version: 2`
- `.gitignore` updated: `git check-ignore .claude/session.md` → exit 0
- No writes to `~/.claude/`: `find ~/.claude/notes/projects -newer documentation/planning/2026-05-15-session-handoff-resume-redesign-plan.md 2>/dev/null` → no output

If any check fails, fix the skill, recommit, retry.

- [ ] **Step 2: Reaper TTL test**

Edit `.claude/session.md` and change one Activity item's timestamp to 8 days ago (e.g., today minus 8d in ISO-8601). Then run:
```
/session-resume
```

Verify:
- The 8-day-old item is no longer in `.claude/session.md` after the run
- The file's `last_updated` was advanced (because the reaper wrote back)

- [ ] **Step 3: Reaper evidence test**

Add a line to Open Questions referencing a known-closed PR:
```
- 2026-05-15T10:00:00Z — Should we close PR #1?
```

(Use a real merged PR number from `gh pr list --state merged -L 1`.)

Run `/session-resume`. Verify the line is gone.

- [ ] **Step 4: Empty-cwd test**

```bash
mkdir -p /tmp/sessiontest && cd /tmp/sessiontest && git init
```

Run `/session-resume`. Verify graceful empty-state — a brief greeting + live-scan summary, no errors about missing files.

- [ ] **Step 5: Legacy import test**

Pick one of your existing legacy files in `~/.claude/notes/projects/` whose corresponding cwd you can `cd` into. (E.g., if you have `Example-org--warehouse`, `cd` into the dbt repo on disk.)

In that cwd, with no `.claude/session.md` present, run `/session-resume`. Verify:
- Prompt appears: "Found a legacy handoff at `<path>`. Import it? [y/N]"
- On `y`: `<cwd>/.claude/session.md` created with imported content; legacy file deleted
- On second invocation in same cwd: no prompt, no legacy file (confirms one-shot behavior)

- [ ] **Step 6: --auto resume test**

Back in the clauDNA repo, run `/session-resume --auto`. Verify:
- Briefing emitted to context
- No "What would you like to focus on?" prompt — control returns immediately

- [ ] **Step 7: Final cleanup commit (if needed)**

If any iteration was needed in steps 1–6, ensure all skill fixes are committed. Then the redesign is complete in clauDNA.

```bash
git status
git log --oneline -10
```

Expected: 7 redesign commits ahead of where we started, working tree clean.

---

## Post-implementation

After this plan completes:

1. Push the clauDNA branch and open a PR.
2. Switch to the Claudlobby repo. Implement Claudfather/Claudlobby#223 (rename `/claudna:context-resume` → `/claudna:session-resume` in the `/restart` skill, accept `--auto`, propagate it).
3. Land both PRs together to keep the contract intact.
4. Schedule a 30-day-out follow-up to remove the legacy import branch from `/session-resume`.
