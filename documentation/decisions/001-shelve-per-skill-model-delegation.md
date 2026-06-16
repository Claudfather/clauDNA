---
title: "Shelve per-skill cheap-model subagent delegation"
type: decision
status: accepted
owner: Chris Rogers
created: 2026-06-16
updated: 2026-06-16
tags: [agents, orchestration, model-tiering, performance, cost, rejected-approach]
---

# ADR 001 — Shelve per-skill cheap-model subagent delegation

## Status

Accepted (2026-06-16). Decision: **do not build.** Recorded so the approach is not re-proposed from scratch.

## Context

A `/forge` proposal (2026-06-14) suggested running mechanical, self-contained skills — `name-session`, `notes`, `lessons`, `skill-health` — on a cheaper/faster model (Haiku) by delegating their work to a subagent, for cost, main-context relief, and latency. The motivating ask was "simpler models for speed of operation on things like `/name-session`."

A hardened plan was drafted and put through an independent adversarial review that verified claims against the codebase. Two findings drove this decision:

- **The mechanism is unproven in this repo.** No clauDNA skill dispatches a *custom* agent by `subagent_type` (all skill dispatches use built-in types like `general-purpose`/`Explore`, which are exempt from the integration check). And "the validator accepts `model: haiku`" ≠ "the subagent actually runs on Haiku" — `orchestration-guide.md:414` states subagents inherit the parent model; no agent has demonstrably run on a non-Opus tier.
- **The ROI is upside-down** for the chosen targets (see Rationale).

## Decision

Shelve per-skill cheap-model subagent delegation. Do **not** add a `scribe`-style cheap-tier agent, and do **not** refactor these skills to delegate their work.

## Rationale

Subagent delegation pays only when the offloaded unit of work is **large and/or parallel**. A dispatch is not free: the subagent re-primes a fresh context (it does not inherit the parent's — `orchestration-guide.md:429`), runs a cold per-model cache, and the expensive main model still writes the brief, makes the call, waits, and relays the result. The targeted skills are the opposite — small, single-shot, sequential:

- **`name-session`** — the expensive part (understanding the conversation) cannot be delegated; a subagent has no conversation context. What remains is ~6 git commands plus string formatting. Net-negative.
- **`notes` / `lessons`** — append one entry to one file; already trivial, and they touch protected personal data in `~/.claude/notes/`. Net-negative and higher-risk.
- **`skill-health`** — the only case with real context-relief (it scans every skill dir), but it runs rarely and its own body promises "Under 5 seconds / No subagents"; delegation would reverse that contract for a marginal gain.

Against marginal, occasional savings, the plan would add **permanent** complexity: a new agent, two execution paths per skill, an unproven dispatch mechanism, a fallback that is only prose (no runtime branch), and a behavior change to skills users pin to — against the "stability and predictability" mission principle.

There is also an architecture smell: per-skill delegation re-implements **model routing inside skill markdown**, one skill at a time. Which model runs trivial work is a session/agent-layer concern, not something each skill should re-litigate via cross-context dispatch.

## Consequences

- These skills continue to run in-session on the user's model. No change.
- No cheap-tier agent or per-skill delegation convention is introduced.
- The hardened plan and its full adversarial findings are preserved as scratch at `~/.claude/plans/greedy-noodling-lantern.md` (not committed) for reference.

## Better alternative (not adopted now)

Apply model-tiering where work is **already** delegated and heavy: set `model:` (sonnet/haiku) on agents that do bulk read-only fan-out — Explore-type research agents and the `*-audit` fan-out family. That is a one-line change per agent, with repeated payoff, no new dispatch path, and no skill behavior change.

## Revisit trigger

Reconsider if a skill appears that is **both** genuinely token-heavy (large autonomous tool output) **and** frequently run — the combination where dispatch overhead is amortized. Until then, prefer agent-level tiering over per-skill delegation.

## References

- Proposal/plan (scratch, uncommitted): `~/.claude/plans/greedy-noodling-lantern.md`
- `skills/_shared/orchestration-guide.md` — §"Model stability" (line 414); subagent context isolation (line 429)
- `PROJECT_MISSION.md` — "stability and predictability"; "no phone-home / telemetry"
- `scripts/integration-test.py` — built-in subagent types exempt from the agent-reference check (no precedent for skill→custom-agent dispatch)
