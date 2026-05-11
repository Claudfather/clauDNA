# clauDNA Sync

Compare managed files between the clauDNA repo and `~/.claude/`, then interactively sync differences in either direction.

> **This command is for the headless `install.sh` install path only.** If you installed clauDNA via the marketplace (`/plugin install claudna@Claudfather`), use `/plugin update claudna@Claudfather` instead — the plugin cache is managed by Claude Code and should not be hand-synced.

## Step 0: Detect Install Mode

Check whether the user installed via the marketplace or via `install.sh`:

- If `~/.claude/plugins/cache/Claudfather/claudna/` exists AND `~/.claude/.clauDNA-repo` does **not** exist → marketplace install. Tell the user: "You installed clauDNA via the marketplace. Use `/plugin update claudna@Claudfather` to pull updates, or `/plugin uninstall` + `/plugin install` for a clean reinstall. This `/clauDNA-sync` command is for the headless `install.sh` path only." Stop.
- If `~/.claude/.clauDNA-repo` exists → headless install, proceed with the steps below.
- If neither exists → tell the user: "No clauDNA install detected. Either run `/plugin marketplace add chrisrogers37/claudna` then `/plugin install claudna@Claudfather`, or clone the repo and run `./install.sh`." Stop.

## Backup Policy

Before any sync that would modify files, back up existing managed files to:

```
~/.local/share/clauDNA/backups/<YYYY-MM-DD_HHMMSS>/
```

This location is outside `~/.claude/` so Claude Code will never discover it and confuse itself with duplicate commands.

## Procedure

Follow these steps exactly in order.

### Step 1: Find the Repo

Read `~/.claude/.clauDNA-repo` to get the repo path. If the file doesn't exist, tell the user: "Run `/clauDNA-setup` from the clauDNA repo, or run `./install.sh`" and stop.

Verify the path exists and contains `install.sh`. If not, report the stale breadcrumb and stop.

### Step 2: Build the File Map

These are the managed file pairs (repo path → local path):

| Repo | Local |
|------|-------|
| `skills/<name>/**` | `~/.claude/skills/<name>/**` |
| `commands/*.md` | `~/.claude/commands/*.md` |
| `agents/*.md` | `~/.claude/agents/*.md` |
| `plugin-hooks/*.sh` | `~/.claude/hooks/*.sh` (hooks.json stays plugin-only — not synced) |

Note: `_shared/` directories under `skills/` contain shared reference files used by orchestration skills. They have no `SKILL.md` but are synced like any other skill directory.

**Excluded from sync** (never touched, never compared):
- `~/.claude/settings.json` — user-managed, NEVER synced
- `~/.claude/notes/` — personal notes, lessons, decisions
- `~/.claude/docs/` — installed copies of documentation

For each category, list all files on both sides. Match files by filename.

### Step 3: Diff Every Pair

For each matched file pair, run `diff` to check for differences. Categorize each file:

| Status | Meaning |
|--------|---------|
| **In sync** | Identical content |
| **Modified** | File exists in both but content differs |
| **Repo only** | File exists in repo but not locally |
| **Local only** | File exists locally but not in repo |

Note: Since we can't know which side is "newer" from content alone, report diverged files as **Modified** and show the diff when walking through them.

### Step 4: Report Status Table

Print a summary table like:

```
clauDNA Sync Status
═══════════════════════════════════════════
  commands/techdebt.md           ✓ in sync
  commands/lessons.md            ✓ in sync
  commands/clauDNA-sync.md  ⚡ modified
  hooks/auto-format.sh           ✓ in sync
  commands/my-custom.md          📁 local only
═══════════════════════════════════════════
  8 in sync · 1 modified · 1 local only
```

If everything is in sync, say so and stop.

If the user passed the argument `status`, stop here (report only, no sync).

### Step 5: Backup Before Sync

**Before making any changes**, create a timestamped backup.

First, generate the timestamp and create the backup directory in one call:

```bash
mkdir -p ~/.local/share/clauDNA/backups/$(date +%Y-%m-%d_%H%M%S)
```

Then run four **separate parallel** `cp -r` calls (never combine with `&&`, `||`, or `2>/dev/null` — those shell operators break permission pattern matching):

```bash
cp -r ~/.claude/commands ~/.local/share/clauDNA/backups/<timestamp>/commands
cp -r ~/.claude/skills ~/.local/share/clauDNA/backups/<timestamp>/skills
cp -r ~/.claude/agents ~/.local/share/clauDNA/backups/<timestamp>/agents
cp -r ~/.claude/hooks ~/.local/share/clauDNA/backups/<timestamp>/hooks
```

If a source directory doesn't exist, the `cp` will fail harmlessly — do not suppress errors with `2>/dev/null || true`.

Print: `Backed up current files to ~/.local/share/clauDNA/backups/<timestamp>/`

### Step 6: Walk Through Differences

For each file that is NOT in sync, in order:

1. Show the filename and status
2. Show the diff (use `diff -u` between the two files, or note which side is missing)
3. Ask the user what to do:
   - **Modified** files: **Pull to repo** / **Push to local** / **Skip**
   - **Repo only** files: **Push to local** / **Skip**
   - **Local only** files: **Pull to repo** / **Delete local** / **Skip**
4. Execute the chosen action immediately using Read/Write tools (not `cp`)

When dispatching subagents for bulk sync, instruct them to use **only Read/Write tools** for file operations. Subagents must NOT create their own backups or run `cp`/`mkdir` commands — the master backup in Step 5 already covers this.

### Step 6.5: Permissions Check

After syncing files, check `~/.claude/settings.json` against the repo's `scripts/recommended-permissions.json` and offer to add any missing recommended permissions.

Follow the same two-sub-step procedure as Step 4.5 in `/clauDNA-setup`:

**Sub-step A: Deprecated Syntax Migration**
1. Scan `permissions.allow` for `Bash(<cmd>:<args>)` patterns
2. Skip non-Bash entries
3. Handle `Bash(npx:neonctl*)` correctly — replace first colon with space
4. Present count, example, and migration prompt
5. If accepted: rewrite entries (replace first colon with space), preserve all other fields
6. If declined: proceed normally

**Sub-step B: Missing Permissions Check**
1. Compare permissions against recommended baseline — exact match
2. Label colon-syntax matches as "present (deprecated syntax)", not "missing"
3. Present a report of missing permissions by category
4. Let user choose: All recommended / By category / Skip
5. Merge selected (additive only, never remove, never touch non-permissions fields)

This ensures every sync run surfaces deprecated syntax until migrated, and newly added recommended permissions from updated repos are detected.

### Step 6.6: Settings Defaults Check

After permissions, check if `statusLine` and `hooks` configs are present in `~/.claude/settings.json`. These activate the hook scripts synced in Step 6.

Follow the same procedure as Step 4.6 in `/clauDNA-setup`:
1. Read `scripts/settings-reference.json` from the repo for recommended values
2. Check if `statusLine` and `hooks` keys exist in user's settings
3. Offer to add any that are missing (never overwrite existing values)
4. **PreToolUse check:** If `hooks` is present but `hooks.PreToolUse` is missing, offer to add the PreToolUse block. This auto-approves compound commands where every sub-command matches an allow pattern.

This ensures newly added settings defaults from updated repos are surfaced on sync.

### Step 6.7: Sandbox Configuration Check

After settings defaults, check if sandbox configuration is present in `~/.claude/settings.json`.

Follow the same procedure as Step 4.7 in `/clauDNA-setup`:
1. Read `scripts/settings-reference.json` from the repo for the recommended `sandbox` value
2. Check if the `sandbox` key exists in user's settings (any value → skip)
3. If missing, present the sandbox recommendation with tradeoffs
4. Ask: **"Enable sandbox? [Y/n]"**
5. If accepted: merge the `sandbox` object from repo's `scripts/settings-reference.json` into user's settings
6. If sandbox was accepted, optionally offer `sandbox-extensions` permissions from `recommended-permissions.json` (default: no)

This ensures newly added sandbox recommendations from updated repos are surfaced on sync.

### Step 7: Summary

After walking through all differences:

1. List all actions taken
2. Show the backup restore note:

```
Backup
═══════════════════════════════════════════
Your previous files were backed up to:
  ~/.local/share/clauDNA/backups/<timestamp>/

To restore any file, copy it back:
  cp ~/.local/share/clauDNA/backups/<timestamp>/commands/my-file.md ~/.claude/commands/
═══════════════════════════════════════════
```

3. If any files were pulled to repo, remind the user: "Don't forget to commit the changes pulled into the repo."
4. If any files were pushed to local, note they're active immediately

## Notes

- Never auto-sync without asking. Every file change requires explicit confirmation.
- `settings.json` is always excluded — it is user-managed and never synced or compared.
- `~/.claude/notes/` is never synced — that's user data, not managed config.
- `~/.claude/docs/` is never synced — installed once during setup, not managed afterward.
- If the user passes the argument `status`, only run Steps 1–4 (report, don't sync).
- Use Read/Write tools for file operations, not shell `cp`. Exception: backup copies use shell `cp -r` since they're preservation, not reviewed changes.
- Backups go to `~/.local/share/clauDNA/backups/` — outside `~/.claude/` so Claude Code never discovers them.
- Never combine shell commands with `&&`, `||`, `;`, `|`, or redirects like `2>/dev/null` — these operators prevent permission pattern matching. Use separate parallel Bash calls instead.
