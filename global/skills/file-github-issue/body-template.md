# Issue body template

Use this structure when drafting the issue body (step 4 of `SKILL.md`).

## Single image

```markdown
## What I saw
<1-2 sentences grounded in the screenshot and user prose>

## What I expected
<1-2 sentences>

## Where / how to reproduce
- **Page / URL:** <URL from browser chrome if visible; otherwise app section + page title + any breadcrumb, e.g. "MyApp — entity page — Item123"; or the user's reply from the Step 4b.5 prompt. Only use "unknown — user declined to provide" if the user explicitly skipped the prompt.>
- **Action:** <what the user did to surface this — a query, a click path, a prompt; omit if clearly stateless>
- **Inputs:** <the specific query, entity, date range, or data the issue depends on — omit if not relevant>

## Related
- **Issues:** <from the dupe-check search — "#N [open|closed]: title — one-line relationship note". "none found" if the search returned nothing.>
- **Links:** <Slack threads, docs, dashboards, pipeline/CI run URLs, related PRs — from user prose. Omit the line entirely if none.>

## Screenshot
![screenshot](<attachment-url-1>)

---
_Filed via `/file-github-issue`._
```

## Multiple images

Replace the `## Screenshot` section with:

```markdown
## Screenshots
![screenshot 1](<attachment-url-1>)
![screenshot 2](<attachment-url-2>)
…
```

## Rules

- **Title:** action-phrased, ≤80 characters. Good: *"Search results stale after entity rebuild"*. Bad: *"bug in myapp"*.
- **Placeholders** `<attachment-url-N>` must stay literal in the body until step 6 swaps them for resolved raw URLs from the attachments repo. Match by turn order: first image → `<attachment-url-1>`, second → `<attachment-url-2>`, etc.
- **Sparse-prose warning:** if the user provided <10 words of description, prepend this line above `## What I saw`:
  ```markdown
  > ⚠ Description is sparse — consider adding context.
  ```
- **Lean toward richer context, but don't fabricate.** Every bullet under "Where / how to reproduce" and "Related" should be extracted from the screenshot, the user's prose, the user's reply to the Step 4b.5 URL prompt, or the duplicate-check search. For optional enrichers (Action, Inputs, Links), omit the bullet entirely if no source exists. For the required Page/URL anchor, the skill prompts the user explicitly (Step 4b.5) rather than guessing or leaving silent-unknown. Never guess URLs, product names, or issue numbers.
- **Omit empty "Related" lines.** If the dupe search found nothing AND the user prose had no links, drop the whole `## Related` section rather than rendering empty bullets.
- **No assignee, no milestone, no project board.** GitHub shows the filer automatically in the issue header — no explicit author tag needed.

## Proposed labels

Always include `from-user`. Add others based on user framing:

| Framing | Proposed labels |
|---|---|
| Broken behavior | `from-user`, `bug` |
| Missing feature | `from-user`, `enhancement` |
| Clearly a question | `from-user`, `question` |
| Ambiguous | `from-user` only |

The effective label set is computed by the pre-flight in step 3 of `SKILL.md` (intersect proposed ∩ labels present in the repo).
