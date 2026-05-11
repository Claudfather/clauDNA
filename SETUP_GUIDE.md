# clauDNA Setup Guide

**Last Updated:** 2026-05-06

This guide is the deep-dive companion to [README.md](./README.md). The README covers the happy paths (marketplace install via `/plugin install claudna@Claudfather`, or headless `./install.sh`); this guide covers the things those tools deliberately don't handle — Snowflake key-pair authentication, shell aliases, the Claude Code configuration hierarchy, troubleshooting, and the principles behind clauDNA's defaults.

If all you need is "install clauDNA", read the README. Come here when something goes sideways or you want to understand *why* the defaults are what they are.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Configuration Hierarchy](#2-configuration-hierarchy)
3. [Snowflake Key-Pair Authentication](#3-snowflake-key-pair-authentication)
4. [Shell Configuration](#4-shell-configuration)
5. [Troubleshooting](#5-troubleshooting)
6. [Appendix A: Boris Cherny's Key Tips](#appendix-a-boris-chernys-key-tips)
7. [Appendix B: Workflow Orchestration Principles](#appendix-b-workflow-orchestration-principles)

---

## 1. Prerequisites

### Required Software

| Software | Version | Purpose | Installation |
|----------|---------|---------|--------------|
| Claude Code | Latest | AI coding assistant | `npm install -g @anthropic-ai/claude-code` |
| Git | 2.20+ | Version control | `brew install git` |
| zsh | 5.0+ | Shell | Default on macOS |

### Optional (skill-specific)

| Software | Used By | Installation |
|----------|---------|--------------|
| SnowSQL | `/dbt` | Download from Snowflake |
| OpenSSL | Snowflake key-pair auth | Pre-installed on macOS |
| `gh` (GitHub CLI) | `/review-pr`, `/heist`, GitHub-issue output modes | `brew install gh` |
| `psql` | `/neon-query`, `/neon-info`, `/neon-branch` | `brew install libpq` |
| `ruff` | Python auto-format hook | `pip install ruff` |
| `prettier` | JS/TS/MD auto-format hook | `npm install -g prettier` |

Skills only need the tools they invoke — install on demand, not up front.

---

## 2. Configuration Hierarchy

Claude Code reads configuration from multiple locations, merged in this order (later overrides earlier):

1. **Managed settings** (enterprise) — `/etc/claude/settings.json`
2. **Global user settings** — `~/.claude/settings.json`
3. **Project settings** — `<project>/.claude/settings.json`
4. **Local settings** — `<project>/.claude/settings.local.json` (gitignored)

### What goes where

| Configuration | Location | Shared? | Examples |
|---------------|----------|---------|----------|
| Personal tools | `~/.claude/` | No | Snowflake auth, personal aliases |
| Team standards | `<project>/.claude/` | Yes (committed) | Project conventions, shared commands |
| Local overrides | `<project>/.claude/settings.local.json` | No | Machine-specific paths |

### Where clauDNA's files live

Two layouts, depending on install path:

**Marketplace install** (interactive `/plugin install`):
```
~/.claude/plugins/cache/Claudfather/claudna/0.2.0/
├── .claude-plugin/plugin.json     # declares "hooks": "./plugin-hooks/hooks.json"
├── skills/            # plugin auto-discovers; invocation namespaced as /claudna:<name>
├── agents/
├── commands/
└── plugin-hooks/      # renamed from hooks/ to work around Claude Code's hooks/-deletion bug
    ├── hooks.json     # auto-wired on plugin enable (path declared in plugin.json)
    └── *.sh
```

**Headless install** (`./install.sh`):
```
~/.claude/
├── settings.json       # USER-MANAGED — install.sh only adds permissions, never overwrites
├── skills/             # Skills (slash commands + context skills)
├── agents/             # Specialized subagents (snowflake-analyst, dbt-engineer, etc.)
├── commands/           # (empty by default — install/update via /plugin or install.sh)
├── hooks/              # auto-format, statusline, notify, pretooluse-permissions
├── notes/              # Personal — never synced from this repo
└── docs/               # Installed once during setup, never resynced
```

### The lessons system

Two-tier, by intent:

| Tier | Location | Scope |
|------|----------|-------|
| Global | `~/.claude/notes/lessons/global.md` | Universal patterns (tool quirks, general rules) |
| Project | `<project>/.claude/lessons.md` | Project-specific conventions |

The `/lessons` skill captures lessons after corrections. `/init-project` creates the project-level file.

---

## 3. Snowflake Key-Pair Authentication

Passwordless, browser-free Snowflake access via SnowSQL. This is the most fragile part of the setup, so it gets a dedicated section.

### 3.1 Login Name vs User Name

Snowflake has two different identifiers — they are often different and the distinction breaks people regularly:

| Identifier | What it is | How to find it |
|------------|------------|----------------|
| **Login Name** | What you authenticate with (often email) | What you type when logging in |
| **User Name** | Your Snowflake identity after login | `SELECT CURRENT_USER();` |

**Use the LOGIN NAME in your SnowSQL config, not the user name.**

### 3.2 Generate RSA Key Pair

```bash
mkdir -p ~/.snowflake
chmod 700 ~/.snowflake

openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.snowflake/rsa_key.p8 -nocrypt
chmod 600 ~/.snowflake/rsa_key.p8

openssl rsa -in ~/.snowflake/rsa_key.p8 -pubout -out ~/.snowflake/rsa_key.pub
```

### 3.3 Extract the Public Key

```bash
cat ~/.snowflake/rsa_key.pub | grep -v "PUBLIC KEY" | tr -d '\n' && echo ""
```

Outputs a single base64 string — copy it.

### 3.4 Register with Snowflake

You (or an admin) runs:

```sql
ALTER USER your_username SET RSA_PUBLIC_KEY='<paste_public_key_here>';
```

Verify:

```sql
DESC USER your_username;
-- Look for RSA_PUBLIC_KEY property
```

If you hit `Insufficient privileges to operate on user`, send your admin:
1. Your username (`SELECT CURRENT_USER();`)
2. The public key string from §3.3

### 3.5 Configure SnowSQL

Use the template at `snowflake/snowsql-config-template` in this repo as a starting point, then write to `~/.snowsql/config`:

```ini
[connections]
accountname = YOUR_ACCOUNT_IDENTIFIER
username = your_login_name@example.com
private_key_path = /Users/YOUR_USERNAME/.snowflake/rsa_key.p8

[connections.default]
accountname = YOUR_ACCOUNT_IDENTIFIER
username = your_login_name@example.com
private_key_path = /Users/YOUR_USERNAME/.snowflake/rsa_key.p8
warehousename = YOUR_WAREHOUSE
rolename = YOUR_ROLE

[connections.dbt]
accountname = YOUR_ACCOUNT_IDENTIFIER
username = your_login_name@example.com
private_key_path = /Users/YOUR_USERNAME/.snowflake/rsa_key.p8
warehousename = YOUR_WAREHOUSE
dbname = YOUR_DATABASE
schemaname = YOUR_SCHEMA
rolename = YOUR_ROLE

[options]
auto_completion = True
log_file = ~/.snowsql/log
log_level = INFO
timing = True
output_format = psql
```

**Three things that bite people:**
1. Use **absolute paths** for `private_key_path` (not `~/.snowflake/...`). SnowSQL does not expand `~`.
2. Use your **login name** (often email), not the user name.
3. Don't include `authenticator = SNOWFLAKE_JWT` — it's auto-detected and setting it explicitly causes issues.

### 3.6 Test

```bash
snowsql -c default -q "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE();"
```

No browser should open. If one does, see [Troubleshooting](#5-troubleshooting).

---

## 4. Shell Configuration

clauDNA ships shell aliases for git worktrees in [`shell/zshrc-additions.sh`](./shell/zshrc-additions.sh). To install:

```bash
cat shell/zshrc-additions.sh >> ~/.zshrc
source ~/.zshrc
```

This adds:

| Alias | Purpose |
|-------|---------|
| `wt-new <branch>` | Create a new worktree at `<repo>-worktrees/<branch>` and `cd` into it |
| `wt-list` | List all worktrees |
| `wt-rm <path>` | Remove a worktree |
| `wt-set <letter> <path>` | Bind `z<letter>` as a quick-jump alias |

### Typical parallel-Claude workflow

```bash
cd ~/Projects/myrepo
wt-new feature-a
wt-new feature-b

wt-set a ~/Projects/myrepo-worktrees/feature-a
wt-set b ~/Projects/myrepo-worktrees/feature-b

# Now use `za`, `zb` to hop between them. Open a Claude session in each.
```

The `/worktree` skill manages this interactively if you'd rather not memorize the aliases.

---

## 5. Troubleshooting

### Snowflake: "JWT token is invalid"

**Cause:** Wrong username format — usually using user name where login name is required.

**Fix:**
1. `SELECT CURRENT_USER();` in a Snowflake session — that's the USER name.
2. SnowSQL config wants the LOGIN name (often email).
3. Verify by hand: `snowsql -a YOUR_ACCOUNT_IDENTIFIER -u "your_login_name@example.com" --private-key-path /Users/YOUR_USERNAME/.snowflake/rsa_key.p8 -q "SELECT 1;"`

### Snowflake: "No such file" for private key

**Cause:** Using `~` instead of absolute path.

**Fix:** Use `/Users/YOUR_USERNAME/.snowflake/rsa_key.p8`, not `~/.snowflake/rsa_key.p8`. SnowSQL does not expand tildes.

### Snowflake: a browser opens

**Cause:** Public key isn't actually registered, or SnowSQL is falling back to externalbrowser auth.

**Fix:**
- Confirm: `DESC USER your_user;` should show `RSA_PUBLIC_KEY` populated.
- Check the public key on the user matches the public key on disk: extract via §3.3 and compare.

### Hooks not running

**Marketplace install:** hooks ship in `plugin-hooks/hooks.json` inside the plugin and auto-wire on enable. If they're not firing, check:
- `/plugin list` shows `claudna` as enabled
- Try `/reload-plugins`

**Headless install (`install.sh`):** hooks live at `~/.claude/hooks/*.sh` and are wired by `~/.claude/settings.json`. Check:
```bash
chmod +x ~/.claude/hooks/*.sh
~/.claude/hooks/statusline.sh   # smoke test
```

### Status line not showing

Claude Code does not yet support statusLine declarations inside plugin manifests, so the `statusline.sh` script is opt-in regardless of install path.

**Marketplace install:** add to your `~/.claude/settings.json`:
```json
{
  "statusLine": {
    "type": "command",
    "command": "bash ${HOME}/.claude/plugins/cache/Claudfather/claudna/0.2.0/plugin-hooks/statusline.sh"
  }
}
```

**Headless install:** `install.sh` interactively offers to add a statusLine pointing at `~/.claude/hooks/statusline.sh`. If it didn't, run it again or add the block manually.

If the script runs but produces no output, smoke-test it directly:
```bash
~/.claude/hooks/statusline.sh        # headless path
bash ~/.claude/plugins/cache/Claudfather/claudna/0.2.0/plugin-hooks/statusline.sh  # marketplace path
```

### Shell aliases not working

**Cause:** Haven't reloaded shell config.

**Fix:** `source ~/.zshrc`

### Permission prompts firing for things that should be allowlisted

**Cause:** Compound shell commands (e.g. `cmd1 && cmd2`, `cmd1 | cmd2`) bypass simple wildcard match.

**Fix:** clauDNA ships a `pretooluse-permissions.sh` hook that auto-approves compound commands when *every* sub-command matches an allow pattern.

- **Marketplace install:** the hook is wired automatically via `plugin-hooks/hooks.json` when the plugin is enabled. Run `/plugin list` to confirm `claudna` is on.
- **Headless install:** the hook needs to be wired into `~/.claude/settings.json`:

```jsonc
"hooks": {
  "PreToolUse": [
    { "hooks": [{ "type": "command", "command": "~/.claude/hooks/pretooluse-permissions.sh" }] }
  ]
}
```

`install.sh` offers to add this block automatically for the headless path.

---

## Appendix A: Boris Cherny's Key Tips

From the creator of Claude Code:

1. **Run multiple Claudes in parallel** — use git worktrees.
2. **Start complex tasks in plan mode** (Shift+Tab twice).
3. **Invest in your CLAUDE.md** — update it after every correction.
4. **Create slash commands** for workflows you do multiple times a day.
5. **Use subagents** for complex, multi-step tasks.
6. **Give Claude verification loops** — tests, lint, typecheck = 2-3× quality.
7. **Use voice dictation** (fn × 2 on macOS) — 3× faster than typing.

---

## Appendix B: Workflow Orchestration Principles

The clauDNA project template (`project-template/CLAUDE.md`) embeds these principles. They're reproduced here as a reference for projects not using the template.

### Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user

### Self-Improvement Loop
- After ANY correction from the user: update `.claude/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Review lessons when relevant (via `/lessons`)

### Core Principles
- **Simplicity First** — make every change as simple as possible
- **No Laziness** — find root causes, no temporary fixes
- **Minimal Impact** — changes should only touch what's necessary

---

**End of guide.** For day-to-day usage of skills, see the [README](./README.md). For the changelog, see [CHANGELOG.md](./CHANGELOG.md).
