---
name: review-pr
user-invocable: true
description: "Use when you need to review a pull request -- yours or someone else's -- before merging."
argument-hint: "[PR number or URL]"
---

# Review PR

Structured code review on a pull request. Produce clear, actionable comments -- then post them with user approval.

## Engineering Lens

> **Violating the letter of verification is violating the spirit. If every checklist item isn't explicitly verified with evidence, the review is incomplete.**

Ground every comment in first principles, simplicity, modularity, separation of concerns, and clean implementation. Be **helpful, not pedantic** -- flag what matters, skip linter-level style nitpicks.

## Procedure

Follow these steps exactly in order.

### Step 1: Identify the PR

Accept PR number, URL, or no argument (run `gh pr list` and ask user to pick). Fetch with `gh pr view <number> --json title,body,author,baseRefName,headRefName,files,additions,deletions,reviews,comments`. Present overview (author, branch, files, status, existing reviews).

### Step 2: Read the Diff

Fetch with `gh pr diff <number>`. Read thoroughly -- for each changed file, read enough surrounding context to understand the change in situ. For large PRs (>500 lines), organize by file or logical concern and use **Explore subagents** to parallelize.

### Step 3: Understand Intent

Before critiquing, understand what the PR is trying to do. Read the PR body, referenced plan docs, linked issues, and commit messages. Summarize: **"This PR does X because Y."** Ask user to confirm if unsure.

### Step 4: Review

Evaluate the PR across the dimensions defined in `review-dimensions.md`. Categorize each finding by severity using the system in `severity-categories.md`.

<HARD-GATE>
Do NOT post approval or positive comments until every checklist item in Step 4 has been explicitly verified with evidence. Reading code is not verification -- check CI status, confirm test coverage, trace logic through the actual codebase, and run local verification commands when the branch is available.
</HARD-GATE>

### Step 5: Present Review

Present findings organized by severity (Blockers, Suggestions, Nits, Questions) with file:line references and concrete fixes. Include a one-sentence assessment and verdict (Approve / Request Changes / Comment Only). Follow the rules in `severity-categories.md`.

### Step 6: Post Review

Ask user: **"Want me to post this review to the PR?"** Options: post as-is, edit first, or keep local. Use `gh pr review <number>` with `--approve`, `--request-changes`, or `--comment`. Post file-level comments via `gh api`. Confirm when posted.

## Notes

- **Helpful, not hostile.** Phrase feedback constructively.
- **Proportional depth.** Scale review to the PR's scope.
- **Understand before criticizing.** Step 3 exists for a reason.
- **Concrete suggestions always.** "Replace X with Y because Z" -- not "this could be better."
- **Respect the plan.** If the PR follows a plan doc, review against it. Don't re-litigate approved decisions unless new evidence appears.
- **Security findings are always blockers.** No exceptions.
- **Don't rubber-stamp.** Actually check -- even good engineers miss things.

Before finalizing any review, consult `red-flags-and-rationalizations.md` and verify you haven't fallen into any of those traps.
