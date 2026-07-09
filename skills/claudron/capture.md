Invoked by /claudna:claudron in capture mode — the detection ladder (claudron-engine.md §1) has already run. `capture` needs present-with-vault (Step 0 gates). Do NOT skip the Step 4 confirmation gate.

# Capture

Deliberately save one note to the shared fleet vault via `claudron capture`. Mutating — it writes to the vault. Follow these steps in order.

## Step 0: Gate on the vault verdict

From the pre-flight detection ladder (claudron-engine.md §1):
- **present-with-vault** → continue.
- **present-no-vault** → stop. Report: "Claudron is installed but no vault is configured — run `claudron init <path> --personal`, then retry." There is no raw-tree fallback for `capture` (claudron-engine.md §3).
- **absent** → stop. Report: "Claudron is not installed — save to the vault with `/claudna:publish --to vault` instead, or install Claudron (SETUP_GUIDE)."

In `--auto`, either non-usable verdict emits the structured result with `outcome: "blocked"` and a `blocker_description` naming the remedy — never a silent skip.

## Step 1: Gather the note

Collect, from the request:
- **type** (required) — one of `knowledge`, `decision`, `runbook`, `plan`, `audit`, `review`. The vault type enum has no `skill` — see Step 2.
- **title** (required) — short and unique.
- **body** — the note content (markdown).
- **tags** — comma-separated.
- **project** — the owning project, if scoped (mutually exclusive with `--fleet`).

Never set or infer `maturity`/status — the engine stamps `draft`; promotion is Claudron curation, not this skill's job.

## Step 2: Boundary check

If the content is **skill-shaped** — an imperative how-to procedure, a reusable workflow, a list of steps meant to be executed — it does not belong in the vault (the type enum excludes `skill` by design). Stop and point at `/claudna:skill-scaffold`. The vault is for knowledge / decisions / runbooks / plans / audits / reviews, not executable skills.

## Step 3: Build the capture call

Prefer flags (all verified against v0.2.0):

```bash
claudron capture --type <type> --title "<title>" --body "<body>" --tags "<a,b>" --project <project> --json
```

For a multi-paragraph body that is awkward to quote inline, write the finding to a scratch JSON file (fields: `type`, `title`, `body`, `tags`, `owner`, `project`) and pass it via stdin instead:

```bash
claudron capture --stdin --json < <scratch-finding.json>
```

`--type` and `--title` are required (the CLI exits 2 without them). Do **not** pass `--force` here — dedup routing (Step 4) decides that.

## Step 4: Confirmation gate + envelope (contract §5)

Validate the envelope (claudron-engine.md §2), then branch on `data.action`:

- **`created`** → done. Report the path (`data.path`, absolute).
- **`suggest_update`** (a *current* note already covers this) → present `data.reason` and the existing note (`data.path`, vault-relative). Ask: **"A current note already covers this — append to it, create a new note anyway, or cancel? (append/create/cancel)"**
  - *append* → `claudron capture --update <path> --body "<addendum>" --json` (→ `updated`).
  - *create* → re-run Step 3 with `--force` added (→ `created`, with a `-N` slug suffix).
  - *cancel* → stop, nothing written.
- **`suggest_supersede`** (the near-dup is **stale**) → present `data.reason`. True supersession (marking the old note obsolete) is Claudron curation, not in v0.2.0 — so offer the same three routes: **"A stale note is near this — append to it, create a fresh note anyway, or cancel? (append/create/cancel)"**
- **`rejected`** (exit 1) → the capture was refused; surface `data.reason` and the `errors[]` Findings verbatim. This is a validation failure, not transient — fix the inputs and retry; do not loop.

**`--auto` (no prompts, never `--force`):**
- `created` → done.
- `suggest_update` → take the suggested route: `claudron capture --update <path> --body "<body>" --json`.
- `suggest_supersede` → do **not** write — force is forbidden, and appending current knowledge to a stale note would mislabel it. Record the suggestion in `errors[]`, set `outcome: "needs-input"` and `blocker_description` naming the stale near-dup path for a human to resolve.
- `rejected` → `outcome: "blocked"`, `blocker_description` = the validation reason.

## Step 5: Report

Interactive — a boxed summary:

```
Vault capture
  Action:  created
  Path:    <path>
  Type:    <type>    Title: <title>
```

`--auto` — emit the single structured result block (orchestration-guide.md "Structured Result Shape"): `artifacts.action` (`created` / `updated`), `artifacts.path`, `artifacts.engine: "claudron"`; any degradation or refusal in `errors[]`; `outcome` per Step 4.
