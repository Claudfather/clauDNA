# /simplify Chain — Subagent Dispatch Prompt

Used by `/claudna:build` (Step 6.5) to run `/simplify` against changed files after verification passes. /simplify operates non-interactively on the working tree by design — this file documents the chain pattern so other skills can adopt it later if needed.

## When this chain runs

In `/claudna:build` Step 6.5, AFTER Step 6 verification passes. Triggered when the diff exceeds a size threshold (>50 LOC OR >2 files changed).

## Procedure

1. Compute the diff size:

```bash
git diff --stat <base-branch>...HEAD
```

Parse the output for total lines changed and file count.

2. If diff size is below the trigger threshold, skip /simplify entirely. Proceed to Step 7.

3. Run /simplify. The skill operates against the current working tree non-interactively:

```
Invoke: /simplify
```

(/simplify does not require arguments. It reviews recently changed files and reshapes them in place.)

4. Stage and commit /simplify's edits if any were made:

```bash
git status --short
git add -u  # or specific files /simplify edited
git commit -m "refactor: simplify pass (post-verify)"
```

5. Re-run the Step 6 verification checklist (tests, lint, types). If verification passes, proceed to Step 7.

6. **If verification fails after /simplify:**
   - **Interactive mode:** Present the regression to the user via AskUserQuestion. Options: "Fix forward (debug the regression)", "Revert /simplify's commit", "Abort". Process the user's choice.
   - **`--auto` mode:** Revert /simplify's commit unconditionally:

```bash
git reset --hard HEAD~1
```

  Add a note to the eventual PR body (Step 7): "Simplification pass attempted; reverted due to verification regression: <error summary>". Proceed to Step 7 with the pre-simplify diff.

## Why a separate commit for /simplify

Having /simplify's edits in their own commit makes revert trivial (`git reset --hard HEAD~1`) and makes the PR's history clear: implementation commits, then simplification commit. Reviewers can quickly see what /simplify changed.

## What /simplify does NOT do

- It does not change test code (unless tests themselves are simplifiable — uncommon).
- It does not introduce new abstractions; it removes incidental complexity.
- It does not change observable behavior. If verification regresses, that's the trigger to revert.
