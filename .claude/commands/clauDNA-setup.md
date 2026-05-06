# clauDNA Setup

Bootstrap or sync the clauDNA global configuration. Handles both first-time install and ongoing sync to `~/.claude/`.

## Backup Policy

Before any install or sync that would overwrite files, back up existing managed files to:

```
~/.local/share/clauDNA/backups/<YYYY-MM-DD_HHMMSS>/
```

This location is outside `~/.claude/` so Claude Code will never discover it and confuse itself with duplicate commands. Only managed files (commands, agents, hooks) are backed up — never `settings.json`, `notes/`, or `docs/`.

## Procedure

Follow these steps exactly in order.

### Step 1: Detect Mode

Check if the breadcrumb file `~/.claude/.clauDNA-repo` exists.

- **Missing** → INSTALL mode (first-time setup). Go to Step 2.
- **Present** → SYNC mode (already installed). Go to Step 6.

---

## INSTALL MODE (Steps 2–5)

### Step 2: Scan Both Sides

Scan the **repo** to count what will be installed:

- Skills: list directories in `global/skills/` (each contains `SKILL.md`, except `_shared/` which contains shared reference files)
- Commands: list `*.md` files in `global/commands/`
- Agents: list `*.md` files in `global/agents/`
- Hooks: list `*.sh` files in `global/hooks/`
- Docs: `SETUP_GUIDE.md` + `CLAUDE_MD_TEMPLATE.md`

Scan the **local** `~/.claude/` to detect existing files:

- Skills: list directories in `~/.claude/skills/` (if directory exists)
- Commands: list `*.md` files in `~/.claude/commands/` (if directory exists)
- Agents: list `*.md` files in `~/.claude/agents/` (if directory exists)
- Hooks: list `*.sh` files in `~/.claude/hooks/` (if directory exists)

**Match filenames** between repo and local. Categorize each repo file as:

| Status | Meaning |
|--------|---------|
| **New** | File exists in repo only — safe to install |
| **Collision** | File with same name exists locally — needs review |

Present the summary:

```
clauDNA — First-Time Install
═══════════════════════════════════════════
This will install to ~/.claude/:
  Skills:    N skills (M collisions)
  Commands:  N slash commands (M collisions)
  Agents:    N subagents (M collisions)
  Hooks:     N hook scripts (M collisions)
  Docs:      2 documentation files

Also creates:
  ~/.claude/notes/    (personal notes directory)
  ~/.snowflake/       (Snowflake config directory)

Will NOT touch:
  ~/.claude/settings.json  (user-managed)
═══════════════════════════════════════════
```

If there are collisions, also show:

```
Collisions detected (will prompt for each):
  commands/techdebt.md    — local version exists
  hooks/auto-format.sh    — local version exists
```

Ask the user to confirm before proceeding. If they decline, stop.

### Step 3: Create Structure & Backup

**Create directories:**

```bash
mkdir -p ~/.claude/{commands,skills,agents,hooks,notes/{projects,patterns,decisions,lessons},docs}
mkdir -p ~/.snowflake
```

**Backup existing files** (if ANY managed files exist locally):

If `~/.claude/commands/`, `~/.claude/agents/`, or `~/.claude/hooks/` contain files, create a timestamped backup:

```bash
BACKUP_DIR=~/.local/share/clauDNA/backups/$(date +%Y-%m-%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
```

Copy existing managed files into the backup (use shell `cp` — this is a preservation copy, not a reviewed change):

```bash
# Only copy directories that exist and have files
cp -r ~/.claude/commands "$BACKUP_DIR"/commands 2>/dev/null || true
cp -r ~/.claude/skills "$BACKUP_DIR"/skills 2>/dev/null || true
cp -r ~/.claude/agents "$BACKUP_DIR"/agents 2>/dev/null || true
cp -r ~/.claude/hooks "$BACKUP_DIR"/hooks 2>/dev/null || true
```

Print: `Backed up existing files to $BACKUP_DIR`

If no existing managed files were found, skip the backup and print: `No existing managed files found — skipping backup.`

**Write breadcrumb:**

Write the breadcrumb file `~/.claude/.clauDNA-repo` containing the absolute path to this repo (use `pwd` from the repo root, or the known working directory).

**Create starter lessons file** at `~/.claude/notes/lessons/global.md` ONLY if it does not already exist. Contents:

```markdown
# Global Lessons

Patterns and rules learned from corrections. Review when relevant (via `/lessons`).

---

_Add lessons below this line after corrections_
```

### Step 4: Copy Files

Use Read and Write tools (NOT `cp`) to install files from the repo to `~/.claude/`.

#### Non-collision files (auto-install)

For each repo file that has NO local collision:
- Read from repo path
- Write to `~/.claude/` path
- No user prompt needed

#### Collision files (interactive review)

For each repo file that HAS a local collision:

1. Show the filename
2. Run `diff -u` between the local file and the repo file
3. Ask the user what to do:
   - **Overwrite** — Replace local with repo version
   - **Keep local** — Skip this file, leave local version in place
4. Execute the chosen action using Read/Write tools

#### Categories

**Skills** — for each directory in `global/skills/`:
- Create `~/.claude/skills/<name>/` (and `references/` if it exists in the repo)
- Read and Write each file within the skill directory (`SKILL.md` and any `references/*.md`)
- Note: `_shared/` contains shared reference files used by orchestration skills. It has no `SKILL.md` and won't appear as a user-invocable skill. Install it like any other skill directory.

**Commands** — for each `*.md` file in `global/commands/`:
- Read from `global/commands/<name>.md`
- Write to `~/.claude/commands/<name>.md`

**Agents** — for each `*.md` file in `global/agents/`:
- Read from `global/agents/<name>.md`
- Write to `~/.claude/agents/<name>.md`

**Hooks** — for each `*.sh` file in `global/hooks/`:
- Read from `global/hooks/<name>.sh`
- Write to `~/.claude/hooks/<name>.sh`
- Run `chmod +x ~/.claude/hooks/<name>.sh` after writing

**Docs**:
- Read `SETUP_GUIDE.md` → Write to `~/.claude/docs/SETUP_GUIDE.md`
- Read `CLAUDE_MD_TEMPLATE.md` → Write to `~/.claude/docs/CLAUDE_MD_TEMPLATE.md`

**Skip `settings.json`** — print an explicit note:
> `settings.json` is user-managed and was NOT overwritten. See `global/settings.json` for a reference example.

### Step 4.5: Permissions Merge

Offer to add recommended permissions to `~/.claude/settings.json`. This is additive-only — never removes entries, never touches non-permissions fields.

#### Sub-step A: Deprecated Syntax Migration

Scan the user's `permissions.allow` for deprecated colon syntax and offer migration.

1. Read `~/.claude/settings.json`. If missing, treat as `{}`. If invalid JSON, warn and skip this step.
2. Extract the user's current `permissions.allow` array (default to `[]` if missing).
3. Identify all entries matching `Bash(<cmd>:<args>)` — entries starting with `Bash(` that contain a colon before the closing `)`.
   - **Edge case — `Bash(npx:neonctl*)`:** This IS deprecated colon syntax. Replace the FIRST colon after `Bash(` with a space → `Bash(npx neonctl*)`.
   - **Non-Bash entries** like `Read`, `Write`, `WebFetch(domain:example.com)` are skipped.
4. If zero deprecated entries found, print "All permissions use modern syntax" and continue to Sub-step B.
5. If deprecated entries found, present:

```
Deprecated Syntax Detected
═══════════════════════════════════════════════════════
  N permissions use Bash(cmd:*) — deprecated
  Modern syntax is Bash(cmd *)

  Example: Bash(git:*) → Bash(git *)

  Migrate all to modern syntax? [Y/n]
═══════════════════════════════════════════════════════
```

6. If accepted: transform all matching entries (replace first colon with space), write back, preserve all other fields.
7. If declined: print "Skipped syntax migration." Continue to Sub-step B.

**This sub-step ONLY modifies syntax of existing entries. Never adds or removes permissions.**

#### Sub-step B: Missing Permissions Check

1. Read `global/recommended-permissions.json` from the repo.
2. For each recommended permission in each category, check coverage:
   - **Exact match** in user's array → "already present"
   - `Bash(CMD *)` when user has `Bash(CMD:*)` → "present (deprecated syntax)"
   - Otherwise → "missing"
3. Present a permissions report grouped by category:

```
Permissions Check
═══════════════════════════════════════════
  Core CLI Tools (recommended):
    ✓  Bash(git *)        — present
    ⚠  Bash(curl *)       — present (via Bash(curl:*) — deprecated syntax)
    ✗  Bash(lsof *)       — missing
    ...

  Claude Code Workflow (recommended):
    ✓  Read               — present
    ✓  Write              — present
    ...
═══════════════════════════════════════════
  N present · N deprecated syntax · N missing across N categories
```

4. If nothing missing: print "All recommended permissions already present" and skip.
5. Otherwise, ask the user: **"Add missing permissions? Options: All recommended / By category / Skip"**
   - **All recommended** — add all missing permissions from default categories
   - **By category** — show each category, let user accept/decline
   - **Skip** — proceed without changes
6. Merge selected permissions: read `settings.json`, append new entries to `permissions.allow` (create the key path if needed), write back. Use `unique` to prevent duplicates.
7. **NEVER remove existing permission entries. NEVER modify `model` or `deny`.**

### Step 4.6: Settings Defaults (statusLine & hooks)

After permissions, offer to add the recommended `statusLine` and `hooks` config from `global/settings.json`. These activate the hook scripts installed in `~/.claude/hooks/`.

1. Read `global/settings.json` from the repo for the recommended `statusLine` and `hooks` values.
2. Read `~/.claude/settings.json` (or `{}` if missing).
3. Check each setting:
   - **`statusLine`** — if the key is missing or null in user's settings → offer to add. If already present (any value) → skip (respect user's custom config).
   - **`hooks`** — if the key is missing or null → offer to add. If already present → skip.
4. Present what's missing:

```
Settings Defaults
═══════════════════════════════════════════
  statusLine    ✗ not configured  →  shows branch, lines changed, model, context %
  hooks         ✗ not configured  →  auto-format on Write/Edit, macOS notifications
═══════════════════════════════════════════
```

5. Ask the user: **"Add these settings defaults? They activate the hook scripts just installed. Options: All / Pick individually / Skip"**
6. For each accepted setting, merge into `settings.json` using Read/Edit/Write. **Never overwrite an existing `statusLine` or `hooks` value** — only add if the key is absent.
7. If both are already present, print "statusLine and hooks already configured" and skip.
8. **PreToolUse check:** After the above, if `hooks` is now present but `hooks.PreToolUse` is missing, offer to add the PreToolUse block from `global/settings.json`. This auto-approves compound commands where every sub-command matches an allow pattern. Present:

```
PreToolUse Hook
═══════════════════════════════════════════
  hooks.PreToolUse    ✗ not configured
    → auto-approve compound commands (&&, |, ;)
    → bypass write-safety for allowed file commands
═══════════════════════════════════════════
```

If accepted, read the `hooks.PreToolUse` value from `global/settings.json` and merge it into the user's `hooks` object. Never overwrite an existing `hooks.PreToolUse` value.

### Step 4.7: Sandbox Configuration (Opt-In)

After settings defaults, offer to enable OS-level sandboxing with automatic Bash approval.

1. Read `~/.claude/settings.json` (or `{}` if missing).
2. Check if the `sandbox` key exists (any value, including `{"enabled": false}`):
   - **Present** → print "Sandbox already configured" and skip.
   - **Missing** → present recommendation.
3. Show tradeoffs:

```
Sandbox Configuration (Recommended)
═══════════════════════════════════════════
  Eliminates ~84% of permission prompts

  How it works:
    Bash commands in project directory  →  auto-approved (sandboxed)
    Read/Write/Edit tools               →  unaffected (not subject to sandbox)
    Cross-directory Bash (e.g. chmod)   →  falls through to normal prompt

  Settings:
    sandbox.enabled                = true
    sandbox.autoAllowBashIfSandboxed = true
    sandbox.allowUnsandboxedCommands = true   (escape hatch for cross-dir)
    sandbox.excludedCommands       = []       (add docker, watchman, etc. if needed)
═══════════════════════════════════════════
```

4. Ask: **"Enable sandbox? [Y/n]"**
5. If accepted: read the `sandbox` value from `global/settings.json` and merge it into `~/.claude/settings.json`. Use Read/Edit/Write — never overwrite other keys.
6. If declined: print "Skipped sandbox configuration." and continue.
7. **Sandbox extensions (optional):** If sandbox was accepted, check `recommended-permissions.json` for the `sandbox-extensions` category. Present it as opt-in:

```
Sandbox Filesystem Extensions (Optional)
═══════════════════════════════════════════
  Extends sandbox write access beyond CWD:
    + Edit(/tmp/**)       — scratch directories for orchestration skills
    + Edit(~/.claude/**)  — hook scripts, config management

  Without these, cross-dir Bash writes use the escape hatch prompt.
═══════════════════════════════════════════
```

Ask: **"Add sandbox filesystem extensions? [y/N]"** (default: no). If accepted, add the permissions to `permissions.allow`.

### Step 5: Install Summary

Print a summary table:

```
Install Complete
═══════════════════════════════════════════
  skills/       N skills installed
  commands/     N files installed (M skipped)
  agents/       N files installed
  hooks/        N files installed (chmod +x)
  docs/         2 files installed
  settings.json  skipped (user-managed)
  breadcrumb     written → ~/.claude/.clauDNA-repo
  backup         ~/.local/share/clauDNA/backups/<timestamp>/
═══════════════════════════════════════════
```

Jump to Step 9.

---

## SYNC MODE (Steps 6–8)

### Step 6: Build File Map

Read `~/.claude/.clauDNA-repo` to get the repo path. Verify the path exists and contains `install.sh`. If not, report the stale breadcrumb and stop.

These are the managed file pairs (repo path → local path):

| Repo | Local |
|------|-------|
| `global/skills/<name>/**` | `~/.claude/skills/<name>/**` |
| `global/commands/*.md` | `~/.claude/commands/*.md` |
| `global/agents/*.md` | `~/.claude/agents/*.md` |
| `global/hooks/*.sh` | `~/.claude/hooks/*.sh` |

**Excluded from sync** (never touched):
- `~/.claude/settings.json` — user-managed
- `~/.claude/notes/` — personal data
- `~/.claude/docs/` — installed copies of documentation

For each category, list all files on both sides. Match files by filename.

### Step 7: Diff and Report

For each matched file pair, run `diff` to check for differences. Categorize each file:

| Status | Meaning |
|--------|---------|
| **In sync** | Identical content |
| **Modified** | File exists in both but content differs |
| **Repo only** | File exists in repo but not locally |
| **Local only** | File exists locally but not in repo |

Print a summary table:

```
clauDNA Sync Status
═══════════════════════════════════════════
  commands/techdebt.md         ✓ in sync
  commands/lessons.md          ✓ in sync
  commands/clauDNA-sync.md  ⚡ modified
  hooks/auto-format.sh         ✓ in sync
  commands/my-custom.md        📁 local only
═══════════════════════════════════════════
  8 in sync · 1 modified · 1 local only
```

If everything is in sync, say so and stop.

If the user passed the argument `status`, stop here (report only, no sync).

### Step 8: Walk Through Differences

**Before making any changes**, create a backup:

```bash
BACKUP_DIR=~/.local/share/clauDNA/backups/$(date +%Y-%m-%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
cp -r ~/.claude/commands "$BACKUP_DIR"/commands 2>/dev/null || true
cp -r ~/.claude/skills "$BACKUP_DIR"/skills 2>/dev/null || true
cp -r ~/.claude/agents "$BACKUP_DIR"/agents 2>/dev/null || true
cp -r ~/.claude/hooks "$BACKUP_DIR"/hooks 2>/dev/null || true
```

Print: `Backed up current files to $BACKUP_DIR`

For each file that is NOT in sync, in order:

1. Show the filename and status
2. Show the diff (use `diff -u` between the two files, or note which side is missing)
3. Ask the user what to do:
   - **Modified** files: **Pull to repo** / **Push to local** / **Skip**
   - **Repo only** files: **Push to local** / **Skip**
   - **Local only** files: **Pull to repo** / **Delete local** / **Skip**
4. Execute the chosen action immediately using Read/Write tools (not `cp`)

---

### Step 8.5: Permissions Merge (Sync)

Same as Step 4.5 — check `~/.claude/settings.json` against `global/recommended-permissions.json` and offer to add missing permissions. This surfaces newly added recommended permissions when the repo updates.

Follow the exact same procedure as Step 4.5.

---

## SUMMARY (Step 9)

### Step 9: Summary

List all actions taken.

**If a backup was created**, always show the restore note:

```
Backup
═══════════════════════════════════════════
Your previous files were backed up to:
  ~/.local/share/clauDNA/backups/<timestamp>/

To restore any file, copy it back:
  cp ~/.local/share/clauDNA/backups/<timestamp>/commands/my-file.md ~/.claude/commands/
═══════════════════════════════════════════
```

**If first install (came from Step 5)**, show next steps:

```
Next Steps
═══════════════════════════════════════════
1. SHELL ALIASES (optional):
   cat <repo>/shell/zshrc-additions.sh >> ~/.zshrc
   source ~/.zshrc

2. SNOWFLAKE SETUP (if needed):
   See ~/.claude/docs/SETUP_GUIDE.md Section 5

3. PROJECT SETUP (for each project):
   cp -r <repo>/project-template/.claude /path/to/project/
   cp <repo>/project-template/CLAUDE.md /path/to/project/

4. FUTURE SYNC:
   From any project, use /clauDNA-sync
   From this repo, use /clauDNA-setup
═══════════════════════════════════════════
```

**If sync mode (came from Step 8)**:
1. List all actions taken
2. If any files were pulled to repo, remind: "Don't forget to commit the changes pulled into the repo."
3. If any files were pushed to local, note they're active immediately

## Notes

- Never auto-sync without asking. Every file change requires explicit confirmation.
- `settings.json` is always excluded — it is user-managed and never synced.
- `~/.claude/notes/` is never synced — that's personal data.
- If the user passes the argument `status`, only run the report steps (no sync).
- Use Read/Write tools for file operations, not shell `cp`. This avoids permission issues and lets the user see exactly what changes. Exception: backup copies use shell `cp -r` since they're preservation, not reviewed changes.
- Backups go to `~/.local/share/clauDNA/backups/` — outside `~/.claude/` so Claude Code never discovers them.
