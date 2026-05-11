# Changelog

All notable changes to clauDNA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-05-11

### Added
- `.claude-plugin/plugin.json` — plugin manifest for the `claudna` plugin.
- `.claude-plugin/marketplace.json` — self-hosted `Claudfather` marketplace listing `claudna`. Users can now install via:
  ```
  /plugin marketplace add chrisrogers37/claudna
  /plugin install claudna@Claudfather
  ```
- `plugin-hooks/hooks.json` — declarative hook wiring that activates automatically when the plugin is enabled. PreToolUse permission expansion, PostToolUse auto-format, and Notification hooks no longer require manual `settings.json` edits. (Directory is `plugin-hooks/`, not the spec's default `hooks/`, because Claude Code's runtime deletes any `hooks/` directory at a project root between tool calls — see [#40139](https://github.com/anthropics/claude-code/issues/40139), [#54521](https://github.com/anthropics/claude-code/issues/54521). The path is declared explicitly in `.claude-plugin/plugin.json` via `"hooks": "./plugin-hooks/hooks.json"`. Revert to `hooks/` once the upstream bug is fixed.)

### Changed
- **BREAKING (skill invocation):** When installed via the marketplace, skills are namespaced under the plugin: `/claudna:<skill-name>` instead of `/<skill-name>`. Headless `install.sh` users continue to invoke skills unnamespaced.
- **BREAKING (repo layout):** `global/skills/`, `global/agents/`, `global/commands/`, `global/hooks/` moved to repo root (`skills/`, `agents/`, `commands/`, `plugin-hooks/`). The `global/` directory is removed. Hook scripts moved to `plugin-hooks/` instead of `hooks/` to work around the Claude Code deletion bug above.
- `global/recommended-permissions.json` → `scripts/recommended-permissions.json` (still used only by `install.sh`).
- `global/settings.json` → `scripts/settings-reference.json` (still used only by `install.sh`).
- `install.sh` is repositioned as the **headless / CI / fleet provisioning** path. Marketplace install is now the recommended path for human users. The script's permissions-merge, sandbox-opt-in, and statusLine-opt-in logic is unchanged and still runs for headless installs.
- `/clauDNA-setup` and `/clauDNA-sync` commands now detect install mode and direct marketplace users to `/plugin install` / `/plugin update` instead.
- `scripts/validate-skills.py` and `SKILL_CONTRACT.md` updated to reference `skills/` instead of `global/skills/`. CI workflow unchanged.

### Notes
- `statusline.sh` cannot ship as a plugin-managed statusLine (Claude Code's plugin surface does not yet support it). Marketplace users wishing to use the statusLine add a snippet to their own `~/.claude/settings.json`; see README for the exact path. `install.sh` continues to wire it for headless installs.

## [0.1.0] - 2026-05-05

### Added
- Initial open-source release of clauDNA — a global Claude Code configuration repo with skills, agents, hooks, and commands installable to `~/.claude/`.
