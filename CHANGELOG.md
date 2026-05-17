# Changelog

All notable changes to clauDNA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
