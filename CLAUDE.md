# clauDNA

Claude Code plugin pack distributed via the `Claudfather` marketplace. Ships skills, agents, and hooks as a single plugin (`claudna`). Marketplace install is the only supported channel — for headless / CI use, see [SETUP_GUIDE §4](./SETUP_GUIDE.md#4-headless--ci--docker-provisioning) for the declarative-settings + env-var pattern.

## Repo Structure

```
.claude-plugin/
  plugin.json                   → Plugin manifest (name: claudna, version)
  marketplace.json              → Marketplace manifest (name: Claudfather, lists claudna)
skills/                         → Skill directories (one per skill, plugin auto-discovers)
  _shared/                      → Shared orchestration material referenced by skills (no SKILL.md)
agents/                         → Agent definition files
plugin-hooks/                   → Hook scripts + declarative hook config (renamed from hooks/ to work around Claude Code bug — see CHANGELOG)
  hooks.json                    → Declarative hook wiring (referenced from .claude-plugin/plugin.json; loaded on plugin enable)
  *.sh                          → Hook scripts referenced from hooks.json via ${CLAUDE_PLUGIN_ROOT}/plugin-hooks/
project-template/               → Aux: per-project .claude/ setup template (not shipped via plugin)
shell/                          → Aux: zshrc additions (not shipped via plugin)
snowflake/                      → Aux: Snowflake connection config template (not shipped via plugin)
scripts/
  validate-skills.py            → CI-enforced SKILL_CONTRACT validator (walks skills/)
.claude/                        → Repo-local settings (permission allowlists for working in this repo)
```

## Install Paths

- **Human users (interactive):**
  ```
  /plugin marketplace add Claudfather/clauDNA
  /plugin install claudna@Claudfather
  ```
  Skills are invoked as `/claudna:<skill-name>`.

- **Bots / CI / Docker (declarative):** drop a `settings.json` with `enabledPlugins` + `extraKnownMarketplaces`, set `CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1`, run `claude -p`. Full recipe in [SETUP_GUIDE §4](./SETUP_GUIDE.md#4-headless--ci--docker-provisioning).

## Rules

### Don't

- **Never write to `~/.claude/settings.json`** — that's user-managed. Recommended settings tweaks are documented in SETUP_GUIDE for the user to apply manually; the plugin never modifies user settings.
- **Never touch `~/.claude/notes/`** — personal data (lessons, decisions, patterns).
- **Never touch `~/.claude/plugins/cache/Claudfather/claudna/<ver>/`** directly — Claude Code manages that directory. Make changes in this repo and bump `version` in `plugin.json` to ship them.
- **Use Read/Write tools for file operations** — Not shell `cp`. This gives visibility into what changes and avoids permission issues.

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

When modifying components inside the plugin tree (`skills/`, `agents/`, `plugin-hooks/`):
1. Edit the file in place (this repo is the source of truth).
2. Test by loading the plugin locally: `claude --plugin-dir /Users/chris/Projects/clauDNA` and invoking the affected skill.
3. Update `CHANGELOG.md` with the change.
4. Before opening a PR, run `python3 scripts/validate-skills.py` — CI runs the same check and will block merge on violations.
5. When bumping for release, update `version` in `.claude-plugin/plugin.json`. Without a bump, marketplace users do not receive the update.

When adding or modifying a skill, the binding rules live in [SKILL_CONTRACT.md](./SKILL_CONTRACT.md). The contract is enforced by `scripts/validate-skills.py` and the `validate-skills` GitHub Actions workflow. If you need to relax a rule, update both the contract and the validator together — never one without the other.
