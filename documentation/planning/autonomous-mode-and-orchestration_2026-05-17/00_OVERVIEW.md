---
title: Autonomous Mode & Orchestration — Implementation Plan Overview
type: plan
status: draft
owner: chrisrogers37
created: 2026-05-17
tags: [autonomous-mode, orchestration, planning, overview]
repos: [clauDNA, Claudlobby]
links: []
---

# Autonomous Mode & Orchestration — Implementation Plan Overview

> **For implementing teams:** read `documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md` before starting any phase. This overview names the phases, their deliverables, dependency order, and which repo each lives in.

## Goal

Make every clauDNA procedural skill invocable from headless orchestration with a uniform contract, bake quality discipline into clauDNA at natural workflow homes, and provide a configurable wrapper skill in claudlobby that turns any clauDNA procedural skill into a bot's continuous work pattern.

## Repos affected

| Phase | Repo | Working directory |
|---|---|---|
| 1, 2, 3 | clauDNA | `/Users/chris/Projects/claudna` |
| 4 | claudlobby | `/Users/chris/Projects/claudlobby` |

## Phases and dependency order

Phases MUST be implemented in order. Later phases consume artifacts from earlier ones.

```
Phase 1 (clauDNA contract)
    ├── orchestration-guide.md §10 extension
    ├── structured-result shape
    ├── /adversarial-review --dispatch non-interactive mode
    ├── /weigh-development-paths --auto mode
    └── structured-result emission added to 9 existing --auto skills
            │
            ▼
Phase 2 (clauDNA discipline chains)
    ├── adversarial-review chain added to 6 planning skills
    ├── /simplify Step 6.5 added to /implement-plan
    └── /implement-plan interactive Step 3 revised (seed + matrix)
            │
            ▼
Phase 3 (/implement-plan --auto)
    ├── --auto argument parsing
    ├── Step 1.5 sparse-issue refusal
    ├── Step 2.5 scope-expansion tripwire
    ├── §5.5.2 synthesis pass (invokes /weigh-development-paths --auto)
    ├── never-merge in --auto
    └── structured-result emission
            │
            ▼
Phase 4 (claudlobby wrapper)
    ├── library/skills/autonomous-runner skill
    ├── structural_vs_mechanical risk classifier
    ├── fleet.yaml schema extension (validator.py, loader.py, config.py)
    └── bot archetype docs + validation deployment
```

## Per-phase deliverables

### Phase 1 — clauDNA contract (prerequisite)
Plan: `01_phase1-contract-and-shape.md`

Deliverables:
1. New §10.B subsection in `skills/_shared/orchestration-guide.md` for Tier-3 implementation skills.
2. New §10.C subsection in same file specifying the structured-result shape.
3. `/claudna:adversarial-review` updated: `--dispatch` implies non-interactive subagent-driven critique with structured output.
4. `/claudna:weigh-development-paths` updated: new `--auto` mode that suppresses Plan Mode + AskUserQuestion and synthesizes recommendations.
5. Structured-result emission added to 9 existing `--auto` skills: tech-debt, security-audit, product-enhance, frontend-performance-audit, docs-review, access-path-audit, product-vision, session-handoff, visual-crawl.
6. Optional: extend `scripts/validate-skills.py` with a structured-result-emission check for skills declaring `--auto` support.

Ships independently. Other phases consume the contract.

### Phase 2 — clauDNA discipline chains
Plan: `02_phase2-discipline-chains.md`

Deliverables:
1. Shared subagent-dispatch prompt template added to `skills/_shared/` for adversarial-review chaining.
2. Adversarial-review chain step added to 6 planning skills: tech-debt, security-audit, product-enhance, frontend-performance-audit, docs-review, access-path-audit.
3. New Step 6.5 (`/simplify` gate) added to `/claudna:implement-plan` between current Step 6 (Verify) and Step 7 (PR).
4. Step 3 (Challenge Round) revised in `/claudna:implement-plan` per design §5.5.1: open adversarial findings seed the round; full matrix runs after.
5. `challenge-round-questions.md` updated if matrix categories need to align with adversarial-review concern areas.

Ships independently of Phases 3/4 once Phase 1 is in.

### Phase 3 — /implement-plan --auto
Plan: `03_phase3-implement-plan-auto.md`

Deliverables:
1. `--auto` (alias `--autonomous`) argument added to `/claudna:implement-plan`.
2. New Step 1.5: sparse-issue refusal — exits `outcome: blocked` if plan lacks `## Implementation Plan` section.
3. New Step 2.5: scope-expansion tripwire — exits `outcome: bypassed` if Step 2 reveals scope significantly larger than the plan describes.
4. Step 3 in `--auto`: replaced with synthesis pass that packages open adversarial findings + matrix concerns and invokes `/claudna:weigh-development-paths --auto` to produce a refined plan.
5. Step 5 "feels wrong" in `--auto`: exits `outcome: blocked` instead of stopping for user discussion.
6. Step 6.5 `/simplify` regression handling in `--auto`: auto-revert simplify commit on verification regression, note in PR body, proceed.
7. Step 8 (Merge gate) skipped entirely in `--auto`.
8. Step 9 (Summary) emits the structured result shape from §5.2 in `--auto`.

Requires Phases 1 and 2.

### Phase 4 — claudlobby wrapper
Plan: `04_phase4-claudlobby-wrapper.md`

Deliverables:
1. New skill `library/skills/autonomous-runner/SKILL.md` in claudlobby.
2. New `structural_vs_mechanical` risk classifier subagent prompt template.
3. `fleet.yaml` schema extension for the `autonomous_runner` config block on bot entries.
4. `claudlobby/config.py`: new `AutonomousRunnerConfig` dataclass.
5. `claudlobby/loader.py`: parse the new config block.
6. `claudlobby/validator.py`: validate the new config block.
7. `claudlobby/composer.py`: compose autonomous-runner config into the bot's CLAUDE.md.
8. New bot archetype entry in `docs/bot-archetypes.md`: "Autonomous Worker."
9. Validation deployment: single-bot fleet running `autonomous-runner` against a real repo (e.g., `artemis-xyz/dbt`).

Requires Phases 1-3 to be merged in clauDNA before validation deployment.

## Cross-cutting conventions

All plans follow these conventions to keep edits findable across future doc refactors:

- **Anchor by heading text, not line numbers.** Tasks say "find the section starting with `## 10. Autonomous Mode`" rather than "at line 294."
- **One PR per phase.** Each phase is a single merged change. Phase plans are NOT meant to be split.
- **Test-then-edit ordering where possible.** For Python code changes (Phase 4), write pytest tests first. For skill-body markdown changes, the proxy is `scripts/validate-skills.py` and skill-invocation smoke tests.
- **Commit at the end of each task** with a conventional commit message. Don't batch multiple tasks into one commit unless explicitly noted.
- **Never `--no-verify`.** Pre-commit hooks must pass. If a hook fails, fix it; don't bypass.
- **Match existing style.** Skill markdown follows the contract in `SKILL_CONTRACT.md`. The `validate-skills.py` script enforces it.

## Verification across all phases

After each phase ships, run `python3 scripts/validate-skills.py` from the clauDNA repo root. The CI workflow `validate-skills` runs the same check; merge is gated on it.

After Phase 3 ships, smoke-test the full chain by running `/claudna:tech-debt --auto` followed by `/claudna:implement-plan --source github <#> --auto` against a sample repo. Confirm both emit structured results matching the §5.2 shape.

After Phase 4 ships, compose a single-bot fleet with `autonomous-runner` against a real target repo, let it run for a cadence cycle, and confirm:
- Picker selects an eligible issue
- Risk classifier classifies the change
- `/claudna:implement-plan --auto` runs end-to-end
- Structured result is parsed
- Telegram report-back fires

## Estimated effort

Rough estimates per phase, assuming a skilled engineer unfamiliar with clauDNA:

| Phase | Effort | Why |
|---|---|---|
| 1 | 2-3 days | 9 skills to update + 1 shared doc + 2 skill behavior additions. Mostly mechanical but spread across many files. |
| 2 | 2 days | 6 planning skill updates + 2 implement-plan changes. Each planning skill is a similar shape; can copy-paste the chain step pattern. |
| 3 | 3-4 days | The most complex phase. New `--auto` mode for a skill that has 9 steps, plus 2 new tripwire steps, plus the synthesis pass. Needs careful testing. |
| 4 | 3-5 days | New skill in a different repo, Python schema work, classifier subagent design, end-to-end deployment validation. |

Total: ~10-14 days of implementation work for a single engineer; faster with parallel work across phases (Phases 1 and 2 can overlap; 3 must follow 1+2; 4 must follow 3 in clauDNA but can be designed in parallel).

## Out of scope

- Multi-bot dispatch (already in claudlobby).
- Domain-specific rules (live in `library/expertise/`).
- Auto-merge (forbidden by contract).
- Polling PR status after `--auto` opens it (future enhancement).
