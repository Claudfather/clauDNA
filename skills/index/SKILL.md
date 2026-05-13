---
name: index
user-invocable: true
description: "Scan a documentation directory, validate frontmatter, and regenerate INDEX.md. Use after creating or updating shared docs, or to audit knowledge base health. This is the sole writer of INDEX.md files."
argument-hint: "[directory-path] [--validate-only] [--recursive] [--fix] [--stale]"
---

# Index

Scan, validate, and index shared documentation. INDEX.md is the discovery layer — other bots scan it to find relevant docs without reading every file.

**This skill is the SOLE writer of INDEX.md files.** Other skills (/claudna:learn, /claudna:reflect, /claudna:publish) create or update docs, then call /claudna:index to regenerate the index.

## Arguments

Parse `$ARGUMENTS` at invocation:
- **First positional arg:** Directory path to index. Defaults to the shared docs root (from `SHARED_DOCS_PATH` env var or detect from cwd).
- `--validate-only`: Check frontmatter without regenerating INDEX.md.
- `--recursive`: Index all subdirectories, not just the target.
- `--fix`: Auto-fill missing required fields where inferrable.
- `--stale`: Flag docs past their `expires:` date or with no update in >90 days.

---

## Step 1: Discover Documents

Walk all `.md` files in the target directory (excluding `INDEX.md` itself).

```bash
# Find all markdown files, skip INDEX.md
find <target-dir> -maxdepth 1 -name '*.md' ! -name 'INDEX.md' -type f | sort
```

If `--recursive`, walk subdirectories too. Each subdirectory gets its own INDEX.md.

## Step 2: Parse and Validate Frontmatter

For each file, read and parse YAML frontmatter. Validate against the schema:

**Required fields:**

| Field | Type | Validation |
|-------|------|------------|
| title | string | Non-empty |
| type | enum | plan, decision, knowledge, runbook, audit, review |
| status | enum | Type-dependent (see below) |
| owner | string | Non-empty |
| created | date | Valid YYYY-MM-DD |

**Type-dependent status values:**

| Type | Valid statuses |
|------|---------------|
| plan | draft, active, completed, superseded |
| knowledge | current, stale, superseded |
| decision | draft, ratified, superseded |
| runbook | current, stale, superseded |
| audit, review | draft, completed |

For each validation error, record: file path, field name, issue (missing, invalid value, wrong type).

### --fix Mode

When `--fix` is set, auto-fill missing fields where inferrable:
- `created:` — use file modification time (`stat` or `git log --format=%aI --diff-filter=A -- <file>`)
- `owner:` — use `git log --format=%an -1 -- <file>`
- `status:` — default to first valid status for the type (draft for plan/decision, current for knowledge/runbook)
- `type:` — infer from parent directory name if possible (planning/ → plan, knowledge/ → knowledge, decisions/ → decision, runbooks/ → runbook)

Write the fixed frontmatter back to the file. Report each auto-fix applied.

### --stale Mode

When `--stale` is set, flag documents that may be outdated:
- `expires:` date is in the past
- No `updated:` field and `created:` is >90 days ago
- `updated:` is >90 days ago
- `last_verified:` is >90 days ago

Report stale docs separately from validation errors.

## Step 3: Regenerate INDEX.md

Skip this step if `--validate-only` is set.

Sort documents:
1. **Primary:** active/current/ratified/draft first, then completed/stale/superseded
2. **Secondary:** alphabetical by title

Generate INDEX.md with one line per doc, including inline tags for grep-friendly filtering:

```markdown
# Index: <directory-name>

- [Title](filename.md) — description (status: active, owner: greg, tags: auth, oauth)
- [Another Doc](another.md) — description (status: current, owner: clog)
```

The description is the first sentence of the document body (after frontmatter), truncated to 80 characters. If the doc has a `description:` in frontmatter, use that instead.

Write the generated INDEX.md to the target directory.

## Step 4: Report

Output a summary:

```
Indexed: <target-dir>
  Documents: N
  Validation warnings: M
  Stale (if --stale): K
  Auto-fixed (if --fix): J

Warnings:
  - path/to/file.md: missing required field 'owner'
  - path/to/other.md: invalid status 'done' for type 'plan'

Stale:
  - path/to/old.md: expires 2026-03-01 (expired 71 days ago)
```

## Rules

- Never modify document content — only frontmatter (and only with `--fix`).
- INDEX.md is always fully regenerated, never appended to. This avoids stale entries.
- If the target directory doesn't exist, error clearly — don't create it.
- If no `.md` files are found (excluding INDEX.md), write an empty INDEX.md with just the header.

$ARGUMENTS
