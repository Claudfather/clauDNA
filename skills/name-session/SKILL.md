---
name: name-session
user-invocable: true
description: "Use when ending a session and you want to label it for easy identification in /resume. Also useful mid-session when work scope becomes clear."
allowed-tools: Bash(git *), Bash(gh *)
---

# Name Session

Generate a descriptive session name in the format: `DESCRIPTION - REPO#PR - BRANCH` (all caps).

**The session name must reflect what this session actually did — not just whatever branch is currently checked out.** Sessions often switch branches, run in worktrees, or do investigative work unrelated to the current HEAD. Ground the name in the conversation, then use git state to confirm (or flag divergence).

## Step 1 — Synthesize the session's actual work (from conversation, not git)

Before running any commands, write down in your head:

- **What did we do this session?** (e.g., "investigated stale-cache bug in api-server", "shipped webhook retry logic", "reviewed PR #123")
- **Did we ship code, investigate, review, or mix?** Investigative sessions may not map to any branch/PR.
- **Did the session reference a specific PR number or branch by name?** That explicit reference beats whatever is checked out now.
- **Did we switch branches or worktrees during the session?** If so, which branch holds the session's work?

This synthesis is the primary input. Steps 2–4 gather evidence to reconcile it with git state.

## Step 2 — Gather git signals (all of them, not just current branch)

Run these in parallel:

```
git branch --show-current
git worktree list
git log --walk-reflogs --oneline -20 HEAD          # branches visited recently
git log --oneline -10 --all --source               # commits across all branches
git status --short                                 # uncommitted work on current branch
basename $(git remote get-url origin) .git
```

If the session mentioned a specific PR/branch not on this checkout, also check it directly:

```
gh pr view <number> --json number,title,headRefName
gh pr list --head <branch> --json number,title --limit 1
```

## Step 3 — Reconcile: does the current branch match the session's work?

Compare the Step 1 synthesis against the Step 2 signals. One of these is true:

**A. Match** — current branch and its PR (if any) reflect the session's work.
→ Use `DESCRIPTION - REPO#PR - BRANCH`.

**B. Mismatch (the common failure mode)** — current branch is unrelated; real work was elsewhere.
Signs of mismatch:
- No commits on current branch during this session, but the conversation shipped/investigated something specific.
- Session explicitly referenced a different PR/branch by name or number.
- `reflog` shows we switched away from the work branch recently.
- Files discussed in the session don't match recent diffs on current branch.

When mismatched, do **not** silently take the current branch. Choose one:
- If the session's real work branch is identifiable (from conversation or reflog), name with *that* branch and its PR.
- If the session was investigative (no branch is a natural home), drop the branch/PR entirely and use `DESCRIPTION` alone.
- If uncertain, output the name you believe is correct *and* a one-line note explaining the mismatch so the user can override.

**C. No git context** — not in a repo, or session spanned unrelated repos.
→ Use `DESCRIPTION` alone.

## Step 4 — Generate a 3–4 word description

- Primary source: your Step 1 synthesis of what the session actually did.
- Secondary: PR title and commit messages *of the branch you selected in Step 3*, not necessarily the current one.
- Capture the essence, not the mechanics. Prefer outcome/topic over action verbs when investigative.
- Examples: `AUTH FLOW REFACTOR`, `FIX STALE CACHE BUG`, `WEBHOOK RETRY DIAGNOSIS`

## Step 5 — Assemble and output

- **Matched branch/PR:** `DESCRIPTION - REPO#NUMBER - BRANCH`
- **Matched branch, no PR:** `DESCRIPTION - BRANCH`
- **Investigative / mismatch with no natural branch:** `DESCRIPTION`

All caps. Output as:

```
/rename DESCRIPTION - REPO#NUMBER - BRANCH
```

If you detected a mismatch in Step 3, append one short note after the command explaining what you chose and why — so the user can correct you in one turn instead of getting a wrong name silently.

## Examples

Matched:
```
/rename AUTH FLOW REFACTOR - MYAPP#53 - FEAT/AUTH-REDESIGN
```

Investigative, current branch unrelated:
```
/rename WEBHOOK RETRY DIAGNOSIS
Note: current branch FEAT/EXAMPLE-FEATURE (PR #N) is unrelated to this session's work — dropped branch/PR from the name.
```

Session ended on wrong branch after context switch:
```
/rename FIX STALE CACHE BUG - MYREPO#42 - FIX/CACHE-INVALIDATION
Note: HEAD is on main, but this session's work landed on fix/cache-invalidation (PR #42) per reflog — named by the work branch, not HEAD.
```
