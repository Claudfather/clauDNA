# Handoff File Format — `<cwd>/.claude/session.md`

Schema version: 2. Written by `/claudna:session` handoff and checkpoint modes, read by resume mode. Optimized for agent consumption.

## Stable surface

This file is consumed **outside clauDNA** — Claudlobby age-gates bot resume on it
and parses `last_updated:` — so a minimal subset is a declared promise rather
than an implementation detail. Two things, and only two:

| Guarantee | Detail |
|---|---|
| **The file exists** at `<cwd>/.claude/session.md` after a handoff or checkpoint | Written atomically (`.tmp` then `mv`), so a reader sees a complete file or none |
| **`last_updated:`** is present in the frontmatter, an **ISO-8601 UTC** timestamp | The freshness signal external consumers gate on |

**Everything else here is informal** and may change without notice: section
names, ordering, `schema_version`, and every field below the frontmatter. An
external consumer that parses those is reading an implementation detail and
will break.

Changing either guarantee is a breaking change: it gets a CHANGELOG entry, and
the consumers named above are told before it ships. Consumers needing more than
this subset should open an issue rather than widening their parser.

```markdown
---
cwd: <absolute path to current working directory>
last_updated: <ISO-8601 UTC, e.g. 2026-05-15T14:30:00Z>
schema_version: 2
---

## State
branch: <current branch>
working_tree: <clean | dirty: N modified, N untracked, N staged>
stashes: <count>
open_prs:
  - "#N <title> (<state>)"
in_flight_branches:
  - <branch-name>

## Activity
- <ISO-8601 UTC> — <one-line summary, prefix with short hash if from a commit>

## Decisions
- <ISO-8601 UTC> — <decision and rationale>

## Open Questions
- <ISO-8601 UTC> — <blocker, unknown, pending input>

## Next Steps
- <ISO-8601 UTC> — <what the next session should start with>
```

## Format rules

- Every bullet under Activity / Decisions / Open Questions / Next Steps starts with an ISO-8601 UTC timestamp followed by ` — ` (em-dash with spaces). The reaper parses on this format.
- `State` is regenerated on handoff/resume writes — never merged with prior content. Checkpoint refreshes `branch`/`working_tree` only and preserves the remaining State fields.
- Empty sections may be omitted.
- A bullet may carry a `(stale-flagged YYYY-MM-DD)` suffix added by the reaper. On the next pass, if the soft-drop conditions still hold, the bullet is dropped.
- A bullet may carry a `[pin]` suffix added by the user to opt out of soft drops.
- Maximum 10 bullets per section. If a section grows past 10, the reaper drops oldest-first regardless of TTL.

## Migration from schema_version: 1

Legacy files at `~/.claude/notes/projects/<slug>/context-resume.md` use schema_version: 1 (no per-item timestamps; bullets in plain `- text` form; frontmatter with `session_date` only).

When resume mode imports a v1 file, it assigns the file's `session_date` as the timestamp for every imported item, then runs the reaper. Most v1 items will hard-drop on first reap because they exceed TTL (Activity > 7d, etc.) — which is the correct behavior.
