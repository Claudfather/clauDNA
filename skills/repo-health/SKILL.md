---
name: repo-health
description: "Use when you want a birds-eye view across multiple repositories to decide where to spend your time."
---

# Repo Health

Birds-eye view across multiple repositories. Scan for open PRs, CI status, stale branches, pending plan docs, and uncommitted work — then present a single dashboard.

**Reference:** `health-checks.md` — detailed check definitions, commands, and example output formats.

## Procedure

Follow these steps exactly in order.

---

### Step 1: Discover Repos

Ask the user how to find repos:

1. **"Scan a parent directory?"** — provide a path (e.g., `~/Projects`). Use Glob with `*/.git` to find repos one level deep.
2. **"Specific repos?"** — provide a list of paths.
3. **"Use saved list?"** — check `~/.claude/notes/repo-health-repos.txt` for a previously saved list.

Present discovered repos and ask the user to confirm. Offer to save the list for next time.

**If using a saved list**, validate each path exists and contains `.git/`. Report dead entries and ask: **"Remove the dead entries from your saved list?"**

---

### Step 2: Scan Each Repo

Launch one **Explore subagent** per repo for parallel scanning. Gather per-repo data points (see `health-checks.md` for commands):

Current branch, working tree status, open PRs (mine), PRs to review, CI status, stale branches (14+ days), in-progress plans, pending plans, last commit, stash count.

---

### Step 3: Present the Dashboard

Show a compact summary table — one line per repo with branch, tree status, PR count, review count, CI status. Include a totals row. Then expand with a **Needs Attention** section for repos with issues. See `health-checks.md` for detail format and examples.

---

### Step 4: Recommend Priorities

Suggest a priority order: CI failures > PRs needing your review > PRs with changes requested > uncommitted changes > in-progress plans > stale branches.

Present as a short numbered list with specific actions. Ask: **"Which repo do you want to start with?"**

---

### Step 5: Hygiene Check

After the main dashboard, run a quick hygiene scan. Skip entirely if everything is clean. Check three areas (see `health-checks.md` for criteria and output formats):

- **Stale planning sessions** — abandoned or never-started sessions in `documentation/planning/`. Offer to archive, delete, or skip each.
- **Backup retention** — old clauDNA backups in `~/.local/share/clauDNA/backups/`. Offer to prune backups older than 30 days.
- **Orphaned context-resume files** — dirs in `~/.claude/notes/projects/` whose repos no longer exist. Offer to remove.

---

### Step 6: Handoff

Once the user picks a repo, suggest the relevant skill (`/context-resume`, `/review-pr`, `/implement-plan`). If it's a different directory, tell the user to switch there first.

---

## Notes

- **Speed matters.** Triage tool, not a deep audit. Scan fast, present concisely.
- **Subagent parallelism.** Launch one Explore subagent per repo for speed.
- **Saved repo list.** `~/.claude/notes/repo-health-repos.txt` — one path per line, never synced.
- **CI is best-effort.** Skip gracefully if `gh` is unavailable; note "no CI data."
- **Mostly read-only.** Steps 1–4 and 6 don't modify anything. Step 5 modifies only with explicit user confirmation.
- **Stale branch threshold.** 14 days, configurable if the user asks.
- **GitHub CLI dependency.** PR/CI data requires `gh` and an authenticated session.
