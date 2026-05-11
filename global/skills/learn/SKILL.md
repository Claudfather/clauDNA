---
name: learn
description: "Knowledge ingestion — pull content from external sources into the knowledge base"
argument-hint: "<url|path|text> [--repo name] [--tags a,b] [--full] [--update]"
---

# Learn

You are a knowledge curator. Your job is to pull content from external sources — URLs, files, or inline text — into the fleet's shared knowledge base as clean, frontmattered markdown. Extract signal, discard noise, and make the result discoverable.

## Arguments

Parse `$ARGUMENTS` at invocation:
- **First positional arg:** URL (starts with `http`), file path (starts with `/` or `./`), or inline text. If omitted, prompt for it.
- `--repo <name>` — Target knowledge subdirectory under `shared/knowledge/`
- `--tags <a,b>` — Comma-separated discovery tags for frontmatter
- `--full` — Verbatim capture instead of summarize (still strips HTML chrome from URLs)
- `--update` — Refresh existing doc if `source_url` matches an entry in INDEX.md

---

## Phase 1: Input Resolution

### Step 1: Detect Input Mode

Determine the input type from the first positional argument:

| Pattern | Mode | Action |
|---------|------|--------|
| Starts with `http://` or `https://` | URL | Fetch via `WebFetch`, extract page content |
| Starts with `/` or `./` | File | `Read` the file |
| Anything else | Inline | Use the provided text directly |

### Step 2: Fetch Content

- **URL:** Fetch the page. Extract the main content — strip navigation, ads, sidebars, cookie banners. Preserve code blocks, examples, and tables.
- **File:** Read the full file contents.
- **Inline:** Use the text as-is.

If fetching fails (network error, 404, auth wall), report the error verbatim and stop. Do not fabricate content.

---

## Phase 2: Dedup Check

### Step 1: Locate Target Directory

Determine the target: `shared/knowledge/<repo>/` where `<repo>` comes from:
1. The `--repo` flag if provided
2. Inferred from the current working context (active repo name)
3. A topic slug derived from the content if no repo context exists

### Step 2: Check for Duplicates

If an `INDEX.md` exists in the target directory, grep for a matching `source_url` (for URL and file inputs).

- **Match found, no `--update` flag:** Warn — `"Existing doc found: <title>. Use --update to refresh."` — and stop.
- **Match found, `--update` flag set:** Proceed. The existing file will be overwritten.
- **No match:** Proceed to extraction.

---

## Phase 3: Extract & Format

### Step 1: Process Content

**Default behavior (summarize):**
- Extract key insights, main arguments, and actionable information
- Preserve code blocks, examples, data tables, and command-line snippets verbatim
- Strip boilerplate: navigation, author bios, related-article links, ads, cookie notices
- Aim for 30-50% of original length while retaining all technical substance

**With `--full` flag:**
- Capture content verbatim
- Still strip HTML chrome if source was a URL (nav bars, footers, scripts)
- Preserve all structure, headings, and formatting

### Step 2: Generate Slug

From the extracted or provided title:
1. Lowercase the title
2. Replace spaces and special characters with hyphens
3. Collapse consecutive hyphens
4. Truncate at 40 characters on a word boundary (do not split mid-word)
5. Strip trailing hyphens

If the slug collides with an existing file in the target directory, append `-2`, `-3`, etc.

### Step 3: Format as Knowledge Doc

Write the document with this frontmatter:

```yaml
---
title: <extracted or provided title>
type: knowledge
status: current
owner: {{BOT_NAME}}
created: <today YYYY-MM-DD>
source_type: url|file|inline
source_url: <original URL if applicable>
tags: [<from --tags flag>]
---
```

Follow the frontmatter with the processed content as markdown.

---

## Phase 4: Write & Index

### Step 1: Write the File

Write to `shared/knowledge/<repo-or-topic>/<slug>.md`.

Create the target directory if it does not exist.

### Step 2: Update Index

Auto-run `/index` on the target directory to regenerate INDEX.md.

### Step 3: Report

Report the result: `"Learned: <title> -> <path>"`

---

## Flags Reference

| Flag | Purpose |
|------|---------|
| `--repo <name>` | Target knowledge subdirectory |
| `--tags <a,b>` | Discovery tags for frontmatter |
| `--full` | Verbatim capture instead of summarize |
| `--update` | Refresh existing doc if `source_url` matches |

---

## Notes

- This skill is one verb in the knowledge lifecycle: `/learn` (ingest) -> work -> `/reflect` (synthesize) -> `/index` (organize) -> next session reads indexed knowledge.
- Default to summarize. Engineers want the signal, not the full MDN page. Use `--full` only when the original structure matters (specs, API references, schemas).
- Frontmatter follows the fleet's documentation schema. The `slug` field enables future wikilink `[[linking]]` support.
- When in doubt about the target directory, prefer creating a new subdirectory over dumping into a catch-all. Knowledge is easier to find when it is organized by repo or topic.
