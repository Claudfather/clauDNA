# Handoff content format — native session-owned continuity

Schema version: 2. The durable file belongs to the verified native session at `R/sessions/<native-sid>/handoff.md`. `handoff-write` accepts complete content on stdin; the runtime validates the v2 schema, absolute cwd, UTC timestamp, and 1 MiB bound, then persists atomically. The current artifact path is separate from source-session identity. This is the source contract; native-host and downstream consumer acceptance remain pending.

```markdown
---
cwd: <absolute path to the session working directory>
last_updated: <ISO-8601 UTC, e.g. 2026-11-11T14:30:00Z>
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

Legacy project and personal files may use schema_version: 1 (no per-item timestamps; plain bullets; frontmatter with `session_date`). Import only an explicitly selected project file, or the exact authorized slug-based personal path. Preserve the source unchanged. Bind selected source bytes with their SHA-256 and verify the hash before mutation. Assign `session_date` as the timestamp for every imported item in the v2 copy, then reap that copy in memory. An immutable receipt records the source fingerprint and makes repeated imports idempotent across targets; changed content requires explicit `reimport`. A missing/corrupt receipt or stale pointer stops resolution without fallback.

## Stable surface

The source contract declares only these guarantees; broader compatibility remains unaccepted by downstream readers:

- On successful handoff/checkpoint persistence, the runtime returns an absolute `handoff_path` owned by the verified native session SID, with durable filename `handoff.md`. This path is not the source SID for a resumed predecessor.
- `last_updated:` is an ISO-8601 UTC timestamp.
- Persistence is atomic. If identity or storage is unavailable, the structured result uses `handoff_path: null`; a guessed location is not evidence of a write.

Section names, ordering, `schema_version`, and other fields are informal and may change without notice. Changing a declared guarantee is a breaking change and requires a `CHANGELOG.md` entry under a breaking heading. These source-level promises do not establish native host or external consumer acceptance.


Complete content is submitted through `session-store handoff-write`; do not use shell temp files or `mv`. Handoff publishes a scoped reference only after the write succeeds and only when effective privacy permits discovery. Checkpoint writes the current owner and retains any existing pointer without advancing a predecessor.
