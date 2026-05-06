# Briefing Output Template

Use this format for the context resume briefing:

```
Context Resume: <project-name>
═══════════════════════════════════════════════════════════════════════════

  Last session:  <date from handoff file, or "no handoff file found">

  Working tree:
    <clean / N modified, N untracked, N staged>
    <active branch: branch-name>

  Recent commits (last 3):
    abc1234  <message>
    def5678  <message>
    ghi9012  <message>

  Open PRs:
    #47  Add search filtering   (waiting on review)
    #45  Fix rate limiter        (changes requested)

  PRs to review:
    #48  Update auth middleware  (from @teammate)

  In-progress plans:
    documentation/planning/phases/search_2026-02-10/02_filtering.md  🔧

  Next up:
    documentation/planning/phases/search_2026-02-10/03_pagination.md  📋

  Stashes:  <N stashes, or "none">
  Branches: <N local branches>

═══════════════════════════════════════════════════════════════════════════
```

If a handoff file exists, append:

```
  Session notes (from last handoff):
    - <key points from the handoff file>
    - <open questions>
    - <suggested next steps>
```

## Rules for the template

- Omit sections with no data (e.g., no open PRs = skip that section)
- Show at most 3 recent commits, 5 open PRs, 3 PRs to review
- Keep the template compact — this is a scannable dashboard, not a report
