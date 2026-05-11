# Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| Creating worktree inside the repo | Use `<repo>-worktrees/` (sibling dir) |
| `cd` into worktree then losing it | `cd` persists within a session — run it once, then use relative paths for Bash. Always use absolute paths for Read/Edit/Write/Glob/Grep |
| Subagent commands run in wrong directory | Subagent's first Bash call should be `cd <WORKTREE>` — this persists for all subsequent calls |
| Subagent Read/Edit uses relative paths | Always use absolute paths under the worktree |
| Subagent can't run Bash/Edit | Use `subagent_type: "general-purpose"` |
| Subagent has no context | Include ALL needed info in the prompt — inline plan docs fully |
| Fire-and-forget agents | Use `run_in_background: true` and monitor via output files |
| Branch already exists | Use `git worktree add <path> <existing-branch>` (no `-b`) |
| Import/runtime errors in worktree | Worktrees lack venvs, node_modules, .env — bootstrap first |
| Main repo venv but imports fail | Package isn't installed in that venv — run `./venv/bin/pip install -e .` from worktree |
| Orchestrator running commands in worktree dirs | Triggers permission prompts — delegate to subagents |
| `gh pr merge --delete-branch` fails | Remove worktrees BEFORE merging — can't delete checked-out branches |
| Second/third PR has merge conflicts | Rebase on updated main after each prior merge |
| Running `/claudna:worktree` from inside a worktree | `--show-toplevel` returns worktree root — use `git worktree list` to find main repo |
