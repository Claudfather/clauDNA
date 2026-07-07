---
title: "[plan] P4: /claudron engine skill + the engine contract — write|read|status, drafts by default, degrade loudly"
type: plan
status: draft
owner: chris
created: 2026-07-07
updated: 2026-07-07
tags: [planning, claudron, new-skill]
repos: clauDNA
links:
---

# P4 — `/claudron` engine skill + the engine contract

Part of the Claudron-integration epic (`00_OVERVIEW.md`). Size: **L**. Gates: Claudron
**0.2.0 release tag** + the epic's re-confirmation checkpoint (re-verify shipped CLI
against these specs — step 0 of the phase). Fork gates: **F1, F2, F5, F6 locked before
merge.** New-skill approval rides the epic ratification.

## Summary

The deferred bridge, built to house code: one engine skill named for the tool
(SKILL_CONTRACT §4, per `infra-cli-contract.md` — thin body, verb depth files), verbs
`write` | `read` | `status`. Drafts by default on the maturity axis; the
routes-never-rejects dedup contract surfaced verbatim. This phase also creates
`skills/_shared/claudron-engine.md` — the one place the detection ladder, envelope
validation, retry-then-degrade posture, and fallback-freeze policy live — and upgrades
`publish --to vault` to prefer the engine. The `read` verb is deliberate: it is the
read-door parity P7's disposition (fork F4) depends on.

## Evidence

- `documentation/archive/2026-05-15-session-handoff-resume-redesign-design.md:199-205`
  (the deferred bridge, ratified in PR #88) + `CHANGELOG.md:138`.
- Claudron `02-session-loop.md` deliverable 2 — `capture` (flags, stdin JSON, dedup
  warn/`--update`); `03-mcp-server.md` deliverable 2 — the routed envelope
  `{action: created|updated|suggest_update|suggest_supersede, path, reason}` and
  `read`'s not-found → nearest-title candidates. **0.2.0 is single-writer** (the flock
  lock is E3) — hence the retry/degrade posture below.
- `skills/_shared/infra-cli-contract.md` — the binding engine shape (SKILL_CONTRACT
  §4, `SKILL_CONTRACT.md:119`): thin routing body, first-token verb dispatch, per-verb
  depth files, destructive-op confirmation posture.
- Panel: a `>=0.2` version ritual is neither implementable per-session nor sufficient —
  envelope-shape validation on every call is; degradation must be visible in `--auto`
  results.

## Implementation Plan

### Dependencies
Claudron 0.2.0 tag; re-confirmation checkpoint run; F1/F2/F5/F6 locked. P1 merged (for
the `--to vault` upgrade step).

### Blocks
P5, P6 (both consume `claudron-engine.md` + the write conventions); P7 (replacement
surface + read door).

### Steps

0. **Re-confirmation checkpoint:** diff the shipped 0.2.0 CLI (envelope keys, capture
   flags, `init --personal`, exit codes) against this doc and `claudron-engine.md`
   drafts; fold deltas as amendments on the phase issue before writing skill prose.
1. **`skills/_shared/claudron-engine.md`** (the engine contract, single source for all
   consumer skills):
   - **Detection ladder:** `CLAUDRON_VAULT_PATH` → `claudron` on PATH +
     `status --json` resolves a vault → **claudron present, no vault** (remedy:
     `claudron init --personal` pointer — never treated as "not installed") → absent.
     Precedence/mismatch rules shared with P3's section spec.
   - **Envelope validation:** every engine call asserts the expected keys for its verb
     (`action|path|reason` for writes; documented shapes for read/status). Missing or
     unknown-shaped envelope → treat as engine failure (below), never parse-and-guess.
   - **Failure posture:** bounded retry (2 attempts, short backoff — 0.2.0 is
     single-writer and parallel worktree sessions are the house workflow), then
     **degrade loudly**: skills with a raw-tree fallback (learn/reflect/publish-vault)
     take it and say so; skills without one (`/claudron write`) report the failure
     explicitly. In `--auto`, any degradation lands in `errors[]` and
     `artifacts.engine: "fallback"` (F5 as amended). Silence is the only forbidden
     outcome.
   - **Fallback-freeze policy:** the raw-tree path is frozen compatibility behavior —
     no new features land on it; asks are redirected to the engine path.
2. **`skills/claudron/SKILL.md`** — thin engine body per infra-cli-contract (verb
   table + contract references + negative routing), with depth files `write.md`,
   `read.md`, `status.md`:
   - Frontmatter: `name: claudron`; `requires: [{cli: claudron>=0.2}]`;
     `argument-hint: "<write|read|status> [--type t] [--title s] [--project p] [--tags a,b] [--auto]"`;
     description = trigger-first save-door framing + negative routing ("For recalling
     knowledge before work, use /claudna:remember; for distilling the current session,
     use /claudna:reflect").
   - **write:** collect type/title/body/tags/project; `claudron capture --json`; parse
     the envelope. `created|updated` → report path. `suggest_update|suggest_supersede`
     → present suggestion + reason; interactive: confirm route; `--auto`: take the
     suggested route (never force-create). Maturity never set by the skill (engine
     stamps `draft`; promotion is Claudron E5's job). Confirmation posture per
     infra-cli-contract's mutating-verb gate: creating over an explicit suggestion
     requires interactive confirmation; `--auto` never overrides a suggestion.
   - **read:** `claudron read <title|path> --json` → render frontmatter + body;
     not-found → surface the nearest-title candidates verbatim. (The post-migration
     browse door — F4's parity precondition.)
   - **status:** `claudron status --json` → one-screen vault health.
   - **Boundary rule:** skill-shaped content (imperative how-to step lists) is refused
     with a pointer to `/claudna:skill-scaffold` — the vault type enum excludes `skill`
     by design.
   - **Door note:** configured claudron MCP tools are the same engine — equivalent
     semantics; the CLI is the contract floor (F1).
3. **Reciprocal routing:** add negative-routing lines to `/learn` and `/publish`
   descriptions partitioning the four vault-writing doors (SKILL_CONTRACT §2.1 rule 4;
   the which-door table itself shipped in P1's doctrine).
4. **`publish --to vault` engine upgrade:** vault detected → route through
   `claudron capture` per this contract (suggestions surfaced to the caller); fallback:
   raw write + `/claudna:index`, unchanged.
5. **`--auto` structured result** per §10.C with `artifacts.action`, `artifacts.path`,
   `artifacts.engine`, degradation in `errors[]`. No `AskUserQuestion` (§5.1).
6. **Docs:** README row; SETUP_GUIDE "Claudron integration" append (engine door,
   permissions example `Bash(claudron *)`); CHANGELOG.

## Test Plan

- Fixture vault: write→created; near-dup→suggestion surfaced; `--auto` takes the route;
  read round-trips a migrated-shaped note; not-found lists candidates.
- Envelope with a missing key → loud degradation path, `errors[]` populated in
  `--auto`.
- claudron absent / present-no-vault / too old → three distinct, correct messages.
- Skill-shaped input refused with scaffold pointer.
- `validate-skills.py` green (grammar, §5.1, references, requires schema).

## Verification Checklist

- [ ] Step-0 re-confirmation recorded on the phase issue before any skill prose merges
- [ ] Thin body + three depth files per infra-cli-contract; validator green
- [ ] Near-duplicate write returns the routed suggestion — never silent create/drop; `--auto` never overrides a suggestion
- [ ] Every engine call validates the envelope; degradation visible in `--auto` `errors[]`
- [ ] `/learn` + `/publish` descriptions carry reciprocal routing
- [ ] Zero MCP config, zero settings writes

## What NOT To Do

- Don't add a raw-tree fallback to `/claudron write` — an unguarded write door
  recreates the noise problem; loud failure is the fallback.
- Don't set or promote `maturity` — drafts by default; promotion is curation.
- Don't implement a per-session version ritual — envelope validation per call is the
  mechanism.
- Don't inline verb depth in the engine body — infra-cli-contract's thin-body rule.

## Context

- Source skill: forge · Area: skills/claudron/ (new), skills/_shared/claudron-engine.md (new), skills/publish, skills/learn (description line), SETUP_GUIDE.md, README.md · Effort: L · Risk: Medium (new surface, external pre-1.0 CLI) — mitigated by envelope validation + degrade-loudly · Priority: High
- Dependencies: Claudron 0.2.0 tag; F1/F2/F5/F6 locked; P1 · Blocks: P5, P6, P7
