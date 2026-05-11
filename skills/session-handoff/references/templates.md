# Handoff File Template

Write the handoff file using this structured format. Optimized for agent consumption by `/claudna:context-resume`.

```markdown
# Context Resume: <project-name>

session_date: YYYY-MM-DD
branch: <current-branch>
working_tree: <clean | dirty — list modified files if dirty>
stashes: <count or 0>

## Activity

- <one-line commit summaries, prefixed with short hash>
- PR #N: <title> (<state>)
- Plan: <doc-path> <status-change>

## Decisions

- <decision made and rationale, one per line>

## Open Questions

- <blockers, unknowns, pending inputs>

## Next Steps

- <what the next session should start with>
- <pending plan phases if applicable>
- <uncommitted work note if applicable>

## State

open_prs:
  - "#N <title> (<state>)"
branches: <list of active feature branches>
```

## Format Notes

- Use flat key-value pairs where possible — easier for the resuming agent to parse.
- Keep each section to 3-7 bullet points max. If a section has nothing, omit it entirely.
- The Decisions and Open Questions sections come from session observation. If the user provided explicit input, include it. If not, infer from the git history and PR activity.
- Never pad with filler content. Empty sections are better than vague ones.
