---
name: review-changes
user-invocable: true
description: "Use when you have uncommitted changes and want them reviewed before committing. For a pull request that is already open, use /claudna:review-pr."
---

# Review Changes

> **Violating the letter of verification is violating the spirit. Partial checks prove nothing.**

<HARD-GATE>
Do NOT approve or express satisfaction with changes until verification commands have been run and output confirms the claim.
</HARD-GATE>

## Procedure

1. Run `git status` to see what's changed
2. Run `git diff` to see the actual changes
3. For each modified file, analyze:
   - Is the change correct and complete?
   - Are there any potential bugs?
   - Does it follow project conventions?
   - Are there any security concerns?
   - Is error handling adequate?
4. **Verify claims with evidence** — before expressing any positive assessment:
   - If tests exist: run them and confirm output
   - If linting is configured: run the linter and confirm clean
   - If the change fixes a bug: reproduce the original symptom and confirm it's resolved
   - Do NOT say "looks good" based on reading code alone when verification commands are available
5. Provide a summary with:
   - What looks good (with evidence from Step 4)
   - Any concerns or suggestions
   - Recommended next steps (test, commit, or make changes)

---

## Red Flags — STOP

If you catch yourself thinking any of these during review, STOP — you are about to skip verification:

- "The code looks correct" — based on what? Visual inspection is not verification. Did you trace the logic path? Did you check edge cases? "Looks correct" is an opinion, not evidence.
- "Tests are probably passing" — "Probably" is not evidence. Run `git diff` to identify what changed, then verify that relevant tests exist and were actually executed. If you haven't seen test output, you don't know.
- "It's a small change, no need for full review" — Small changes cause production outages. A one-line typo in a config file can take down a service. Review depth scales with risk, not line count.
- "I already reviewed this mentally" — Mental review is not review. Show your work — the summary in Step 4 proves you actually analyzed each file.
- "The diff is clean" — Clean diffs can contain logic errors, missing error handling, security vulnerabilities, and broken edge cases. "Clean" means well-formatted, not correct.
- Providing a summary without mentioning a single specific file or line — Generic feedback ("looks good overall") means you didn't actually review the changes. Name files. Cite lines.
- Recommending "commit" without checking for test coverage — Untested changes are incomplete changes. If there are no tests, that IS a concern to flag.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "The code looks correct" | Visual inspection catches formatting, not logic. Trace the actual execution path. |
| "Tests are probably passing" | "Probably" = "I didn't check." Run them or confirm they were run. |
| "Small change, quick review" | Small change, full review — just faster. Not no review. |
| "I already reviewed this mentally" | Mental review has no evidence trail. Write down what you found. |
| "The diff is clean" | Clean != correct. Clean diffs hide logic bugs. |
| "It's just a refactor" | Refactors break behavior. Verify the old tests still pass. |
| "No security concerns here" | Did you actually check for injection, auth, and data exposure? Saying "no concerns" requires evidence. |
| "Error handling is adequate" | Adequate by what standard? Check every error path. What happens on null? On timeout? On malformed input? |
