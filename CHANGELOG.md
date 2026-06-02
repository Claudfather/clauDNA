# Changelog

All notable changes to clauDNA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Phase 2 plan: ironclad review lens skills.** `documentation/planning/2026-06-02-phase2-ironclad-lens-skills.md` — forged plan for six lens skills (`/first-principles`, `/align-to-mission`, `/extension-check`, `/precedent-check`, `/plan-health-audit`, `/cost-benefit`) that `/ironclad` dispatches for multi-angle plan hardening. All emit markdown with YAML frontmatter per the `--dispatch` contract (PR #130). First dogfood input for `/ironclad`. All three decision forks ratified during `/ironclad` cycle 1.
- **`skills/_shared/planning-standard.md`.** Extracted the "handoff to junior engineering team" quality contract and phase doc structure from `orchestration-guide.md` (Sections 4-5). Single source of truth for plan quality standards.
- **`skills/_shared/pre-handoff-checklist.md`.** Extracted the adversarial review gate that was duplicated across 6 skills. Defines when to run `/adversarial-review`, how to invoke it, what passes, and how to fold findings.
- **`/forge` skill.** Plan architect skill that scaffolds structured planning documents with decision forks, phasing, validation strategy, risks, and companion plan references. Supports `--output github` (docs PR) and `--auto` (structured-result JSON). Designed as the entry point to the plan-hardening pipeline (`/forge` → `/ironclad`).
- **CI guard `check_no_raw_gh_commands`.** `validate_skill_md` now blocks executable `gh issue/pr create` and `gh issue/pr comment` in a skill body (allowlist: `publish`, `file-github-issue`, `commit-push-pr`), enforcing that skills delegate GitHub output to `/claudna:publish`.
- **Full-validation escape hatch.** Set `FULL_VALIDATE=1` env var or add a `full-validate` label to the PR to force full blocking validation regardless of touched-skill scoping. Useful for release-gating.

### Changed
- **New `skills/_shared/contracts/` directory for cross-skill integration schemas.** Moved `synthesis-contract.md` into `contracts/`; updated all references in `implement-plan`, `weigh-development-paths`, planning docs. Added `lens-result-contract.md` — single source of truth for all lens skill `--dispatch` output format consumed by `/ironclad`. Defines frontmatter fields (`lens`, `worker`, `pr_url`, `plan-path`, `started`, `completed`, `status`, `severity`), body sections (Blockers/Risks/Gaps/Questions/Observations), severity vocabulary, and blocked/failed output shape. `/adversarial-review` now references this contract instead of inlining its own format.
- **All 5 `--dispatch` consumers aligned to `lens-result-contract.md`.** `adversarial-chain.md` inline template updated to contract fields (`status`, `pr_url`, `started`/`completed`, `worker`). `pre-handoff-checklist.md` updated to parse `status` instead of `outcome`, `failed` instead of `errors`. `tech-debt`, `security-audit`, `docs-review` adversarial-review pass sections now reference the canonical contract.
- **`/adversarial-review --dispatch` now emits markdown with YAML frontmatter instead of JSON.** Contract change for the ironclad pipeline. Frontmatter carries `lens`, `severity`, `pr`, `plan-path`, `timestamp`, `outcome`. Body uses five sections (Blockers, Risks, Gaps, Questions, Observations) with `[severity] concern_area` tagged bullets. Severity vocabulary updated to canonical `critical/major/minor/info` across SKILL.md, `adversarial-chain.md`, and `pre-handoff-checklist.md`. The generic `--auto` JSON shape in orchestration-guide.md §10.C is unchanged.
- **`pre-handoff-checklist.md` simplified to invoke `/adversarial-review --dispatch` directly.** Removed the subagent dispatch wrapper and `adversarial-chain.md` reference — the skill's `--dispatch` mode already handles context isolation, parallel critics, and structured-result emission internally. Inlined the findings format and concern-area vocabulary so the checklist is self-contained.
- **`orchestration-guide.md` now focuses on dispatch mechanics.** Sections 4-5 replaced with cross-references to `planning-standard.md`. Content unchanged; location consolidated.
- **8 skills now reference shared `planning-standard.md` and `pre-handoff-checklist.md`** instead of inlining quality standards and adversarial review procedures: `tech-debt`, `security-audit`, `frontend-performance-audit`, `product-enhance`, `access-path-audit`, `docs-review`, `product-vision`, `design-review`. Skill-specific concern areas preserved inline.
- **`/claudna:publish` is now the single output sink for GitHub/session output.** Analysis skills author a markdown doc; publish validates house style (deep, per-`type:` skeleton with a hard gate on `## Implementation Plan` + `### Steps`), dedups per-medium, and routes to a github-issue or the chat session. Added a `session` adapter. `output-guide.md` and the 14 analysis skills now delegate GitHub output to publish instead of embedding `gh issue create`. The default `docs` target still writes to `documentation/planning/` directly — unifying it through publish's disk adapter is deferred.

### Fixed
- **Cross-skill CI attribution bug.** Duplicate-name and duplicate-description checks now attribute errors to BOTH participating skills. In CI scoping mode, cross-skill errors block if ANY participant is PR-touched — previously, alphabetical ordering could land the error on only the untouched skill, silently demoting it to a warning.
- **Git diff fallback now logs a warning.** When `get_touched_skills()` falls back to full validation due to a failed `git diff`, it prints the reason and stderr to help diagnose CI environment issues.

## [0.4.0] - 2026-05-18
### Changed (BREAKING)
- **Renamed `/context-resume` → `/session-resume`.** Sibling change required in any caller (notably Claudlobby's `/restart`, tracked at https://github.com/Claudfather/Claudlobby/issues/223).
- **`/session-handoff` and `/session-resume` redesigned for per-cwd scope.** Handoff now lives at `<cwd>/.claude/session.md` (not `~/.claude/notes/projects/<slug>/context-resume.md`). Identity is the cwd, not a derived slug. Legacy files are imported once on first `/session-resume` in a given cwd and then deleted.
- **`/session-handoff` no longer touches `~/.claude/`.** Memory validation, notes/lessons capture, MEMORY.md pruning, and CHANGELOG backfill are removed. Use `/lessons` and `/notes` for cross-session knowledge until the Claudron-write skill ships.
- **Both skills now accept `--auto`.** Headless mode for Claudlobby bots and any other automated caller. Callers that wrap these skills (e.g., Claudlobby's `/restart`) should accept their own `--auto` flag and forward it, keeping the headless contract end-to-end.
- **Schema version 2** for `session.md`: per-item ISO-8601 timestamps, regenerated `State` section, evidence + TTL reaper run on every read and write.

### Migration
Legacy `~/.claude/notes/projects/<slug>/context-resume.md` files are imported on first `/session-resume` in their corresponding cwd. Files for projects you never reopen will sit until manually deleted (the `/repo-health` orphan check covers this). 30 days post-release, the legacy import path itself will be removed.

Spec: `documentation/planning/2026-05-15-session-handoff-resume-redesign-design.md`

### Fixed
- **CI validate-skills scoped to PR-touched skills.** `validate-skills.py` and `integration-test.py` now detect CI via `GITHUB_ACTIONS` env var and only block on errors from skills modified in the PR. Untouched skill violations are reported as warnings for visibility but do not fail the build. Prevents pre-existing violations (e.g. a broken reference in an unrelated skill) from blocking every PR. `_shared/` changes still validate all skills as blocking. CI workflow updated with `fetch-depth: 0` so `git diff origin/main...HEAD` works.

### Changed
- **Repo doc layout migrated to `documentation/` per the standard.** clauDNA now follows its own [`documentation/specs/repo-documentation-standard.md`](./documentation/specs/repo-documentation-standard.md) (formerly at `docs/specs/`). All three files moved via `git mv` to preserve history: `SKILL_AUTHORING_GUIDE.md` → `documentation/guides/`, two specs → `documentation/specs/`. Scaffolded the full `documentation/` tree (`planning/{phases,tech_debt,security,access-paths,product-vision,investigations}`, `decisions/`, `archive/`) with `.gitkeep` markers so the repo dogfoods what `/claudna:init-project` produces for downstream projects. Updated in-repo references in `README.md` (×2), `skills/init-project/SKILL.md`, and relative links inside the moved `SKILL_AUTHORING_GUIDE.md`. Ecosystem-wide alignment tracked at [Claudfather/.github#2](https://github.com/Claudfather/.github/issues/2) and [Claudfather/Claudlobby#269](https://github.com/Claudfather/Claudlobby/issues/269).

### Added
- **PreCompact reflect hook** (`plugin-hooks/precompact-reflect.sh`) — auto-triggers `/claudna:reflect` before context compaction so session learnings get captured before they're lost. Blocks first compaction attempt, instructs Claude to reflect, then allows the retry. Opt-out: `CLAUDNA_PRECOMPACT_REFLECT=0`. (#27)
- **Validator behavioral checks** — three new enforcement rules in `scripts/validate-skills.py` (#25):
  - Skills claiming `--output github` in `argument-hint` must reference `output-guide.md` in the body (hard error).
  - Skills claiming `--auto` in `argument-hint` must not contain `AskUserQuestion` in the body (hard error).
  - Skills with `allowed-tools` entries not mentioned in the body emit advisory `[WARN]` (non-blocking, catches stale tool declarations).
- **`--output github|session` backfill** on remaining planning/audit skills: `repo-health`, `data-model-audit`, `weigh-development-paths`, `development-retro`. Each now supports the shared output guide contract (`skills/_shared/output-guide.md`), with argument-hint in frontmatter, an Arguments section, and an Output Targets section. (#23)
- `/claudna:skill-health` — diagnostic skill that checks plugin installation state: version currency, hook wiring, skill integrity, dependency availability, and telemetry configuration. Degrades gracefully without network access. (#63)
- `AGENT_CONTRACT.md` + `scripts/validate-agents.py` + `.github/workflows/validate-agents.yml` — agents get the same contract/validator/CI gate pattern as skills. Validates frontmatter (name, description, model, memory, tools, background, isolation), body length, name-filename match, and duplicate detection. All 8 existing agents pass. (#26)
- **Unified CI workflow** (`.github/workflows/ci.yml`) — gates PRs with four jobs: skill validation, manifest validation, changelog check (new [Unreleased] content required), and Python lint via ruff. Added `ruff.toml` config.
- **Autonomous-mode contract — Phase 1 of the autonomous-mode-and-orchestration rollout** (Claudfather/clauDNA#82). Extends the shared `--auto` contract to cover Tier-3 implementation skills and standardizes the structured-result shape every `--auto` skill emits as its final output. Design spec at `documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md`; implementation plans at `documentation/planning/autonomous-mode-and-orchestration_2026-05-17/`. Specifically:
  - `skills/_shared/orchestration-guide.md §10` — new "For implementation skills (Tier 3)" sub-section (produces PR, never merges, requires explicit work item, replaces interactive challenge rounds with trust or machine synthesis). New "Structured Result Shape" sub-section (§10.C) defines the fenced JSON block every `--auto` run emits, with five canonical `outcome` values (`completed | bypassed | needs-input | blocked | partial`). Compatibility matrix now lists `/implement-plan`, `/weigh-development-paths`, `/adversarial-review`.
  - `/claudna:adversarial-review` — `--dispatch` now implies non-interactive mode (suppresses Plan Mode and interactive question prompts) and emits the §10.C structured-result shape with critique findings in `artifacts.findings`. Enables chaining from planning skills and `/implement-plan --auto` without per-skill prompt customization.
  - `/claudna:weigh-development-paths` — new `--auto` synthesis mode: accepts a context bundle (plan + open adversarial findings + open matrix decisions + codebase artifacts) and synthesizes a refined plan by running the 7-dimensional analysis on each open question. Emits the §10.C shape with the refined plan in `artifacts.refined_plan`.
  - **Structured-result emission added to all 9 existing `--auto` skills**: `/claudna:tech-debt`, `/claudna:security-audit`, `/claudna:product-enhance`, `/claudna:frontend-performance-audit`, `/claudna:docs-review`, `/claudna:access-path-audit`, `/claudna:product-vision`, `/claudna:session-handoff`, `/claudna:visual-crawl`. Each now emits a fenced ```json block as the final output of an `--auto` run with skill-specific artifact fields.
  - **New validator check** `check_structured_result_emission` in `scripts/skill_checks.py` (hard error). Skills declaring `--auto` in `argument-hint` must reference structured-result emission in the body. Locks in the contract for future skills. Includes `scripts/test_skill_checks.py` with 10 unit tests covering the new check plus regression coverage for existing behavioral checks.
- **Discipline chains — Phase 2 of the autonomous-mode-and-orchestration rollout** (Claudfather/clauDNA#83). Chains `/claudna:adversarial-review` into every planning skill and `/simplify` into `/claudna:implement-plan`, so generated plans arrive at consumers already stress-tested and implementation PRs get a quality polish before review.
  - New shared dispatch prompts at `skills/_shared/subagent-prompts/`:
    - `adversarial-chain.md` — used by planning skills to chain `/claudna:adversarial-review --dispatch` at the end of plan generation
    - `simplify-chain.md` — used by `/claudna:implement-plan` Step 6.5 to invoke `/simplify` non-interactively
  - Adversarial-review chain added to 6 planning skills as a new sub-phase (Phase 2.5 / Step 5.5 / Phase 4.5 depending on the skill's structure): `/claudna:tech-debt`, `/claudna:security-audit`, `/claudna:product-enhance`, `/claudna:frontend-performance-audit`, `/claudna:docs-review`, `/claudna:access-path-audit`. After Plan agents return, each planning skill dispatches `--dispatch` adversarial review on every generated phase doc and appends an `## Adversarial Review Findings` section with markdown-checkbox findings (OPEN by default) that downstream `/implement-plan` Step 3A consumes.
  - **New Step 6.5 in `/claudna:implement-plan`**: simplification pass via `/simplify` when the diff exceeds 50 LOC or 2+ files. Commits the simplify edits as a separate commit (trivial revert). On post-simplify verification regression: interactive mode asks the user (fix-forward / revert / abort); `--auto` mode (added by Phase 3) will revert unconditionally and note in the PR body.
  - **`/claudna:implement-plan` Step 3 split into 3A + 3B**: Step 3A seeds the challenge round with any OPEN adversarial-review findings from the plan body (first interactive question presents findings as picks; selected concerns drive matrix questions). Step 3B runs the existing matrix-driven flow as today, AFTER 3A regardless of whether findings were resolved — the matrix may surface concerns adversarial-review didn't raise. Ad-hoc plans without adversarial findings skip 3A and behave exactly as before.
  - Flowchart in `/claudna:implement-plan` updated to reflect 3A/3B and Step 6.5.
  - `skills/implement-plan/challenge-round-questions.md` documents concern-area alignment with the adversarial-review vocabulary so 3A can route findings to the right matrix questions.
  - `scripts/integration-test.py` updated for the new layout: `get_shared_files()` now recurses into `_shared/` subdirectories so references like `skills/_shared/subagent-prompts/adversarial-chain.md` resolve, and `resolve_reference()` recognizes cross-skill references like `skills/implement-plan/challenge-round-questions.md`. `tests/test_behavioral_checks.py::test_clean_skill_passes` fixture updated to reference `§10.C` so it remains compliant with the Phase 1 structured-result check.
- **`/implement-plan --auto` mode — Phase 3 of the autonomous-mode-and-orchestration rollout** (Claudfather/clauDNA#84). `/claudna:implement-plan` now supports a fully non-interactive `--auto` (alias `--autonomous`) mode that runs end-to-end without user input and emits the §10.C structured-result JSON block as the final output. All existing interactive behavior is preserved when `--auto` is not set.
  - Required invocation: explicit work item only (`--source github <#>` or single plan file path). Picker/queue modes are disallowed and exit `outcome: blocked` with a descriptive `blocker_description`.
  - **New Step 1.5 (Plan-detail check)**: validates the plan has an `## Implementation Plan` section before proceeding. Interactive mode offers to expand sparse plans via Explore subagents; `--auto` mode refuses with `outcome: blocked` and points back at planning skills for expansion.
  - **New Step 2.5 (Scope-expansion tripwire, `--auto` only)**: when Step 2's codebase comparison reveals an implementation surface significantly larger than the plan anticipated, exits `outcome: bypassed` and posts a comment on the source issue explaining why. Uses qualitative judgment (no hardcoded thresholds — calibrate against real-run data, not arbitrary file counts).
  - **New Step 3-AUTO (Synthesis pass)**: replaces interactive 3A/3B in `--auto`. Packages open adversarial findings + machine-form matrix decisions + Step 2 codebase artifacts into a context bundle, dispatches `/claudna:weigh-development-paths --auto` as a synthesizer subagent, and parses the structured result per the canonical contract.
  - **New `skills/_shared/contracts/synthesis-contract.md`**: canonical producer/consumer schema between `/claudna:weigh-development-paths --auto` (producer) and `/claudna:implement-plan --auto` Step 3-AUTO (consumer). Both skills reference this file instead of restating the shape inline so future drift breaks loudly.
  - Steps 5, 6.5, 7, 8, 9 gain `--auto` mode branches: "feels wrong" → `outcome: blocked` (Step 5); persistent regression after simplify revert → `outcome: partial` (Step 6.5); PR body gets a bot-opened footer noting absence of interactive review (Step 7); Step 8 merge gate is skipped entirely; Step 9 emits the structured-result JSON as the FINAL output.
  - DOT flowchart in the skill body rewritten with the `--auto` branches woven in alongside the preserved interactive flow.
  - Synthesis decisions are recorded back into the plan body (refined plan replaces the original; open adversarial findings get marked resolved with rationale sub-bullets).

### Removed
- `/claudna:snowflake-cutover` — off-mission one-shot playbook, never merged to main. (#43)
- `/claudna:cache-audit` — cache efficiency guidance folded into `/claudna:init-project` Step 3. (#44)
- `/claudna:notifications` — notification setup content folded into `/claudna:init-project` as optional guidance. (#45)
- `requires` optional frontmatter field for skill dependency manifests. Each entry declares a `cli` tool (with optional `>=X.Y` version constraint) or `env` variable needed at runtime, plus an optional `reason`. Validated by `validate-skills.py` and `integration-test.py`.
- `check_dependencies()` runtime function in `skill_checks.py` -- verifies required tools exist on PATH and env vars are set.
- Populated `requires` for 20 skills with external CLI dependencies: dbt, vercel-*, modal-*, railway-*, neon-*, gh-dependent skills (commit-push-pr, review-pr, file-github-issue, github-activity-report, tech-debt, repo-health), and find-skills.
- Unit tests for `validate_requires()` and `check_dependencies()` in `tests/test_requires.py`.
- `/claudna:skill-scaffold` — interactive scaffolding wizard that generates a new skill directory with valid frontmatter, body skeleton, and optional subagent reference stubs. Validates output passes `validate-skills.py` before presenting. (#49)

## [0.2.0] - 2026-05-11

This release converts clauDNA from a bash-installed `~/.claude/` overlay into a Claude Code plugin pack distributed via the `Claudfather` marketplace. Marketplace install is the only supported channel. Headless / CI / Docker provisioning is handled declaratively via `settings.json` (`enabledPlugins` + `extraKnownMarketplaces`) and the `CLAUDE_CODE_SYNC_PLUGIN_INSTALL` env var — no script clone required.

### Added
- `.claude-plugin/plugin.json` — plugin manifest for the `claudna` plugin.
- `.claude-plugin/marketplace.json` — self-hosted `Claudfather` marketplace listing `claudna`. Users install via:
  ```
  /plugin marketplace add Claudfather/clauDNA
  /plugin install claudna@Claudfather
  ```
- `plugin-hooks/hooks.json` — declarative hook wiring that activates automatically when the plugin is enabled. PreToolUse permission expansion, PostToolUse auto-format, and Notification hooks no longer require manual `settings.json` edits.
- `LICENSE` (MIT) at the plugin root.
- New skills shipped with this release (some inherited from upstream commits already merged to main, included here for completeness):
  - `/claudna:cleanup-legacy-install` — one-shot cleanup of pre-plugin `~/.claude/` overlays (install.sh, claudfather, claudefather). Discovery-based: enumerates the plugin's own components and removes only matching-name files from the legacy install, with diff-based safety checks and timestamped backups.
  - `/claudna:adversarial-review` — structured plan challenge with evidence and anti-groupthink guards.
  - `/claudna:learn`, `/claudna:reflect`, `/claudna:index`, `/claudna:remember`, `/claudna:publish` — knowledge system lifecycle (ingest → synthesize → organize → recall → distribute).
- SETUP_GUIDE §0 — "Upgrading from 0.1.x" with the 4-step upgrade sequence (`/plugin install` → `/claudna:cleanup-legacy-install` → `/reload-plugins`).
- SETUP_GUIDE §3 — recommended `~/.claude/settings.json` snippets (permissions, statusLine, sandbox) for users to merge manually since plugins cannot write to user settings.
- SETUP_GUIDE §4 — full headless / CI / Docker provisioning recipe using `enabledPlugins`, `extraKnownMarketplaces`, and `CLAUDE_CODE_SYNC_PLUGIN_INSTALL`.

### Changed
- **BREAKING (invocation):** Skills are namespaced under the plugin: `/claudna:<skill-name>` instead of `/<skill-name>`. All 164 intra-plugin cross-references in skill bodies were updated to the namespaced form.
- **BREAKING (repo layout):** `global/skills/`, `global/agents/`, `global/commands/`, `global/hooks/` moved to repo root (`skills/`, `agents/`, `plugin-hooks/`). The `global/` directory is removed.
- Hook scripts directory is `plugin-hooks/` instead of the spec's default `hooks/` because Claude Code's runtime deletes any `hooks/` directory at a project root between tool calls — see [#40139](https://github.com/anthropics/claude-code/issues/40139), [#54521](https://github.com/anthropics/claude-code/issues/54521). The path is declared explicitly in `plugin.json` via `"hooks": "./plugin-hooks/hooks.json"`. Revert to `hooks/` once the upstream bug is fixed.
- `scripts/validate-skills.py` and `SKILL_CONTRACT.md` updated to reference `skills/` instead of `global/skills/`.

### Removed
- `install.sh` and the `~/.claude/`-overlay install model entirely. Claude Code now supports declarative headless install via settings + env var, making the bash script redundant. The recommended-permissions and reference-settings JSON used by the script were folded into SETUP_GUIDE §3 as copy-paste snippets.
- `scripts/recommended-permissions.json` and `scripts/settings-reference.json` — content migrated to SETUP_GUIDE.
- `/clauDNA-setup`, `/clauDNA-sync`, `/clauDNA-migrate` commands and skills. The marketplace install path uses `/plugin install` / `/plugin update`; headless users use the declarative pattern. The diff/sync/migrate logic these provided is no longer relevant under the plugin model.

### Notes
- The plugin ships a `statusline.sh` but Claude Code does not yet support statusLine declarations inside plugin manifests. Users wishing to use the statusLine add a one-line snippet to their own `~/.claude/settings.json` — see SETUP_GUIDE §3.2.
- Third-party marketplaces (which Claudfather is) do not auto-update by default. Bots / CI runners should bake `claude plugin update claudna@Claudfather` into their startup script to keep current.

## [0.1.0] - 2026-05-05

### Added
- Initial open-source release of clauDNA — a global Claude Code configuration repo with skills, agents, hooks, and commands installable to `~/.claude/`.
