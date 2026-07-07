Invoked by /claudna:audit in repo-health mode — a birds-eye view across multiple repositories to decide where to spend your time: activity, staleness, CI health, and open work.

Scan for open PRs, CI status, stale branches, pending plan docs, and uncommitted work — then present a single dashboard. For depth on a single codebase's debt, use `/claudna:audit tech-debt`.

**Reference:** `health-checks.md` (same directory) — detailed check definitions, commands, and example output formats.

## Lens arguments (beyond contract §2)

Shared argument semantics live in `skills/_shared/audit-lens-contract.md` §2. Lens-specific:

- `[focus]` — a parent directory path to scan. If provided, skip the discovery prompt (Step 1).
- **Interactive-only** (**auto: no** in the engine table). This lens has no non-interactive variant — `--auto` is answered by the engine's blocked-result path (contract §4); never improvise one here.

## GitHub reads vs. issue filing

Reading GitHub via `gh` (PR lists, CI checks, run history — see `health-checks.md`) is core to this lens and stays direct. Contract §2's rule that lenses never call `gh` directly governs issue **filing**: findings filed as issues route through `/claudna:publish`.

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

Once the user picks a repo, suggest the relevant skill (`/session-resume`, `/review-pr`, `/implement-plan`). If it's a different directory, tell the user to switch there first.

---

## Output Targets

Follow the output guide at `skills/_shared/output-guide.md`. Beyond the shared `--output github|session` surface (contract §2), this lens supports a `docs` target for persisting the dashboard:

- For `github`: write each finding as a doc (frontmatter + the Section 4 body skeleton) and delegate to `/claudna:publish <file> --to github-issue --repo <repo>` — publish validates, dedups, and applies labels from `tags:`. Create one issue per repo with actionable findings (stale branches, failing CI, PRs needing review). Label with `auto-audit` and `repo-health`.
- For `session` (engine default): produce the doc, then `/claudna:publish <file> --to session` prints it to chat (Section 5)
- For `docs`: write the dashboard and priority recommendations to `documentation/planning/repo_health/<session_name>_<YYYY-MM-DD>/` (underscore form, matching the `tech_debt/` planning-dir convention)

---

## Notes

- **Speed matters.** Triage tool, not a deep audit. Scan fast, present concisely.
- **Subagent parallelism.** Launch one Explore subagent per repo for speed.
- **Saved repo list.** `~/.claude/notes/repo-health-repos.txt` — one path per line, never synced.
- **CI is best-effort.** Skip gracefully if `gh` is unavailable; note "no CI data."
- **Mostly read-only.** Steps 1–4 and 6 don't modify anything. Step 5 modifies only with explicit user confirmation.
- **Stale branch threshold.** 14 days, configurable if the user asks.
- **GitHub CLI dependency.** PR/CI data requires `gh` and an authenticated session.
