---
name: index
user-invocable: true
description: "Use after creating, promoting, or editing docs in a directory whose INDEX.md should be regenerated, when frontmatter needs validating against the documentation standard, or to audit knowledge-base health. The sole writer of INDEX.md files."
argument-hint: "[directory-path] [--validate-only] [--recursive] [--fix] [--stale]"
---

# Index

Scan, validate, and index shared documentation. INDEX.md is the discovery layer — other bots scan it to find relevant docs without reading every file.

**This skill is the SOLE writer of INDEX.md files.** Other skills (/claudna:capture, /claudna:reflect, /claudna:publish) create or update docs, then call /claudna:index to regenerate the index.

## Arguments

Parse `$ARGUMENTS` at invocation:
- **First positional arg:** Directory path to index. Defaults to the shared docs root — `CLAUDRON_VAULT`/`CLAUDRON_VAULT_PATH`/`SHARED_DOCS_PATH` env vars (in that order), else CLAUDE.md's `## Shared Documentation` section (contract: `skills/_shared/documentation-standard.md` §10; env wins on disagreement, note the mismatch), else detect from cwd.
- `--validate-only`: Check frontmatter without regenerating INDEX.md.
- `--recursive`: Index all subdirectories, not just the target.
- `--fix`: Auto-fill missing required fields where inferrable.
- `--stale`: Flag docs past their `expires:` date or with no update in >90 days.

---

## Step 1: Discover Documents

**Engine-managed roots are never indexed.** If the target is a root annotated `(claudron vault)` in CLAUDE.md's `## Shared Documentation` section (or came from `CLAUDRON_VAULT`/`CLAUDRON_VAULT_PATH`), stop with: "engine-managed root; install claudron or point the section at a raw tree." — appending, when the root came from env: "(root came from `CLAUDRON_VAULT`/`CLAUDRON_VAULT_PATH` — unset it to fall back)". The engine owns vault indexing — an INDEX.md written there would be stale on arrival.

Walk all `.md` files in the target directory (excluding `INDEX.md` itself).

```bash
# Find all markdown files, skip INDEX.md
find <target-dir> -maxdepth 1 -name '*.md' ! -name 'INDEX.md' -type f | sort
```

If `--recursive`, walk subdirectories too. Each subdirectory gets its own INDEX.md.

## Step 2: Parse and Validate Frontmatter

For each file, read and parse YAML frontmatter. Validate against the schema (vocabulary SSOT: `skills/_shared/output-guide.md` §3 — the repo's only type/status enum table):

**Required fields:**

| Field | Type | Validation |
|-------|------|------------|
| title | string | Non-empty |
| type | enum | A valid note type per the output-guide §3 vocabulary table |
| status | enum | Valid for the type per the §3 table — canonical or accepted legacy (legacy gets a mapping note, not an error) |
| owner | string | Non-empty |
| created | date | Valid YYYY-MM-DD |

**Pass-through fields** (accepted, never flagged, never required — output-guide §3): `maturity`, `schema_version`, and any `x-*`-prefixed field. Index reads past them; they are never validation errors.

For each validation error, record: file path, field name, issue (missing, invalid value, wrong type).

### --fix Mode

When `--fix` is set, auto-fill missing fields where inferrable:
- `created:` — use file modification time (`stat` or `git log --format=%aI --diff-filter=A -- <file>`)
- `owner:` — use `git log --format=%an -1 -- <file>`
- `status:` — default per type: `current` for knowledge/runbook, `draft` for plan/decision/audit/review (the §3 type defaults; unchanged by the SSOT rendering)
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
1. **Primary:** active/current/ratified/draft first, then completed/stale/superseded/archived
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
- Never index an engine-managed root — Step 1's refusal applies before any walk.
- If no `.md` files are found (excluding INDEX.md), write an empty INDEX.md with just the header.

$ARGUMENTS
