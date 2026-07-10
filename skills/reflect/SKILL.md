---
name: reflect
user-invocable: true
description: "Use when a session produced process learnings worth keeping — after corrections, surprises, or hard-won fixes — and before compacting a long session. Distills session experience into shared knowledge. For ingesting external content, use /claudna:capture."
argument-hint: "[--target local|shared] [--notes file]"
---

# Reflect

You are extracting durable process knowledge from a live session. This is a quick, structured snapshot — not a thesis. Pull concrete learnings, write them down, and get out. The session context you have right now is perishable; after `/compact` it is gone.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--target local|shared` — Override the default target decision (default: shared)
- `--notes <file>` — Path to accumulated session notes to synthesize alongside session context

---

## When to Run

Run `/claudna:reflect` BEFORE `/compact`. The context-management protocol sequence is:

```
complete task -> /claudna:reflect -> /compact
```

| Context Level | Action |
|---------------|--------|
| Below 50% | Mandatory — full extraction |
| 50-60% | Best-effort — hit the high points |
| Above 60% | Skip — not enough room to do it well |

**Time budget:** Must complete in under 30 seconds. This is a quick extraction, not a retrospective.

---

## Phase 1: Session Scan

Scan the current session context for:

- **What tools or approaches worked** and why they were effective
- **What failed** — the root cause and what was tried before finding the fix
- **What was repeated unnecessarily** — wasted cycles that a note could prevent next time
- **What took multiple attempts to get right** — the final approach vs. the initial attempts

Focus on concrete, specific observations. "The API was tricky" is not useful. "The Spotify API returns 429 after 30 requests/minute; batching in groups of 25 with 2s delay worked" is useful.

---

## Phase 2: Structured Extraction

Apply this template strictly. Every field must be concrete and specific, not platitudes.

| Field | Rule |
|-------|------|
| **Context** | One line — what task or situation triggered this reflection |
| **Worked** | Specific tool/approach + why it saved time. Concrete example required. |
| **Failed** | What broke, root cause, what was tried. Concrete example required. |
| **Would Change** | Specific alternative for next time |
| **Reusable** | Only if genuinely generalizable. Leave blank rather than force it. |

If a field has nothing meaningful, write "Nothing notable" — do not invent filler.

### Quality Gate

Before proceeding, check each field against these red flags:
- **Vague:** "Tests are important" — rewrite with specifics or mark "Nothing notable"
- **Obvious:** "Read the docs first" — only include if the session proved a non-obvious nuance
- **Duplicative:** Already captured in a protocol or guardrail — skip it

---

## Phase 3: Target Decision

Determine where this reflection belongs using the boundary heuristic:

| Signal | Target | Example |
|--------|--------|---------|
| "This user prefers X" | `memory/` (per-bot) | User likes terse commit messages |
| "The Spotify API rate-limits at Y" | `shared/knowledge/` (fleet-wide domain fact) | API quirk any bot hitting Spotify needs |
| "Running tests before commit saves rework" | `shared/knowledge/` (process learning) | But only if not already captured in a protocol or guardrail |
| Bot-specific workflow preference | `memory/` (per-bot) | "I find it faster to X before Y" |

**Default:** shared. Most learnings benefit the fleet, not just one bot.

The `--target` flag overrides the heuristic.

---

## Phase 4: Dedup & Write

### Step 1: Filename Convention

`reflect-<bot-name>-YYYY-MM-DD.md`

Date-stamped to avoid collision across sessions. If a file with that name already exists (second reflect in the same day), **append to the existing file** rather than creating a new one. Add a horizontal rule (`---`) separator before the new entry.

### Step 2: Frontmatter

```yaml
---
title: Session Reflection — <brief topic>
type: knowledge
status: current
owner: {{BOT_NAME}}
created: <today YYYY-MM-DD>
tags: [process, retrospective]
---
```

### Step 3: Write

Write the file to the determined target location:
- **Shared target:** `shared/knowledge/reflections/reflect-<bot>-YYYY-MM-DD.md`
- **Local target:** `memory/reflect-<bot>-YYYY-MM-DD.md`

Create the target directory if it does not exist.

### Step 4: Update Index

Auto-run `/claudna:index` on the target directory to update INDEX.md.

### Step 5: Report

Report the result: `"Reflected: <title> -> <path>"`

---

## Phase 5: Context Protocol Integration

After writing, proceed to `/compact` as the context-management protocol dictates.

`/claudna:reflect` is a pre-compact step, not a standalone activity. The full sequence:

```
complete task -> /claudna:reflect -> /compact
```

Do not wait for human confirmation between `/claudna:reflect` and `/compact` — the point is to capture context before it evaporates.

---

## Flags Reference

| Flag | Purpose |
|------|---------|
| `--target local\|shared` | Override target decision (default: shared) |
| `--notes <file>` | Path to accumulated session notes to synthesize |

---

## Notes

- This skill is one verb in the knowledge lifecycle: `/claudna:capture` (ingest) -> work -> `/claudna:reflect` (synthesize) -> `/claudna:index` (organize) -> next session reads indexed knowledge.
- Speed over completeness. A quick, concrete reflection captured before `/compact` is worth more than a thorough retrospective written from faded memory.
- The structured template exists to prevent platitudes. If you catch yourself writing generic advice ("always test first"), either make it specific ("the `auth_callback` endpoint needs integration tests because mocking the OAuth flow hides redirect bugs") or skip the field.
- Same-day appending prevents file explosion during active sprint days where a bot may reflect multiple times.
