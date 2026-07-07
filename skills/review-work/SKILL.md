---
name: review-work
user-invocable: true
description: "Use when work needs review before it lands — uncommitted changes before committing, a pull request before merging, or several PRs reviewed in parallel. For hardening a plan Issue with the lens panel, use /claudna:ironclad. Replaces /review-changes, /review-pr."
argument-hint: "[changes|pr|multi-pr] [PR-numbers-or-args]"
requires:
  - cli: gh
    reason: "PR diff/metadata reads and review submission for the pr and multi-pr modes"
---

# Review Work

One engine for code review — `changes`, `pr`, and `multi-pr` as modes over the same verification discipline: evidence before approval, findings ranked by severity, never a rubber stamp.

## Mode dispatch

Arguments to dispatch (first token = mode, the rest belong to the mode): $ARGUMENTS

| Mode | When | Depth |
|------|------|-------|
| `changes` | Uncommitted local changes, reviewed before committing | `changes.md` |
| `pr` | One open pull request, reviewed before merging | `pr.md` |
| `multi-pr` | Two or more PRs reviewed in parallel — per-PR verdicts plus cross-PR findings and merge order | `multi-pr.md` |

For the selected mode, read ONLY its depth file in this skill directory and follow it exactly — never load another mode's depth.

**No mode token → infer only when the signal is unambiguous, rules checked in order — first match wins:**

- Dirty working tree and no PR reference in the request → `changes`.
- Exactly one PR number or URL → `pr`.
- Two or more PR references → `multi-pr`.
- Anything else → print the table above and stop — never ask a blocking question when the table answers it.
- **Headless / non-interactive contexts: the mode token is required** — never inferred.

## Shared support files

The three support files in this skill directory — `review-dimensions.md`, `severity-categories.md`, `red-flags-and-rationalizations.md` — are `pr.md`'s references and are shared by all modes: depth files and their subagents cite them by bare filename (same directory). Only the `pr` and `multi-pr` modes need `gh`; `changes` runs on git alone.
