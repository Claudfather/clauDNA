---
name: publish
user-invocable: true
description: "Use when a finished markdown document — plan, audit or review findings, retro, decision, or knowledge page — needs to reach its destination: shared docs on disk, a GitHub issue, a PR description, the chat session, or a Notion page. The single output sink: skills author content, publish delivers it."
argument-hint: "<source-file> [--to disk|github-issue|github-pr|session|notion] [--update <issue#|url>] [--repo <name>] [--dry-run]"
---

# Publish

Markdown-first, output-last. Takes a doc with frontmatter and publishes it to the right destination. The doc is always the source of truth — /claudna:publish is just the adapter.

**This skill is the single output sink.** Analysis/planning skills are *authors*: they produce a markdown doc with valid frontmatter and the house-style body skeleton, then hand it to /claudna:publish. /claudna:publish is the *publisher*: it enforces house style, dedups per-medium, and routes the one manuscript to whichever edition the caller asked for. Skills must never call `gh issue create` / `gh pr create` themselves — they delegate here. The canonical house-style spec (frontmatter schema, per-type body skeleton, label taxonomy) lives in `skills/_shared/output-guide.md`; this skill enforces it.

## Arguments

Parse `$ARGUMENTS` at invocation:
- **First positional arg:** Path to the source markdown file. Required.
- `--to <dest>`: Destination adapter. One of: `disk` (default), `github-issue`, `github-pr`, `session`, `notion`.
- `--update <issue#|url>`: Replace the named GitHub issue's body instead of creating anything. Implies `--to github-issue` — the only adapter with an update path — so `--to` may be omitted. See "In-place update" under the github-issue adapter.
- `--repo <name>`: Target repository (for github adapters).
- `--dry-run`: Show what would be published without doing it.

---

## Step 1: Read and Validate Source (house style)

Read the source markdown file. Parse YAML frontmatter. Validation is **deep** — a malformed manuscript is never published. If any check below fails, report the specific errors and stop.

### 1a. Frontmatter schema

Validate required fields exist and are well-formed:

| Field | Rule |
|-------|------|
| `title` | non-empty string |
| `type` | one of: `plan`, `decision`, `knowledge`, `runbook`, `audit`, `review` |
| `status` | valid for the `type` (see table) |
| `owner` | non-empty string |
| `created` | valid `YYYY-MM-DD` |

Type-dependent `status` values:

| Type | Valid statuses |
|------|----------------|
| `plan` | draft, active, completed, superseded |
| `knowledge` | current, stale, superseded |
| `decision` | draft, ratified, superseded |
| `runbook` | current, stale, superseded |
| `audit`, `review` | draft, completed |

Optional fields: `tags` (→ issue labels), `repos` (→ disk dir + repo inference), `links` (publish writes the destination URL back here), `updated`, `expires`, `description`.

### 1b. Body skeleton (per `type:`)

The body must match the house-style skeleton for its `type:`. This is keyed off `type:` (≤6 types) — publish validates the *skeleton*, never the prose, and never rewrites the body.

- **`audit`, `review`, `plan`** — must contain the implementation-ready skeleton (see `skills/_shared/output-guide.md` Section 4.1):
  `## Summary`, `## Evidence`, `## Implementation Plan` (with `### Dependencies`, `### Blocks`, `### Steps`), `## Test Plan`, `## Verification Checklist`, `## What NOT To Do`, `## Context`.
  **Hard gate:** the `## Implementation Plan` heading and its `### Steps` subsection MUST be present. This is the contract `/claudna:implement-plan --source github` depends on to tell an implementable issue from a findings-only one — without it, `--auto` implementation blocks. Reject the publish if missing.
- **`decision`, `knowledge`, `runbook`** — require a non-trivial body (not just frontmatter) and a leading `#`/`##` heading. No fixed section gate (see `skills/_shared/documentation-standard.md`); validate presence, not structure.

---

## Step 2: Route to Adapter

### Adapter: disk (default)

Write the doc to the appropriate shared docs directory based on the `type:` field:

| Type | Destination |
|------|-------------|
| plan | `shared/planning/active/` (or `completed/` if status is completed) |
| decision | `shared/decisions/` |
| knowledge | `shared/knowledge/<repo>/` (requires `repos:` field or `--repo` flag) |
| runbook | `shared/runbooks/` |
| audit, review | `shared/planning/active/` |

If the file already exists at the destination, compare and warn before overwriting (this is the disk adapter's dedup).

After writing:
1. Run `/claudna:index` on the destination directory to update INDEX.md.
2. Report the file path written.

### Adapter: github-issue

**Dedup first (mandatory).** Before creating, search for an existing issue and apply the decision rules in `skills/_shared/output-guide.md` Section 4.5:

```bash
gh issue list --repo <owner>/<repo> --search "<key terms from title/tags/files>" --state open --limit 20
```

- Exact match → prefer offering `--update` of the existing issue (§4.5); skip and report its URL only if the caller declines.
- Related but different → create and add `Related: #NNN` to the body.
- Same pattern, different location → prefer adding to an umbrella issue.

Then create the issue:

```bash
gh issue create \
  --repo <owner>/<repo> \
  --title "<title from frontmatter>" \
  --body "<markdown body after frontmatter>" \
  --label "<tags from frontmatter, comma-separated>"
```

Labels come from `tags:` — skills express severity/priority as tags (`priority:critical`, `security`, `auto-audit`, …); publish maps `tags` → `--label` and creates any missing labels. The `--repo` flag is required; if `repos:` is set in frontmatter with exactly one repo, infer from that.

After creating:
1. Add the issue URL to the source doc's `links:` frontmatter field.
2. Report the issue URL.

**In-place update (`--update <issue#|url>`).** When the caller names an existing issue — a re-forged plan body, an epic gaining its phase-issues table, a corrected audit — replace that issue's body instead of creating anything:

```bash
gh issue edit <number> --repo <owner>/<repo> --body-file <rendered-body-file>
```

Rules: dedup is skipped (the target is explicit); the title is never changed (`gh issue edit --body-file` only — retitling stays a manual act); labels are additive only (`--add-label` for new `tags:`, never removing existing ones); report the issue URL and note "updated in place". The exact-match dedup rule lives in `skills/_shared/output-guide.md` §4.5 and routes here: an exact match prefers an offered `--update` over a skip.

### Adapter: github-pr

Format the doc as a PR description body. Output the formatted text for the caller to use in `gh pr create --body`:

```
## Summary

<first paragraph of doc body>

## Details

<rest of doc body>

---
Source: <source file path>
Type: <type> | Status: <status> | Owner: <owner>
```

This adapter does not create the PR — it formats the description. The caller creates the PR with the output.

### Adapter: session

Render the doc's body (everything after the frontmatter) back into the chat session. **No file is written, no issue is created, no frontmatter is updated.** This is the "think with me" edition — the same manuscript every other adapter publishes, just printed instead of persisted. Optionally prepend a one-line header derived from `title:`/`type:`. There is no dedup for this adapter.

### Adapter: notion

Create a Notion page via the MCP Notion tool:

1. Map frontmatter to Notion properties:
   - `title:` → page title
   - `type:` → select property
   - `status:` → select property
   - `tags:` → multi-select property
   - `created:` → date property
2. Set page body to the markdown content after frontmatter.
3. After creating, add the Notion page URL to the source doc's `links:` frontmatter field.

Requires the Notion MCP server to be configured. If not available, report the error clearly.

## Step 3: Dry Run

When `--dry-run` is set, show exactly what would happen without doing it (including the result of Step 1 validation):

```
Dry run: /claudna:publish doc.md --to github-issue --repo shuffify

House style: OK (type=audit, skeleton valid)
Would create GitHub issue:
  Repo: chrisrogers37/shuffify
  Title: Spotify API Rate Limits & Quirks
  Labels: api, spotify, rate-limits
  Dedup: no open match for "spotify rate limit"
  Body: [243 chars, first line: "Spotify enforces 30 req/sec per app..."]

No changes made.
```

## Rules

- **Never modify the doc body.** Only frontmatter updates are allowed (adding links, updating status).
- **Validate before publishing.** Invalid frontmatter or a missing body skeleton = no publish.
- **One source of truth.** The markdown file is authoritative. Published outputs (issues, Notion pages) are copies — they may go stale.
- **Report what you did.** After every publish, output: destination, URL/path, and any frontmatter updates made.
- If an adapter fails (auth error, missing repo, MCP not configured), report the error verbatim. Don't fabricate success.

$ARGUMENTS
