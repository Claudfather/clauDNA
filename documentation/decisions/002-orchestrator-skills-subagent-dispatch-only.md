---
title: "Orchestrator-style skills dispatch via subagents, never fleet-specific mechanisms"
type: decision
status: accepted
owner: Chris Rogers
created: 2026-07-06
updated: 2026-07-06
tags: [orchestration, ironclad, dispatch, claudlobby, architecture]
---

# ADR 002 — Orchestrator-style skills dispatch via subagents, never fleet-specific mechanisms

## Status

Accepted. Ratified during the `/ironclad` migration review (PR #141, `/ironclad` cycle 1, 2026-06-03). Recorded here because the decision previously lived only inline in `skills/ironclad/SKILL.md` and in planning docs now marked as archival candidates — this ADR gives it a permanent home.

## Scope (read this first)

This decision governs **dispatch-mechanism choice for the small subset of clauDNA skills that fan out to multiple parallel workers** — today that's `/ironclad` (dispatches review lenses) and `/adversarial-review --dispatch` (dispatches reviewer personas). It does **not** mean every clauDNA skill can only be invoked as a subagent. Most of the ~60 skills in this repo (`/tech-debt`, `/session-resume`, `/forge`, etc.) are run directly by the user in the main conversation and dispatch nothing — this decision doesn't apply to them because there's no dispatch mechanism to choose. The shorthand "clauDNA skills are subagent-only," used in the source planning doc, is easy to misread as a repo-wide invocation constraint; it isn't one.

## Context

`/ironclad` was originally designed to live in Claudlobby (the fleet-orchestration sibling repo) and dispatch review-lens skills to worker bots over `tmux send-keys`, collecting results via `[BOTREPORT]` messages and tracking state in `fleet-state.json`. A dispatch-abstraction framework plan (PR #141) proposed generalizing this pattern with a `fleet-dispatch.md` module inside clauDNA itself, so any future orchestrator-style skill could reuse the fleet-dispatch primitives directly.

An `/ironclad` cycle-1 review (6/6 lenses) rejected that framing. Putting fleet concepts — tmux, `[BOTREPORT]`, `fleet-state.json` — inside a standalone clauDNA plugin conflicts with clauDNA's own "no hosted dependencies for the user" principle (`PROJECT_MISSION.md`): a user who installs the clauDNA marketplace plugin with no fleet running should still get full `/ironclad` functionality.

## Decision

When a clauDNA skill needs to run multiple independent workers in parallel, it dispatches them as **subagents** (the `Agent` tool, `general-purpose` type) running on the current machine — never via fleet-specific tooling. No clauDNA `SKILL.md` may reference `tmux`, `[BOTREPORT]`, `fleet-state.json`, or `FLEET_STATE_PATH` directly.

Fleet execution is added **externally**, at composition time, by Claudlobby: a compositor-injected protocol (`fleet-dispatch-capability`, claudlobby-side) overrides the skill's default subagent dispatch when a bot's environment indicates it's running in a fleet (`FLEET_STATE_PATH` set). The clauDNA skill carries a generic override hook — "check for a fleet-dispatch protocol before dispatching; if present, follow it instead" — but contains no fleet-specific logic itself. This mirrors how other cross-cutting concerns (report-back, context-management, telegram-routing) already augment skill behavior in fleet contexts without living inside the skill.

`skills/ironclad/SKILL.md` is the reference implementation: subagent dispatch is the default and only path described in the skill body; the dispatch preamble names the override hook; a visible "Dispatching N lenses via [fleet|subagent] mode" indicator makes a misconfigured fleet bot (one with `FLEET_STATE_PATH` set but no protocol composed in) detectable rather than silently falling back.

## Rationale

- **Standalone-first.** clauDNA ships as a self-contained marketplace plugin. Any skill that hard-depends on fleet infrastructure to function stops being usable standalone — a direct conflict with the project's "no hosted dependencies" principle.
- **One skill, not two.** The alternative considered was two skills (`/ironclad` in clauDNA for subagent mode, `/ironclad-fleet` in claudlobby for fleet mode). Rejected: the aggregation/convergence logic — dedup, severity sort, PR comment posting, fork-lock scanning — is identical in both modes. Splitting it duplicates the most complex part of the skill and lets the two copies drift.
- **Consistent override pattern.** Claudlobby already augments composed bots' behavior via injected protocols for other cross-cutting concerns. Fleet dispatch follows the same mechanism instead of inventing a second one.

## Consequences

- `skills/ironclad/SKILL.md` and any future orchestrator-style skill are subagent-only by default; grep for `tmux|BOTREPORT|fleet-state` in `skills/*/SKILL.md` should always return zero matches.
- Fleet behavior is entirely invisible to and unowned by clauDNA — verifying it requires a live Claudlobby bot with the `fleet-dispatch-capability` protocol composed into its `CLAUDE.md`, which cannot be checked from this repo alone.
- Standalone subagent mode currently supports only single-cycle review (`cycle: 1`); multi-cycle hardening in subagent mode would need a persisted local scratch dir, not yet built. Fleet mode already supports multi-cycle via `$CLAUDLOBBY_ROOT/state/ironclad-runs/`.

## References

- `skills/ironclad/SKILL.md` — shipped reference implementation (dispatch preamble, mode indicator, subagent-only body)
- `documentation/planning/2026-06-02-ironclad-migration-claudlobby-to-clauDNA.md` — the migration plan this decision drove (Fork F1, Fork F2; PR #141 rescoping notes)
- `documentation/archive/2026-06-01-forge-ironclad-plan-hardening-ecosystem.md` — original design that assumed `/ironclad` would stay in Claudlobby; superseded by this decision
- `PROJECT_MISSION.md` — "No hosted dependencies for the user"
