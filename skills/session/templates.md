# Handoff File Format — `<cwd>/.claude/session.md`

Schema version: 2. Written by `/claudna:session` handoff and checkpoint modes, read by resume mode. Optimized for agent consumption. This file has a small **stable surface** for readers outside clauDNA — declared at the bottom.

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

## Stable surface

This file is read outside clauDNA, so two things are promised and the rest is not:

- **The file exists** at `<cwd>/.claude/session.md` after handoff or checkpoint, and a reader sees a complete file or none.
- **`last_updated:`** is an ISO-8601 UTC timestamp in the frontmatter — the freshness signal.

Everything else — section names, ordering, `schema_version`, every field below the frontmatter — is **informal and may change without notice**. Changing either promise is a breaking change and gets a CHANGELOG entry under a breaking heading.
