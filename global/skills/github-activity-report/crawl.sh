#!/bin/bash
# Per-repo crawl for GitHub activity stats.
# Avoids the search API's 1,000-result pagination cap by hitting each repo's
# pulls and commits endpoints directly.
#
# Required env vars:
#   SCOPE          GitHub org login OR username (personal scope)
#   SINCE_DATE     YYYY-MM-DD (window start, inclusive)
#   UNTIL_DATE     YYYY-MM-DD (window end, inclusive)
#
# Optional:
#   OUT            output dir (default: /tmp/gh-activity-stats)
#   SCOPE_TYPE     "org" or "user" (default: org). Affects which API path lists repos.
#                  Repos must already be listed in $OUT/repos.txt — this script does not
#                  list repos itself; the calling skill writes that file.

set -u

: "${SCOPE:?SCOPE is required (org login or username)}"
: "${SINCE_DATE:?SINCE_DATE is required (YYYY-MM-DD)}"
: "${UNTIL_DATE:?UNTIL_DATE is required (YYYY-MM-DD)}"

OUT="${OUT:-/tmp/gh-activity-stats}"
SINCE="${SINCE_DATE}T00:00:00Z"
UNTIL="${UNTIL_DATE}T23:59:59Z"

mkdir -p "$OUT"

if [ ! -s "$OUT/repos.txt" ]; then
  echo "ERROR: $OUT/repos.txt not found or empty. The calling skill should write the repo list there before invoking this script." >&2
  exit 2
fi

: > "$OUT/prs.jsonl"
: > "$OUT/commits.jsonl"
echo -e "repo\tprs\tcommits" > "$OUT/per_repo.tsv"

i=0
total=$(wc -l < "$OUT/repos.txt" | tr -d ' ')
while read -r repo; do
  [ -z "$repo" ] && continue
  i=$((i+1))
  echo "[$i/$total] $repo" >&2

  # ---- PRs: list state=all, sorted desc by created, page until oldest < SINCE_DATE ----
  pr_count=0
  page=1
  while :; do
    resp=$(gh api "repos/$SCOPE/$repo/pulls?state=all&sort=created&direction=desc&per_page=100&page=$page" 2>/dev/null)
    n=$(echo "$resp" | jq 'length' 2>/dev/null)
    [ -z "$n" ] && break
    [ "$n" = "0" ] && break

    in_window=$(echo "$resp" | jq -c --arg s "$SINCE_DATE" --arg u "$UNTIL_DATE" --arg r "$repo" \
      '.[] | select(.created_at[:10] >= $s and .created_at[:10] <= $u)
           | {repo: $r, user: .user.login, created: .created_at, merged: .merged_at, state: .state, number: .number}')
    if [ -n "$in_window" ]; then
      echo "$in_window" >> "$OUT/prs.jsonl"
      pr_count=$((pr_count + $(echo "$in_window" | wc -l | tr -d ' ')))
    fi

    oldest=$(echo "$resp" | jq -r '.[-1].created_at[:10]')
    if [[ "$oldest" < "$SINCE_DATE" ]]; then break; fi
    [ "$n" -lt 100 ] && break
    page=$((page+1))
    [ "$page" -gt 100 ] && break
  done

  # ---- Commits: use since/until on the API ----
  commit_count=0
  page=1
  while :; do
    resp=$(gh api "repos/$SCOPE/$repo/commits?since=$SINCE&until=$UNTIL&per_page=100&page=$page" 2>/dev/null)
    n=$(echo "$resp" | jq 'length' 2>/dev/null)
    [ -z "$n" ] && break
    [ "$n" = "0" ] && break

    echo "$resp" | jq -c --arg r "$repo" \
      '.[] | {repo: $r, sha: .sha, author: (.author.login // .commit.author.name), date: .commit.author.date}' \
      >> "$OUT/commits.jsonl"
    commit_count=$((commit_count + n))

    [ "$n" -lt 100 ] && break
    page=$((page+1))
    [ "$page" -gt 100 ] && break
  done

  echo -e "$repo\t$pr_count\t$commit_count" >> "$OUT/per_repo.tsv"
done < "$OUT/repos.txt"

echo "DONE" >&2
