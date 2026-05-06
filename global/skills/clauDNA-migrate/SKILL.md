---
name: clauDNA-migrate
description: "Use after upgrading clauDNA when legacy command files in ~/.claude/commands/ may still exist alongside newer skills."
---

# clauDNA Migrate

Migrate from legacy commands (`.claude/commands/`) to skills format (`.claude/skills/`). One-time cleanup for users who had clauDNA installed before the skills migration.

## When to Run

Run after `/clauDNA-setup` or `./install.sh` if you see "Legacy commands detected." Safe to run multiple times.

## Procedure

### Step 1: Scan for Legacy Commands

List all `.md` files in `~/.claude/commands/`. If empty or missing, report "Nothing to migrate" and stop.

For each file, check if `~/.claude/skills/<name>/SKILL.md` exists (where `<name>` is filename without `.md`).

Categorize:
- **Superseded** — skill equivalent exists, safe to remove
- **Custom** — no matching skill, keep it

### Step 2: Present Migration Plan

```
clauDNA Migration Plan
═══════════════════════════════════════════════════════════════════════════
  Legacy commands found:  N files in ~/.claude/commands/

  Will remove (superseded by skills):
    commands/tech-debt.md        → skills/tech-debt/SKILL.md
    commands/review-pr.md        → skills/review-pr/SKILL.md
    ... (N total)

  Will keep (custom, no skill equivalent):
    commands/my-custom-tool.md   → no matching skill
    ... (N total)

  Backup: ~/.local/share/clauDNA/backups/<timestamp>/commands/
═══════════════════════════════════════════════════════════════════════════
```

Ask: **"Proceed? This will back up and remove N superseded command files."**

### Step 3: Backup

```bash
BACKUP_DIR=~/.local/share/clauDNA/backups/$(date +%Y-%m-%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
cp -r ~/.claude/commands "$BACKUP_DIR"/commands
```

### Step 4: Remove Superseded Commands

Delete each superseded `.md` file. Keep custom commands. If directory is empty after removal, remove it with `rmdir`.

### Step 5: Verify

For each removed command, verify `~/.claude/skills/<name>/SKILL.md` exists.

### Step 6: Summary

```
Migration Complete
═══════════════════════════════════════════════════════════════════════════
  Removed:  N (superseded by skills)
  Kept:     N (custom)
  Backup:   ~/.local/share/clauDNA/backups/<timestamp>/commands/
═══════════════════════════════════════════════════════════════════════════
```

## Notes

- **Safe and reversible.** Everything backed up before removal.
- **Custom commands preserved.** Only exact name matches removed.
- **Skills take precedence anyway.** This cleanup removes dead files to avoid confusion.
- **Backup location:** `~/.local/share/clauDNA/backups/` — outside `~/.claude/`.
