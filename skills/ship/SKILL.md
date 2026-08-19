---
name: ship
user-invocable: true
description: "Use when changes are ready to land — a fast local checkpoint, or the full flow through push and an open pull request. Defaults to the PR flow; say 'commit' or 'quick commit' for a checkpoint-only. Replaces /commit-push-pr, /quick-commit."
argument-hint: "[commit|pr]"
requires:
  - cli: gh
    reason: "GitHub CLI for PR creation (pr mode)"
---

# Ship

Two-mode pipeline for landing work. Use whichever scope you want.

- **Commit mode** — stage and commit locally, push if tracked. No PR. (`/claudna:ship commit`, or say "commit"/"quick commit")
- **PR mode** (default) — rebase onto the base branch, verify, review the diff, commit, push, open a PR. (`/claudna:ship`, `/claudna:ship pr`, or say "ship")

---

## Commit mode

**When:** user says "commit", "quick commit", "stage and commit," or invokes `/claudna:ship commit`.

1. Run `/claudna:verify-completion`'s discipline — tests pass, lint clean, type-check clean — before staging.
2. Run `git status` to see the current state.
3. Run `git diff` to understand the changes.
4. Stage the appropriate files with `git add`, named explicitly (never `git add -A` — it sweeps in `.env`, editor auto-saves, and debug code left in unrelated files).
5. Create a commit with a clear message:
   - Starts with a type prefix (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
   - Briefly describes what changed, imperative mood ("Add feature" not "Added feature")
6. Push to the current branch if tracked.

No PR. Just a checkpoint commit.

Example: `feat: add product search functionality`

---

## PR mode (default)

**When:** user says "ship", "push to main", "create a PR," "open a PR," or invokes `/claudna:ship` / `/claudna:ship pr`.

1. Run `git status` to see what files have changed.
2. Run `git diff` to review the changes.
3. **Detect the base branch** (usually `main`, fall back to `master`). Fetch and merge/rebase `origin/<base>` into the current branch. Resolve conflicts — never discard work.
4. Run `/claudna:verify-completion`'s discipline against the full test suite, lint, and types. Must pass fully — no "most tests pass" rationalizations.
5. Review the diff via `/claudna:review-work changes` — catches structural issues, unintended side effects, and safety problems before a human reviewer sees them.
6. Bump version and update CHANGELOG, if the project uses them — check the project's own CLAUDE.md for its convention. Skip silently if the project doesn't version this way.
7. Stage the appropriate files with `git add`, named explicitly.
8. Create a commit with a clear, descriptive message following conventional commits format.
9. Push to the remote branch (create the remote branch if needed with `-u origin <branch>`).
10. Create a Pull Request using `gh pr create` with:
    - A clear title summarizing the changes, under 70 characters
    - A description with:
      - `## Summary` — what changed and why
      - `## Test plan` — testing done
      - `## Notes for reviewers` — anything reviewers should look at closely (risky areas, deliberate omissions, follow-ups); omit only when there's genuinely nothing to call out
11. Return the PR URL to the user.

Does NOT merge — that's the user's call. If there are any issues at any step, stop and report them.

---

## Red Flags — STOP

If you catch yourself thinking any of these, STOP — you are about to commit or ship without adequate diligence:

- "Just a quick fix" — Quick fixes need review too. Run `git diff` and actually read what you're committing. A "quick fix" that introduces a regression is not quick.
- "I'll clean this up in the next commit" — No you won't. The next commit will have its own scope. If the code needs cleanup, clean it up NOW before committing.
- "The tests aren't related" — Run them anyway. Changes have unintended side effects. If the tests pass, you've confirmed no regression in 30 seconds. If they fail, you just prevented a broken commit or PR.
- "It's just a docs change" — Documentation changes can contain incorrect information, broken links, and outdated examples. Read the diff.
- "I know what I changed" — Read the diff anyway. `git add -A` stages everything, including files you forgot you modified, files your editor auto-saved, and temporary debugging code you meant to remove.
- Staging with `git add -A` without first running `git status` — Step 1/2 exist for a reason. You need to know what's about to be committed. Untracked files, modified configs, and accidental changes all get swept in by `-A`.
- Writing a commit message before reading the diff — The message describes the change. You can't describe what you haven't read.
- Using "misc" or "various" in the commit message — These words mean you're committing unrelated changes together. Split them into separate commits.
- "The parent branch will still be current" — always fetch fresh state before rebasing in PR mode; don't trust a base branch you checked earlier in the session.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Just a quick fix" | Quick fixes need review too. Read the diff. |
| "I'll clean this up next commit" | No you won't. Clean it up now. |
| "The tests aren't related" | Run them anyway. 30 seconds to confirm no regression. |
| "It's just a docs change" | Docs can be wrong too. Read the diff. |
| "I know what I changed" | `git add -A` stages everything. Read `git status` first. |
| "One commit is fine for all of this" | Unrelated changes belong in separate commits. Split them. |
| "The message is good enough" | Vague messages make `git log` useless. Be specific. |
| "I'll run tests after pushing" | Post-push failures cost everyone time. Run tests pre-commit or pre-PR. |
