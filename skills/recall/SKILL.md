---
name: recall
user-invocable: true
description: "Use before starting substantive work in a repo with shared docs — recalls prior decisions, patterns, and lessons relevant to the task at hand. First verb in the knowledge lifecycle loop. Replaces /remember."
argument-hint: "[task description or repo name] [--repo <name>] [--full] [--include-stale]"
---

# Recall

Knowledge consumption — discover what the fleet already knows before starting work. Scan INDEX.md files, filter for relevance, and surface the docs that matter.

This is the **first verb** in the knowledge lifecycle: recall → work → learn → reflect → index → recall (next session).

## Arguments

Parse `$ARGUMENTS` at invocation:
- **First positional arg:** Task description, repo name, or topic query. Used to filter INDEX.md entries by relevance.
- `--repo <name>`: Scope to a specific repo's knowledge directory.
- `--full`: Read and summarize matched docs (default: titles and one-line descriptions only).
- `--include-stale`: Also show docs with terminal statuses (stale, superseded, completed, archived — hidden by default).

---

## Step 1: Locate INDEX.md Files

Determine the shared docs root: `CLAUDRON_VAULT` / `CLAUDRON_VAULT_PATH` / `SHARED_DOCS_PATH` env vars win (in that order); otherwise parse the current CLAUDE.md `## Shared Documentation` section — first non-empty line is the root path, or the first backtick-quoted path when that line is templated prose (contract: `skills/_shared/documentation-standard.md` §10). If env and section disagree, use the env value and note the mismatch.

- **Root annotated `(claudron vault)` (or resolved from `CLAUDRON_VAULT`/`CLAUDRON_VAULT_PATH`):** the root is engine-managed and carries no INDEX.md — do not INDEX-scan it and do not suggest `/claudna:index`. Degrade with: "engine-managed root; install claudron or point the section at a raw tree." — appending, when the root came from env: "(root came from `CLAUDRON_VAULT`/`CLAUDRON_VAULT_PATH` — unset it to fall back)".
- **No root resolves:** say so and point at `/claudna:init-project` — its shared-docs seam step provisions the section.

Scan these INDEX.md files:

| Path (under the resolved root) | Why |
|------|-----|
| `<root>/planning/active/INDEX.md` | Active plans that may affect the task |
| `<root>/knowledge/<repo>/INDEX.md` | Repo-specific learnings (if `--repo` set or repo inferrable from task) |
| `<root>/knowledge/INDEX.md` | Top-level knowledge index |
| `<root>/decisions/INDEX.md` | Ratified decisions that constrain the work |

If `--repo` is set, prioritize `knowledge/<repo>/`. If the task mentions a repo name, infer it.

## Step 2: Filter for Relevance

For each INDEX.md entry, match against the query:
- **Title match** — does the title contain keywords from the task?
- **Tag match** — do inline tags overlap with the task's domain?
- **Repo match** — does the entry's repo tag match the target repo?
- **Status filter** — include only `active`, `current`, `ratified`, `draft`. Exclude `stale`, `superseded`, `completed`, `archived` unless `--include-stale` is set.

Rank matches by: exact repo match > tag overlap > title keyword match.

## Step 3: Present Results

**Context budget: never read more than 5 docs.** This is a hard cap.

### Default Mode (titles only)

Return the top 3-5 matches with title and one-line description:

```
## Relevant Knowledge

Found 4 matching docs for "shuffify auth rework":

1. [Spotify API Rate Limits](knowledge/shuffify/spotify-api-rate-limits.md) — rate limit quirks and retry patterns (status: current, owner: greg)
2. [Shuffify Auth Rework Plan](planning/active/shuffify-auth-rework.md) — OAuth migration plan (status: active, owner: greg)
3. [OAuth Token Refresh Patterns](knowledge/shuffify/oauth-token-refresh.md) — refresh flow and edge cases (status: current, owner: craig)

Review these before starting. Read specific docs with /claudna:recall --full or by opening the file directly.
```

### --full Mode

Read the top matches (up to 5) and provide a brief summary of each:

```
## Relevant Knowledge (detailed)

### 1. Spotify API Rate Limits
**Path:** knowledge/shuffify/spotify-api-rate-limits.md
**Summary:** Spotify enforces 30 req/sec per app. 429 responses include Retry-After header. Batch endpoints exist for tracks/albums but not for user playlists. Rate limits reset per rolling window, not per calendar second.

### 2. Shuffify Auth Rework Plan
**Path:** planning/active/shuffify-auth-rework.md
**Summary:** Active plan to migrate from implicit grant to PKCE auth flow. Phase 1 (token storage) is complete. Phase 2 (refresh logic) is in progress. Depends on the token refresh patterns doc below.

[...up to 5 docs...]
```

## Step 4: Flag Conflicts

If any active plans touch the same repo as the current task, flag them explicitly:

```
⚠ Active plan in scope: "Shuffify Auth Rework Plan" (owner: greg, status: active)
Check planning/active/shuffify-auth-rework.md before starting to avoid contradicting in-flight work.
```

## Rules

- **5-doc cap is non-negotiable.** If more than 5 docs match, show the top 5 and note how many were omitted.
- Scan INDEX.md only — never walk directories to find docs. If INDEX.md is missing or empty on a raw tree, note it and suggest running `/claudna:index` — but never against a `(claudron vault)`-annotated root (Step 1's degraded message applies instead).
- Don't modify any files. This is a read-only skill.
- If no matches are found, say so clearly — don't fabricate relevant docs.

$ARGUMENTS
