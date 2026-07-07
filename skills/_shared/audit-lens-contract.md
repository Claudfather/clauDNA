# Audit Lens Contract

The shared skeleton for the `/audit` engine and its lenses. The engine (`skills/audit/SKILL.md`) is a thin lens router; each lens is a subdirectory (`skills/audit/<lens>/`) holding the lens procedure (`<lens>.md`) plus its support files. This file owns everything the lenses share, so each lens carries only its concern-specific depth.

## 1. Layout and thin-router rule

- Engine body = frontmatter + the lens table + dispatch rules + contract references. Per-lens depth loads **only when that lens is selected** — running the security lens must never load the design rubric.
- A lens directory contains `<lens>.md` (the procedure, opening with `Invoked by /claudna:audit in <lens> mode`) and its support files (scan categories, checklists, rubrics, subagent prompts). Support files are referenced by filename from the lens procedure; both live in the same directory.
- A new audit concern is a new lens directory + a row in the engine's table — never a new skill (the SKU anti-pattern; see the Design Philosophy in the README and SKILL_CONTRACT §4).

## 2. Shared arguments

Every lens accepts, via the engine:

- `[focus]` — free-text scope narrowing (an area, path, page, or repo set, per the lens's Focus note in the table).
- `--output github|session` — `github` files findings as issues per `skills/_shared/output-guide.md` (routing through `/claudna:publish`; lenses never call `gh` directly); `session` (default) presents the analysis in chat.
- `--auto` — non-interactive run, only for lenses whose table row says **auto: yes**. See §4.

## 3. Shared output conventions

- Findings carry the concern vocabulary from `skills/_shared/contracts/lens-result-contract.md` — that file is the **single source** for concern-area names (architecture, scope, performance, compatibility, dependencies, testing, observability, data-integrity); lenses do not mint their own.
- `--output github`: one issue per finding-cluster per the output-guide's §4.1 body contract, labels per its label rules, dedup before filing.
- Session output: severity-ordered findings with file:line evidence, then a phased remediation sketch. Boxed summary at the top: lens, scope, counts by severity.

## 4. Autonomous mode

- Lenses marked **auto: yes** run non-interactively under `--auto`: no plan-mode entry, no blocking questions, and a single fenced structured-result JSON block as the final output per `skills/_shared/orchestration-guide.md` §10.C (skill: `audit`, plus `"lens": "<lens>"` inside `artifacts`).
- `--auto` with a lens marked **auto: no** does not improvise: emit the §10.C structured result with `"outcome": "blocked"` and `blocker_description` naming the lens as interactive-only. The engine's `--auto` surface never over-advertises a lens that cannot honor it.
- Headless contexts (`claude -p`, subagent dispatch): the lens verb is **required** — never inferred.

## 5. Orchestration

Lenses that fan out (multi-area scans, per-repo sweeps) follow `skills/_shared/orchestration-guide.md`: research subagents write findings to the scratch dir, the lens procedure aggregates; subagents never return long results through the orchestrator's context. Lens procedures reference their own `subagent-prompts.md` where one exists.
