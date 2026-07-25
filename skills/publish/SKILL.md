---
name: publish
user-invocable: true
description: "Use when a finished markdown document — plan, audit or review findings, retro, decision, or knowledge page — needs to reach its destination: the shared-docs vault, the repo's documentation/ tree, a GitHub issue, a PR description, the chat session, or a Notion page. The single output sink: skills author content, publish delivers it. For a quick vault note rather than a finished document, use /claudna:claudron."
argument-hint: "<source-file-or-dir> [--to vault|docs|github-issue|github-pr|session|notion] [--dir <path>] [--update <issue#|url>] [--repo <name>] [--dry-run]"
---

# Publish

Markdown-first, output-last. Takes a doc with frontmatter and publishes it to the right destination. The doc is always the source of truth — /claudna:publish is just the adapter.

**This skill is the single output sink.** Analysis/planning skills are *authors*: they produce a markdown doc with valid frontmatter and the house-style body skeleton, then hand it to /claudna:publish. /claudna:publish is the *publisher*: it enforces house style, dedups per-medium, and routes the one manuscript to whichever edition the caller asked for. Skills must never call `gh issue create` / `gh pr create` themselves — they delegate here. The canonical house-style spec (frontmatter schema, per-type body skeleton, label taxonomy) lives in `skills/_shared/output-guide.md`; this skill enforces it.

## Arguments

Parse `$ARGUMENTS` at invocation:
- **First positional arg:** Path to the source markdown file — or, for the docs adapter's family mode, a directory holding one `00_*.md` master plus `NN_*.md` phase docs. Required.
- `--to <dest>`: Destination adapter. One of: `vault` (default), `docs`, `github-issue`, `github-pr`, `session`, `notion`.
- `--dir <path>`: docs adapter only — the target directory under `documentation/` (the calling skill knows its category; registry in `skills/_shared/documentation-standard.md` §2). Required with `--to docs`.
- `--update <issue#|url>`: Replace the named GitHub issue's body instead of creating anything. Implies `--to github-issue` — the only adapter with an update path — so `--to` may be omitted. See "In-place update" under the github-issue adapter.
- `--repo <name>`: Target repository (for github adapters).
- `--dry-run`: Show what would be published without doing it.

---

## Step 1: Read and Validate Source (house style)

Read the source markdown file. Parse YAML frontmatter. Validation is **deep** — a malformed manuscript is never published. If any check below fails, report the specific errors and stop. (Directory source: this step runs per doc via the docs adapter's family loop.)

### 1a. Frontmatter schema

Validate required fields exist and are well-formed:

| Field | Rule |
|-------|------|
| `title` | non-empty string |
| `type` | a valid note type — vocabulary table in `skills/_shared/output-guide.md` §3 (the repo's only enum table, rendered from the Claudron SSOT) |
| `status` | valid for the `type` per the §3 vocabulary table: canonical values pass silently; accepted legacy values (e.g. `active` on a knowledge doc) pass with a one-line mapping note — never a rejection |
| `owner` | non-empty string |
| `created` | valid `YYYY-MM-DD` |

Optional fields: `tags` (→ issue labels), `repos` (→ vault dir + repo inference), `links` (publish writes the destination URL back here), `updated`, `expires`, `description`.

Pass-through fields (accepted, never rejected, never required — output-guide §3): `maturity`, `schema_version`, and any `x-*`-prefixed field. Publish carries them through untouched and never validates their values.

### 1b. Body skeleton (per `type:`)

The body must match the house-style skeleton for its `type:`. This is keyed off `type:` (≤6 types) — publish validates the *skeleton*, never the prose, and never rewrites the body.

- **`audit`, `review`, `plan`** — must contain the implementation-ready skeleton (see `skills/_shared/output-guide.md` Section 4.1):
  `## Summary`, `## Evidence`, `## Implementation Plan` (with `### Dependencies`, `### Blocks`, `### Steps`), `## Test Plan`, `## Verification Checklist`, `## What NOT To Do`, `## Context`.
  **Hard gate:** the `## Implementation Plan` heading and its `### Steps` subsection MUST be present. This is the contract `/claudna:implement-plan --source github` depends on to tell an implementable issue from a findings-only one — without it, `--auto` implementation blocks. Reject the publish if missing.
- **`decision`, `knowledge`, `runbook`** — require a non-trivial body (not just frontmatter) and a leading `#`/`##` heading. No fixed section gate (see `skills/_shared/documentation-standard.md`); validate presence, not structure.

**Master-doc exception (docs adapter):** a `00_*.md` doc validates like the knowledge tier — frontmatter + non-trivial body + leading heading, no §4.1 skeleton gate — even when its `type:` is `audit`/`review`/`plan`, whether it arrives as a family member (directory source) or alone (single-doc source: retros, dashboards, findings reports). Masters and standalone reports are inventories, not implementation plans; the skeleton hard gate exists for implement-plan readiness, which is a property of the `NN_*` phase docs (which validate in full). This exemption is the design, not a workaround.

---

## Step 2: Route to Adapter

Two disk-backed adapters serve two different planes — the plane doctrine and which-door table live in `skills/_shared/documentation-standard.md`:

- **`vault`** → the shared-docs vault (cross-project referential knowledge; INDEX-discovered)
- **`docs`** → the current repo's `documentation/` tree (work-in-flight + repo-coupled records; git/PR-discovered)

### Adapter: vault (default)

This plane has two backends — a Claudron vault (engine) and a raw tree (fallback). Run the **detection ladder in `skills/_shared/claudron-engine.md` §1** first, then route:

**Engine path — verdict present-with-vault.** Route the finished doc through Claudron rather than writing files directly; map its frontmatter onto a capture call:

```bash
# provenance (flags-capable engine only — see below): add --source-url <url> --source-type <url|file|inline>
claudron capture --type <type> --title "<title>" --body "<body>" --tags "<tags>" --project <repo> --json
```

`--project` comes from the doc's `repos:` / `--repo` (omit if unscoped); for a long body pass the finding as JSON via `--stdin` (`/claudna:capture` Step 4). Validate the envelope (claudron-engine.md §2) and branch on `data.action`: `created` → report `data.path`; `suggest_update` / `suggest_supersede` → surface `data.reason` and the existing note to the caller (the engine's index-backed dedup replaces the raw adapter's file-compare); `rejected` (exit 1) → surface the validation errors. An engine failure *during* capture (exit 3 or an unrecognized envelope) degrades to the fallback path below, per claudron-engine.md §3 — say so. Do **not** run `/claudna:index` — the vault is engine-indexed (documentation-standard §10). Maturity is never set here; the engine stamps `draft`.

**Provenance (capability-probed).** If the doc's frontmatter carries `source_url` / `source_type` (SCHEMA optional fields), map them onto `--source-url` / `--source-type` — but **only on a flags-capable engine**: `data.engine_version` present and ≥ **0.4.0** (the Claudron C2 release that added the flags; the same version probe `/claudna:capture` Step 1 uses, and the same floor its PreCompact defer keys on). An older / absent / unreadable version omits them (it would reject the flags, exit 2). Provenance is **never** folded into the body here: that trailing `Source:` workaround was capture's alone, and the github-pr adapter's `Source:` footer is an unrelated surface.

**Fallback path — verdict present-no-vault or absent** (frozen behavior). Say so — "Claudron vault unavailable — writing the raw tree" — then write the doc to the raw-tree directory for its `type:`:

| Type | Destination |
|------|-------------|
| plan | `shared/planning/active/` (or `completed/` for terminal statuses) |
| decision | `shared/decisions/` |
| knowledge | `shared/knowledge/<repo>/` (requires `repos:` field or `--repo` flag) |
| runbook | `shared/runbooks/` |
| audit, review | `shared/planning/active/` |

If the file already exists, compare and warn before overwriting (the raw adapter's dedup). After writing: (1) run `/claudna:index` on the destination to update INDEX.md; (2) report the path. In `--auto`, the fallback sets `artifacts.engine: "fallback"` and notes the degradation in `errors[]` (claudron-engine.md §3).

**Plane-fit advisory** (either path): a `plan`/`audit`/`review` doc landing vault-ward gets a one-line note — "unusual plane for this type: work-in-flight planning usually belongs in the repo's `documentation/` tree (docs adapter)". Advisory only, never a block — fleet workflows legitimately share plans vault-side.

### Adapter: docs

Write the doc — or doc family — into the current repo's `documentation/` tree, the per-project plane. The author produces its output in a scratch directory and hands it here; publish is the single **placement path for finished docs** on this plane (status-marker write-backs and archiving by `/claudna:implement-plan` are the documented exceptions).

- `--dir <path>` is **required** and must resolve under `documentation/`. Reject anything outside it. Create the directory if it doesn't exist (the Write tool creates parents automatically) — don't fail on missing directories.
- **Single-doc mode** (source is a file): validate per Step 1, write into `--dir`, report the path.
- **Family mode** (source is a directory): the source holds **exactly one** `00_*.md` master + `NN_*.md` phase docs (the shape forge and the audit lenses produce); any other `.md` file fails the family (zero or multiple `00_*` files likewise); non-markdown files (screenshots, assets) copy through unvalidated. Loop per doc: phase docs validate against the full Step 1 contract including the §4.1 skeleton hard gate; the master validates under the master-doc exception (Step 1b). Validation reads are bounded — frontmatter (first ~15 lines) plus a Grep for the required section headings decide every check; never pull a family's full prose into context (the orchestration guide's context-window rules apply to the publishing orchestrator too). Any doc failing validation fails the whole family — report every error, write nothing (no partial families). On success, write all docs into `--dir` preserving filenames; report the directory and doc count.
- **No INDEX step.** The docs plane is git/PR-discovered — never run `/claudna:index` here; INDEX.md is the vault plane's discovery layer.
- **Dedup:** if a target file already exists, compare (bounded — same read rules as validation) and warn before overwriting (same rule as the vault adapter).
- **Plane-fit advisory:** a `knowledge`/`runbook` doc landing here gets a one-line note — "unusual plane for this type: cross-project reference knowledge usually belongs in the vault (default adapter)". Advisory only, never a block.

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

When `--dry-run` is set, show exactly what would happen without doing it (including the result of Step 1 validation, the resolved adapter/plane — with any plane-fit advisory — and, in family mode, the per-doc validation verdicts):

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
