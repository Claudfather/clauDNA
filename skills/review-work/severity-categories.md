# Severity Categories

For each finding, categorize it:

| Severity | Meaning |
|----------|---------|
| **Blocker** | Must fix before merge. Bugs, security issues, data loss risks. |
| **Suggestion** | Should fix. Design concerns, missing tests, unclear code. |
| **Nit** | Take it or leave it. Minor improvements, style preferences. |
| **Question** | Asking for clarification, not asserting a problem. |

## Rules

- Every blocker and suggestion must include a **concrete fix** -- not just "this is wrong" but "here's what it should be."
- Nits are optional -- skip them if the PR is otherwise solid and you don't want to create noise.
- Questions are genuine -- ask when you don't understand a decision, not as passive-aggressive criticism.
