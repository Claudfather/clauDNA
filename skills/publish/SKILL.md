---
name: publish
description: "Output adapter for shared docs. Takes a markdown file with frontmatter and publishes it to a destination: disk (shared docs directory), GitHub issue, GitHub PR description, or Notion page."
argument-hint: "<source-file> [--to disk|github-issue|github-pr|notion] [--repo <name>] [--dry-run]"
---

# Publish

Markdown-first, output-last. Takes a doc with frontmatter and publishes it to the right destination. The doc is always the source of truth — /claudna:publish is just the adapter.

## Arguments

Parse `$ARGUMENTS` at invocation:
- **First positional arg:** Path to the source markdown file. Required.
- `--to <dest>`: Destination adapter. One of: `disk` (default), `github-issue`, `github-pr`, `notion`.
- `--repo <name>`: Target repository (for github adapters).
- `--dry-run`: Show what would be published without doing it.

---

## Step 1: Read and Validate Source

Read the source markdown file. Parse YAML frontmatter.

Validate required fields exist: `title`, `type`, `status`, `owner`, `created`. If validation fails, report errors and stop — don't publish invalid docs.

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

After writing:
1. Run `/claudna:index` on the destination directory to update INDEX.md.
2. Report the file path written.

If the file already exists at the destination, compare and warn before overwriting.

### Adapter: github-issue

Create a GitHub issue from the doc:

```bash
gh issue create \
  --repo <owner>/<repo> \
  --title "<title from frontmatter>" \
  --body "<markdown body after frontmatter>" \
  --label "<tags from frontmatter, comma-separated>"
```

The `--repo` flag is required for this adapter. If `repos:` is set in frontmatter and contains exactly one repo, infer from that.

After creating:
1. Add the issue URL to the source doc's `links:` frontmatter field.
2. Report the issue URL.

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

When `--dry-run` is set, show exactly what would happen without doing it:

```
Dry run: /claudna:publish doc.md --to github-issue --repo shuffify

Would create GitHub issue:
  Repo: chrisrogers37/shuffify
  Title: Spotify API Rate Limits & Quirks
  Labels: api, spotify, rate-limits
  Body: [243 chars, first line: "Spotify enforces 30 req/sec per app..."]

No changes made.
```

## Rules

- **Never modify the doc body.** Only frontmatter updates are allowed (adding links, updating status).
- **Validate before publishing.** Invalid frontmatter = no publish.
- **One source of truth.** The markdown file is authoritative. Published outputs (issues, Notion pages) are copies — they may go stale.
- **Report what you did.** After every publish, output: destination, URL/path, and any frontmatter updates made.
- If an adapter fails (auth error, missing repo, MCP not configured), report the error verbatim. Don't fabricate success.

$ARGUMENTS
