---
name: publish
user-invocable: true
description: "Use when a finished markdown document — plan, audit or review findings, retro, decision, or knowledge page — needs to reach its destination: the shared-docs vault, the repo's documentation/ tree, a GitHub issue, a PR description, the chat session, a Notion page, or the default private session artifact area. The single output sink: skills author content, publish delivers it. For a quick vault note rather than a finished document, use /claudna:claudron."
argument-hint: "<source-file-or-dir> [--to artifacts|vault|docs|github-issue|github-pr|session|notion] [--dir <path>] [--update <issue#|url>] [--repo <name>] [--dry-run]"
requires:
  - cli: claudron
    reason: "Optional — `--to vault` routes the doc through `claudron capture` when the engine is present; without it, that one adapter degrades per the standard notice in ../_shared/claudron-engine.md §3.1 and writes the frozen raw tree. Every other adapter is unaffected"
---

# Publish

> **Codex:** Read `../_shared/codex-tools.md` before following this skill. Apply its tool, root and dispatch mappings throughout.

Markdown-first, output-last. Takes a doc with frontmatter and publishes it to the right destination. The doc is always the source of truth — /claudna:publish is just the adapter.

The default destination is the current native session's private `artifacts` area. Other destinations are explicit exports; native receipts and consumer acceptance remain merge/release gates. Resolve the loaded package root through [`../_shared/claudna-root.md`](../_shared/claudna-root.md); examples use the actual `python3 -B <claudna-root>/lib/claudna/session_store` entrypoint.

**This skill is the single output sink.** Analysis/planning skills are *authors*: they produce a markdown doc with valid frontmatter and the house-style body skeleton, then hand it to /claudna:publish. /claudna:publish is the *publisher*: it enforces house style, dedups per-medium, and routes the one manuscript to whichever edition the caller asked for. Skills must never call `gh issue create` / `gh pr create` themselves — they delegate here. The canonical house-style spec (frontmatter schema, per-type body skeleton, label taxonomy) lives in `../_shared/output-guide.md`; this skill enforces it.

## Arguments

Parse `$ARGUMENTS` at invocation:
- **First positional arg:** Path to the source markdown file — or, for artifacts/docs family mode, a directory holding one `00_*.md` master plus `NN_*.md` phase docs. Required except for `--to session`, which may receive the document directly in context without a file.
- `--to <dest>`: Destination adapter. One of: `artifacts` (default), `vault`, `docs`, `github-issue`, `github-pr`, `session`, or `notion`.
- `--dir <path>`: docs adapter only — the target directory under `documentation/` (the calling skill knows its category; registry in `../_shared/documentation-standard.md` §2). Required with `--to docs`.
- `--update <issue#|url>`: Replace the named GitHub issue's body instead of creating anything. Implies `--to github-issue` — the only adapter with an update path — so `--to` may be omitted. See "In-place update" under the github-issue adapter.
- `--repo <name>`: Target repository (for github adapters).
- `--dry-run`: Show what would be published without doing it.

---

## Step 1: Read and Validate Source (house style)

For an in-context `session` document, validate its supplied content below without allocating files. **Before reading any source content**, resolve each explicitly selected source file or asset path (including symlink aliases) and determine whether it is a canonical artifact under the effective root. If it is, validate that exact absolute path and owner with the existing `continuity artifact-path` explicit-path form shown under the artifacts adapter below. Apply this gate to every canonical source for every destination adapter, including files individually selected from a family; never blanket-read a directory or read a canonical payload before its path is authorized. Validate current-session and other-session canonical paths. A current-owner private/manual artifact is permitted; another owner's source requires a public, bounded scope. Missing, private, denied, stale, or otherwise uncertain validation means stop before content read, preserve the source, and report partial/unavailable. Noncanonical scratch/user sources follow the existing Step 1 reads and validation below.

After the gate, read the allowed source markdown file. Parse YAML frontmatter. Validation is **deep** — a malformed manuscript is never published. If any check below fails, report the specific errors and stop. (Directory source: this step runs per doc via the artifacts/docs family loop.)

### 1a. Frontmatter schema

Validate required fields exist and are well-formed:

| Field | Rule |
|-------|------|
| `title` | non-empty string |
| `type` | a valid note type — vocabulary table in `../_shared/output-guide.md` §3 (the repo's only enum table, rendered from the Claudron SSOT) |
| `status` | valid for the `type` per the §3 vocabulary table: canonical values pass silently; accepted legacy values (e.g. `active` on a knowledge doc) pass with a one-line mapping note — never a rejection |
| `owner` | non-empty string |
| `created` | valid `YYYY-MM-DD` |

Optional fields: `tags` (→ issue labels), `repos` (→ vault dir + repo inference), `links` (publish writes the destination URL back here for editable noncanonical sources), `updated`, `expires`, `description`.

**Canonical artifact source rule:** once a file is a canonical artifact, its content and frontmatter remain unchanged during later exports. In particular, do not add an issue, Notion, or other destination URL to that canonical source. For an actual returned non-chat outcome, record the destination in a private receipt under the current session's artifact area; this applies to every destination adapter and never copies the canonical source. A failed or uncertain destination may be recorded only with its actual failed/unknown status, never as success. Session/chat output and dry-run remain mutation-free and create no receipt. A scratch export edition derived from a canonical source retains that source's ownership/privacy gate and receipt obligation: record the canonical source hash plus the rendered edition hash and formatting/cross-link changes. Copying into scratch never bypasses canonical protection. Existing write-back behavior remains available for independently authored noncanonical user sources where the adapter below specifies it.

Pass-through fields (accepted, never rejected, never required — output-guide §3): `maturity`, `schema_version`, and any `x-*`-prefixed field. Publish carries them through untouched and never validates their values.

### 1b. Body skeleton (per `type:`)

The body must match the house-style skeleton for its `type:`. This is keyed off `type:` (≤6 types) — publish validates the *skeleton*, never the prose, and never rewrites the body.

- **`audit`, `review`, `plan`** — must contain the implementation-ready skeleton (see `../_shared/output-guide.md` Section 4.1):
  `## Summary`, `## Evidence`, `## Implementation Plan` (with `### Dependencies`, `### Blocks`, `### Steps`), `## Test Plan`, `## Verification Checklist`, `## What NOT To Do`, `## Context`.
  **Hard gate:** the `## Implementation Plan` heading and its `### Steps` subsection MUST be present. This is the contract `/claudna:build --source github` depends on to tell an implementable issue from a findings-only one — without it, `--auto` implementation blocks. Reject the publish if missing.
- **`decision`, `knowledge`, `runbook`** — require a non-trivial body (not just frontmatter) and a leading `#`/`##` heading. No fixed section gate (see `../_shared/documentation-standard.md`); validate presence, not structure.

**Master-doc exception (artifacts and docs adapters):** a `00_*.md` doc validates like the knowledge tier — frontmatter + non-trivial body + leading heading, no §4.1 skeleton gate — even when its `type:` is `audit`/`review`/`plan`, whether it arrives as a family member (directory source) or alone (single-doc source: retros, dashboards, findings reports). Masters and standalone reports are inventories, not implementation plans; the skeleton hard gate exists for build readiness, which is a property of the `NN_*` phase docs (which validate in full). This exemption is the design, not a workaround.

---

## Step 2: Route to Adapter

The disk-backed adapters serve distinct planes — the plane doctrine and which-door table live in `../_shared/documentation-standard.md`:

- **`vault`** → the shared-docs vault (cross-project referential knowledge; INDEX-discovered)
- **`docs`** → the current repo's `documentation/` tree (work-in-flight + repo-coupled records; git/PR-discovered)
- **`artifacts`** → generated finished output in the current native session's private artifact area; the default

### Adapter: artifacts (default)

Use this adapter when no destination is specified or the caller selects `--to artifacts` (workflow `--output artifacts`). It stores selected finished output in the current session's private artifact area. It does not publish a global pointer or make artifacts broadly discoverable.

**Identity and allocation.** Obtain the current session ID and host from the qualified native runtime source. Never infer identity from cwd, time, an operation ID, a filename, or a guessed value. Resolve the loaded plugin root via `../_shared/claudna-root.md`, then call the existing CLI:

```bash
python3 -B "<claudna-root>/lib/claudna/session_store" scratch \
  --session "<verified-native-sid>" --host "<provider>" --label "publish-artifacts"
python3 -B "<claudna-root>/lib/claudna/session_store" paths \
  --session "<verified-native-sid>" --host "<provider>" --kind artifacts --create
```

Allocate scratch only when promotion or working files need it; reuse a caller's scratch with cleanup left to that owner. Use only the exact returned scratch and artifact paths. `scratch` allocates private temporary work; `paths --kind artifacts --create` resolves/creates the private durable area. A missing, conflicting, or unverified identity, or an ordinary permission failure, makes this route partial/unavailable: stop the artifact write and report the reason. Do not fall back to an OS temp path or claim the host is unsupported. A dry run does neither allocation nor writes. The `session` adapter remains chat-only and does not persist files.

**Input and validation.** Accept a single finished markdown file or a family with exactly one `00_*.md` master and one or more `NN_*.md` phases. Preserve Step 1 validation, including the master-doc presence-only exception, and the docs adapter's all-or-nothing family validation. Non-markdown assets may be included only when explicitly selected as finished output. Never copy the surrounding scratch tree, credentials, or unrelated private files.

If the selected input is already a canonical artifact, validate its exact known path before reading its content, whether it belongs to the current session or another session. Pass the current session/host, an explicit scope, the source session ID, and that absolute path to the existing CLI; the explicit-path form does not use `--workflow`:

```bash
python3 -B "<claudna-root>/lib/claudna/session_store" continuity artifact-path \
  --session "<current-sid>" --host "<provider>" --scope "<scope>" \
  --from-session "<source-sid>" --path "<absolute-source-path>" --json
```

Proceed only if the result validates that same path and ownership. A current-owner private/manual artifact is permitted. Another owner's artifact requires a public, bounded scope. Missing, private, denied, or unverifiable ownership is denied before content read. This validation is for the explicitly selected path; it does not require or mutate a global pointer. For a same-session source, use its exact canonical path and do not create a replacement merely to republish it. Apply the same gate to canonical inputs routed to vault, docs, GitHub, Notion, or any other adapter. Do not copy a canonical source into a new artifact location merely to export it; store only the current-owner private publication receipt described above.

**Promotion of scratch output.** Leave a selected source that is already canonical in place. For a new output, promote only the validated selected file/family and explicitly selected finished assets. Do not overwrite an existing canonical target: if it already contains identical bytes, report it as already canonical; if content differs, stop and surface the conflict. Stage within the private artifact directory on the same filesystem, retain ordinary private permissions (directories `0700`, files `0600`), hash each source, copy to staging, verify hashes, then atomically install into an absent canonical destination without replacement and verify final hashes. A concurrent destination collision is a conflict: retain staging and the existing canonical bytes. A pre-check followed by an overwriting rename is insufficient. Remove the exact allocated scratch only after all writer children have actually exited and verification succeeds. On failure or an uncertain writer, preserve scratch and report partial; never clean by glob or age.

**Canonical export receipts.** For an actual (non-dry-run) invocation of any adapter other than `session`, preserve each canonical source and send only the explicitly selected finished docs/assets through the selected adapter. Before reading, publishing, or exporting the canonical source, resolve the current session's private receipt destination with `paths --kind artifacts --create` using the verified current SID/host; if that identity or ordinary permission check fails, stop before destination mutation and report partial/unavailable. After an actual returned result, write a private receipt owned by the current session under that artifact area, recording each source path and content hash, destination, and actual returned result (URL/path/status). Use a unique receipt file with ordinary private permissions; do not create a shared ledger. If receipt storage fails after an external result, preserve the source and report that the result occurred but receipt persistence failed; do not claim the receipt exists. Do not write a receipt during dry-run, session/chat output, or for a result that did not occur. A genuine failed/uncertain destination may be recorded only with its actual failed/unknown status. The github-pr adapter formats a body only, so its returned result is formatting output unless the caller separately creates a PR and returns its URL.

Native host receipts and consumer acceptance remain pending before merge/release. This source contract is draft implementation, not native acceptance. Preserve that distinction in qualification receipts.

### Adapter: vault (explicit export)

This plane has two backends — a Claudron vault (engine) and a raw tree (fallback). Run the **detection ladder in `../_shared/claudron-engine.md` §1** first, then route:

**Engine path — verdict present-with-vault.** Route the finished doc through Claudron rather than writing files directly; map its frontmatter onto a capture call:

```bash
# provenance (flags-capable engine only — see below): source_url and source_type ride in the finding file
claudron capture --stdin --json < <finding-file>
```

Write the finding as JSON to `<finding-file>`, a file in `<scratch>` (`../_shared/orchestration-guide.md` §1), with the Write tool first (`type`, `title`, `body`, `tags`, `project`; `/claudna:capture` Step 4): the title and body never go on the command line. `project` comes from the doc's `repos:` / `--repo` (omit if unscoped). Validate the envelope (claudron-engine.md §2) and branch on `data.action`: `created` → report `data.path`; `suggest_update` / `suggest_supersede` → surface `data.reason` and the existing note to the caller (the engine's index-backed dedup replaces the raw adapter's file-compare); `rejected` (exit 1) → surface the validation errors. An engine failure *during* capture (exit 3 or an unrecognized envelope) degrades to the fallback path below, per claudron-engine.md §3 — say so. Do **not** run `/claudna:index` — the vault is engine-indexed (documentation-standard §10). Maturity is never set here; the engine stamps `draft`.

**Provenance (capability-probed).** If the doc's frontmatter carries `source_url` / `source_type` (SCHEMA optional fields), put them in the finding file as `source_url` / `source_type` — but **only on a flags-capable engine**: `data.engine_version` present and ≥ **0.4.0** (the Claudron C2 release that added the flags; the same version probe `/claudna:capture` Step 1 uses, and the same floor its PreCompact defer keys on). An older / absent / unreadable version omits them (it would reject the flags, exit 2). Provenance is **never** folded into the body here: that trailing `Source:` workaround was capture's alone, and the github-pr adapter's `Source:` footer is an unrelated surface.

**Fallback path — verdict present-no-vault or absent** (frozen behavior). Emit the standard degradation notice first (`../_shared/claudron-engine.md` §3.1 — quote the `/claudna:publish --to vault` row), then write the doc to the raw-tree directory for its `type:`:

| Type | Destination |
|------|-------------|
| plan | `shared/planning/active/` (or `completed/` for terminal statuses) |
| decision | `shared/decisions/` |
| knowledge | `shared/knowledge/<repo>/` (requires `repos:` field or `--repo` flag) |
| runbook | `shared/runbooks/` |
| audit, review | `shared/planning/active/` |

A memory-home type (`entity`, `concept`, `person`, `project`, `practice`) has no raw-tree destination: Claudron files homes itself (`memory-homes`), and this fallback is frozen. Stop and say the doc needs the engine; in `--auto`, the outcome is `blocked`, with installing Claudron as the unblock.

If the file already exists, compare and warn before overwriting (the raw adapter's dedup). After writing: (1) run `/claudna:index` on the destination to update INDEX.md; (2) report the path. In `--auto`, the fallback sets `artifacts.engine: "fallback"` and puts the §3.1 notice verbatim in `errors[]` (claudron-engine.md §3) — the degradation is never inferred from `artifacts.engine` alone.

**Plane-fit advisory** (either path): a `plan`/`audit`/`review` doc landing vault-ward gets a one-line note — "unusual plane for this type: generated planning normally stays in private session artifacts; a repository edition is an explicit docs export". Advisory only, never a block — fleet workflows legitimately share plans vault-side.

### Adapter: docs

Write the doc — or doc family — into the current repo's `documentation/` tree, the per-project plane. The author retains its canonical output in `<artifacts>` (`../_shared/orchestration-guide.md` §1) and hands it here; publish is the single **placement path for finished docs** on this plane (status-marker write-backs and archiving by `/claudna:build` are the documented exceptions).

- `--dir <path>` is **required** and must resolve under `documentation/`. Reject anything outside it. Create the directory if it doesn't exist (the Write tool creates parents automatically) — don't fail on missing directories.
- **Single-doc mode** (source is a file): validate per Step 1, write into `--dir`, report the path.
- **Family mode** (source is a directory): the source holds **exactly one** `00_*.md` master + `NN_*.md` phase docs (the shape forge and the audit lenses produce); any other `.md` file fails the family (zero or multiple `00_*` files likewise); only explicitly selected finished non-markdown assets (screenshots, assets) copy through; never copy the surrounding directory or private working material. Loop per doc: phase docs validate against the full Step 1 contract including the §4.1 skeleton hard gate; the master validates under the master-doc exception (Step 1b). Validation reads are bounded — frontmatter (first ~15 lines) plus a Grep for the required section headings decide every check; never pull a family's full prose into context (the orchestration guide's context-window rules apply to the publishing orchestrator too). Any doc failing validation fails the whole family — report every error, write nothing (no partial families). On success, write all docs into `--dir` preserving filenames; report the directory and doc count.
- **No INDEX step.** The docs plane is git/PR-discovered — never run `/claudna:index` here; INDEX.md is the vault plane's discovery layer.
- **Dedup:** if a target file already exists, compare (bounded — same read rules as validation) and warn before overwriting (same rule as the vault adapter).
- **Plane-fit advisory:** a `knowledge`/`runbook` doc landing here gets a one-line note — "unusual plane for this type: cross-project reference knowledge may belong in an explicitly selected vault edition". Advisory only, never a block.

### Adapter: github-issue

**Dedup first (mandatory).** A dedup that silently misses is exactly the failure it exists to
prevent, so this step is bounded on purpose and **states its bound in the output**. Run it
before creating, then apply the decision rules in `../_shared/output-guide.md` Section 4.5.

**1. Pick 2–3 deliberately different terms** from the doc's title, tags and cited files. GitHub
issue search is *lexical, not semantic* — it cannot match a duplicate whose filer chose different
words than you did. Rephrasing toward the symptom does not fix that, so vary the vocabulary
instead:

| Term | Draw it from | Why |
|---|---|---|
| **Component** | a file, function, script or module name in the doc | strongest — file and symbol names are the one vocabulary two filers reliably share |
| **Symptom** | what the reader observes going wrong | matches a duplicate filed from the outside in |
| **Synonym** | the same defect said another way | the coverage the other two miss |

**2. Run one query per term — separate commands, one term each.** Write each term to its own file in `<scratch>` with the Write tool first (`<component-file>`, `<symptom-file>`, `<synonym-file>`); a term never goes into the command itself.

```bash
gh issue list --repo <owner>/<repo> --search="$(cat <component-file>)" --state open --limit 20 --json number,title,url
gh issue list --repo <owner>/<repo> --search="$(cat <symptom-file>)"   --state open --limit 20 --json number,title,url
gh issue list --repo <owner>/<repo> --search="$(cat <synonym-file>)"   --state open --limit 20 --json number,title,url
```

**One term per query is the whole point of running three.** GitHub ANDs the words inside a
`--search` string, so `--search "dedup limit truncation"` is a *single* search for issues
containing all three words — it is not three searches, and it is **narrower than any one of
them alone**. Three terms in one query is the opposite of the coverage this step is asking for.

Run each command unpiped and read its output. A `gh` call piped into anything reports the
*pipe's* exit status, so a failed search becomes an empty result that passes every check below.

**3. Check each count against the limit** before drawing any conclusion from it. The count must
be **strictly below the `--limit` you passed**.

- **Count < limit** → complete for that term. Its hits are the whole open match set, and a zero
  is a real zero.
- **Count == limit** → **truncated.** What it returned is still real — a duplicate you can see is
  a duplicate, so act on it. What a truncated query cannot support is the **negative**: you
  cannot tell "no issue in this repo matches" from "none of the first 20 match". Reporting *no
  duplicate found* on the strength of a query that came back at the limit is a false negative,
  not a clean result. Narrow the term (a filename or a symbol rather than a common word) or
  raise `--limit`, re-run, and report both what you changed and the new count.

**4. State the bound with the result** — every query verbatim, its count, the limit it ran under,
and what was outside the search. "No duplicate found" is never the whole claim; "no *open* match
for *these terms*" is.

```
Dedup: 3 queries against OPEN issues in <owner>/<repo>, --limit 20 each.
  "<component>" → 2 hits (under limit)
  "<symptom>"   → 0 hits (under limit)
  "<synonym>"   → 7 hits (under limit)
  Verdict: no open issue matched. Closed issues were not searched.
```

Then apply §4.5 to whatever the searches returned:

- Exact match → prefer offering `--update` of the existing issue (§4.5); skip and report its URL only if the caller declines.
- Related but different → create and add `Related: #NNN` to the body.
- Same pattern, different location → prefer adding to an umbrella issue.

Then create the issue:

```bash
gh issue create \
  --repo <owner>/<repo> \
  --title "$(cat <title-file>)" \
  --body-file <body-file> \
  --label "$(cat <labels-file>)"
```

Write the title, the markdown body after the frontmatter, and the comma-separated labels to those three files, in `<scratch>`, with the Write tool first. Text in them never goes into the command itself.

Labels come from `tags:` — skills express severity/priority as tags (`priority:critical`, `security`, `auto-audit`, …); publish maps `tags` → `--label` and creates any missing labels. The `--repo` flag is required; if `repos:` is set in frontmatter with exactly one repo, infer from that.

After creating:
1. Add the issue URL to the source doc's `links:` frontmatter field only when the source is not a canonical artifact. For a canonical artifact, preserve it and record the URL in the current-owner private publication receipt.
2. Report the issue URL.

**In-place update (`--update <issue#|url>`).** When the caller names an existing issue — a re-forged plan body, an epic gaining its phase-issues table, a corrected audit — replace that issue's body instead of creating anything:

```bash
gh issue edit <number> --repo <owner>/<repo> --body-file <rendered-body-file>
```

Rules: dedup is skipped (the target is explicit); the title is never changed (`gh issue edit --body-file` only — retitling stays a manual act); labels are additive only (`--add-label` for new `tags:`, never removing existing ones); report the issue URL and note "updated in place". The exact-match dedup rule lives in `../_shared/output-guide.md` §4.5 and routes here: an exact match prefers an offered `--update` over a skip.

### Adapter: github-pr

Format the doc as a PR description body. Write the formatted text to a file in `<scratch>` with the Write tool, for the caller to pass as `gh pr create --body-file <file>`:

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

Render the doc's body (everything after the frontmatter) back into the chat session. Accept content directly in context; a source file is optional. Do not allocate scratch or artifacts for this adapter. **No file is written, no issue is created, no frontmatter is updated.** This is the "think with me" edition — the same manuscript every other adapter publishes, just printed instead of persisted. Optionally prepend a one-line header derived from `title:`/`type:`. There is no dedup for this adapter.

### Adapter: notion

Create a Notion page via the MCP Notion tool:

1. Map frontmatter to Notion properties:
   - `title:` → page title
   - `type:` → select property
   - `status:` → select property
   - `tags:` → multi-select property
   - `created:` → date property
2. Set page body to the markdown content after frontmatter.
3. After creating, add the Notion page URL to the source doc's `links:` frontmatter field only when the source is not a canonical artifact. For a canonical artifact, preserve it and record the URL in the current-owner private publication receipt.

Requires the Notion MCP server to be configured. If not available, report the error clearly.

## Step 3: Dry Run

When `--dry-run` is set, show exactly what would happen without doing it (including the result of Step 1 validation, the resolved adapter/plane — with any plane-fit advisory — and, in family mode, the per-doc validation verdicts). For `--to artifacts`, do not allocate scratch/artifact paths, copy, promote, write a receipt, or mutate a destination during dry-run:

```
Dry run: /claudna:publish doc.md --to github-issue --repo example-repo

House style: OK (type=audit, skeleton valid)
Would create GitHub issue:
  Repo: example-org/example-repo
  Title: Spotify API Rate Limits & Quirks
  Labels: api, spotify, rate-limits
  Dedup: 3 queries vs OPEN issues, --limit 20 each — "rate-limits" 2 hits,
         "429 backoff" 0 hits, "throttling" 5 hits; all under limit.
         No open match. Closed issues not searched.
  Body: [243 chars, first line: "Spotify enforces 30 req/sec per app..."]

No changes made.
```

## Rules

- **Never modify the doc body.** Only the documented frontmatter updates are allowed for noncanonical sources. Canonical artifacts remain immutable during publication; record returned links in the private receipt.
- **Validate before publishing.** Invalid frontmatter or a missing body skeleton = no publish.
- **One source of truth.** The markdown file is authoritative. Published outputs (issues, Notion pages) are copies — they may go stale.
- **Report what you did.** After every publish, output: destination, URL/path, and any frontmatter updates made.
- If an adapter fails (auth error, missing repo, MCP not configured), report the error verbatim. Don't fabricate success.

$ARGUMENTS
