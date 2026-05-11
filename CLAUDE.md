# clauDNA

Claude Code plugin pack distributed via the `Claudfather` marketplace. Ships skills, agents, and hooks as a single plugin (`claudna`). Also provides a headless `install.sh` for fleet / CI provisioning where the interactive `/plugin` command isn't available.

## Repo Structure

```
.claude-plugin/
  plugin.json                   → Plugin manifest (name: claudna, version)
  marketplace.json              → Marketplace manifest (name: Claudfather, lists claudna)
skills/                         → Skill directories (one per skill, plugin auto-discovers)
  _shared/                      → Shared orchestration material referenced by skills (no SKILL.md)
agents/                         → Agent definition files
commands/                       → Slash command files (legacy; prefer skills/)
plugin-hooks/                   → Hook scripts + declarative hook config (renamed from hooks/ to work around Claude Code bug — see CHANGELOG)
  hooks.json                    → Declarative hook wiring (referenced from .claude-plugin/plugin.json; loaded on plugin enable)
  *.sh                          → Hook scripts referenced from hooks.json via ${CLAUDE_PLUGIN_ROOT}/plugin-hooks/
project-template/               → Aux: per-project .claude/ setup template (not shipped via plugin)
shell/                          → Aux: zshrc additions (not shipped via plugin)
snowflake/                      → Aux: Snowflake connection config template (not shipped via plugin)
scripts/
  validate-skills.py            → CI-enforced SKILL_CONTRACT validator (walks skills/)
  recommended-permissions.json  → Permission categories offered by install.sh
  settings-reference.json       → Reference settings.json (used by install.sh, never auto-installed)
.claude/                        → Repo-local commands (e.g. /clauDNA-setup for headless setup)
install.sh                      → Headless / fleet / CI install path (alternative to /plugin install)
```

## Key Install Paths

- **Marketplace (preferred, human users):**
  ```
  /plugin marketplace add chrisrogers37/claudna
  /plugin install claudna@Claudfather
  ```
  Skills are invoked as `/claudna:<skill-name>`.

- **Headless (CI, fleet, Docker images):** clone the repo and run `./install.sh`. Files land directly in `~/.claude/`. Skills are invoked unnamespaced (`/<skill-name>`).

## Rules

### Don't (sync/install safety)

- **Never overwrite `settings.json`** — `~/.claude/settings.json` is user-managed. `install.sh`'s permissions merge only ADDS entries to `permissions.allow` — it never removes entries, never modifies other fields (model, hooks, statusLine), and always requires user confirmation.
- **Never sync `~/.claude/notes/`** — Personal data (lessons, decisions, patterns). Never pulled back to the repo.
- **Never sync `~/.claude/docs/`** — Installed once during setup, not managed afterward.
- **Use Read/Write tools for file operations** — Not shell `cp`. This gives visibility into what changes and avoids permission issues. Exception: backup copies use `cp -r` since they're preservation, not reviewed changes.
- **Always ask before syncing** — Every file change during sync requires explicit user confirmation.
- **Always backup before overwriting** — Before any install or sync that modifies files, back up existing managed files to `~/.local/share/clauDNA/backups/<timestamp>/`. This location is outside `~/.claude/` so Claude Code never discovers it.

### You may, without asking

- Bug fixes in skill content (logic errors, broken examples, outdated references)
- Documentation, README, CHANGELOG entries
- Test additions and coverage improvements
- Reformatting to match marketplace plugin spec
- Skill metadata corrections (descriptions, argument hints, categorization)

### Requires approval

- Adding a new skill to the canonical set (curated repo — additions are consequential)
- Removing or demoting an existing skill (disruptive for users on prior versions)
- Major version bumps and breaking changes
- Marketplace plugin metadata changes (name, description, author, scope)
- Changes to the input contract from Claudosseum
- Anything that introduces a hosted dependency for users

## Working on This Repo

When modifying components inside the plugin tree (`skills/`, `agents/`, `commands/`, `plugin-hooks/`):
1. Edit the file in place (this repo is the source of truth).
2. Test by loading the plugin locally: `claude --plugin-dir /Users/chris/Projects/claudna` and invoking the affected skill.
3. Update `CHANGELOG.md` with the change.
4. Before opening a PR, run `python3 scripts/validate-skills.py` — CI runs the same check and will block merge on violations.
5. When bumping for release, update `version` in `.claude-plugin/plugin.json`. Without a bump, marketplace users do not receive the update.

When adding or modifying a skill, the binding rules live in [SKILL_CONTRACT.md](./SKILL_CONTRACT.md). The contract is enforced by `scripts/validate-skills.py` and the `validate-skills` GitHub Actions workflow. If you need to relax a rule, update both the contract and the validator together — never one without the other.
