# Source Guide

Shared reference for skills that support `--source <target>`. Skills reference this file at `skills/_shared/source-guide.md`.

---

## 1. Overview

Implementation skills (primarily `/claudna:build`) support multiple input sources. The source controls **where** the plan is read from, not **how** it is processed — all sources feed into the same implementation workflow.

| Target | Flag | Behavior |
|---|---|---|
| `docs` | (default, no flag needed) | Read from a local file path or session directory |
| `github` | `--source github <number>` | Fetch a GitHub Issue by number and use its body as the plan |
| `github` (browse) | `--source github` (no number) | Browse all open issues via paginated picker, select one or more |

**All sources use Plan Mode** for the deliberation phase (codebase comparison, challenge round). The source only affects where the input comes from.

---

## 2. Common Requirements — All Sources

Regardless of source, the implementation skill must:

1. **Validate the plan has implementation detail.** Check for the presence of an `## Implementation Plan` section (or equivalent structured content). If the source is findings-only, warn the user and offer to expand it before proceeding.
2. **Use Plan Mode for deliberation.** The codebase comparison (Step 2) and challenge round (Step 3) execute identically regardless of source.
3. **Maintain a single source of truth.** During implementation, updates (challenge round changes, status markers, PR references) are written back to the source — whether that's a file on disk or a GitHub Issue body.

---

## 3. Source: `docs` (Default)

Read a planning document from the local filesystem. This is the current default behavior.

### Input formats

- **File path**: Direct path to a single phase document (e.g., `documentation/planning/tech_debt/session_2026-04-07/01_datetime_migration.md`)
- **Session directory**: Path to a session directory containing `00_OVERVIEW.md` and phase files. The skill reads the overview, lists phases, and asks which to start.

### Lifecycle

| Step | Action |
|---|---|
| Receive plan | Read file from disk |
| Challenge round updates | Edit the file directly |
| Mark in progress | Update status field in the file |
| Mark complete | Update status field in the file |
| Archive | `git mv` to `documentation/archive/` |

---

## 4. Source: `github`

Fetch a GitHub Issue by number and use its structured body as the plan input.

### Invocation

**Direct mode** (specific issue):
```
/claudna:build --source github <issue-number>
```

Examples:
- `/claudna:build --source github 190`
- `/claudna:build --source github #190` (with or without `#`)

**Browse mode** (no number):
```
/claudna:build --source github
```

When no issue number is provided, the skill enters browse mode:
1. Fetch all open issues: `gh issue list --state open --limit 50 --json number,title,labels`
2. If no open issues: tell user and stop
3. Print a summary table in chat showing all issues (number, title, labels, priority)
4. Present a paginated multi-select AskUserQuestion picker (3 issues per page + "More..." on 4th slot)
5. Accumulate selections across pages until user is done
6. Confirm selections, then fetch full body for each via `gh issue view <number>`
7. Queue selected issues for sequential implementation (see `/claudna:build` execution queue)

Browse mode produces the same result as direct mode — a fetched issue body fed into the implementation pipeline — but lets the user discover and select from available work.

### Fetching the issue

Use `gh` CLI to retrieve the issue:
```
gh issue view <number> --json number,title,body,labels,state,url
```

Extract:
- `title` → used as the plan title / PR title basis
- `body` → parsed as the plan document
- `labels` → used to determine priority, type
- `number` → used for cross-references (`Closes #<number>`)
- `url` → used in PR body and status updates

### Detecting detail level

Parse the issue body for the structured format defined in the output guide (Section 4.1). The key indicator is the presence of an `## Implementation Plan` section with a `### Steps` subsection.

| Body contains | Detail level | Action |
|---|---|---|
| `## Implementation Plan` with `### Steps` | Full detail | Proceed normally — treat body as phase doc |
| `## Suggested Approach` but no `## Implementation Plan` | Findings only | Warn user: "This issue contains findings but not a full implementation plan. Would you like me to expand it before proceeding?" |
| Neither | Unstructured | Warn user: "This issue doesn't follow the expected format. Would you like me to restructure it, or provide a file path instead?" |

**Expanding a findings-only issue:** If the user agrees, the skill runs codebase exploration to fill in the implementation details (before/after code, step-by-step instructions, verification checklist), then updates the issue body with the full structure before proceeding to the challenge round.

### Lifecycle

| Step | Action |
|---|---|
| Receive plan | `gh issue view <number>` |
| Challenge round updates | `gh issue edit <number> --body <updated body>` |
| Mark in progress | Add `in-progress` label: `gh issue edit <number> --add-label "in-progress"` |
| PR created | PR body includes `Closes #<number>` |
| Mark complete | Remove `in-progress` label. Issue auto-closes when PR merges. |
| Archive | No action needed — GitHub Issues don't need filesystem archival |

### Status labels for `--source github`

These labels track implementation progress on the issue:

| Label | When applied |
|---|---|
| `in-progress` | Step 4 (Mark In Progress) — implementation has started |

The `in-progress` label is removed when the PR is created (the PR itself tracks progress from that point). When the PR merges with `Closes #<number>`, GitHub auto-closes the issue.

### Editing issue bodies

When updating the issue body during the challenge round, preserve the full structured format. Use `gh issue edit` with the complete updated body:

```
gh issue edit <number> --body "$(cat <<'EOF'
<full updated body>
EOF
)"
```

**Important:** Always write the complete body, not a partial update. GitHub's issue edit API replaces the entire body.

---

## 5. Error Handling

- If `gh` is not authenticated or the issue is not accessible, fall back to asking for a file path.
- If the issue is in a closed state, warn the user: "This issue is closed. Would you like to reopen it and proceed, or use a different source?"
- If the issue body is empty, treat as unstructured (Section 4, detail level table).
- If `gh issue edit` fails during challenge round updates, log the failure, continue implementation, and note in the summary that the issue body may be out of sync.

---

## 6. How Skills Should Reference This Guide

In the skill's Arguments section:
```
- `--source github <number>`: Read a specific GitHub Issue as the implementation plan.
- `--source github` (no number): Browse all open issues via paginated picker.
- See source guide (`skills/_shared/source-guide.md`) for details.
- Default (no flag): Ask for a file path or session directory.
```

In the skill's Step 1 (Receive Plan):
```
Parse arguments for `--source` flag. Follow the source guide at `skills/_shared/source-guide.md`:
- `--source github <number>`: Fetch issue, validate detail level, proceed
- `--source github` (no number): Browse mode — list issues, paginated picker, queue selections
- Default: Ask "Which document should I implement?" and accept a file path or session directory
```
