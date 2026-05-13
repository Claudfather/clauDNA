---
name: quick-commit
user-invocable: true
description: "Use when you want to quickly stage and commit all current changes with a conventional commit message."
---

1. Run `git status` to see the current state
2. Run `git diff` to understand the changes
3. Stage all changes with `git add -A`
4. Create a commit with a clear message that:
   - Starts with a type prefix (feat:, fix:, refactor:, docs:, test:, chore:)
   - Briefly describes what changed
   - Uses imperative mood ("Add feature" not "Added feature")

Example: `feat: add product search functionality`

---

## Red Flags — STOP

If you catch yourself thinking any of these, STOP — you are about to commit without adequate diligence:

- "Just a quick fix" — Quick fixes need review too. Run `git diff` and actually read what you're committing. A "quick fix" that introduces a regression is not quick.
- "I'll clean this up in the next commit" — No you won't. The next commit will have its own scope. If the code needs cleanup, clean it up NOW before committing.
- "The tests aren't related" — Run them anyway. Changes have unintended side effects. If the tests pass, you've confirmed no regression in 30 seconds. If they fail, you just prevented a broken commit.
- "It's just a docs change" — Documentation changes can contain incorrect information, broken links, and outdated examples. Read the diff.
- "I know what I changed" — Read the diff anyway. `git add -A` stages everything, including files you forgot you modified, files your editor auto-saved, and temporary debugging code you meant to remove.
- Staging with `git add -A` without first running `git status` — Step 1 exists for a reason. You need to know what's about to be committed. Untracked files, modified configs, and accidental changes all get swept in by `-A`.
- Writing a commit message before reading the diff — The message describes the change. You can't describe what you haven't read.
- Using "misc" or "various" in the commit message — These words mean you're committing unrelated changes together. Split them into separate commits.

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
| "I'll run tests after pushing" | Post-push failures cost everyone time. Run tests pre-commit. |
