---
name: github-activity-report
user-invocable: true
description: "Use when the user asks for GitHub activity stats (PRs authored, commits, top contributors, top repos) across an organization or their personal account over a time window. Iterates per-repo to avoid the search API's 1,000-result cap."
---

# GitHub Activity Report

Pulls accurate per-org or per-user GitHub activity stats over a chosen time window. Avoids the GitHub search API's 1,000-result pagination cap by iterating each repo's `pulls` and `commits` endpoints directly.

**Reference:** `crawl.sh` — the per-repo crawl script. Copy it into a working directory and run.

---

## What this produces

A markdown report with:

- Headline totals: PRs authored (open/merged/closed), commits, repos crawled
- Top PR authors (ranked)
- Top commit authors (ranked)
- **All repos by PR volume** (full long-tail list, not just top 20)
- **All repos by commit volume**
- **PRs by repository × top authors** (top-N repos cross-tabbed with their #1–#4 authors and share %)
- **Concentration insight**: who is #1 in which repos, dominant share (>80%), and which repo patterns exist (solo-driven vs lead-with-team vs multi-contributor)
- Caveats (search-API cap, identity-string fallback for unattributed commits, bot traffic)

Saved to `~/Downloads/<scope>-activity-<since>_to_<until>.md` by default. Raw JSONL data is left in `/tmp/gh-activity-stats/` for further slicing.

---

## Procedure

Follow these steps exactly in order.

### Step 1: Pick the scope

Check `gh auth status` first — confirm the user is logged in. Then list the orgs they belong to:

```bash
gh api user/orgs --jq '.[].login'
gh api user --jq '.login'
```

Present an interactive menu with **all the user's orgs plus their personal account**:

```
Pick a scope:
  1. <org-1>
  2. <org-2>
  ...
  N. <username> (personal repos)
```

Wait for the user's pick. Save the chosen scope as `SCOPE` (the org login or the personal username) and remember whether it's `org` or `user` — the API endpoints differ slightly.

### Step 2: Pick the window

Default to **6 months back from today** (`SINCE = today - 6mo`, `UNTIL = today`, both as `YYYY-MM-DD`). Offer the user a chance to override (e.g., "last 30 days", "2025-01-01 to 2025-06-30", "1 year").

Confirm the resolved dates back to the user before crawling.

### Step 3: List repos

For an **org**:

```bash
gh api graphql --paginate -f query='
query($endCursor: String) {
  organization(login: "<SCOPE>") {
    repositories(first: 100, after: $endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { name isArchived }
    }
  }
}' --jq '.data.organization.repositories.nodes[] | select(.isArchived == false) | .name'
```

For a **personal account** (include private repos the user owns, exclude forks unless they ask):

```bash
gh api graphql --paginate -f query='
query($endCursor: String) {
  viewer {
    repositories(first: 100, after: $endCursor, ownerAffiliations: OWNER, isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes { name isArchived }
    }
  }
}' --jq '.data.viewer.repositories.nodes[] | select(.isArchived == false) | .name'
```

Save to `/tmp/gh-activity-stats/repos.txt`. Show the count and ask the user to confirm before crawling (active repos × 2 endpoints × paged calls = potentially hundreds of API calls).

### Step 4: Run the crawl

Copy `crawl.sh` (alongside this skill) into `/tmp/gh-activity-stats/` and run it. Pass the scope, since, until via env vars:

```bash
SCOPE=<scope> SINCE_DATE=<YYYY-MM-DD> UNTIL_DATE=<YYYY-MM-DD> /tmp/gh-activity-stats/crawl.sh
```

The script writes:
- `/tmp/gh-activity-stats/prs.jsonl` — one PR per line, with repo/user/created/merged/state/number
- `/tmp/gh-activity-stats/commits.jsonl` — one commit per line, with repo/sha/author/date
- `/tmp/gh-activity-stats/per_repo.tsv` — counts per repo
- `/tmp/gh-activity-stats/crawl.log` — progress log

**Run it in the background** with `run_in_background: true` and use `Monitor` to watch progress (see "Monitoring" below). Crawls can take 5–20 minutes depending on org size.

### Step 5: Roll up stats

Once the crawl finishes, compute aggregates with `jq`:

```bash
cd /tmp/gh-activity-stats
echo "PRs total:    $(wc -l < prs.jsonl)"
echo "Commits total: $(wc -l < commits.jsonl)"
echo "Merged PRs:   $(jq -c 'select(.merged != null)' prs.jsonl | wc -l)"
echo "Open PRs:     $(jq -c 'select(.state == "open")' prs.jsonl | wc -l)"

# Top PR authors
jq -r '.user' prs.jsonl | sort | uniq -c | sort -rn | head -25

# Top commit authors
jq -r '.author' commits.jsonl | sort | uniq -c | sort -rn | head -25

# All repos by PRs (full list, not capped — the long tail is informative)
jq -r '.repo' prs.jsonl | sort | uniq -c | sort -rn

# All repos by commits
jq -r '.repo' commits.jsonl | sort | uniq -c | sort -rn

# PRs by repository × top authors (cross-tab for the top 10 repos)
top_repos=$(jq -r '.repo' prs.jsonl | sort | uniq -c | sort -rn | head -10 | awk '{print $2}')
for repo in $top_repos; do
  echo ""
  echo "=== $repo (top 10 authors) ==="
  jq -r --arg r "$repo" 'select(.repo==$r) | .user' prs.jsonl | sort | uniq -c | sort -rn | head -10
done
```

### Step 6: Write the report

Generate `~/Downloads/<scope>-activity-<since>_to_<until>.md` with:

- Title, window, generation date, scope, method line
- Headline totals table
- Top 25 PR authors table
- Top 25 commit authors table
- **All repos by PR volume** (full list — bold the top 10)
- **All repos by commit volume** (full list)
- **PRs by repository × top authors** — for the top 10 repos by PR count, show a row per repo with its #1–#4 authors and each author's share of that repo's PRs as a percent. Bold any repo where one author owns >80% of PRs (solo-driven), and bold the dominant author's row for repos where they're #1.
- **Concentration insight** — narrative section that names:
  - Which user is #1 by PRs in which repos (count of "#1 spots")
  - Which repos are >80% owned by a single author ("solo-driven")
  - The split between solo-driven, lead-with-team, and multi-contributor repos
  - Where the top user is *absent* from the top 10 (often equally informative)
- **Caveats section** (always include — see template below)

### Step 7: Confirm

Tell the user the report path and the raw JSONL location. Offer to slice further (e.g., "Show me <user>'s breakdown by repo" or "Strip bots and re-rank").

---

## Caveats template (always include in the report)

Always include these four caveats verbatim — they're the gotchas that surprised the user the first time and will surprise them again:

```markdown
## Caveats

- **GitHub search API 1,000-result cap**: A naive `gh api search/issues` query returns accurate `total_count` but only paginates through the first 1,000 hits, so author/repo splits derived from search are biased toward whichever sort order GitHub picked. This report iterates each repo's `pulls` and `commits` endpoints, which have no such cap.
- **Commit authorship attribution**: When a commit's GitHub user can't be resolved (no linked account), we fall back to the raw `commit.author.name` string. That's why the same human can appear under multiple identity strings.
- **Bot traffic**: `dependabot[bot]`, CI bots, and similar automated accounts can dominate the rankings. Strip them if you want a "humans only" view.
- **Non-merge commits**: All commits on default branches (including merge commits) are counted. PR review activity (comments, reviews) is not included.
```

---

## Monitoring

The crawl prints `[N/total] <repo>` to stderr per repo. Use `Monitor` with an `until DONE` loop to get progress pings every 30s without polling:

```
until grep -q "^DONE" /tmp/gh-activity-stats/crawl.log; do
  rows=$(wc -l < /tmp/gh-activity-stats/per_repo.tsv 2>/dev/null)
  prs=$(wc -l < /tmp/gh-activity-stats/prs.jsonl 2>/dev/null)
  cms=$(wc -l < /tmp/gh-activity-stats/commits.jsonl 2>/dev/null)
  last=$(tail -1 /tmp/gh-activity-stats/crawl.log)
  echo "progress: repos_done=$((rows-1)) prs=$prs commits=$cms last=$last"
  sleep 30
done
echo "DONE"
```

---

## Anti-patterns

- **Don't trust `gh api search/issues` author/repo splits.** Totals from `total_count` are correct, but per-author and per-repo breakdowns truncate at 1,000 results. The user has been burned by this — always crawl per-repo for splits.
- **Don't add LOC stats by default.** Lines-of-code requires fetching each commit's `stats.additions/deletions`, which is one API call per commit. For an active org over 6 months that's thousands of requests and hits secondary rate limits. Only attempt if the user explicitly asks and accepts the runtime.
- **Don't forget the `--paginate` flag** on the org-repo listing — orgs with >100 repos will silently truncate without it.
- **Don't hard-code any specific org or user.** This skill is generic. Always start with the scope-picker menu.
