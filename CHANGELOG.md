# Changelog

All notable changes to clauDNA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
