---
name: context-resume
user-invocable: true
description: "Use at the start of a new session to pick up where you left off. Counterpart to /claudna:session-handoff."
allowed-tools: Bash(git *), Bash(gh *), Bash(stat *), Bash(ls *), Read, Grep, Glob
---

# Context Resume

Restore context fast. Target: under 30 seconds.

## Step 1: Identify Project & Read Handoff

Derive the project slug:
1. `git remote get-url origin` — extract `org/repo` (e.g., `your-org/api-server`)
2. Fallback: current directory name
3. Replace `/` with `--` for the file path (e.g., `your-org--api-server`)

Check for handoff file at `~/.claude/notes/projects/<slug>/claudna:context-resume.md`.

If it exists, read it — this is the most valuable context. **Staleness check:** if older than 14 days, flag it ("Last handoff was N days ago — context may be stale") but still read it for reference. Weight the live scan more heavily when stale.

## Step 2: Scan Current State (in parallel)

Run these in parallel:

**Git:** `git status`, `git log --oneline -15`, `git branch --list`, `git stash list`

**PRs:** `gh pr list --author @me`, `gh pr list --review-requested @me`

**Plan docs:** Grep `documentation/planning/` for `IN PROGRESS` and `PENDING` status markers. Check for `00_OVERVIEW.md` or `00_TECH_DEBT.md`. Also flag any sessions where all phases are `✅ COMPLETE` but haven't been archived to `documentation/archive/` — suggest archiving.

**Project context:** Skim `CHANGELOG.md` unreleased section if present.

Do NOT read CLAUDE.md or MEMORY.md here — Claude already has those in context.

## Step 3: Present Briefing & Suggest Starting Point

Use the format from [references/templates.md](references/templates.md).

Suggest what to work on, prioritized:
1. PR with changes requested — "PR #N has changes requested. Address those first?"
2. In-progress plan doc — "Phase N is in progress. Continue with `/claudna:implement-plan`?"
3. PRs to review — "N PRs waiting for review. Run `/claudna:review-pr N`?"
4. Handoff next steps — "Last session suggested: [step]. Pick that up?"
5. Dirty working tree — "Uncommitted changes. Review and commit first?"

Ask: **"What would you like to focus on?"**

## Rules

- **Read-only.** Never modify files, never commit.
- **Speed over depth.** Scan, summarize, suggest. No deep analysis.
- **No compound commands.** Never chain commands with `&&`, `||`, or `;`. Make separate parallel tool calls instead — `allowed-tools` patterns only match simple commands, not compound ones.
- **Handoff file is gold.** Prioritize curated handoff context over raw git scanning.
- **Slug must match /claudna:session-handoff.** Both use: git remote `org/repo` with `/` to `--`, directory name fallback.
