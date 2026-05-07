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

- **Never overwrite `settings.json`** — `~/.claude/settings.json` is user-managed. The permissions merge step only ADDS entries to `permissions.allow` — it never removes entries, never modifies other fields (model, hooks, statusLine), and always requires user confirmation.
- **Never sync `~/.claude/notes/`** — Personal data (lessons, decisions, patterns). Never pulled back to the repo.
- **Never sync `~/.claude/docs/`** — Installed once during setup, not managed afterward.
- **Use Read/Write tools for file operations** — Not shell `cp`. This gives visibility into what changes and avoids permission issues. Exception: backup copies use `cp -r` since they're preservation, not reviewed changes.
- **Always ask before syncing** — Every file change during sync requires explicit user confirmation.
- **Always backup before overwriting** — Before any install or sync that modifies files, back up existing managed files to `~/.local/share/clauDNA/backups/<timestamp>/`. This location is outside `~/.claude/` so Claude Code never discovers it.

## Working on This Repo

When modifying managed files in `global/`:
1. Edit the file in `global/` (the source of truth)
2. Test by running `/clauDNA-setup` to push to local
3. Update CHANGELOG.md with the change
