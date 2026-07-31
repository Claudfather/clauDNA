---
name: recall
user-invocable: true
description: "Use before starting substantive work in a repo — surfaces what the fleet and this project already know (prior decisions, patterns, conventions) so you don't rework solved problems. Orientation briefing over `claudron recall`; falls back to scanning INDEX.md when Claudron is absent. First verb in the knowledge loop. To search the vault by term, use /claudna:claudron lookup; to save new knowledge, use /claudna:capture. Replaces /remember."
argument-hint: "[query terms] [--project <name>] [--limit <n>] [--full] [--include-stale]"
requires:
  - cli: claudron>=0.2
    reason: "Claudron CLI — `recall` assembles the briefing (conventions + project/fleet tiers); without it, recall falls back to the frozen INDEX.md scan"
---

# Recall

Orientation briefing: surface what the fleet and this project already know before you start, so prior decisions and patterns inform the work instead of being rediscovered. Engine-preferred — renders `claudron recall`. Read-only.

First verb in the knowledge lifecycle: **recall → work → capture** (next session recalls what you captured).

## Arguments

Parse `$ARGUMENTS`:
- **Positional (query terms):** relevance terms for the fleet tier. Omit for a bare recall that leads with this project's most-recent notes.
- `--project <name>` — override the project scope (default: `claudron` derives it from the cwd git root).
- `--limit <n>` — notes **per tier** (default 5 → up to 5 project + 5 fleet).
- `--full` — read and show the body of the top match in each tier, not just its one-line summary.
- `--include-stale` — include terminal-status notes (`stale` / `superseded` / `completed` / `archived`) that Step 2 otherwise filters out. Applies on **both** the engine path and the fallback.

## Step 0: Detection ladder

Run the detection ladder (`skills/_shared/claudron-engine.md` §1) before anything else. Route on the verdict:
- **present-with-vault** → the engine path (Step 1).
- **present-no-vault** / **absent** → the frozen INDEX.md-scan fallback (below). Degrade loudly — say which path you took and why.

## Step 1: Recall from the engine

Build the relevance query: join the positional terms into `--query "<terms>"`. With no terms, omit `--query` — `claudron recall` then leads with project membership (recency) and uses the project name as the implicit relevance term (index-only, no full-text scan).

```bash
claudron recall [--query "<terms>"] [--project <name>] --limit <n> --json   # <n> from --limit, default 5
```

`--limit` is **per tier**. Validate the envelope (claudron-engine.md §2): assert `data` carries `project`, `query`, `conventions`, and `notes` (a list). On exit 3 or an unrecognized envelope, degrade to the fallback and say so (claudron-engine.md §3).

## Step 2: Render the orientation briefing

Two parts, in this order:

### Vault conventions (never capped)

If `data.conventions` is non-null, render it under a `## Vault conventions` heading — verbatim and uncapped. These are the fleet's standing operating rules; surfacing all of them is the point. (Drop only a leading `# ` H1, since you supply the heading.)

### Recalled notes — two tiers, adaptive lead

`data.notes` is one flat list carrying both tiers. Split it by each entry's `tier` (equivalently, by `score`):
- **Project tier** — `tier` begins `project:` (`score` is `null`). *Membership*, most-recently-updated first — what THIS project knows.
- **Fleet tier** — integer `score` (`tier` `fleet`/`shared`). *Relevance*-ranked against the query — what the FLEET knows.

**Lead adaptively:**
- **A query was given** → lead with the **Fleet** tier (you asked about a topic — relevance first), then Project.
- **Bare recall** → lead with the **Project** tier (recency — what's fresh here), then Fleet.

**Filter terminal-status notes** (parity with the fallback, which already excludes them at Step 3): the engine's project tier returns notes regardless of `status`, so drop any whose `status` is `stale` / `superseded` / `completed` / `archived` before rendering — a superseded decision shown as current is exactly what an orientation briefing must not do. `--include-stale` keeps them; `ratified` / `current` are live constraints and are always kept.

Render each note as one line:
```
- **<title>** (<type>[, <maturity>]) — <summary> `<path>`
```
Omit `, <maturity>` when it is empty. Label each tier so the source is unambiguous:
```
### This project — most recent
### Fleet — most relevant to "<query>"
```
Skip a tier's header entirely when its split is empty — never print a heading with nothing under it. On a **bare** recall (no query), title the fleet header `### Fleet — related to <project>` rather than interpolating an empty `"<query>"`.

With `--full`, additionally read and summarize the top note in each tier from its `path` (vault-relative per §2 — resolve it against the vault `root` already in the Step 0 pre-flight envelope; no fresh `claudron status` call). If `data.notes` is empty, say **"No prior notes recalled"** (conventions may still have shown). Never fabricate notes.

## Harness memory — re-read on both paths

Runs regardless of which retrieval path ran — the harness's per-project auto-memory is a **separate substrate** from the vault. The harness injects this project's `MEMORY.md` **once** at session start, a frozen snapshot: it can miss a topic that only turns relevant later, and it never re-fires if memory changes mid-session (a sibling session, or `/claudna:capture`'s fallback, can write to it while yours is open). So re-read it live on every recall.

1. **Locate it** — resolve, never reconstruct. The directory is the `autoMemoryDirectory` setting, which redirects freely (Claudlobby points every fleet bot at its own `memory/` dir, outside `~/.claude/` entirely); the cwd-derived `~/.claude/projects/<cwd-slug>/memory` is only the default when nothing sets it. Run a bare command, no pipe:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_memory_dir.py"
   ```

   (falls back to the highest-versioned `~/.claude/plugins/cache/Claudfather/claudna/*/scripts/resolve_memory_dir.py` when `${CLAUDE_PLUGIN_ROOT}` is unset). It prints the resolved directory; **exit 1 means no readable `MEMORY.md`** → skip silently (not every project has harness memory). Read `MEMORY.md` and any linked topic files from the directory it printed — do not rebuild that path yourself.
2. **Read the index:** `MEMORY.md` is a flat list of `- [Title](file.md) — hook` lines. Score each against the query terms (title + hook); on a bare recall, take the most-recently-updated few. Cap by `--limit`, like a tier.
3. **With `--full`,** read the linked `memory/<file.md>` body for the top match and summarize it.
4. **Render** under its own header — additive to the vault tiers, never a duplicate:
   ```
   ### This project — harness memory
   - **<Title>** — <hook> `memory/<file.md>`
   ```
   Skip the header when nothing scores. Read-only, like the rest of recall.

## Step 3: Orient

Close with a one-line orientation, not just a dump: point at the single most relevant note or harness-memory entry for the task, and flag any note whose `type` is `plan` with a non-terminal `status` — an in-flight plan the work might collide with. If nothing is relevant, say so plainly.

## Fallback: no engine (frozen)

When the ladder returns **present-no-vault** or **absent**, Claudron can't assemble the briefing. Fall back to the **frozen** INDEX.md scan — no new capability lands here (claudron-engine.md §4); it exists so recall still works on a raw tree. Say so first: *"Claudron vault unavailable — scanning the raw tree's INDEX.md instead."* Then:

1. **Resolve the docs root** per documentation-standard §10 ("locating the root" — env override, else the CLAUDE.md `## Shared Documentation` section). If §10's annotation semantics mark the root engine-managed (a `(claudron vault)` annotation, or an env-derived `CLAUDRON_VAULT_PATH` root), it carries no INDEX.md — do not scan it; degrade with §10's engine-managed-root message. No root resolves → say so and point at `/claudna:init-project` (its shared-docs seam step provisions the section).

2. **Scan INDEX.md only** (never walk directories) under the root:

   | Path | Why |
   |---|---|
   | `<root>/planning/active/INDEX.md` | Active plans that may affect the task |
   | `<root>/knowledge/<repo>/INDEX.md` | Repo-specific learnings (if `--project` set or inferrable) |
   | `<root>/knowledge/INDEX.md` | Top-level knowledge index |
   | `<root>/decisions/INDEX.md` | Ratified decisions that constrain the work |

3. **Filter for relevance:** title / tag / repo match against the query; include only `active` / `current` / `ratified` / `draft` (exclude `stale` / `superseded` / `completed` / `archived` unless `--include-stale`). Rank: exact repo match > tag overlap > title keyword.

4. **Present** the top 3–5 (hard cap 5): title + one-line description (or bodies with `--full`). Flag active plans touching the task's repo. If INDEX.md is missing or empty on a raw tree, note it and suggest `/claudna:index` — never against a `(claudron vault)` root.

Then re-read the **Harness memory** section above (it runs on both paths) before orienting.

## Rules

- **Read-only.** Recall never writes. (To save: `/claudna:capture`. To search by term: `/claudna:claudron lookup`.)
- **Never fabricate.** No relevant notes → say so.
- **Degrade loudly.** A fallback taken is always visible — never silently swap the engine for the INDEX scan.
- **Conventions are uncapped; notes are tier-limited** (5 per tier via `--limit`). On the fallback, the 5-doc cap holds.

$ARGUMENTS
