Invoked by /claudna:audit in repo-health mode — a birds-eye view across multiple repositories to decide where to spend your time: activity, staleness, CI health, and open work.

Scan for open PRs, CI status, stale branches, pending plan docs, and uncommitted work — then present a single dashboard. For depth on a single codebase's debt, use `/claudna:audit tech-debt`.

**Reference:** `health-checks.md` (same directory) — detailed check definitions, commands, and example output formats.

## Lens arguments (beyond contract §2)

Shared argument semantics live in `../../_shared/audit-lens-contract.md` §2. Lens-specific:

- `[focus]` — a parent directory path to scan. If provided, skip the discovery prompt (Step 1).
- **Interactive-only** (**auto: no** in the engine table). This lens has no non-interactive variant — `--auto` is answered by the engine's blocked-result path (contract §4); never improvise one here.

## GitHub reads vs. issue filing

Reading GitHub via `gh` (PR lists, CI checks, run history — see `health-checks.md`) is core to this lens and stays direct under existing permissions. Contract §2 routes output mutations through `/claudna:publish`: findings filed as issues use that path.

## Procedure

Follow these steps exactly in order.

---

### Step 1: Discover Repos

Ask the user how to find repos:

1. **"Scan a parent directory?"** — provide a path (e.g., `~/Projects`). Use Glob with `*/.git` to find repos one level deep.
2. **"Specific repos?"** — provide a list of paths.
3. **"Use saved list?"** — check the shared clauDNA state list below for a previously saved list.

Present discovered repos and ask the user to confirm. Offer to save the list for next time.

**If using a saved list**, validate each path exists and contains `.git/`. Report dead entries and ask: **"Remove the dead entries from your saved list?"** For an older Claude Code list, discovery at `~/.claude/repo-health-repos.txt` is read-only: offer its entries for this run, and never modify or migrate that legacy file. If the user explicitly asks to save the current list, write only the canonical shared file below.

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

After the main dashboard, run a quick hygiene scan. Skip entirely if everything is clean. Check two areas (see `health-checks.md` for criteria and output formats):

- **Stale planning sessions** — abandoned or never-started sessions in `documentation/planning/`. Offer to archive, delete, or skip each.
- **Backup retention** — old clauDNA backups in `~/.local/share/clauDNA/backups/`. Offer to prune backups older than 30 days.

---

### Step 6: Handoff

Once the user picks a repo, suggest the relevant skill (`/claudna:session resume`, `/claudna:review-work pr`, `/build`). If it's a different directory, tell the user to switch there first.

---

## Output Targets

Follow the output guide at `../../_shared/output-guide.md`. This lens defaults to retaining the final dashboard under the current owner's `<artifacts>` directory and supports explicit `session`, `github`, and `docs` destinations:

- For `artifacts` (default): retain `00_REPO_HEALTH.md` with `/claudna:publish <artifacts>/00_REPO_HEALTH.md --to artifacts` and present its path and summary. Resolve the actual SID/provider and exact paths through orchestration guide §1.
- For `session`: present the dashboard in chat only; write no report file.
- For `github`: write selected issue docs under `<artifacts>/repo_health/`, then explicitly export them with `/claudna:publish <artifact-file> --to github-issue --repo <repo>`; retain every source and the report. Use frontmatter and the Section 4 body skeleton; publish validates, dedups, and labels (`auto-audit` and `repo-health`). Create one issue per repo with actionable findings.
- For `docs`: explicitly export the selected canonical dashboard to `documentation/planning/repo_health/<session_name>_<YYYY-MM-DD>/`; retain the source.

---

## Notes

- **Speed matters.** Triage tool, not a deep audit. Scan fast, present concisely.
- **Subagent parallelism.** Launch one Explore subagent per repo for speed.
- **Saved repo list.** `R/repo-health-repos.txt` is shared across hosts, one absolute repo path per line. Resolve `R` with the loaded clauDNA session-store path resolver (`$CLAUDNA_STATE_DIR`, else `~/.claudna`); do not use host config, Claude's plugin cache, or agent memory. Reject an invalid relative override rather than silently falling back. The previous Codex location (`R/repo-health-repos.txt`) is already this file. The old Claude Code list at `~/.claude/repo-health-repos.txt` may be discovered read-only as described in Step 1; never modify or migrate it. Saving requires the user's explicit authorization and writes only the canonical file. Create the state root with private permissions only when saving is authorized, preserve existing directory modes, and write the new shared file; do not create state during lookup.
- **CI is best-effort.** Skip gracefully if `gh` is unavailable; note "no CI data."
- **Mostly read-only.** Steps 1–4 and 6 don't modify anything. Step 5 modifies only with explicit user confirmation.
- **Stale branch threshold.** 14 days, configurable if the user asks.
- **GitHub CLI dependency.** PR/CI data requires `gh` and an authenticated session.
