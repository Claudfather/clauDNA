# clauDNA

Global Claude Code configuration repo. Manages slash commands, agents, hooks, and documentation installed to `~/.claude/`.

## Repo Structure

```
global/                         → Files installed to ~/.claude/ (skills, commands, agents, hooks)
  skills/                       → Skill directories + _shared/ → installed to ~/.claude/skills/
    _shared/                    → Shared orchestration guide (not a skill, no SKILL.md)
  commands/                     → 1 command (clauDNA-sync) → installed to ~/.claude/commands/
  agents/                       → Agent files → installed to ~/.claude/agents/
  hooks/                        → Hook scripts → installed to ~/.claude/hooks/
  settings.json                 → Reference example only (never installed)
  recommended-permissions.json  → Permission categories offered during setup/sync
project-template/               → Template for per-project .claude/ setup
shell/                          → Shell aliases (zshrc additions)
snowflake/                      → Snowflake connection config template
.claude/                        → Repo-local commands (like /clauDNA-setup)
install.sh                      → Fast non-interactive installer (alternative to /clauDNA-setup)
```

## Key Commands

- `/clauDNA-setup` — Bootstrap or sync clauDNA from this repo (works without prior install)
- `/clauDNA-sync` — Sync global config from any project (requires prior install)

## Rules

### Don't (sync/install safety)

- **Never overwrite `settings.json`** — `~/.claude/settings.json` is user-managed. The permissions merge step only ADDS entries to `permissions.allow` — it never removes entries, never modifies other fields (model, hooks, statusLine), and always requires user confirmation.
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

When modifying managed files in `global/`:
1. Edit the file in `global/` (the source of truth)
2. Test by running `/clauDNA-setup` to push to local
3. Update CHANGELOG.md with the change
4. Before opening a PR, run `python scripts/validate-skills.py` — CI runs the same check and will block merge on violations

When adding or modifying a skill, the binding rules live in [SKILL_CONTRACT.md](./SKILL_CONTRACT.md). The contract is enforced by `scripts/validate-skills.py` and the `validate-skills` GitHub Actions workflow. If you need to relax a rule, update both the contract and the validator together — never one without the other.
