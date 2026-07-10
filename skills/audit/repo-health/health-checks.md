# Health Checks Reference

Detailed definitions for each check performed by the repo-health skill.

---

## Per-Repo Data Points (Step 2)

| Data | How |
|------|-----|
| **Current branch** | `git -C <repo> branch --show-current` |
| **Working tree** | `git -C <repo> status --porcelain` (count modified/untracked/staged) |
| **Open PRs (mine)** | `gh pr list -R <remote> --author @me --json number,title,reviewDecision,updatedAt` |
| **PRs to review** | `gh pr list -R <remote> --review-requested @me --json number,title,author` |
| **CI status** | `gh pr checks <number>` for open PRs, or `gh run list -R <remote> --limit 1` |
| **Stale branches** | Local branches with no commits in 14+ days |
| **In-progress plans** | Search `documentation/planning/` for `🔧 IN PROGRESS` markers |
| **Pending plans** | Search `documentation/planning/` for `📋 PENDING` markers |
| **Last commit** | `git -C <repo> log -1 --format="%ar — %s"` |
| **Stashes** | `git -C <repo> stash list` count |

---

## Summary Dashboard Format (Step 3)

```
Repo Health Dashboard
═══════════════════════════════════════════════════════════════════════════

  api-server         main  ✓ clean    2 PRs open   1 to review   CI ✓
  web-frontend       main  ⚠ 3 files  1 PR open    —             CI ✗
  shared-lib         main  ✓ clean    —            —             CI ✓
  data-pipeline      feat  ⚠ 1 file   —            —             CI ✓
  docs-site          main  ✓ clean    —            —             —

═══════════════════════════════════════════════════════════════════════════
  5 repos · 3 open PRs · 1 review needed · 1 CI failing · 4 dirty files
```

---

## Needs-Attention Detail Format (Step 3)

After the summary dashboard, expand repos that need attention:

```
Needs Attention
═══════════════════════════════════════════════════════════════════════════

  web-frontend:
    ⚠  Working tree: 3 modified files (uncommitted)
    🔴 CI failing on PR #31 "Update auth flow"
       Last check: "test-integration" failed 2h ago
    📋 Pending plan: documentation/planning/phases/auth_2026-02-08/03_session.md

  api-server:
    👀 PR #48 from @teammate waiting for your review
    🔧 In-progress plan: documentation/planning/tech_debt/caching_2026-02-09/02_redis.md

  data-pipeline:
    ⚠  On branch feat/new-source — 1 uncommitted file
    🕸  2 stale branches (>14 days): fix/old-bug, experiment/test

═══════════════════════════════════════════════════════════════════════════
```

---

## Hygiene Checks (Step 5)

Only report items that need attention. Skip this step entirely if everything is clean.

### Stale Planning Sessions

Check `documentation/planning/` for session directories where:
- No file has been modified in 14+ days
- The session contains a mix of `✅ COMPLETE` and `📋 PENDING` docs (abandoned mid-session)
- Or all docs are still `📋 PENDING` (never started)

```
Stale Planning Sessions
═══════════════════════════════════════════════════════════════════════════
  api-server:
    🕸  phases/onboarding_2026-01-15/  — last activity 26 days ago
        2 of 4 phases complete, 2 pending (abandoned?)
    🕸  tech_debt/db-cleanup_2026-01-20/  — last activity 21 days ago
        All 3 phases pending (never started)

  web-frontend:
    🕸  phases/auth_2026-01-28/  — last activity 13 days ago
        1 of 2 phases complete, 1 in progress
═══════════════════════════════════════════════════════════════════════════
```

For each stale session, ask: **"Archive it, delete it, or skip?"**
- **Archive** — move the entire session directory to `documentation/archive/` (use `git mv`)
- **Delete** — remove the directory (confirm twice — this is destructive)
- **Skip** — leave it for now

### Backup Retention

Check `~/.local/share/clauDNA/backups/`:
- Count total backup directories and total size
- If there are backups older than 30 days, report:

```
clauDNA Backups
═══════════════════════════════════════════════════════════════════════════
  Total:   12 backups (48 MB)
  Oldest:  2026-01-10 (31 days ago)
  Newest:  2026-02-10 (today)

  8 backups older than 30 days (32 MB)
═══════════════════════════════════════════════════════════════════════════
```

Ask: **"Prune backups older than 30 days?"** If confirmed, delete the old directories.
