# clauDNA Setup Guide

**Last Updated:** 2026-05-11

This guide is the deep-dive companion to [README.md](./README.md). The README covers the marketplace install (`/plugin install claudna@Claudfather`); this guide covers everything beyond that — recommended `settings.json` tweaks, headless provisioning for bots and CI, Snowflake key-pair auth, shell aliases, the Claude Code configuration hierarchy, and troubleshooting.

If all you need is "install clauDNA", read the README. Come here when something goes sideways or you want to understand *why* the defaults are what they are.

---

## Table of Contents

0. [Upgrading from 0.1.x](#0-upgrading-from-01x) — read first if you previously installed via `install.sh`, `claudfather`, or `claudefather`
1. [Prerequisites](#1-prerequisites)
2. [Configuration Hierarchy](#2-configuration-hierarchy)
3. [Bootstrapping `~/.claude/settings.json`](#3-bootstrapping-claudesettingsjson)
4. [Headless / CI / Docker Provisioning](#4-headless--ci--docker-provisioning)
5. [Snowflake Key-Pair Authentication](#5-snowflake-key-pair-authentication)
6. [Shell Configuration](#6-shell-configuration)
7. [Telemetry](#7-telemetry)
8. [Troubleshooting](#8-troubleshooting)
9. [Appendix A: Boris Cherny's Key Tips](#appendix-a-boris-chernys-key-tips)
10. [Appendix B: Workflow Orchestration Principles](#appendix-b-workflow-orchestration-principles)

---

## 0. Upgrading from 0.1.x

**Skip this section if you've never installed clauDNA before.**

If you previously installed clauDNA via `install.sh` (or the sibling `claudfather` / `claudefather` projects), the install copied skills, agents, hooks, and a breadcrumb file directly into `~/.claude/`. Those copies will **shadow the marketplace plugin** unless you remove them — Claude Code resolves bare `/<skill>` invocations against `~/.claude/skills/` first, so the old version wins and you get silent double-installation.

claudna ships a skill that does this cleanup for you. The upgrade sequence:

```
/plugin marketplace add Claudfather/clauDNA
/plugin install claudna@Claudfather
/claudna:cleanup-legacy-install
/reload-plugins
```

What `/claudna:cleanup-legacy-install` does:

- Detects breadcrumb files (`~/.claude/.clauDNA-repo`, `~/.claude/.claudfather-repo`, `~/.claude/.claudefather-repo`).
- Enumerates the plugin's own skills/agents/hooks and finds matching-name files in `~/.claude/skills/`, `~/.claude/agents/`, `~/.claude/hooks/`. Files that match by name AND have identical content to the plugin's version are flagged as safe to remove. Files that differ are flagged for explicit per-file confirmation (so you don't lose anything you customized).
- Detects stale `statusLine` config pointing at `~/.claude/hooks/statusline.sh` and offers to either update the path to the plugin cache or remove the entry.
- Backs everything up to `~/.local/share/clauDNA/backups/cleanup-legacy-install-<timestamp>/` before removing anything. Restore is a `cp -r` away if you change your mind.
- Leaves your `permissions.allow` entries alone — those were added by install.sh additively and are still useful in the plugin world.

If you'd rather do it manually, the affected paths are:

| Path | What it was |
|---|---|
| `~/.claude/.clauDNA-repo` | Breadcrumb pointing at the cloned repo |
| `~/.claude/skills/<name>/` | Copies of the 0.1.x skill set |
| `~/.claude/agents/<name>.md` | Copies of clauDNA agents |
| `~/.claude/hooks/<name>.sh` | Copies of hook scripts |
| `~/.claude/commands/clauDNA-sync.md` | Legacy sync command (removed in 0.2.0) |
| `~/.claude/docs/SETUP_GUIDE.md`, `~/.claude/docs/CLAUDE_MD_TEMPLATE.md` | Stale doc copies |

Don't bulk-`rm -rf` `~/.claude/skills/` or `~/.claude/hooks/` — those directories may contain files from other sources (your own skills, other plugins' headless installs, etc.). The skill's name-by-name matching is the safe path.

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
| SnowSQL | `/claudna:dbt` | Download from Snowflake |
| OpenSSL | Snowflake key-pair auth | Pre-installed on macOS |
| `gh` (GitHub CLI) | `/claudna:review-pr`, `/claudna:heist`, GitHub-issue output modes | `brew install gh` |
| `psql` | `/claudna:neon-query`, `/claudna:neon-info`, `/claudna:neon-branch` | `brew install libpq` |
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

### Where claudna lives once installed

```
~/.claude/plugins/cache/Claudfather/claudna/<version>/
├── .claude-plugin/plugin.json     # declares "hooks": "./plugin-hooks/hooks.json"
├── skills/            # plugin auto-discovers; invocation namespaced as /claudna:<name>
├── agents/
└── plugin-hooks/      # named plugin-hooks/ to avoid a Claude Code bug deleting hooks/
    ├── hooks.json     # auto-wired on plugin enable (path declared in plugin.json)
    └── *.sh
```

Claude Code manages this directory itself — you should not edit files there. Updates land in a new version directory; old versions are kept for ~7 days before automatic cleanup.

### The lessons system

Two-tier, by intent:

| Tier | Location | Scope |
|------|----------|-------|
| Global | `~/.claude/notes/lessons/global.md` | Universal patterns (tool quirks, general rules) |
| Project | `<project>/.claude/lessons.md` | Project-specific conventions |

The `/claudna:lessons` skill captures lessons after corrections. `/claudna:init-project` creates the project-level file.

---

## 3. Bootstrapping `~/.claude/settings.json`

The plugin install handles skills, agents, and hooks. It does **not** modify your personal `settings.json` — Claude Code intentionally doesn't let plugins write to user settings. Several recommended tweaks make claudna's skills run cleanly. Add the snippets below to `~/.claude/settings.json` once.

> **Format:** these are partial JSON snippets. Merge them into your existing `settings.json` rather than replacing the whole file. Any JSON tool (`jq`, your editor) can do this.

### 3.1 Recommended permissions

These reduce the number of permission prompts you'll see while claudna's skills work. Permissions are additive — adding these never removes anything.

The minimum set (most skills need these):

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Write",
      "Edit",
      "Grep",
      "Glob",
      "WebFetch",
      "WebSearch",
      "Bash(git *)",
      "Bash(gh *)",
      "Bash(ls *)",
      "Bash(cat *)",
      "Bash(head *)",
      "Bash(tail *)",
      "Bash(wc *)",
      "Bash(which *)",
      "Bash(pwd *)",
      "Bash(find *)",
      "Bash(grep *)",
      "Bash(mkdir *)",
      "Bash(touch *)",
      "Bash(diff *)",
      "Bash(chmod *)",
      "Bash(cp *)",
      "Bash(mv *)",
      "Bash(curl *)",
      "Bash(lsof *)",
      "Bash(test *)"
    ]
  }
}
```

Optional categories — add only the ones whose skills you actually use:

| Category | Add when using | Permissions |
|---|---|---|
| **Python** | Python projects, formatters | `Bash(python *)`, `Bash(python3 *)`, `Bash(pip *)`, `Bash(pip3 *)`, `Bash(pytest *)`, `Bash(ruff *)` |
| **Node** | JS/TS projects | `Bash(node *)`, `Bash(npm *)`, `Bash(npx *)`, `Bash(prettier *)` |
| **Data & Analytics** | `/claudna:dbt`, `/claudna:neon-*`, `snowflake-analyst` agent | `Bash(snowsql *)`, `Bash(dbt *)`, `Bash(psql *)`, `Bash(pg_isready *)` |
| **Infrastructure CLIs** | `/claudna:railway-*`, `/claudna:vercel-*`, `/claudna:modal-*` | `Bash(railway *)`, `Bash(vercel *)`, `Bash(modal *)` |
| **Browser Automation** | `/claudna:design-review`, `/claudna:visual-crawl` | `Bash(/Applications/Google*)`, `Bash("/Applications/Google*)`, `Bash(google-chrome*)`, `Bash(chromium*)` |
| **Auto-skill-approval** | Bots / cron / non-interactive runs | See "Auto-skill-approval" expansion below |

#### Auto-skill-approval expansion

For bots, cron, and non-interactive runs that invoke claudna skills programmatically, add `Skill(...)` rules to prevent permission prompts. **Anthropic's docs do not specify whether `Skill()` matches against the bare skill name (`session-handoff`) or the plugin-namespaced form (`claudna:session-handoff`).** To be safe, write both forms. Permission rules are additive — extra rules don't hurt.

```json
{
  "permissions": {
    "allow": [
      "Skill(session-handoff)",            "Skill(session-handoff:*)",
      "Skill(claudna:session-handoff)",    "Skill(claudna:session-handoff:*)",
      "Skill(context-resume)",             "Skill(context-resume:*)",
      "Skill(claudna:context-resume)",     "Skill(claudna:context-resume:*)",
      "Skill(tech-debt)",                  "Skill(tech-debt:*)",
      "Skill(claudna:tech-debt)",          "Skill(claudna:tech-debt:*)",
      "Skill(security-audit)",             "Skill(security-audit:*)",
      "Skill(claudna:security-audit)",     "Skill(claudna:security-audit:*)",
      "Skill(product-enhance)",            "Skill(product-enhance:*)",
      "Skill(claudna:product-enhance)",    "Skill(claudna:product-enhance:*)",
      "Skill(docs-review)",                "Skill(docs-review:*)",
      "Skill(claudna:docs-review)",        "Skill(claudna:docs-review:*)",
      "Skill(frontend-performance-audit)", "Skill(frontend-performance-audit:*)",
      "Skill(claudna:frontend-performance-audit)", "Skill(claudna:frontend-performance-audit:*)"
    ]
  }
}
```

Extend the list for any other skills your bot invokes. If empirical testing confirms which form Claude Code actually matches, this section will be tightened in a future release.

### 3.2 statusLine (optional)

The plugin ships a `statusline.sh` that shows branch, lines changed, model, and context %. Claude Code doesn't support plugins shipping a statusLine declaration, so you wire it in your own `settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash ${HOME}/.claude/plugins/cache/Claudfather/claudna/0.2.0/plugin-hooks/statusline.sh"
  }
}
```

> **Known friction:** the version segment (`0.2.0`) is **hardcoded** because the plugin cache path includes the version. Every claudna release bump leaves this path pointing at a stale (or pruned) version directory, and the statusLine silently stops rendering. Workarounds, none of them great:
>
> 1. **Update the path on every `/plugin update`** — a `sed` / `jq` one-liner in your post-update routine. Simplest. The path you want is `~/.claude/plugins/cache/Claudfather/claudna/<latest-version>/plugin-hooks/statusline.sh`.
> 2. **Symlink to a stable path** — `ln -sfn ~/.claude/plugins/cache/Claudfather/claudna/0.2.0/plugin-hooks/statusline.sh ~/.local/bin/claudna-statusline.sh` and point the statusLine command at the symlink. You still re-run the symlink command on every plugin bump, but the statusLine entry in settings.json stays stable.
> 3. **Copy `statusline.sh` to a path you control** — `cp ~/.claude/plugins/cache/Claudfather/claudna/0.2.0/plugin-hooks/statusline.sh ~/.claude/hooks/claudna-statusline.sh` and point statusLine there. Frozen version (won't pick up improvements) but zero maintenance.
>
> Anthropic hasn't shipped a plugin-shipped statusLine surface yet (`statusLine` in `plugin.json` is not honored), so until they do, one of the three options is unavoidable.

### 3.3 Sandbox (recommended)

Sandbox configuration eliminates ~84% of permission prompts by auto-approving Bash commands that run inside the project directory (sandboxed) while leaving cross-directory commands and Read/Write/Edit tools subject to your normal `permissions.allow` rules:

```json
{
  "sandbox": {
    "enabled": true,
    "autoAllowBashIfSandboxed": true,
    "allowUnsandboxedCommands": true,
    "excludedCommands": []
  }
}
```

If you enable sandbox, you may also want the sandbox filesystem extensions for the orchestration skills that write to `/tmp/`:

```json
{
  "permissions": {
    "allow": [
      "Edit(/tmp/**)",
      "Edit(~/.claude/**)"
    ]
  }
}
```

### 3.4 Plugin-provided hooks (no action required)

The PreToolUse permission-expansion hook, the PostToolUse auto-format hook, and the Notification hook all ship with the plugin and auto-wire on enable. You don't need to add anything to `settings.json` for them. To verify they're firing, run `/plugin list` and confirm `claudna` is enabled, then trigger a `Write` to a `.py` file and watch `ruff` run.

---

## 4. Headless / CI / Docker Provisioning

Claude Code's `/plugin install` is interactive, but plugins can be auto-installed on session start by combining declarative settings with an environment variable. Use this pattern for bots, CI runners, and Docker images.

### 4.1 Settings template

Drop a `settings.json` like this into the image / runner's `~/.claude/`:

```json
{
  "extraKnownMarketplaces": {
    "Claudfather": {
      "source": { "source": "github", "repo": "Claudfather/clauDNA" }
    }
  },
  "enabledPlugins": {
    "claudna@Claudfather": true
  },
  "permissions": {
    "allow": ["Read", "Write", "Edit", "Bash(git *)", "..."],
    "defaultMode": "acceptEdits"
  }
}
```

The `"source": { "source": "github", ... }` nesting is **not a typo**. The outer key `"source"` is the field name on the marketplace entry; the inner `{ "source": "github", "repo": "..." }` is the [source descriptor](https://code.claude.com/docs/en/plugin-marketplaces) — `"source"` here is a discriminator naming the source type (`github`, `url`, `git`, etc.), and `"repo"` is the repo identifier for that type. Both keys are required by the Claude Code marketplace schema. If this looks ugly, blame the schema, not the docs.

Add whatever `permissions.allow` entries the bot needs. For locked-down CI, use `"defaultMode": "dontAsk"` which denies anything not on the allow list (plus the built-in read-only command set).

### 4.2 Launch command

Set `CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1` before invoking Claude Code. The plugin auto-installs before the first turn:

```bash
CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1 \
    claude -p "your prompt here" --allowedTools "Bash,Read,Edit"
```

For locked-down runs that need a single result with no surprises:

```bash
CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1 \
    claude --bare -p "your prompt" --settings ./bot-settings.json --allowedTools "Read"
```

`--bare` skips auto-discovery of hooks/skills/MCP/CLAUDE.md from the working dir, so the bot run is reproducible across machines.

### 4.3 Updates

Third-party marketplaces (which Claudfather is) **do not auto-update by default**, even with `FORCE_AUTOUPDATE_PLUGINS=1`. To pick up new claudna versions, run the update explicitly:

```bash
claude plugin update claudna@Claudfather
```

Wire this into your bot's startup script or a deploy hook so each run gets the latest published version. Or, if you want strict version pinning, set the plugin's `version` field in the marketplace listing and never call update — the bot stays on whatever version was last installed.

### 4.4 Dockerfile sketch

```dockerfile
FROM node:20-bookworm
RUN npm install -g @anthropic-ai/claude-code

# Copy the bot's pre-baked settings (marketplace + enabledPlugins declarations
# from §4.1, plus whatever permissions and defaults the bot needs).
COPY bot-settings.json /root/.claude/settings.json

# Pre-install claudna at image *build* time so cold container starts don't
# pay the marketplace-clone + install cost on every container boot.
RUN claude plugin marketplace add Claudfather/clauDNA && \
    claude plugin install claudna@Claudfather

# Set ANTHROPIC_API_KEY at runtime (e.g., via `docker run -e ANTHROPIC_API_KEY=...`).
ENV ANTHROPIC_API_KEY=""

# Belt-and-suspenders: if a container ever boots with a fresh ~/.claude/
# (e.g., volume mount that masks the baked-in install), CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1
# tells Claude Code to install enabledPlugins on session start. With the image
# baked above, this is a no-op; on a fresh mount, it's the rescue path.
ENV CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1

ENTRYPOINT ["claude", "--bare", "-p"]
```

The two install paths (`RUN claude plugin install ...` at build time + `ENV CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1` at runtime) **are intentionally both present**: the build-time install delivers fast cold starts, and the runtime env var is the rescue path if a volume mount or fresh `~/.claude/` ever lands without the bake-in. Claude Code is idempotent here — the env var is a no-op when the plugin is already installed at the declared version.

---

## 5. Snowflake Key-Pair Authentication

Passwordless, browser-free Snowflake access via SnowSQL. This is the most fragile part of the setup, so it gets a dedicated section.

### 5.1 Login Name vs User Name

Snowflake has two different identifiers — they are often different and the distinction breaks people regularly:

| Identifier | What it is | How to find it |
|------------|------------|----------------|
| **Login Name** | What you authenticate with (often email) | What you type when logging in |
| **User Name** | Your Snowflake identity after login | `SELECT CURRENT_USER();` |

**Use the LOGIN NAME in your SnowSQL config, not the user name.**

### 5.2 Generate RSA Key Pair

```bash
mkdir -p ~/.snowflake
chmod 700 ~/.snowflake

openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.snowflake/rsa_key.p8 -nocrypt
chmod 600 ~/.snowflake/rsa_key.p8

openssl rsa -in ~/.snowflake/rsa_key.p8 -pubout -out ~/.snowflake/rsa_key.pub
```

### 5.3 Extract the Public Key

```bash
cat ~/.snowflake/rsa_key.pub | grep -v "PUBLIC KEY" | tr -d '\n' && echo ""
```

Outputs a single base64 string — copy it.

### 5.4 Register with Snowflake

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
2. The public key string from §5.3

### 5.5 Configure SnowSQL

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

### 5.6 Test

```bash
snowsql -c default -q "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE();"
```

No browser should open. If one does, see [Troubleshooting](#7-troubleshooting).

---

## 6. Shell Configuration

claudna ships shell aliases for git worktrees in [`shell/zshrc-additions.sh`](./shell/zshrc-additions.sh). To install:

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

The `/claudna:worktree` skill manages this interactively if you'd rather not memorize the aliases.

---

## 7. Telemetry

clauDNA can emit lightweight telemetry events when skills are invoked. Events are **local-only** -- written to a JSONL file on disk. clauDNA does not phone home. The fleet observability system (Claudlobby) can optionally push these events to Claudosseum.

### What's collected

Each event records:

| Field | Value |
|-------|-------|
| `event` | `"skill_invocation"` |
| `skill` | Skill name (e.g., `claudna:review-pr`) |
| `ts` | ISO 8601 timestamp (UTC) |
| `bot` | `BOT_NAME` env var, or `"interactive"` |
| `duration_ms` | `null` (not available in PostToolUse hooks) |
| `success` | `true` / `false` (heuristic based on error indicators in output) |

No prompts, tool arguments, file paths, or PII are captured.

### Where events go

Events are appended as JSONL to:

```
~/.claude/telemetry/skill-events.jsonl
```

Override the path with `CLAUDNA_TELEMETRY_PATH`.

### Enabling / disabling

| Context | Default | How to change |
|---------|---------|---------------|
| Interactive users | **Off** | Set `CLAUDNA_TELEMETRY=1` to enable |
| Fleet bots | **On** (Claudlobby sets `CLAUDNA_TELEMETRY=1`) | Set `CLAUDNA_TELEMETRY=0` to disable |

The hook checks `CLAUDNA_TELEMETRY` on every invocation and exits immediately if it's not `1`. There is no startup cost when telemetry is off.

### Auto-pruning

Entries older than 30 days are pruned automatically. Pruning runs opportunistically (roughly every 100th write) to avoid adding latency to normal skill invocations.

### Integration with fleet observability

Claudlobby's fleet observability system can read `skill-events.jsonl` and optionally push events to Claudosseum for fleet-wide dashboards. See Claudlobby's observability documentation for configuration.

---

## 8. Troubleshooting

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
- Check the public key on the user matches the public key on disk: extract via §5.3 and compare.

### Plugin hooks not running

Hooks ship in `plugin-hooks/hooks.json` inside the plugin and auto-wire on enable. If they're not firing:
- Confirm `/plugin list` shows `claudna` as enabled.
- Try `/reload-plugins`.
- Check `plugin-hooks/*.sh` are executable inside `~/.claude/plugins/cache/Claudfather/claudna/<ver>/`. (They should be — the plugin install handles permissions.)

### Status line not showing

Claude Code does not support statusLine declarations inside plugin manifests. The plugin ships a `statusline.sh` but you have to wire it in your own `settings.json` — see §3.2. If you added the snippet and it still doesn't show:

```bash
bash ~/.claude/plugins/cache/Claudfather/claudna/0.2.0/plugin-hooks/statusline.sh
```

Run that directly to see if the script itself errors. If it does, your shell environment is missing something (likely `gh` for branch info).

### Shell aliases not working

**Cause:** Haven't reloaded shell config.

**Fix:** `source ~/.zshrc`

### Permission prompts firing for things that should be allowlisted

**Cause:** Compound shell commands (e.g. `cmd1 && cmd2`, `cmd1 | cmd2`) bypass simple wildcard match.

**Fix:** claudna ships a `pretooluse-permissions.sh` hook that auto-approves compound commands when *every* sub-command matches an allow pattern. It's wired automatically via `plugin-hooks/hooks.json` when the plugin is enabled. Run `/plugin list` to confirm `claudna` is on. If the hook still doesn't fire, try `/reload-plugins`.

**Still getting prompted?** The hook splits on `&&`, `||`, `|`, and `;` only. Commands using other shell constructs fall through to the normal permission prompt:

- Command substitution: `$(cmd)` or `` `cmd` ``
- Process substitution: `<(cmd)` or `>(cmd)`
- Here-docs / here-strings: `<< EOF`, `<<<`
- Brace groups: `{ cmd1; cmd2; }`

This is by design — these constructs are too complex to split reliably. If you're seeing prompts for a compound form you use often, consider adding the full command as a single `Bash(...)` pattern in your allow list.

### Plugin not auto-updating

Third-party marketplaces don't auto-update by default. Run updates explicitly:

```bash
claude plugin update claudna@Claudfather
```

Bake this into your bot's startup or a deploy hook if you want each run to pick up the latest version.

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
- Review lessons when relevant (via `/claudna:lessons`)

### Core Principles
- **Simplicity First** — make every change as simple as possible
- **No Laziness** — find root causes, no temporary fixes
- **Minimal Impact** — changes should only touch what's necessary

---

**End of guide.** For day-to-day usage of skills, see the [README](./README.md). For the changelog, see [CHANGELOG.md](./CHANGELOG.md).
