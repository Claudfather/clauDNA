---
name: worktree
description: "Use when you want to run multiple Claude sessions in parallel on different branches using git worktrees."
---

# Git Worktree Manager

Create worktrees and orchestrate parallel subagents for concurrent feature work.

## Instructions

### Step 1: Determine repo layout

Run `git rev-parse --show-toplevel` to get the repo root. Shell variables do NOT persist between Bash calls — hardcode absolute paths everywhere.

Convention: worktrees live at `<repo-root>-worktrees/<branch>/` (sibling to repo, never inside it).

**Note:** Inside a worktree, `--show-toplevel` returns the worktree root. Use `git worktree list` for the main repo path.

### Step 2: Show current state

Always run `git worktree list` first.

### Step 3: Create worktrees

Use `git worktree add` with **absolute paths**. `mkdir -p` the parent first. Use `-b <branch>` for new branches; omit `-b` for existing ones.

**Critical**: `cd` does not persist between Bash calls from the orchestrator. Always use absolute paths.

### Step 3b: Permission boundaries

Worktrees are sibling directories — **outside the orchestrating session's project scope**. Every Bash/Read/Edit command targeting a worktree triggers a permission prompt.

To minimize friction:
- **Delegate all work to subagents** — they operate in their own permission scope and handle testing, committing, pushing, and PR creation.
- **Orchestrator should only:** create worktrees, launch subagents, monitor via TaskOutput, and merge/cleanup.
- **Never run tests, edit files, or commit from the orchestrator in a worktree.**
- **Tell the user upfront** how many worktrees and subagents you'll create.

### Step 4: Orchestrate parallel subagents

1. **Read plan/task documents first** — include complete content in each subagent prompt (subagents have no conversation history).
2. **Create one worktree per task** (Step 3).
3. **Launch Task agents in parallel** — one Task tool call per agent, all in a single message.

**CRITICAL — `subagent_type` MUST be `"general-purpose"`**. This gives all tools (Bash, Read, Edit, Write, Grep, Glob). Any other type fails silently.

Set `run_in_background: true` for concurrency. Build each prompt from `subagent-prompt-template.md`, substituting absolute paths and full task description.

### Step 5: Monitor and handle failures

Use TaskOutput with `block=false` for non-blocking checks. Wait for all agents to complete.

**If a subagent fails:** read its output, report to the user, ask whether to relaunch, fix manually, or skip. Do NOT silently retry.

### Step 6: Merge and cleanup

**CRITICAL — remove worktrees BEFORE merging.** `gh pr merge --delete-branch` fails on branches still checked out in a worktree.

Required order (each as a separate Bash call):
1. `git worktree remove <path>` for every worktree, then `git worktree prune`
2. Confirm with user, then `gh pr merge <pr> --merge --delete-branch` sequentially
3. If remaining PRs conflict, rebase on updated main: `git fetch origin`, `git checkout <branch>`, `git rebase origin/main`, `git push --force-with-lease`, then merge
4. Return to main: `git checkout main`, `git pull`

## Reference files

- **`bootstrap-commands.md`** — Venv setup, npm install, .env copy (included in subagent prompts)
- **`subagent-prompt-template.md`** — Full prompt template for Task tool calls
- **`common-pitfalls.md`** — Pitfall/fix table for worktree operations

## Shell aliases (user reference)

`wt-new <branch>`, `wt-list`, `wt-rm <path>`, `wt-set a <path>` — available in user's terminal (from `~/.zshrc`), but may not work inside the Bash tool. Prefer explicit `git worktree` commands.
