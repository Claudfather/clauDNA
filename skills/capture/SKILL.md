---
name: capture
user-invocable: true
description: "Use to save knowledge to the shared fleet vault — a note you write, or external content worth keeping (an article URL, a file, a transcript). One write door: routes text / URL / file to `claudron capture`. For recalling what the vault already knows, use /claudna:recall; to search it by term, use /claudna:claudron lookup; to route a finished, frontmattered doc across planes, use /claudna:publish. Replaces /learn."
argument-hint: "<text | url | file> [--type t] [--title s] [--project p] [--tags a,b] [--full] [--auto]"
requires:
  - cli: claudron>=0.2
    reason: "Claudron CLI — `capture` writes the note to the vault with index-backed dedup; without it, capture falls back to the frozen raw-tree write + /claudna:index"
---

# Capture

The write door to the shared fleet vault. One domain, three input shapes — you save **what you wrote**, or ingest **something external** (a URL, a file). Everything terminates in `claudron capture`; the engine dedups, ranks, and stamps maturity. Mutating.

Second verb in the knowledge lifecycle: recall → work → **capture** (next session recalls what you captured).

## Arguments

Parse `$ARGUMENTS`:
- **First positional** — the thing to capture. Routed by shape (Step 1): a `http(s)://` URL, a `/`- or `./`-path, or inline text. If omitted, the content is whatever the request supplies (e.g. "capture this finding: …").
- `--type <t>` — vault note type: `knowledge`, `decision`, `runbook`, `plan`, `audit`, `review` (no `skill` — see Step 2).
- `--title <s>` — short, unique title.
- `--project <p>` — owning project (mutually exclusive with `--fleet <name>` for fleet-wide notes).
- `--tags <a,b>` — comma-separated discovery tags.
- `--full` — for URL/file input: capture verbatim instead of summarizing (still strips HTML chrome).
- `--auto` — non-interactive; emit the structured result. Never `--force`.

Never set or infer `maturity`/status — the engine stamps `draft`; promotion is Claudron curation, not this skill's job.

## Step 0: Gate on the vault verdict

Run the detection ladder (`skills/_shared/claudron-engine.md` §1) first. Route on the verdict:
- **present-with-vault** → continue (Step 1).
- **present-no-vault** / **absent** → the engine can't write. Take the **frozen raw-tree fallback** (bottom of this file) and say so — capture is an occasion-workflow with a fallback (claudron-engine.md §3), unlike the bare `/claudron` engine skill.

In `--auto`, a non-usable verdict still takes the fallback; only a fallback that *also* fails emits `outcome: "blocked"` — never a silent skip.

## Step 1: Route the input

Classify the first positional argument (or the supplied content):

| Shape | Mode | Action |
|---|---|---|
| starts `http://` / `https://` | **URL** | Fetch via `WebFetch`; extract the main content — strip nav, ads, sidebars, cookie banners; keep code blocks, tables, examples. |
| starts `/` or `./` | **file** | `Read` the file. |
| anything else | **text** | Use the inline text as-is. |

If a fetch fails (network, 404, auth wall), report the error verbatim and stop — never fabricate content.

**Provenance.** For URL/file input, the origin matters but `claudron capture` has no `--source-url` flag (and stdin keys it doesn't know are dropped). Fold provenance into the note instead: a first body line — `Source: <url-or-path> (captured <today>)` — and a tag (the domain, or `source:file`).

## Step 2: Boundary check

If the content is **skill-shaped** — an imperative how-to, a reusable procedure, a list of steps meant to be executed — it does not belong in the vault (the type enum excludes `skill` by design). Stop and point at `/claudna:skill-scaffold`. The vault holds knowledge / decisions / runbooks / plans / audits / reviews, not executable skills.

## Step 3: Shape the note

Decide the fields:
- **type** — from `--type`, else inferred (an article or transcript → `knowledge`; a decision record → `decision`; etc.). Required by the CLI.
- **title** — from `--title`, else derived from the content's own title/heading. Required.
- **body** — the processed content. Default is a tight summary (30–50% length, keep all technical substance, strip boilerplate); `--full` captures verbatim. Prepend the provenance line for URL/file input.
- **tags**, **project/fleet** — from flags or inferred from context.

## Step 4: Build the capture call

Prefer flags (verified against v0.2.0):

```bash
claudron capture --type <type> --title "<title>" --body "<body>" --tags "<a,b>" --project <project> --json
```

For a multi-paragraph body awkward to quote inline, write the fields to a scratch JSON file (`type`, `title`, `body`, `tags`, `owner`, `project`) and pipe it:

```bash
claudron capture --stdin --json < <scratch-note.json>
```

`--type` and `--title` are required (the CLI exits 2 without them). Do **not** pass `--force` here — dedup routing (Step 5) decides that.

## Step 5: Confirmation gate + envelope (contract §5)

Validate the envelope (claudron-engine.md §2), then branch on `data.action`:

- **`created`** → done. Report `data.path` (absolute).
- **`suggest_update`** (a *current* note already covers this) → present `data.reason` and the existing note (`data.path`, vault-relative). Ask: **"A current note already covers this — append to it, create a new note anyway, or cancel? (append/create/cancel)"**
  - *append* → `claudron capture --update <path> --body "<addendum>" --json` (→ `updated`).
  - *create* → re-run Step 4 with `--force` (→ `created`, `-N` slug suffix).
  - *cancel* → stop, nothing written.
- **`suggest_supersede`** (the near-dup is **stale**) → present `data.reason`. True supersession is Claudron curation, not v0.2.0 — offer the same three routes: **"A stale note is near this — append, create fresh, or cancel? (append/create/cancel)"**
- **`rejected`** (exit 1) → surface `data.reason` + the `errors[]` Findings verbatim. Validation failure, not transient — fix the inputs; do not loop.

**`--auto` (no prompts, never `--force`):**
- `created` → done.
- `suggest_update` → take the suggested route: `claudron capture --update <path> --body "<body>" --json`.
- `suggest_supersede` → do **not** write (force is forbidden; appending current knowledge to a stale note mislabels it). Record the suggestion in `errors[]`, set `outcome: "needs-input"` naming the stale path.
- `rejected` → `outcome: "blocked"`, `blocker_description` = the validation reason.

## Step 6: Report

Interactive — a boxed summary:

```
Vault capture
  Action:  created
  From:    <text | url | file>
  Path:    <path>
  Type:    <type>    Title: <title>
```

`--auto` — emit the single structured result (orchestration-guide.md "Structured Result Shape"): `artifacts.action` (`created`/`updated`), `artifacts.path`, `artifacts.engine: "claudron"`; any degradation or refusal in `errors[]`; `outcome` per Step 5.

## Fallback: no engine (frozen)

When the ladder returns **present-no-vault** / **absent**, write to the raw tree instead — **frozen** compatibility behavior (claudron-engine.md §4); no new capability lands here. Say so first: *"Claudron vault unavailable — wrote to the raw tree; run `/claudna:index`."* Then:

1. Resolve the docs root (documentation-standard §10: `CLAUDRON_VAULT` / `CLAUDRON_VAULT_PATH` / `SHARED_DOCS_PATH`, else the CLAUDE.md `## Shared Documentation` section). A `(claudron vault)`-annotated root is engine-managed — never write a raw tree into it; report the no-vault remedy (`claudron init <path> --personal`) instead.
2. Extract/format the content as a frontmattered doc (`title`, `type`, `status: current`, `owner`, `created`, provenance in the body, `tags`). Slug the title (lowercase, hyphenate, ≤40 chars on a word boundary, `-N` on collision).
3. Write to `<root>/knowledge/<project-or-topic>/<slug>.md`, creating the directory if needed.
4. Auto-run `/claudna:index` on the target directory to regenerate INDEX.md.
5. Report: `"Captured (raw tree): <title> -> <path>"`.

## Rules

- **One write door.** Deliberate notes and external ingestion both come through here — there is no separate ingest command. (To *read* the vault: `/claudna:recall`; to *search* it: `/claudna:claudron lookup`; to route a finished doc across planes: `/claudna:publish`.)
- **Never set maturity.** The engine stamps `draft`; promotion is curation.
- **Degrade loudly.** A raw-tree fallback is always announced — never silently swap the vault for the tree.
- **Don't fabricate.** A failed fetch stops the capture; it never invents content.

$ARGUMENTS
