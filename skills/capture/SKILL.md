---
name: capture
user-invocable: true
description: "Use to save knowledge to the vault — a note you write, external content (an article URL, a file, a transcript), or the current session's learnings (bare `/claudna:capture` distills what happened after corrections, surprises, or fixes, before compaction). One write door. To read the vault use /claudna:recall; to search by term use /claudna:claudron lookup; to route a finished doc use /claudna:publish. Replaces /learn and /reflect."
argument-hint: "[<text | url | file>] [--type t] [--title s] [--project p | --fleet f] [--tags a,b] [--full] [--auto]"
requires:
  - cli: claudron>=0.2
    reason: "Claudron CLI — `capture` writes the note to the vault with index-backed dedup; without it, capture falls back to the frozen raw-tree write + /claudna:index"
---

# Capture

The write door to the vault. One domain, four input shapes — you save **what you wrote**, ingest **something external** (a URL, a file), or, on a **bare invocation**, distill **the current session's learnings**. Everything terminates in `claudron capture`; the engine dedups, ranks, and stamps maturity. Mutating.

Second verb in the knowledge lifecycle: recall → work → **capture** (next session recalls what you captured).

## Arguments

Parse `$ARGUMENTS`:
- **First positional** — the thing to capture. Routed by shape (Step 1): a `http(s)://` URL, a `/`- or `./`-path, or inline text. **Omitted, with no content in the same turn → session mode** (Step 1a): distill the current session. Omitted but content supplied *in that turn* ("capture this finding: …") → route that content by shape. Material from earlier in the session is session context, not the thing to capture.
- `--type <t>` — vault note type: `knowledge`, `decision`, `runbook`, `plan`, `audit`, `review` (no `skill` — see Step 2).
- `--title <s>` — short, unique title.
- `--project <p>` / `--fleet <f>` — **manual overrides** on the scope Step 3 infers (mutually exclusive).
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
| nothing to capture — no positional, no content this turn | **session** | Distill the live session — **Step 1a**. |
| starts `http://` / `https://` | **URL** | Fetch via `WebFetch`; extract the main content — strip nav, ads, sidebars, cookie banners; keep code blocks, tables, examples. |
| starts `/` or `./` **and names an existing file** | **file** | `Read` the file. |
| anything else | **text** | Use it as-is — including a `/`-leading string that isn't a file (`/api/v2/users returns 500`), a bare domain, a `file://` URL, or a Windows path. Only an explicit `http(s)://` scheme triggers a fetch. |

If a URL fetch or a real file `Read` fails (network, 404, auth wall, missing file), report the error verbatim and stop — never fabricate content.

**Provenance (capability-probed — F7).** For URL/file input the origin matters; how it is recorded depends on the engine Step 0 detected, read from `data.engine_version`:

- **Flags-capable engine** — `engine_version` present and **≥ 0.4.0** (the Claudron C2 release that added `--source-url` / `--source-type`) → carry provenance in **frontmatter**: pass `--source-url <url-or-path>` and `--source-type <url|file>` (URL input → `url`, file input → `file`) on the Step 4 call, plus a discovery tag (the domain, or `source:file`). Do **not** add a `Source:` body line.
- **Older / absent / unreadable version** — including a between-tags git build reporting a dev version below 0.4.0 → **keep the fold**: record provenance as a **trailing** body line — `Source: <url-or-path> (captured <today>)` — plus the tag. Keep it **last**, never first.

The guard is the version probe, never an install pin (claudron-engine.md §1): a git-installed engine between tags degrades to the fold rather than erroring on a flag it doesn't have. Why the body line must stay last, and why frontmatter is preferred once available: Claudron derives a note's one-line recall summary from the first non-heading body line (`session.py` `_summary`), so a leading `Source:` line hijacks every recall summary — and folding provenance into the body at all couples this skill to how that summary is picked (Claudron `docs/CLI_CONTRACT.md` §capture: *provenance rides in frontmatter, not in the body*). **0.4.0 is unreleased at this writing** — the C2 flags and the PreCompact shim removal ship in the same next Claudron release; verify this floor when that release cuts (it must match the release that actually adds the flags). The identical constant gates `plugin-hooks/precompact-reflect.sh`'s capture-prompt defer.

## Step 1a: Session mode — distill what happened

Reached from Step 1's session row. Scan the live session and pull concrete, durable learnings before compaction loses them — a quick snapshot, not a retrospective. If context is already near-full, hit the high points rather than skip.

Extract against this rubric; every field concrete and specific, never a platitude:

| Field | Rule |
|---|---|
| **Context** | One line — the task or situation this came out of. |
| **Worked** | A specific tool/approach + why it saved time. Concrete example required. |
| **Failed** | What broke, the root cause, what was tried first. Concrete example required. |
| **Would change** | The specific alternative for next time. |
| **Reusable** | Only if genuinely generalizable — leave blank rather than force it. |

**Quality gate** — drop any field that is **vague** ("tests are important" → make it specific or cut it), **obvious** ("read the docs first" — keep only if the session proved a non-obvious nuance), or **duplicative** (already in a convention or a prior note). If nothing survives the gate, say so and **write nothing** — a forced reflection is worse than none.

What survives becomes the note body (Step 3); type is `knowledge`. Scope defaults to the current **project** (Step 3) — session work is about the repo you are in — unless a learning is plainly fleet-wide process or general/reusable.

## Step 2: Boundary check

If the content is **skill-shaped** — an imperative how-to, a reusable procedure, a list of steps meant to be executed — it does not belong in the vault (the type enum excludes `skill` by design). Stop and point at `/claudna:skill-scaffold`. The vault holds knowledge / decisions / runbooks / plans / audits / reviews, not executable skills.

## Step 3: Shape the note

Decide the fields:
- **type** — from `--type`, else inferred (an article or transcript → `knowledge`; a decision record → `decision`; session distillation → `knowledge`). Required by the CLI.
- **title** — from `--title`, else derived from the content's own title/heading (session mode: a short topic, e.g. `Session — <what you worked on>`). Required.
- **body** — the processed content. Default is a tight summary (30–50% length, keep all technical substance, strip boilerplate); `--full` captures verbatim. Provenance for URL/file input follows the Step 1 branch: on a flags-capable engine it rides frontmatter (`--source-url` / `--source-type`, Step 4), **not** the body; on an older engine, **append** the `Source:` line at the end (never first — the first body line becomes the recall summary).
- **wikilinks** — if the note relates to one already in the vault (Step 5's dedup surfaces near-matches, or you know its title), link it in the body as `[[Exact Title]]`. This is the vault's authoring convention — **relate** notes, don't duplicate them; capture just writes the `[[Title]]` into the body (Claudron resolves those references on demand, read-side — not at write time).
- **tags** — from flags or inferred from context.
- **project / fleet — scope by what the note is *about*, and state the call.** Claudron files by location — there is no `scope:` field; the tier follows the flag you pass, or none. Read the scope from the content, then **say which you chose and why** (`Scoped to project clauDNA — a gotcha in this repo`); the flags are manual overrides on that inference. When genuinely ambiguous, state your reasoning and pick — but **reusable / general knowledge wins `_shared/` even when it is also repo-flavored** (filing it in a project tier hides it from cross-repo recall); reserve the narrower tier for notes that are genuinely repo- or fleet-bound. The three tiers:
  - **General / foreign / cross-project** (an article, a reusable pattern, a foreign repo) → **unscoped → `_shared/`**. The default — leave both flags off.
  - **Specifically about this repo** (session learnings, a decision or gotcha about this codebase) → `--project <cwd-git-root-name>`. Pass it **explicitly** — capture, unlike recall, won't infer it from cwd — so a bare `/claudna:recall` later surfaces it in the project tier.
  - **A fleet-wide workflow or process** (how the fleet's tools interoperate, a protocol spanning repos) → `--fleet <name>`, when the ambient vault registers that fleet — read the names from `data.fleets` in the Step 0 status envelope (re-run `claudron status --json` if you didn't retain it; claudron-engine.md §2 owns the shape). A Claudlobby-provisioned bot vault carries them. No fleet registered → it falls to `_shared/`; never invent a `--fleet` name.

## Step 4: Build the capture call

Prefer flags (base capture flags verified against v0.2.0):

```bash
# repo-scoped (incl. session mode): --project <name>; fleet-wide: --fleet <name>; general: omit both
# provenance (URL/file input, flags-capable engine — Step 1): add --source-url <url-or-path> --source-type <url|file>
claudron capture --type <type> --title "<title>" --body "<body>" --tags "<a,b>" --project <project> --json
```

For a multi-paragraph body awkward to quote inline (session distillations usually are), write the fields to a scratch JSON file (`type`, `title`, `body`, `tags`, `owner`, `project` or `fleet`, and — flags-capable engine only — `source_url` / `source_type`) and pipe it:

```bash
claudron capture --stdin --json < <scratch-note.json>
```

`--type` and `--title` are required (the CLI exits 2 without them). `--source-type` (and the `source_type` stdin key) accept only `url|file|inline` — the SCHEMA vocabulary; capture emits `url`/`file`. An engine without the flags rejects them (exit 2), which is why Step 1 gates provenance on the version probe. Do **not** pass `--force` here — dedup routing (Step 5) decides that.

## Step 5: Confirmation gate + envelope (contract §5)

Validate the envelope (claudron-engine.md §2), then branch on `data.action`:

- **`created`** → done. Report `data.path` (absolute).
- **`suggest_update`** (a *current* note already covers this) → present `data.reason` and the existing note (`data.path`, vault-relative). Ask: **"A current note already covers this — append to it, create a new note anyway, or cancel? (append/create/cancel)"**
  - *append* → `claudron capture --update <path> --body "<addendum>" --json` (→ `updated`).
  - *create* → re-run Step 4 with `--force` (→ `created`, `-N` slug suffix).
  - *cancel* → stop, nothing written.
- **`suggest_supersede`** (the near-dup is **stale**) → present `data.reason` (the CLI emits this action when the matched note's status is `stale`). Automatic supersession — marking the old note superseded for you — is Claudron curation, not this skill's job; offer the same three routes: **"A stale note is near this — append, create fresh, or cancel? (append/create/cancel)"**
- **`rejected`** (exit 1) → surface `data.reason` + the `errors[]` Findings verbatim. Validation failure, not transient — fix the inputs; do not loop.
- **Anything else — terminal, whatever the exit code.** An `action` value this step doesn't list, an absent `action`, or a partial/unrecognized envelope (§2) → **STOP.** Surface the raw envelope and stderr **verbatim** and report engine failure (claudron-engine.md §3). Never improvise success, report a path you didn't get from a recognized envelope, or retry. Do **not** take the raw-tree fallback from this gate — the call reached the engine, so the vault state is unknown and a second write risks a silent duplicate. The loud-fail rule applies **at this decision point**, not just in the engine contract: an envelope the skill doesn't recognize has no success branch.

**`--auto` (no prompts, never `--force`):**
- `created` → done.
- `suggest_update` → take the suggested route: `claudron capture --update <path> --body "<body>" --json`.
- `suggest_supersede` → do **not** write (force is forbidden; appending current knowledge to a stale note mislabels it). Record the suggestion in `errors[]`, set `outcome: "needs-input"` naming the stale path.
- `rejected` → `outcome: "blocked"`, `blocker_description` = the validation reason.
- anything else (unlisted/absent `action`, partial/unrecognized envelope) → `outcome: "blocked"`, `blocker_description` = the engine failure, the raw envelope + stderr verbatim in `errors[]`. No `artifacts.action`/`artifacts.path` from an unrecognized envelope, and no raw-tree fallback (vault state unknown) — a loud blocked result, never an improvised success.

## Step 6: Report

Interactive — a boxed summary:

```
Vault capture
  Action:  created
  From:    <text | url | file | session>
  Scope:   <_shared | project:<name> | fleet:<name>>  (<why>)
  Path:    <path>
  Type:    <type>    Title: <title>
```

`--auto` — emit the single structured result (orchestration-guide.md "Structured Result Shape"): `artifacts.action` (`created`/`updated`), `artifacts.path`, `artifacts.engine: "claudron"`; any degradation or refusal in `errors[]`; `outcome` per Step 5.

## Fallback: no engine (frozen)

When the ladder returns **present-no-vault** / **absent**, write to the raw tree instead — **frozen** compatibility behavior (claudron-engine.md §4); no new capability lands here. Say so first: *"Claudron vault unavailable — wrote to the raw tree; run `/claudna:index`."* Then:

1. Resolve the docs root per documentation-standard §10 ("locating the root" — env override, else the CLAUDE.md `## Shared Documentation` section). If §10's annotation semantics mark the root engine-managed, there is no raw tree to write — do not write into it; surface §10's engine-managed-root message and stop.
2. Extract/format the content as a frontmattered doc (`title`, `type`, `status: current`, `owner`, `created`, provenance in the body, `tags`). **For session mode, first run Step 1a** (the rubric + quality gate) to derive the fields — `type: knowledge`, the surviving fields as the body; **if nothing survives the gate, write nothing, even here**. Slug the title (lowercase, hyphenate, ≤40 chars on a word boundary, `-N` on collision).
3. Write to `<root>/knowledge/<project-or-topic>/<slug>.md`, creating the directory if needed.
4. Auto-run `/claudna:index` on the target directory to regenerate INDEX.md.
5. Report: `"Captured (raw tree): <title> -> <path>"`.

## Rules

- **One write door.** Deliberate notes, external ingestion, and session distillation all come through here — there is no separate ingest or reflect command. (To *read* the vault: `/claudna:recall`; to *search* it: `/claudna:claudron lookup`; to route a finished doc across planes: `/claudna:publish`.)
- **Read scope from content; state it.** Never force scope from cwd; announce the tier you chose and why (Step 3 owns the tier map).
- **Never set maturity.** The engine stamps `draft`; promotion is curation.
- **Degrade loudly.** A raw-tree fallback is always announced — never silently swap the vault for the tree.
- **Don't fabricate.** A failed fetch stops the capture; a session with nothing worth keeping writes nothing.

$ARGUMENTS
