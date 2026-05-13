---
name: cleanup-legacy-install
user-invocable: true
description: "Use when upgrading from a pre-plugin clauDNA install (install.sh, claudefather, or claudfather) to the marketplace plugin. Detects and removes the legacy ~/.claude/ overlay so plugin-installed skills don't get shadowed by stale copies."
allowed-tools: Read(*), Bash(ls *), Bash(cat *), Bash(diff *), Bash(cp *), Bash(rm *), Bash(rmdir *), Bash(mkdir *), Bash(date *), Bash(find *), Bash(test *)
---

# Cleanup Legacy Install

Removes the pre-plugin clauDNA overlay from `~/.claude/` so plugin-installed skills don't get shadowed by stale copies. Works for users who previously installed via clauDNA's `install.sh`, or via the sibling `claudefather` / `claudfather` projects.

The skill is **discovery-based**: it enumerates the names this plugin would now install (skills, agents, hook scripts) and only removes matching-name files in `~/.claude/`. Anything you added yourself with a different name is untouched.

## Procedure

Follow these steps exactly in order.

### Step 1: Detect Legacy Install

Look for breadcrumb files written by the old install scripts:

```bash
ls -la ~/.claude/.clauDNA-repo ~/.claude/.claudfather-repo ~/.claude/.claudefather-repo 2>/dev/null
```

Also check the actual overlay directories — a breadcrumb may be absent if the user removed it manually, but the overlay still exists:

```bash
ls -d ~/.claude/skills ~/.claude/hooks ~/.claude/commands 2>/dev/null
```

If none of these exist and no breadcrumbs are present, print:

> No legacy clauDNA / claudfather / claudefather install detected. Nothing to clean up.

And stop.

Otherwise, continue.

### Step 2: Enumerate the Plugin's Own Components

Locate the plugin's installed directory. The plugin is at `~/.claude/plugins/cache/Claudfather/claudna/<version>/`. Find the version:

```bash
ls -d ~/.claude/plugins/cache/Claudfather/claudna/*/ 2>/dev/null | sort -V | tail -1
```

Call this `PLUGIN_ROOT`. Then list what the plugin ships:

```bash
ls "$PLUGIN_ROOT/skills/" | grep -v '^_'    # skill names (skip _shared)
ls "$PLUGIN_ROOT/agents/"                   # agent file names
ls "$PLUGIN_ROOT/plugin-hooks/"*.sh         # hook script names
```

If `PLUGIN_ROOT` doesn't exist (plugin not installed yet), tell the user:

> The plugin must be installed before this cleanup runs. Please run:
>   /plugin marketplace add Claudfather/clauDNA
>   /plugin install claudna@Claudfather
> Then re-run this skill.

And stop.

### Step 3: Build the Cleanup Manifest

For each component the plugin ships, check whether a matching file exists in the legacy overlay location.

**Skills:** for each `<name>` in the plugin's `skills/` directory, check if `~/.claude/skills/<name>/SKILL.md` exists.

**Agents:** for each `<name>.md` in the plugin's `agents/` directory, check if `~/.claude/agents/<name>.md` exists.

**Hook scripts:** for each `<basename>.sh` in the plugin's `plugin-hooks/` directory, check if `~/.claude/hooks/<basename>.sh` exists.

**Commands:** check for known-legacy command files in `~/.claude/commands/`:
- `clauDNA-sync.md`
- `clauDNA-setup.md`
- `clauDNA-migrate.md`
- `claudfather-sync.md`
- `claudefather-sync.md`
(These were never plugin components — they're install.sh artifacts that the plugin doesn't replace.)

**Breadcrumb files:** `.clauDNA-repo`, `.claudfather-repo`, `.claudefather-repo` in `~/.claude/`.

**Docs:** check `~/.claude/docs/SETUP_GUIDE.md` and `~/.claude/docs/CLAUDE_MD_TEMPLATE.md` — install.sh copied these. They're stale once the plugin is in place.

Build a manifest of full paths to be removed.

### Step 4: Detect Customizations (Safety Check)

For each candidate file in the manifest, compare its content to the plugin's version:

```bash
diff -q ~/.claude/skills/<name>/SKILL.md "$PLUGIN_ROOT/skills/<name>/SKILL.md"
```

Categorize:
- **Identical to plugin version** → safe to remove without question.
- **Differs from plugin version** → may be user customization. Flag for explicit confirmation.

Skills with subdirectories (e.g., `references/`) — diff the full tree using `diff -rq`.

For hook scripts, agents, docs: same approach — `diff -q` against the plugin's copy.

Breadcrumb files and legacy command files have no plugin equivalent, so they're always safe to remove.

### Step 5: Present the Plan

Show the user what will happen, grouped by category:

```
Cleanup Plan
═══════════════════════════════════════════════════════════════

Breadcrumbs (always safe to remove):
  ~/.claude/.clauDNA-repo

Legacy command files (no plugin equivalent — safe):
  ~/.claude/commands/clauDNA-sync.md
  ~/.claude/commands/clauDNA-setup.md

Skills (N total: M identical to plugin, K differ — see below):
  Identical (safe):
    ~/.claude/skills/access-path-audit/      (matches plugin)
    ~/.claude/skills/cache-audit/            (matches plugin)
    ...
  Differ (you may have customized these — confirm individually):
    ~/.claude/skills/tech-debt/              (differs from plugin)

Hooks (N total: M identical, K differ):
  Identical (safe):
    ~/.claude/hooks/auto-format.sh           (matches plugin)
    ...
  Differ:
    ~/.claude/hooks/pretooluse-permissions.sh  (differs from plugin)

Agents (N total: M identical, K differ):
  ...

Docs:
  ~/.claude/docs/SETUP_GUIDE.md   (stale copy of plugin's SETUP_GUIDE.md — safe to remove)
  ~/.claude/docs/CLAUDE_MD_TEMPLATE.md   (stale copy — safe to remove)

═══════════════════════════════════════════════════════════════
Summary: N files/directories total, M safe, K need confirmation.
```

### Step 6: Confirm Differing Items One-by-One

For each item flagged as "differs":

1. Show the diff (`diff -u` between the user's copy and the plugin's copy).
2. Ask: **Keep / Remove / Show full diff**.
3. If **Keep**: drop from the manifest, leave the file in place. Note that this file will shadow the plugin's `/claudna:<name>` version under its bare `/<name>` invocation. The user can later rename or delete it manually.
4. If **Remove**: keep in the manifest.

Do not auto-resolve. Ambiguous cases must be the user's call.

### Step 7: statusLine Check

If `~/.claude/settings.json` exists, check whether `statusLine.command` points at `~/.claude/hooks/statusline.sh` (the old install location):

```bash
grep -l '~/.claude/hooks/statusline.sh' ~/.claude/settings.json 2>/dev/null
```

If yes, the user's statusLine will break once `~/.claude/hooks/statusline.sh` is removed. Ask:

1. **Update path to plugin cache** — rewrite the command to `bash ~/.claude/plugins/cache/Claudfather/claudna/<version>/plugin-hooks/statusline.sh`. Warn that this version is pinned and will need updating on plugin bumps.
2. **Remove statusLine entirely** — delete the `statusLine` key from settings.json. User can re-add later.
3. **Skip** — leave settings.json alone; user will fix it manually.

Use Read + Edit (not Bash) to modify settings.json. Never use `>` redirect to overwrite — that can race with other writers.

### Step 8: Final Confirmation

Print the full final manifest (after Step 6 user choices) and ask one last time:

> Will remove N files/directories. Continue? [y/N]

Require explicit `y` or `yes`. Anything else aborts.

### Step 9: Backup

Before any destructive operation, back up the entire manifest to a timestamped directory:

```bash
TS=$(date +%Y-%m-%d_%H%M%S)
BACKUP_DIR=~/.local/share/clauDNA/backups/cleanup-legacy-install-$TS
mkdir -p "$BACKUP_DIR"
```

For each path in the manifest, `cp -r` (or `cp` for files) into a mirror structure under `$BACKUP_DIR`. Preserve the original path structure so restoration is `cp -r` back.

This location is outside `~/.claude/` so Claude Code never discovers the backup.

Print:
> Backed up N items to ~/.local/share/clauDNA/backups/cleanup-legacy-install-<timestamp>/

### Step 10: Execute

Remove each item in the manifest:

- Skills: `rm -rf ~/.claude/skills/<name>` (skill dirs are subdirectories)
- Agents: `rm ~/.claude/agents/<name>.md`
- Hooks: `rm ~/.claude/hooks/<name>.sh`
- Commands: `rm ~/.claude/commands/<name>.md`
- Breadcrumbs: `rm ~/.claude/.clauDNA-repo` etc.
- Docs: `rm ~/.claude/docs/SETUP_GUIDE.md` etc.

After removing all items, prune now-empty parent directories:

```bash
rmdir ~/.claude/skills ~/.claude/hooks ~/.claude/agents ~/.claude/commands ~/.claude/docs 2>/dev/null
```

(`rmdir` only succeeds if the directory is empty — don't add `-rf`.)

### Step 11: Print Next Steps

```
Cleanup complete.
═══════════════════════════════════════════════════════════════
  Removed:  N files/directories
  Backup:   ~/.local/share/clauDNA/backups/cleanup-legacy-install-<timestamp>/
  
Restore any file with:
  cp -r ~/.local/share/clauDNA/backups/cleanup-legacy-install-<timestamp>/<path> ~/.claude/<path>

Next:
  - Run /reload-plugins (or restart Claude Code) to pick up the cleanup.
  - Invoke any claudna skill as /claudna:<skill-name> to verify the plugin is the only source.
═══════════════════════════════════════════════════════════════
```

## Safety Notes

- **Never run without an installed plugin.** Step 2 enforces this. Without the plugin, the discovery step has no manifest to work from.
- **Never auto-resolve customized files.** Step 6 requires per-file confirmation for anything that differs from the plugin's version.
- **Always back up before removing.** Step 9 is mandatory.
- **Never modify `permissions.allow` entries in settings.json.** Old `Bash(...)` patterns added by install.sh are additive and still useful in the plugin world. Leaving them alone is correct.
- **Use Read + Edit for settings.json edits.** Never `>` overwrite — that races with concurrent Claude sessions writing to the same file.
- **Backups live outside `~/.claude/`** at `~/.local/share/clauDNA/backups/` so Claude Code never discovers them and confuses itself with duplicate copies.
