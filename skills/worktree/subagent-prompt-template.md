# Subagent Prompt Template

Use this template for each Task tool call when launching subagents into worktrees.

```
WORKTREE: /absolute/path/to/repo-worktrees/<branch>
MAIN REPO: /absolute/path/to/repo

## CRITICAL — READ THIS FIRST

Your working directory is NOT the worktree. It is the main repo. If you forget this, every command will silently operate on the wrong codebase.

**First Bash call:** `cd /absolute/path/to/repo-worktrees/<branch>` — this persists for all subsequent Bash calls in your session.
**All Read/Edit/Write/Glob/Grep:** use `/absolute/path/to/repo-worktrees/<branch>/path/to/file` (absolute paths always).

## Bootstrap (run before ANY other work)

Follow the bootstrap steps in bootstrap-commands.md:
1. cd into worktree (persists for session)
2. Copy .env from main repo
3. Install dependencies (Python venv or Node npm)
4. Run commands normally after setup

For Python: use `./venv/bin/python` and `./venv/bin/pytest` directly — never `source venv/bin/activate`.

## Task

<full task description — include the COMPLETE content of the plan/spec doc, not a reference to it>

## When done

1. Run tests to verify your changes work
2. Commit your changes with a descriptive message
3. Push the branch: git push -u origin <branch-name>
4. Create a PR: gh pr create --base main --title "<title>" --body "<body>"
5. Report back: the PR URL and a summary of what was done
```
