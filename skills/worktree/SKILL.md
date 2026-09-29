---
name: worktree
user-invocable: true
description: "Use when starting feature work that needs isolation from the current workspace, or when running multiple Claude sessions in parallel on different branches — creates and manages git worktrees. For fetching latest main into every existing worktree and branch across your sibling repos, use /claudna:sync-branches instead."
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

**CRITICAL — `subagent_type` MUST be `"general-purpose"`** (that is Claude Code's name for it; a host that calls the general-purpose type something else is still the dispatch path — use its name). This gives all tools (Bash, Read, Edit, Write, Grep, Glob). Any other type fails silently.

Set `run_in_background: true` for concurrency. Build each prompt from `subagent-prompt-template.md`, substituting absolute paths and full task description.

**No dispatch primitive at all** (`skills/_shared/orchestration-guide.md` §14.1) → the parallelism this skill exists for is unavailable, so say so and change shape rather than faking it. Per §14.2 and §14.5: announce the inline path, then work **one worktree at a time** from the main session, following `subagent-prompt-template.md` yourself as the task description. Two consequences to state to the user up front, not discover later: the orchestrator is now doing exactly the work Step 3b reserves for subagents, so **every** Bash/Read/Edit against the sibling directory raises a permission prompt; and there is no concurrency, so the cost is the sum of the tasks. If the prompt volume is unacceptable, the honest answer is to skip worktrees and work serially on branches in place — not to keep the worktree ceremony without the isolation it was buying.

### Step 5: Monitor and handle failures

Use TaskOutput with `block=false` for non-blocking checks. Wait for all agents to complete. (On the inline path there is nothing to monitor — each task is finished before the next starts.)

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
