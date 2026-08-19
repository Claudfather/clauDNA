---
name: sync-branches
user-invocable: true
description: "Use to bring every local branch and worktree across your sibling git repos up to date with origin/main in one pass — fetches, fast-forwards where safe, and reports conflicts without forcing anything. For creating a NEW worktree to isolate feature work, use /claudna:worktree instead."
argument-hint: "[workspace-root]"
---

# Sync Branches

Fetch latest origin/main and merge into all active local branches and worktrees, across every sibling repo in the workspace. Designed to run manually or on a recurring interval via `/loop 2h /claudna:sync-branches`.

**Important**: This assumes a multi-repo workspace — each sibling directory under the workspace root has its own `.git`. Iterate over all of them, not just the current repo.

## Instructions

### Step 1: Determine the workspace root

If the user names a workspace root (the `[workspace-root]` argument), use it. Otherwise default to the parent directory of the current repo's root:

```bash
dirname $(git rev-parse --show-toplevel)
```

### Step 2: Discover repos

```bash
for dir in <workspace-root>/*/; do if [ -d "$dir/.git" ]; then echo "$dir"; fi; done
```

### Step 3: For each repo — fetch, list branches, sync

```bash
git -C <repo-path> fetch origin main
git -C <repo-path> worktree list
git -C <repo-path> branch --format='%(refname:short) %(upstream:track)' | grep -v HEAD
```

Identify:
- The current branch in the main working tree
- All worktree branches
- Any other local branches with a remote

### Step 4: Sync the main working tree

If on main:
```bash
git -C <repo-path> pull origin main
```

If on a feature branch, check for uncommitted changes first — never stash (a pre-existing unrelated stash entry on the stack would get silently popped into this branch):
```bash
git -C <repo-path> status --porcelain
```

If clean, merge:
```bash
git -C <repo-path> merge origin/main
```

If dirty, skip and report — same as Step 5 does for worktrees:
```
Skipped (uncommitted changes)
```

If merge fails, abort and report — do NOT force anything:
```bash
git -C <repo-path> merge --abort
```

### Step 5: Sync each worktree

For each worktree (skip if it has uncommitted changes — just report it):

```bash
git -C <worktree-path> status --porcelain
```

If clean, merge:
```bash
git -C <worktree-path> merge origin/main
```

If merge conflicts, abort and report — do NOT force anything:
```bash
git -C <worktree-path> merge --abort
```

### Step 6: Report

Show a summary:

| Repo | Branch | Worktree? | Status |
|------|--------|-----------|--------|
| repo-a | main | - | Up to date |
| repo-a | feature/x | /path/to/wt | Merged (3 new commits) |
| repo-b | feature/y | /path/to/wt | Skipped (uncommitted changes) |
| repo-c | feature/z | - | Conflict — needs manual merge |

If running via `/loop`, keep the output concise — just the table unless there are conflicts.
