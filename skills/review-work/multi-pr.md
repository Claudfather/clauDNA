Invoked by /claudna:review-work in multi-pr mode — review two or more pull requests in parallel, one subagent per PR, then aggregate per-PR verdicts and cross-PR findings.

Each PR receives the full pr-mode discipline inside its own subagent. The orchestrator verifies the PR set, dispatches, aggregates, and gates posting — it never reviews code itself and never pulls full findings into its context.

## Step 1: Collect and Verify the PR Set

Accept two or more PR references (numbers or URLs) from the arguments. A single reference is `pr` mode's job — re-route there instead of degrading.

Verify each ref with `gh pr view <number> --json number,title,author,state,baseRefName,headRefName,additions,deletions` (separate Bash calls, never chained). Report refs that fail to resolve or are already merged/closed, then confirm the final set with the user. If fewer than two remain, stop.

All PRs must belong to the current repository — cross-repo sets are out of scope (see Non-Goals).

## Step 2: Scratch Directory

Define the session scratch directory per the research-agent pattern in `skills/_shared/orchestration-guide.md` (§1–§2):

```
/tmp/review-work-<YYYY-MM-DD_HHMMSS>/research/
```

Do not `mkdir` — the first subagent Write call creates it.

## Step 3: Dispatch One Review Subagent per PR (Parallel)

Soft cap: more than 5 PRs → confirm with the user or batch into waves of 5 — an unbounded fan-out multiplies review cost and scratch-dir churn without improving synthesis.

Launch one `general-purpose` subagent per PR, all in parallel in a single message (Explore agents lack the Write tool — guide §1). Each subagent's prompt must tell it to:

1. Read `pr.md` in this skill directory (give the absolute path) and apply its discipline to its assigned PR — Steps 1–5 in full: fetch the PR, read the diff with surrounding context, understand intent, review across `review-dimensions.md`, categorize per `severity-categories.md`, and self-check against `red-flags-and-rationalizations.md` before finalizing. The pr-mode HARD-GATE binds inside the subagent: no positive verdict without verified evidence.
2. Skip pr.md Step 6 — posting belongs to the orchestrator (Step 5 below).
3. Write the full review as a post-ready body to `/tmp/review-work-<ts>/research/pr-<number>.md`: one-sentence assessment, verdict (Approve / Request Changes / Comment Only), findings by severity with `file:line` references and concrete fixes.
4. Return ONLY a 3–5 line summary: verdict, finding counts per severity, the single worst finding, files or areas touched, and the findings-file path. Subagents never return full findings through the orchestrator (guide §2).

## Step 4: Aggregate

Work from the returned summaries only — do NOT read the findings files into orchestrator context. Present:

1. **Per-PR verdict table** — PR, title, verdict, Blocker/Suggestion/Nit/Question counts, worst finding, findings-file path.
2. **Cross-PR findings** — the patterns single-PR reviews cannot see:
   - **Shared root causes** — the same underlying bug or gap surfacing in more than one PR (one fix, not N).
   - **Conflicting changes** — PRs touching the same files or behavior in incompatible ways; name the collision.
   - **Merge-order recommendation** — which PR lands first and why (dependencies between PRs, conflict minimization, blocker status). Ordering advice only — merging is out of scope.
3. Order all findings by severity per `severity-categories.md` — Blockers first across the whole set, every Blocker and Suggestion with a concrete fix.

If confirming a suspected conflict or shared root cause needs more than the summaries provide, dispatch one focused follow-up subagent — never read the research files yourself.

## Step 5: Post Reviews (Per-PR, Gated)

Posting is per-PR and gated on explicit user approval, exactly like pr.md Step 6:

- Ask for each PR: **"Want me to post this review to PR #<n>?"** Options: post as-is, edit first (the *user* edits the findings file at its reported path — the orchestrator never reads it), or keep local.
- On approval: `gh pr review <number>` with `--approve`, `--request-changes`, or `--comment`, passing `--body-file /tmp/review-work-<ts>/research/pr-<number>.md` — the findings file posts directly and never enters orchestrator context. Post file-level comments via `gh api` where warranted.
- Confirm each post. For skipped PRs, report the findings-file paths so nothing is lost.
- Headless / non-interactive contexts cannot clear this gate — keep all reviews local and report the paths.

## Non-Goals

- **No auto-merge.** This mode recommends a merge order; it never merges. Merging stays with the user.
- **No cross-repo.** Every PR in the set must live in the current repository; drop foreign refs and say so.
