---
name: example-review
description: "Use when you want to review pull requests with detailed, actionable feedback on code quality, correctness, and maintainability."
allowed-tools: Bash(git *), Bash(gh *), Read, Grep, Glob
---

# Example Review

A skill for reviewing pull requests with detailed, actionable feedback.

## Procedure

1. Read the PR diff using gh pr diff
2. Analyze each changed file for correctness, style, and potential issues
3. Post a structured review with specific line references
4. Provide an overall verdict (approve, request changes, comment)

## Review Criteria

- **Correctness:** Does the code do what it claims?
- **Style:** Does it follow the project conventions?
- **Tests:** Are changes adequately tested?
- **Security:** Any obvious vulnerabilities?
