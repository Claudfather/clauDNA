---
status: ✅ COMPLETE
date: 2026-05-15
owner: chris
related_repos: clauDNA, Claudlobby, Claudron
breaking_change: true
sibling_issues:
  - https://github.com/Claudfather/Claudlobby/issues/223
---

> **✅ COMPLETE (verified 2026-07-06 docs audit).** Every clauDNA-side item in this design is shipped: `skills/session-resume/SKILL.md` exists, `skills/context-resume/` is gone, handoff writes to `<cwd>/.claude/session.md` with schema v2 and atomic writes, the reaper lives in `skills/_shared/reaper-rules.md`, legacy import is implemented in `skills/session-resume/SKILL.md`, and all internal cross-references (`orchestration-guide.md`, `repo-health/SKILL.md`, `README.md`, `CHANGELOG.md`) were updated. Strong candidate for archival to `documentation/archive/` — see companion `-plan.md` for per-task detail. The Claudlobby-side sibling issue (#223) is unverifiable from this repo.

# Session Handoff & Resume Redesign

Replace the current `/session-handoff` + `/context-resume` skills with a tightly scoped pair: `/session-handoff` + `/session-resume`. Move the file out of `~/.claude/`, key it by cwd, reap stale items on every read and write, and shed all knowledge-capture responsibilities (those belong to Claudron).

## Motivation

The existing skills bundle three orthogonal jobs into one:

1. **Session continuity** — "where was I, what's next?"
2. **Knowledge capture** — memories, lessons, MEMORY.md pruning, changelog backfill
3. **Cross-project state validation**

Bundling causes three concrete failures, each verifiable today on disk:

- **Slug duplicates.** `~/.claude/notes/projects/` contains both `Example-org--warehouse` and `Example-org-warehouse` for the same repo, and both `Example-org--analytics` and `example-org--analytics` (case mismatch). The git-remote-or-dirname-fallback slug rule produces drift across machines.
- **Stale forever.** Six handoff files dated March–April 2026 sit in `~/.claude/notes/projects/` with no eviction mechanism. Step 0 validates the *current* project's state but never touches cross-project rot.
- **Permission friction.** Both jobs write into `~/.claude/`, which is Claude Code's own config tree and the source of constant permission prompts.

Claudlobby's `PROJECT_MISSION.md` and Claudron's `PROJECT_MISSION.md` together draw a clean architectural boundary: clauDNA owns procedural knowledge (skills), Claudron owns referential knowledge (findings, decisions, patterns) with built-in lifecycle (draft → verified → canonical). The current `/session-handoff` is hoarding referential knowledge inside `~/.claude/`, with no lifecycle.

This redesign collapses the skill to one job — short-burst session continuity — and gets out of Claudron's way.

## Mental model

The handoff is a Memento tattoo: a short note Claude writes to its future self about what it was just doing. It is *not* a journal. The journal is Claudron.

## Architecture

### Identity

The handoff is keyed by **cwd** — the working directory of the Claude Code process at write time. cwd at write equals cwd at read; no slug derivation, no global index, no cross-project state.

- Human in a 1:1 terminal: cwd = the repo, so the handoff is naturally per-repo.
- Claudlobby bot: cwd = the bot's runtime dir (e.g., `runtime/bots/manager/`), so the handoff is per-bot. Bot work spans multiple repos; bullets carry repo references in their content.

### File location

`<cwd>/.claude/session.md`

- Lives next to the work.
- Cleaned up automatically when the cwd is deleted.
- No collision with `~/.claude/`, so the permission tree friction goes away.
- `.gitignore` auto-managed (see Behavior).

### File format

```markdown
---
cwd: /path/to/clauDNA
last_updated: 2026-05-15T14:30:00Z
schema_version: 2
---

## State
branch: main
working_tree: clean
stashes: 0
open_prs: []
in_flight_branches: []

## Activity
- 2026-05-15T14:25:00Z — abc123f refactor: rename context-resume → session-resume
- 2026-05-15T13:10:00Z — Designed handoff v2 with @chris

## Decisions
- 2026-05-15T13:45:00Z — Handoff lives in <cwd>/.claude/session.md, not ~/.claude/notes/
- 2026-05-15T14:00:00Z — Reaper is evidence + TTL (7d activity, 14d open Q, 30d decisions)

## Open Questions
- 2026-05-15T13:50:00Z — Should /session-resume offer to import old ~/.claude/notes/projects/ handoffs?

## Next Steps
- 2026-05-15T14:30:00Z — Update Claudlobby /restart skill to use /session-resume
- 2026-05-15T14:30:00Z — Write the spec doc, then plan
```

Per-item ISO-8601 timestamps are required so the reaper can reason about staleness. `State` is the only section that is fully regenerated on every write; everything else is merged with reaped prior content.

## Reaper rules

The reaper runs on **every** write (in `/session-handoff`) and **every** read (in `/session-resume`). Identical contract in both skills, sourced from a shared module.

| Section | Rule | Action |
|---|---|---|
| `State` | Never reaped — always overwritten from live scan | n/a |
| `Activity` | Item timestamp > 7d old | hard drop |
| `Activity` | Item references a PR/branch that no longer exists | hard drop |
| `Open Questions` | Item timestamp > 14d old | soft — LLM judges; if no current signal, drop |
| `Open Questions` | Item references a closed PR or merged plan phase | hard drop |
| `Decisions` | Item timestamp > 30d old | soft — drop unless still load-bearing for current Next Steps |
| `Decisions` | Referenced by current Next Steps | never auto-drop |
| `Next Steps` | Commit message since last handoff references the step as done | hard drop, move to Activity |
| `Next Steps` | Plan phase referenced is now `✅ COMPLETE` | hard drop |
| `Next Steps` | Pure timestamp | never drop by TTL alone |

"LLM judges" means the skill instructs Claude to evaluate the item against current state (recent commits, open PRs, current branch, plan-doc status) and decide. The instruction is explicit in the SKILL.md so the judgment is reproducible, not vibes.

## Behavior

### `/session-handoff`

Single skill, accepts `--auto` for non-interactive use.

1. Read `<cwd>/.claude/session.md` if present.
2. Reaper pass on existing content.
3. Live scan in parallel: `git status`, `git log --since=8h`, `git stash list`, `gh pr list --author @me`, scan `documentation/planning/` for `IN PROGRESS`, `PENDING`, and completed-but-unarchived plans.
4. Capture this session's new items (Activity from commits, Decisions/Open Questions/Next Steps from session reasoning). With `--auto`: silent. Interactive: one approval round.
5. Regenerate the `State` section from the live scan.
6. Merge reaped-survivors + new items, deduped by content.
7. Write `<cwd>/.claude/session.md`.
8. Ensure `.gitignore` contains `.claude/session.md` — append idempotently if missing. Use `.claude/.gitignore` if no root `.gitignore` exists.

### `/session-resume`

Read-mostly. Accepts `--auto` for non-interactive callers (Claudlobby bots, post-restart hooks).

1. Read `<cwd>/.claude/session.md`. If absent, check legacy path (see Migration); else greet with live-scan summary only.
2. Reaper pass.
3. If reaper changed anything, write back the cleaned file.
4. Live scan (same calls as handoff).
5. Present briefing: State, Next Steps, Open Questions, then a one-line activity recap.
6. Suggest a focus, prioritized: PR with changes-requested → in-progress plan → PRs awaiting review → handoff Next Step → dirty tree.
7. Ask: "What would you like to focus on?" — **skipped under `--auto`**.

`--auto` differences:
- Step 7 is skipped. Steps 5 and 6 still run — the briefing and focus suggestion are the agent's context payload; skipping the explicit question lets the agent return control to its own loop.
- The legacy-file import prompt (Migration section) becomes silent: import is performed automatically with no confirmation.

## What stops happening

Removed responsibilities, with their replacement (if any):

| Removed | Replacement |
|---|---|
| Step 0A — `MEMORY.md` validation/pruning | Auto-memory system in main system prompt continues to write `MEMORY.md`. No skill audits it on a session boundary. |
| Step 0C — `~/.claude/notes/` notes validation | `/lessons` and `/notes` skills already exist; user invokes deliberately. |
| Step 2 — Capture learnings to memory + notes | Same as above. Future `/claudron-write` skill will handle durable findings. |
| Step 3 — `CHANGELOG.md` backfill | If wanted, belongs in `/commit-push-pr`. Out of scope here. |
| Writes to `~/.claude/notes/projects/<slug>/` | Replaced by `<cwd>/.claude/session.md`. |
| Writes to `~/.claude/projects/<path>/memory/` | Untouched by these skills. Auto-memory system retains exclusive ownership. |

## Migration

Existing files at `~/.claude/notes/projects/*/context-resume.md` (six observed today) become orphans the moment the new skills ship.

**Strategy:** `/session-resume` checks the legacy path on first run in any given cwd. If a file exists, it offers a one-time import — copy content to `<cwd>/.claude/session.md`, run the reaper on the way in, delete the legacy file. Skip silently if no legacy file. After 30 days post-release, drop the import branch entirely (one follow-up cleanup commit).

The legacy slug derivation rule (`org/repo` with `/` → `--`, dirname fallback) is used *only* by the import path, and only because that's how legacy files were named.

## Renames and paired updates

This is a breaking change. Both repos must land paired updates.

**clauDNA repo:**
- Rename `global/skills/context-resume/` → `global/skills/session-resume/`
- Rewrite `global/skills/session-handoff/SKILL.md` to this spec
- Rewrite `global/skills/session-resume/SKILL.md` to this spec
- Add reaper rules to a shared file (`global/skills/_shared/reaper-rules.md`) or inline in both SKILL.md files if compact enough
- Update `CHANGELOG.md` with breaking-change note
- Grep for and update any other internal references to `/context-resume`, `~/.claude/notes/projects`, `Step 0A`, `Step 0C`, etc.

**Claudlobby repo:**
- Update `library/skills/restart/SKILL.md` — `/claudna:context-resume` → `/claudna:session-resume`
- Make `/restart` itself accept `--auto` and propagate it to the inner `/claudna:session-handoff` and `/claudna:session-resume` calls (today `--auto` is hardcoded inside `/restart`). Default `/restart` = interactive; `/restart --auto` = headless top-to-bottom.
- Update the systemd/launchd invocation sites that call `/restart` to pass `--auto` explicitly.
- Grep for any other references

## Integration points

These contracts are preserved (only the skill names change):

- **Claudlobby `/restart`** invokes `/claudna:session-handoff` then kicks the process; the new session auto-runs `/claudna:session-resume`. Whether `--auto` is passed depends on how `/restart` itself was invoked (see `--auto` convention below).
- **`/commit-push-pr`** continues to suggest `/session-handoff` after PR creation.
- **`/implement-plan`** continues to suggest `/session-handoff` after the final phase.
- **Context compaction hooks** continue to trigger `/session-handoff --auto` if configured.

### `--auto` propagation convention

`--auto` means "headless — no prompts, no questions, exit cleanly." This convention is propagable across the call stack:

- A skill that invokes `/session-handoff` or `/session-resume` SHOULD accept its own `--auto` flag and forward it to the clauDNA skills it calls.
- Default = interactive (prompts allowed at every layer).
- `--auto` at the top of the stack = headless at every layer.

This keeps the same orchestrator skill usable both by humans (manual invocation, prompts welcome) and by automated systems (systemd, launchd, cron, hooks) without forking the skill.

## Claudron bridge — deferred

`/session-handoff` does not write to Claudron in this redesign. When Claudron's MCP server lands and a `/claudron-write` skill (or equivalent) ships, the handoff doc may grow a `## Promotion Candidates` section the reaper populates with items it judged durable. That is a v2 enhancement, not in this scope.

## Out of scope

- Building `/claudron-write` or any Claudron MCP integration
- Refactoring `/lessons` or `/notes`
- A cross-project session list / dashboard
- Touching the auto-memory system that writes `MEMORY.md`

## Validation

The skills can't be unit-tested, but the contract is verifiable end-to-end:

1. Run `/session-handoff --auto` in this clauDNA repo with a known dirty tree → `<cwd>/.claude/session.md` written, `.gitignore` updated, zero writes to `~/.claude/`.
2. Manually edit an Activity timestamp to be 8 days old → run `/session-resume` → reaper drops it; file is rewritten without it.
3. Reference a closed PR `#N` in Open Questions → run `/session-resume` → reaper drops it.
4. Run `/session-resume` in a cwd with no `session.md` and no legacy file → graceful empty-state ("no prior session — here's the live scan").
5. Run `/session-resume` in a cwd whose legacy `~/.claude/notes/projects/<slug>/context-resume.md` exists → one-time import prompt; on accept, file moves and legacy is deleted.
6. After paired Claudlobby update, run `/restart` on a bot → bot writes `<runtime>/.claude/session.md`, restarts, new session reads it via `/session-resume`.

## Risks and open questions

- **Bot runtime dirs vary in `.gitignore` posture.** Claudlobby's `runtime/` is gitignored at the Claudlobby root, so individual `<bot>/.gitignore` management may be unnecessary or harmful. Skill should detect: if cwd is inside a gitignored tree, skip the gitignore append.
- **Compaction-triggered handoffs may collide with concurrent writes** if a bot is mid-task. Mitigation: write atomically (`tmp` file + rename). Specified in the implementation plan, not here.
- **The `--auto` interactive-fallback question** ("any items to drop?") — under `--auto`, the reaper is the only pruning mechanism; user-driven pruning is interactive-only. Acceptable.
