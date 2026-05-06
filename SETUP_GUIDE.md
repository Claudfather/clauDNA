# Claude Code Developer Experience Setup Guide

This guide documents a complete setup of Claude Code for an opinionated developer experience, with optional Snowflake and dbt integrations.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Understanding the Configuration Hierarchy](#3-understanding-the-configuration-hierarchy)
4. [Global Setup (~/.claude/)](#4-global-setup-claude)
5. [Snowflake Key Pair Authentication](#5-snowflake-key-pair-authentication)
6. [Shell Configuration](#6-shell-configuration)
7. [Project-Level Setup](#7-project-level-setup)
8. [Self-Improvement & Lessons System](#8-self-improvement--lessons-system)
9. [Verification & Testing](#9-verification--testing)
10. [Usage Guide](#10-usage-guide)
11. [Troubleshooting](#11-troubleshooting)
12. [Reference: All Configuration Files](#12-reference-all-configuration-files)
13. [Appendix A: Quick Setup Script](#appendix-a-quick-setup-script)
14. [Appendix B: Power User Tips](#appendix-b-power-user-tips)
15. [Appendix C: Workflow Orchestration Principles](#appendix-c-workflow-orchestration-principles)

---

## 1. Overview

### What This Guide Covers

This guide sets up:

1. **Global Claude Code Configuration** - Settings, hooks, commands, and agents available in ALL projects
2. **Snowflake Key Pair Authentication** - Passwordless, browser-free Snowflake access via SnowSQL
3. **Shell Aliases** - Git worktree management for parallel Claude sessions
4. **Project-Level Configuration** - Example setup for a specific project

### Why This Setup?

Built around the core power-user practices for Claude Code:

- **Slash commands** automate repetitive workflows (commit, test, lint)
- **Subagents** handle complex tasks autonomously (code review, data analysis)
- **Hooks** automate quality checks (auto-format after every edit)
- **Persistent notes** capture learnings across sessions
- **Worktrees** enable parallel Claude sessions on different features
- **Key pair auth** eliminates Snowflake browser popups

### Architecture Overview

```
~/.claude/                          # GLOBAL (all projects)
├── settings.json                   # Model, permissions, hooks
├── commands/                       # Slash commands (/snowflake, /dbt, etc.)
├── agents/                         # Subagents (snowflake-analyst, dbt-engineer)
├── hooks/                          # Hook scripts (auto-format, notify)
├── notes/                          # Persistent notes across sessions
│   ├── projects/                   # Per-project learnings
│   ├── patterns/                   # Reusable patterns
│   ├── decisions/                  # Key decisions
│   └── lessons/
│       └── global.md               # GLOBAL lessons (apply to all projects)
└── docs/                           # This documentation

~/.snowflake/                       # Snowflake credentials
├── rsa_key.p8                      # Private key
└── rsa_key.pub                     # Public key

~/.snowsql/config                   # SnowSQL connection profiles

/path/to/project/                   # PROJECT-SPECIFIC
├── .claude/
│   ├── settings.json               # Project permissions
│   ├── commands/                   # Project-specific commands
│   ├── agents/                     # Project-specific agents
│   ├── todo.md                     # Current task plan (per-task)
│   └── lessons.md                  # PROJECT-SPECIFIC lessons
└── CLAUDE.md                       # Project instructions for Claude
```

### Lessons File Structure (Global vs Per-Project)

| File | Scope | When to Update | Examples |
|------|-------|----------------|----------|
| `~/.claude/notes/lessons/global.md` | ALL projects | Universal patterns | "SnowSQL needs absolute paths, not ~" |
| `/project/.claude/lessons.md` | One project | Project-specific rules | "This codebase uses X pattern for Y" |

**Rule of thumb:** If a lesson applies everywhere, put it in global. If it's specific to a codebase's conventions, put it in the project's `.claude/lessons.md`.

---

## 2. Prerequisites

### Required Software

| Software | Version | Purpose | Installation |
|----------|---------|---------|--------------|
| Claude Code | Latest | AI coding assistant | `npm install -g @anthropic-ai/claude-code` |
| SnowSQL | 1.4+ | Snowflake CLI | Download from Snowflake |
| OpenSSL | Any | Key generation | Pre-installed on macOS |
| Git | 2.20+ | Version control | `brew install git` |
| ruff | 0.1+ | Python linting/formatting | `pip install ruff` |
| zsh | 5.0+ | Shell | Default on macOS |

### Required Access

- **Snowflake account** with your username
- **Admin assistance** to register your public key (if you can't ALTER USER yourself)
- **GitHub access** (for gh CLI commands)

### Information You'll Need

Before starting, gather:

1. **Snowflake Account Identifier** (e.g., `XXXXXXX-YYYYYYY`)
2. **Snowflake Login Name** (often your email, e.g., `you@example.com`)
3. **Snowflake Username** (run `SELECT CURRENT_USER();` - may differ from login name)
4. **Default Warehouse** (e.g., `<YOUR_WAREHOUSE>`)
5. **Default Role** (e.g., `<YOUR_ROLE>`)
6. **Default Database/Schema** (e.g., `<YOUR_DATABASE>.PROD`)

---

## 3. Understanding the Configuration Hierarchy

Claude Code reads configuration from multiple locations, merged in this order (later overrides earlier):

1. **Managed settings** (enterprise) - `/etc/claude/settings.json`
2. **Global user settings** - `~/.claude/settings.json`
3. **Project settings** - `/project/.claude/settings.json`
4. **Local settings** - `/project/.claude/settings.local.json` (gitignored)

### What Goes Where?

| Configuration | Location | Shared? | Examples |
|--------------|----------|---------|----------|
| Personal tools | `~/.claude/` | No | Snowflake auth, personal aliases |
| Team standards | `/project/.claude/` | Yes (git) | Project conventions, shared commands |
| Local overrides | `/project/.claude/settings.local.json` | No | Machine-specific paths |

---

## 4. Global Setup (~/.claude/)

This section sets up configuration available in ALL your projects.

### 4.1 Create Directory Structure

```bash
# Create all required directories
mkdir -p ~/.claude/commands
mkdir -p ~/.claude/agents
mkdir -p ~/.claude/hooks
mkdir -p ~/.claude/notes/projects
mkdir -p ~/.claude/notes/patterns
mkdir -p ~/.claude/notes/decisions
mkdir -p ~/.claude/docs
```

### 4.2 Global Settings (~/.claude/settings.json)

This file configures:
- Default model (Opus 4.5)
- Status line (shows git branch)
- Pre-allowed permissions (no prompts for safe commands)
- Hooks (auto-format, notifications)

**Create the file:**

```bash
cat > ~/.claude/settings.json << 'EOF'
{
  "model": "opus",
  "statusLine": {
    "type": "command",
    "command": "~/.claude/hooks/statusline.sh"
  },
  "permissions": {
    "allow": [
      "Bash(snowsql:*)",
      "Bash(git:*)",
      "Bash(gh:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(head:*)",
      "Bash(tail:*)",
      "Bash(wc:*)",
      "Bash(which:*)",
      "Bash(pwd:*)",
      "Bash(find:*)",
      "Bash(grep:*)",
      "Bash(ruff:*)",
      "Bash(prettier:*)",
      "Bash(dbt:*)"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/auto-format.sh"
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/notify.sh"
          }
        ]
      }
    ]
  }
}
EOF
```

**Explanation of each section:**

| Section | Purpose |
|---------|---------|
| `model` | Use Opus 4.5 by default (best for coding) |
| `statusLine` | Custom status bar showing git branch |
| `permissions.allow` | Commands that won't prompt for permission |
| `hooks.PostToolUse` | Run auto-format after Write/Edit operations |
| `hooks.Notification` | Send macOS notification when Claude needs input |

### 4.3 Hook Scripts

#### 4.3.1 Auto-Format Hook

This hook automatically formats code after Claude writes or edits a file.

```bash
cat > ~/.claude/hooks/auto-format.sh << 'EOF'
#!/bin/bash
# Auto-format hook for Claude Code
# Runs after Write/Edit operations to format code

# Read the hook event from stdin
EVENT=$(cat)

# Extract the file path from the event
FILE_PATH=$(echo "$EVENT" | grep -o '"file_path":"[^"]*"' | cut -d'"' -f4)

# Exit if no file path found
if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Format based on file extension
case "$FILE_PATH" in
    *.py)
        # Python: use ruff if available
        if command -v ruff &> /dev/null; then
            ruff format "$FILE_PATH" 2>/dev/null
            ruff check --fix "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.js|*.jsx|*.ts|*.tsx|*.json|*.md)
        # JavaScript/TypeScript/JSON/Markdown: use prettier if available
        if command -v prettier &> /dev/null; then
            prettier --write "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.sql)
        # SQL: use sqlfluff if available
        if command -v sqlfluff &> /dev/null; then
            sqlfluff fix "$FILE_PATH" 2>/dev/null
        fi
        ;;
esac

exit 0
EOF

chmod +x ~/.claude/hooks/auto-format.sh
```

#### 4.3.2 Status Line Hook

Shows the current git branch in the Claude Code status bar.

```bash
cat > ~/.claude/hooks/statusline.sh << 'EOF'
#!/bin/bash
# Status line script for Claude Code
# Shows git branch and other useful context

# Get git branch if in a repo
branch=$(git branch --show-current 2>/dev/null)
if [ -n "$branch" ]; then
    # Truncate long branch names
    if [ ${#branch} -gt 20 ]; then
        branch="${branch:0:17}..."
    fi
    echo -n "⎇ $branch"
else
    echo -n "⎇ -"
fi
EOF

chmod +x ~/.claude/hooks/statusline.sh
```

#### 4.3.3 Notification Hook

Sends a macOS notification when Claude needs attention.

```bash
cat > ~/.claude/hooks/notify.sh << 'EOF'
#!/bin/bash
# Send macOS notification when Claude needs attention

MESSAGE=$(cat)
if [ -z "$MESSAGE" ]; then
    MESSAGE="Claude needs your attention"
fi

osascript -e "display notification \"$MESSAGE\" with title \"Claude Code\""
EOF

chmod +x ~/.claude/hooks/notify.sh
```

### 4.4 Slash Commands

Slash commands are invoked with `/command-name` in Claude Code.

#### 4.4.1 Snowflake Query Command (/snowflake)

```bash
cat > ~/.claude/commands/snowflake.md << 'EOF'
# Snowflake Query

Run ad-hoc Snowflake queries using SnowSQL with key pair authentication.

## Connection Profiles

Available connection profiles in `~/.snowsql/config`:
- **default** - General queries (warehouse=`<YOUR_WAREHOUSE>`, role=`<YOUR_ROLE>`)
- **dbt** - dbt models (database=`<YOUR_DATABASE>.PROD`)

## Usage

Run a query:
```bash
snowsql -c default -q "YOUR SQL HERE"
```

For multi-line or complex queries, use a heredoc:
```bash
snowsql -c default -q "$(cat <<'ENDSQL'
SELECT
    table_schema,
    table_name,
    row_count
FROM information_schema.tables
WHERE table_schema = 'PROD'
ORDER BY row_count DESC
LIMIT 10;
ENDSQL
)"
```

## Common Queries

**List databases:**
```bash
snowsql -c default -q "SHOW DATABASES;"
```

**List schemas in a database:**
```bash
snowsql -c default -q "SHOW SCHEMAS IN DATABASE <YOUR_DATABASE>;"
```

**List tables in a schema:**
```bash
snowsql -c default -q "SHOW TABLES IN SCHEMA <YOUR_DATABASE>.PROD;"
```

**Describe a table:**
```bash
snowsql -c default -q "DESCRIBE TABLE <YOUR_DATABASE>.PROD.table_name;"
```

**Sample data:**
```bash
snowsql -c default -q "SELECT * FROM <YOUR_DATABASE>.PROD.table_name LIMIT 10;"
```

## Output Formats

Use `-o output_format=FORMAT` for different output:
- `psql` (default) - PostgreSQL-style
- `csv` - Comma-separated
- `tsv` - Tab-separated
- `json` - JSON format

Example:
```bash
snowsql -c default -o output_format=csv -q "SELECT * FROM table LIMIT 10;"
```

## Instructions

When the user asks to query Snowflake:
1. Use the appropriate connection profile
2. Write and execute the SQL query
3. Present results clearly
4. Offer to refine or expand the query
EOF
```

#### 4.4.2 Tech Debt Command (/techdebt)

```bash
cat > ~/.claude/commands/techdebt.md << 'EOF'
# Tech Debt Finder

Find and report technical debt in the current codebase.

## Instructions

Scan the codebase for common technical debt patterns:

### 1. Duplicated Code
```bash
find . -name "*.py" -type f | head -50
```

Look for:
- Copy-pasted functions
- Similar logic in multiple places
- Repeated patterns that could be abstracted

### 2. TODO/FIXME Comments
```bash
grep -rn "TODO\|FIXME\|HACK\|XXX" --include="*.py" --include="*.js" --include="*.ts" . 2>/dev/null | head -30
```

### 3. Large Files
```bash
find . -name "*.py" -type f -exec wc -l {} + 2>/dev/null | sort -rn | head -10
```

Files over 300 lines may need splitting.

### 4. Complex Functions
Look for functions with:
- Deep nesting (>3 levels)
- Many parameters (>5)
- Multiple responsibilities

### 5. Missing Tests
Compare source files to test files - flag untested modules.

### 6. Outdated Dependencies
```bash
pip list --outdated 2>/dev/null | head -20
```

### 7. Dead Code
- Unused imports
- Unreachable code paths
- Commented-out code blocks

## Output

Provide a prioritized list:
1. **High Priority** - Bugs waiting to happen, security issues
2. **Medium Priority** - Maintainability concerns, duplication
3. **Low Priority** - Style issues, minor improvements

For each item, suggest a specific fix.
EOF
```

#### 4.4.3 dbt Command (/dbt)

```bash
cat > ~/.claude/commands/dbt.md << 'EOF'
# dbt Command Runner

Quick dbt operations.

## Authentication

Before running dbt commands, ensure Snowflake credentials are loaded in the shell — typically via `source .env` or a project-specific auth helper (e.g., `source ./scripts/auth.sh`). See your dbt project's README for the expected workflow.

## Quick Commands

**Build a model:**
```bash
dbt build --select model_name
```

**Run with upstream deps:**
```bash
dbt build --select +model_name
```

**Test only:**
```bash
dbt test --select model_name
```

**Compile (no run):**
```bash
dbt compile --select model_name
```

**Full refresh (for incremental):**
```bash
dbt run --select model_name --full-refresh
```

## Instructions

When user asks about dbt:
1. Confirm they're in the dbt project directory
2. Confirm Snowflake auth is loaded (project-specific — usually `source .env` or a helper script)
3. Run the appropriate command
4. Report results and any test failures
EOF
```

#### 4.4.4 Worktree Command (/worktree)

```bash
cat > ~/.claude/commands/worktree.md << 'EOF'
# Git Worktree Manager

Manage git worktrees for parallel Claude sessions.

## Why Worktrees?

Worktrees let you have multiple branches checked out simultaneously in separate directories. This enables:
- Running multiple Claude sessions in parallel on different features
- Keeping one "clean" worktree for analysis/reading
- Quick context switching without stashing

## Shell Aliases (in ~/.zshrc)

```bash
wt-new <branch>     # Create new worktree and cd into it
wt-list             # List all worktrees
wt-rm <path>        # Remove a worktree
wt-set a <path>     # Set 'za' alias to jump to path
```

## Quick Setup for Parallel Work

```bash
# From main repo, create worktrees for parallel features
wt-new feature-a
wt-new feature-b
wt-new analysis    # Read-only analysis worktree

# Set up quick jump aliases
wt-set a ~/Projects/myrepo-worktrees/feature-a
wt-set b ~/Projects/myrepo-worktrees/feature-b
wt-set c ~/Projects/myrepo-worktrees/analysis

# Now use za, zb, zc to hop between them
```

## Recommended Workflow

1. **Main repo** - Keep on main/master for quick reference
2. **Feature worktrees** - One per active feature, each with its own Claude session
3. **Analysis worktree** - Read-only, for logs and queries

## Instructions

When user asks about worktrees:
1. Show current worktrees: `git worktree list`
2. Help create new ones as needed
3. Suggest the parallel workflow pattern
EOF
```

#### 4.4.5 Notes Command (/notes)

```bash
cat > ~/.claude/commands/notes.md << 'EOF'
# Notes Manager

Maintain persistent notes across Claude sessions.

## Notes Directory

Global notes: `~/.claude/notes/`

Structure:
```
~/.claude/notes/
├── projects/           # Per-project learnings
│   ├── api-server.md
│   ├── data-pipeline.md
│   └── myproject.md
├── patterns/           # Reusable patterns discovered
│   ├── snowflake.md
│   ├── streamlit.md
│   └── python.md
└── decisions/          # Key decisions and rationale
    └── YYYY-MM-DD-topic.md
```

## Instructions

When asked to take notes or after completing significant work:

1. **Identify the category**:
   - Project-specific learning → `~/.claude/notes/projects/{project}.md`
   - General pattern/technique → `~/.claude/notes/patterns/{topic}.md`
   - Important decision → `~/.claude/notes/decisions/{date}-{topic}.md`

2. **Append to existing notes** (don't overwrite):
   ```markdown
   ## YYYY-MM-DD: Topic

   ### Context
   What was the task/problem?

   ### Solution
   What worked?

   ### Lessons
   - Key takeaway 1
   - Key takeaway 2
   ```

3. **Reference notes** when starting related work:
   - Check `~/.claude/notes/projects/{project}.md` before working on a project
   - Review patterns that might apply

## Commands

**Save a note:**
```bash
cat >> ~/.claude/notes/projects/myproject.md << 'ENDNOTE'
## 2024-01-15: Topic here

Content here...
ENDNOTE
```

**Read project notes:**
```bash
cat ~/.claude/notes/projects/myproject.md
```

**List all notes:**
```bash
find ~/.claude/notes -name "*.md" -type f
```

## Auto-Note Prompt

After completing a PR or significant task, Claude should ask:
> "Should I add notes about this work to `~/.claude/notes/projects/{project}.md`?"
EOF
```

#### 4.4.6 Notifications Command (/notifications)

```bash
cat > ~/.claude/commands/notifications.md << 'EOF'
# Notification Setup

Get notified when Claude needs your attention.

## Automatic Notifications

A notification hook is configured in `~/.claude/settings.json` that sends a macOS notification when Claude needs input.

## iTerm2 Built-in Notifications (Recommended)

For even better notifications, enable iTerm2's built-in alert:

1. **Open iTerm2 Preferences** (⌘,)
2. Go to **Profiles** → **Terminal**
3. Check **"Send notification when idle"**
4. Set idle time (e.g., 5 seconds)

Now iTerm2 will notify you when any terminal tab has been waiting for input.

### Additional iTerm2 Tips

**Tab Naming:**
Right-click a tab → "Edit Tab Title" to name your Claude sessions

**Tab Colors:**
Right-click a tab → "Tab Color" to color-code different worktrees/tasks

**Badge:**
Show current directory or custom text in the terminal background:
- Profiles → General → Badge → `\(session.path)`

## Testing

To test the notification hook works, Claude will trigger it when asking for input during long-running tasks.
EOF
```

### 4.5 Subagents

Agents are more autonomous than slash commands - they can execute multi-step workflows.

#### 4.5.1 Snowflake Analyst Agent

```bash
cat > ~/.claude/agents/snowflake-analyst.md << 'EOF'
# Snowflake Analyst Agent

Data analysis agent that queries Snowflake and provides insights.

## Purpose

Answer data questions by writing and executing Snowflake queries. Think like a data analyst - explore, query, and explain findings.

## Connection

Use SnowSQL with key pair auth:
```bash
snowsql -c default -q "YOUR QUERY"
```

## Process

1. **Understand the question** - What data do they need?

2. **Explore the schema** (if needed):
   ```bash
   snowsql -c default -q "SHOW SCHEMAS IN DATABASE <YOUR_DATABASE>;"
   snowsql -c default -q "SHOW TABLES IN SCHEMA <YOUR_DATABASE>.PROD;"
   snowsql -c default -q "DESCRIBE TABLE <YOUR_DATABASE>.PROD.table_name;"
   ```

3. **Write the query** - Start simple, then refine:
   - Sample data first to understand structure
   - Build up complexity incrementally
   - Use CTEs for readability

4. **Execute and analyze**:
   - Run the query
   - Interpret results
   - Identify patterns or anomalies

5. **Present findings**:
   - Summarize key insights
   - Include relevant numbers
   - Suggest follow-up questions

## Best Practices

- Always LIMIT queries during exploration
- Use appropriate aggregations (don't pull raw data unnecessarily)
- Consider query cost - prefer smaller warehouses when possible
- Explain your reasoning as you go

## Output Formats

For data export:
```bash
snowsql -c default -o output_format=csv -o header=true -q "..." > output.csv
```

## Example

User: "What are the top 10 tables by row count?"

```bash
snowsql -c default -q "
SELECT
    table_schema,
    table_name,
    row_count
FROM information_schema.tables
WHERE table_schema NOT IN ('INFORMATION_SCHEMA')
ORDER BY row_count DESC NULLS LAST
LIMIT 10;
"
```
EOF
```

#### 4.5.2 dbt Engineer Agent

```bash
cat > ~/.claude/agents/dbt-engineer.md << 'EOF'
# dbt Engineer Agent

Analytics engineering agent for dbt projects.

## Purpose

Write, review, and test dbt models. Think like an analytics engineer - focus on data modeling best practices, testing, and documentation.

## Prerequisites

Before running dbt commands, ensure Snowflake credentials are loaded — typically via `source .env`, a project-specific auth helper (e.g., `source ./scripts/auth.sh`), or env vars exported in your shell profile. After auth is loaded, dbt commands work normally.

## Common Commands

```bash
# Run models
dbt run                          # Run all models
dbt run --select model_name      # Run specific model
dbt run --select +model_name     # Run model and upstream deps
dbt run --select model_name+     # Run model and downstream deps

# Test
dbt test                         # Run all tests
dbt test --select model_name     # Test specific model

# Build (run + test)
dbt build --select model_name

# Compile (check SQL without running)
dbt compile --select model_name

# Generate docs
dbt docs generate
dbt docs serve
```

## Model Writing Best Practices

### Staging Models (stg_*)
```sql
-- models/staging/stg_source_table.sql
with source as (
    select * from {{ source('source_name', 'table_name') }}
),

renamed as (
    select
        id,
        created_at,
        column_name as cleaner_name
    from source
)

select * from renamed
```

### Intermediate Models (int_*)
- Join staging models
- Apply business logic
- Keep transformations focused

### Mart Models (fct_*, dim_*)
```sql
-- models/marts/fct_events.sql
{{ config(
    materialized='incremental',
    unique_key='event_id',
    cluster_by=['event_date']
) }}

with events as (
    select * from {{ ref('int_events') }}
)

select * from events
{% if is_incremental() %}
where event_date > (select max(event_date) from {{ this }})
{% endif %}
```

## Testing

Always add tests in schema.yml:
```yaml
models:
  - name: fct_events
    columns:
      - name: event_id
        tests:
          - unique
          - not_null
      - name: user_id
        tests:
          - not_null
          - relationships:
              to: ref('dim_users')
              field: user_id
```

## Process

1. **Understand requirements** - What data, what grain, what business logic?
2. **Check existing models** - `ls models/` and review for reuse
3. **Write the model** - Follow naming conventions (stg_, int_, fct_, dim_)
4. **Add tests** - At minimum: unique, not_null on keys
5. **Compile first** - `dbt compile --select model_name` to check SQL
6. **Run and test** - `dbt build --select model_name`
7. **Document** - Add description in schema.yml

## Code Review Checklist

When reviewing dbt models:
- [ ] Follows naming conventions
- [ ] Has appropriate tests
- [ ] Uses refs instead of hardcoded table names
- [ ] CTEs are well-named and focused
- [ ] Incremental logic is correct (if applicable)
- [ ] No SELECT * in final output
- [ ] Column names are clear and consistent
EOF
```

---

## 5. Snowflake Key Pair Authentication

This section sets up passwordless Snowflake authentication that works from the command line without browser popups.

### 5.1 Understanding Login Name vs User Name

**IMPORTANT:** Snowflake has two different identifiers:

| Identifier | What it is | How to find it |
|------------|-----------|----------------|
| **Login Name** | What you authenticate with (often email) | What you type when logging in |
| **User Name** | Your Snowflake identity after login | `SELECT CURRENT_USER();` |

These are often different! For example:
- Login name: `you@example.com`
- User name: `<YOUR_USERNAME>`

**You must use the LOGIN NAME in your SnowSQL config, not the user name.**

### 5.2 Generate RSA Key Pair

```bash
# Create secure directory for keys
mkdir -p ~/.snowflake
chmod 700 ~/.snowflake

# Generate 2048-bit RSA private key (PKCS8 format, no password)
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.snowflake/rsa_key.p8 -nocrypt

# Secure the private key
chmod 600 ~/.snowflake/rsa_key.p8

# Generate corresponding public key
openssl rsa -in ~/.snowflake/rsa_key.p8 -pubout -out ~/.snowflake/rsa_key.pub

# Verify files were created
ls -la ~/.snowflake/
```

### 5.3 Extract Public Key for Snowflake

Run this command to get the public key content (without headers):

```bash
cat ~/.snowflake/rsa_key.pub | grep -v "PUBLIC KEY" | tr -d '\n' && echo ""
```

This outputs a long string like:
```
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
```

**Save this string - you'll need it for the next step.**

### 5.4 Register Public Key with Snowflake

**You or a Snowflake admin must run this SQL:**

```sql
ALTER USER your_username SET RSA_PUBLIC_KEY='paste_public_key_here';
```

**Example:**
```sql
ALTER USER <YOUR_USERNAME> SET RSA_PUBLIC_KEY='MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyjW3RWrLgatIQculOJiL...';
```

**If you get a permission error:**
```
SQL access control error: Insufficient privileges to operate on user
```

You need to ask an admin to run the ALTER USER command. Send them:
1. Your username (`SELECT CURRENT_USER();`)
2. Your public key (from step 5.3)

**To verify the key was registered:**
```sql
DESC USER your_username;
-- Look for RSA_PUBLIC_KEY property
```

### 5.5 Configure SnowSQL

Create or update `~/.snowsql/config`:

```bash
cat > ~/.snowsql/config << 'EOF'
# Default connection using key pair auth (no password needed!)
[connections]
accountname = YOUR_ACCOUNT_IDENTIFIER
username = your_login_name@example.com
private_key_path = /Users/YOUR_USERNAME/.snowflake/rsa_key.p8

# Named connection profile - Analytics
[connections.default]
accountname = YOUR_ACCOUNT_IDENTIFIER
username = your_login_name@example.com
private_key_path = /Users/YOUR_USERNAME/.snowflake/rsa_key.p8
warehousename = YOUR_WAREHOUSE
rolename = YOUR_ROLE

# Named connection profile - DBT
[connections.dbt]
accountname = YOUR_ACCOUNT_IDENTIFIER
username = your_login_name@example.com
private_key_path = /Users/YOUR_USERNAME/.snowflake/rsa_key.p8
warehousename = YOUR_WAREHOUSE
dbname = YOUR_DATABASE
schemaname = YOUR_SCHEMA
rolename = YOUR_ROLE

[variables]

[options]
auto_completion = True
log_file = ~/.snowsql/log
log_level = INFO
timing = True
output_format = psql
key_bindings = emacs
repository_base_url = https://sfc-repo.snowflakecomputing.com/snowsql
EOF
```

**IMPORTANT:** Replace these placeholders with your values:
- `YOUR_ACCOUNT_IDENTIFIER` → e.g., `XXXXXXX-YYYYYYY`
- `your_login_name@example.com` → Your Snowflake login (often email)
- `/Users/YOUR_USERNAME/` → Your home directory path
- `YOUR_WAREHOUSE` → e.g., `<YOUR_WAREHOUSE>`
- `YOUR_ROLE` → e.g., `<YOUR_ROLE>`
- `YOUR_DATABASE` → e.g., `<YOUR_DATABASE>`
- `YOUR_SCHEMA` → e.g., `PROD`

**Critical notes:**
1. Use **absolute paths** for `private_key_path` (not `~/.snowflake/...`)
2. Use your **login name** (email), not user name
3. Don't include `authenticator = SNOWFLAKE_JWT` - it's auto-detected

### 5.6 Test the Connection

```bash
# Test with named profile
snowsql -c default -q "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE();"
```

**Expected output:**
```
+----------------+----------------+---------------------+
| CURRENT_USER() | CURRENT_ROLE() | CURRENT_WAREHOUSE() |
|----------------+----------------+---------------------|
| <YOUR_USERNAME>   | <YOUR_ROLE>    | <YOUR_WAREHOUSE>        |
+----------------+----------------+---------------------+
1 Row(s) produced.
```

**No browser should open!** If it does, check:
1. Is the public key registered? (`DESC USER ...`)
2. Is your login name correct? (email vs username)
3. Is the private key path absolute?

---

## 6. Shell Configuration

### 6.1 Git Worktree Aliases

Add these to your `~/.zshrc` (or `~/.bashrc` for bash):

```bash
cat >> ~/.zshrc << 'EOF'

# ===== Git Worktree Aliases =====
# Create a new worktree: wt-new feature-name
wt-new() {
    if [ -z "$1" ]; then
        echo "Usage: wt-new <branch-name>"
        return 1
    fi
    local repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
    if [ -z "$repo_root" ]; then
        echo "Not in a git repository"
        return 1
    fi
    local repo_name=$(basename "$repo_root")
    local worktree_path="${repo_root}-worktrees/$1"
    git worktree add -b "$1" "$worktree_path" && cd "$worktree_path"
    echo "Created worktree at $worktree_path"
}

# List all worktrees: wt-list
alias wt-list='git worktree list'

# Remove a worktree: wt-rm worktree-path
wt-rm() {
    if [ -z "$1" ]; then
        echo "Usage: wt-rm <worktree-path-or-name>"
        return 1
    fi
    git worktree remove "$1" && echo "Removed worktree: $1"
}

# Quick jump aliases (set these per-session as needed)
# Usage: wt-set a /path/to/worktree  -> then use 'za' to jump there
wt-set() {
    if [ -z "$1" ] || [ -z "$2" ]; then
        echo "Usage: wt-set <letter> <path>"
        echo "Example: wt-set a ~/Projects/myrepo-worktrees/feature-x"
        return 1
    fi
    alias "z$1"="cd $2"
    echo "Set z$1 -> $2"
}
EOF
```

### 6.2 Activate the Aliases

```bash
source ~/.zshrc
```

### 6.3 Using Worktrees

```bash
# Navigate to your repo
cd ~/Projects/myrepo

# Create worktrees for parallel work
wt-new feature-a    # Creates ~/Projects/myrepo-worktrees/feature-a
wt-new feature-b    # Creates ~/Projects/myrepo-worktrees/feature-b

# Set up quick jump aliases
wt-set a ~/Projects/myrepo-worktrees/feature-a
wt-set b ~/Projects/myrepo-worktrees/feature-b

# Now you can:
za    # Jump to feature-a
zb    # Jump to feature-b

# List all worktrees
wt-list

# Remove a worktree when done
wt-rm ~/Projects/myrepo-worktrees/feature-a
```

---

## 7. Project-Level Setup

This section shows how to set up Claude Code for a specific project.

### 7.1 Create Project .claude Directory

```bash
cd /path/to/your/project
mkdir -p .claude/commands .claude/agents
```

### 7.2 Create CLAUDE.md

Create a `CLAUDE.md` file in your project root:

```markdown
# CLAUDE.md - Project Instructions

This file provides project-specific guidance for Claude Code.

## Project Overview

(Describe your project - what it does, tech stack, etc.)

## Development Workflow

1. Make changes
2. Run linter: `ruff check .`
3. Run formatter: `ruff format .`
4. Run tests: `pytest`
5. Before PR: run full test suite

## Code Style & Conventions

(List your project's conventions)

## Commands Reference

```sh
# Verification commands
ruff check .          # Lint
ruff format .         # Format
pytest               # Test

# Git workflow
git status
git diff
```

## Things Claude Should NOT Do

(List common mistakes to avoid)

---

_Update this file whenever Claude makes a mistake._
```

### 7.3 Project-Specific Settings

Create `.claude/settings.json` for project-specific permissions:

```json
{
  "permissions": {
    "allow": [
      "Bash(pytest:*)",
      "Bash(python:*)",
      "Bash(pip:*)",
      "Bash(ruff:*)",
      "Bash(streamlit:*)"
    ]
  }
}
```

### 7.4 Project-Specific Commands

Create commands in `.claude/commands/` for project-specific workflows.

**Example: /commit-push-pr**

```bash
cat > .claude/commands/commit-push-pr.md << 'EOF'
# Commit, Push, and Create PR

## Current State

```bash
git status
```

```bash
git diff --stat
```

```bash
git log --oneline -5
```

## Instructions

1. Review the changes
2. Stage all relevant changes
3. Create a descriptive commit message
4. Push to remote
5. Create a PR using `gh pr create`

Before committing, run verification:
```bash
ruff check . && pytest -x -q
```
EOF
```

### 7.5 Commit to Git

```bash
git add CLAUDE.md .claude/
git commit -m "Add Claude Code configuration"
```

---

## 8. Self-Improvement & Lessons System

This section implements the self-improvement loop from the Workflow Orchestration principles. The goal is to capture lessons from corrections so Claude doesn't repeat mistakes.

### 8.1 Understanding the Two-Tier Lessons Structure

| Tier | Location | Scope | When to Use |
|------|----------|-------|-------------|
| **Global** | `~/.claude/notes/lessons/global.md` | All projects | Universal patterns (tool quirks, general best practices) |
| **Project** | `/project/.claude/lessons.md` | One project | Project-specific conventions, codebase patterns |

**Examples:**

- **Global lesson:** "SnowSQL requires absolute paths, not ~ expansion"
- **Project lesson:** "This codebase namespaces session state with project ID"

### 8.2 Create Global Lessons File

```bash
mkdir -p ~/.claude/notes/lessons

cat > ~/.claude/notes/lessons/global.md << 'EOF'
# Global Lessons

Patterns and rules learned from corrections. Review when relevant (via `/lessons`).

---

_Add lessons below this line after corrections_
EOF
```

### 8.3 Create Project Lessons File (Per-Project)

In each project, create:

```bash
mkdir -p tasks

cat > .claude/lessons.md << 'EOF'
# [Project Name] Lessons

Project-specific patterns and rules. Review when relevant (via `/lessons`).

---

_Add lessons below this line after corrections_
EOF
```

### 8.4 The Self-Improvement Loop

After ANY correction from a user, Claude should:

1. **Acknowledge** the correction
2. **Identify** if it's global or project-specific
3. **Write** the lesson in this format:

```markdown
## YYYY-MM-DD: [Category] Brief Title

**Mistake:** What was done wrong
**Correction:** What should have been done
**Rule:** General rule to prevent this in the future
```

4. **Append** to the appropriate file:

```bash
# For global lessons
cat >> ~/.claude/notes/lessons/global.md << 'EOF'

## 2026-02-02: [Tool Use] Descriptive Title

**Mistake:** ...
**Correction:** ...
**Rule:** ...
EOF

# For project lessons
cat >> .claude/lessons.md << 'EOF'

## 2026-02-02: Descriptive Title

**Mistake:** ...
**Rule:** ...
EOF
```

### 8.5 Reviewing Lessons (On Demand)

When relevant (especially for complex tasks or areas where past mistakes occurred), review lessons:

```bash
# Review global lessons
cat ~/.claude/notes/lessons/global.md

# Review project lessons (if in a project)
cat .claude/lessons.md 2>/dev/null
```

### 8.6 Lesson Categories

Use these categories to organize global lessons:

| Category | Examples |
|----------|----------|
| `[Code Style]` | Formatting, naming conventions |
| `[Architecture]` | Design patterns, structure decisions |
| `[Testing]` | Test coverage, verification approaches |
| `[Git]` | Commit messages, PR workflow |
| `[Tool Use]` | Bash, SQL, CLI tools, APIs |
| `[Communication]` | How to explain, when to ask |

### 8.7 Task Management Files

Task management files live in the `.claude/` directory alongside other project-specific Claude configuration:

```
/project/.claude/
├── settings.json  # Project permissions
├── todo.md        # Current task plan with checkable items
└── lessons.md     # Project-specific lessons
```

**.claude/todo.md format:**

```markdown
# Task: [Brief Description]

## Plan
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

## Progress Notes
[Updated as work progresses]

## Review
[Added when task is complete]
```

---

## 9. Verification & Testing

### 9.1 Verify Global Setup

```bash
# Check all files exist
ls -la ~/.claude/settings.json
ls -la ~/.claude/commands/
ls -la ~/.claude/agents/
ls -la ~/.claude/hooks/

# Test hooks are executable
~/.claude/hooks/statusline.sh
~/.claude/hooks/notify.sh  # Should show a notification
```

### 8.2 Verify Snowflake Connection

```bash
# Test connection (no browser should open)
snowsql -c default -q "SELECT 'Connection successful!' as status;"

# Test a real query
snowsql -c default -q "SELECT CURRENT_USER(), CURRENT_ROLE();"
```

### 8.3 Verify Shell Aliases

```bash
# Reload shell config
source ~/.zshrc

# Test worktree commands
cd /path/to/any/git/repo
wt-list
```

### 8.4 Test in Claude Code

Start Claude Code and try:

```
/snowflake "SHOW DATABASES"
```

This should:
1. Run without prompting for Snowflake password
2. Display the list of databases
3. Not open a browser

---

## 10. Usage Guide

### 10.1 Daily Workflow

**Starting a session:**
1. Open terminal
2. Navigate to project: `cd ~/Projects/myproject`
3. Start Claude: `claude`
4. (Optional) Use Plan mode for complex tasks: Press Shift+Tab twice

**Using slash commands:**
- `/snowflake "your query"` - Run Snowflake queries
- `/dbt` - dbt operations
- `/techdebt` - Find tech debt
- `/worktree` - Manage worktrees
- `/notes` - Manage notes

**Using agents:**
- "Use snowflake-analyst to find the largest tables"
- "Use dbt-engineer to review this model"

### 10.2 Parallel Claude Sessions

```bash
# Create worktrees
cd ~/Projects/myproject
wt-new feature-a
wt-new feature-b

# Set up jump aliases
wt-set a ~/Projects/myproject-worktrees/feature-a
wt-set b ~/Projects/myproject-worktrees/feature-b

# Open terminals and start Claude in each
# Terminal 1: za && claude
# Terminal 2: zb && claude
```

### 10.3 Updating CLAUDE.md

After Claude makes a mistake:
1. Correct Claude
2. Say: "Update CLAUDE.md so you don't make that mistake again"
3. Review and commit the update

---

## 11. Troubleshooting

### Snowflake "JWT token is invalid"

**Cause:** Usually wrong username format

**Fix:**
1. Check your login name vs user name:
   ```sql
   SELECT CURRENT_USER();  -- This is the USER name
   ```
2. Your SnowSQL config should use the LOGIN name (often email)
3. Verify with: `snowsql -a ACCOUNT -u "you@example.com" --private-key-path ~/.snowflake/rsa_key.p8 -q "SELECT 1;"`

### Snowflake "No such file" for private key

**Cause:** Using `~` instead of absolute path

**Fix:** Use `/Users/yourname/.snowflake/rsa_key.p8` not `~/.snowflake/rsa_key.p8`

### Hooks not running

**Cause:** Not executable or wrong path

**Fix:**
```bash
chmod +x ~/.claude/hooks/*.sh
```

### Status line not showing

**Cause:** Script not executable or error in script

**Fix:**
```bash
# Test script directly
~/.claude/hooks/statusline.sh

# Make executable
chmod +x ~/.claude/hooks/statusline.sh
```

### Shell aliases not working

**Cause:** Haven't reloaded shell config

**Fix:**
```bash
source ~/.zshrc
```

---

## 12. Reference: All Configuration Files

### File Locations Summary

| File | Purpose |
|------|---------|
| `~/.claude/settings.json` | Global model, permissions, hooks |
| `~/.claude/commands/*.md` | Global slash commands |
| `~/.claude/agents/*.md` | Global subagents |
| `~/.claude/hooks/*.sh` | Hook scripts |
| `~/.claude/notes/` | Persistent notes |
| `~/.snowflake/rsa_key.p8` | Snowflake private key |
| `~/.snowflake/rsa_key.pub` | Snowflake public key |
| `~/.snowsql/config` | SnowSQL connection profiles |
| `~/.zshrc` | Shell aliases |
| `/project/CLAUDE.md` | Project instructions |
| `/project/.claude/` | Project-specific config |

### Complete ~/.claude/settings.json

```json
{
  "model": "opus",
  "statusLine": {
    "type": "command",
    "command": "~/.claude/hooks/statusline.sh"
  },
  "permissions": {
    "allow": [
      "Bash(snowsql:*)",
      "Bash(git:*)",
      "Bash(gh:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(head:*)",
      "Bash(tail:*)",
      "Bash(wc:*)",
      "Bash(which:*)",
      "Bash(pwd:*)",
      "Bash(find:*)",
      "Bash(grep:*)",
      "Bash(ruff:*)",
      "Bash(prettier:*)",
      "Bash(dbt:*)"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/auto-format.sh"
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/notify.sh"
          }
        ]
      }
    ]
  }
}
```

### Complete ~/.snowsql/config Template

```ini
# Default connection using key pair auth
[connections]
accountname = YOUR_ACCOUNT
username = you@example.com
private_key_path = /Users/YOUR_USERNAME/.snowflake/rsa_key.p8

# Analytics connection
[connections.default]
accountname = YOUR_ACCOUNT
username = you@example.com
private_key_path = /Users/YOUR_USERNAME/.snowflake/rsa_key.p8
warehousename = YOUR_WAREHOUSE
rolename = YOUR_ROLE

# DBT connection
[connections.dbt]
accountname = YOUR_ACCOUNT
username = you@example.com
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
key_bindings = emacs
repository_base_url = https://sfc-repo.snowflakecomputing.com/snowsql
```

---

## Appendix A: Quick Setup Script

For automated setup, save and run this script:

```bash
#!/bin/bash
# Claude Code Quick Setup Script
# Run with: bash setup-claude-code.sh

set -e

echo "=== Claude Code Developer Experience Setup ==="

# Create directories
echo "Creating directories..."
mkdir -p ~/.claude/{commands,agents,hooks,notes/{projects,patterns,decisions},docs}
mkdir -p ~/.snowflake

echo "Directories created."
echo ""
echo "Next steps:"
echo "1. Generate Snowflake keys (see Section 5.2)"
echo "2. Register public key with Snowflake admin (see Section 5.4)"
echo "3. Create ~/.snowsql/config (see Section 5.5)"
echo "4. Copy hook scripts from the guide (see Section 4.3)"
echo "5. Copy command files from the guide (see Section 4.4)"
echo "6. Copy agent files from the guide (see Section 4.5)"
echo "7. Create ~/.claude/settings.json (see Section 4.2)"
echo "8. Add shell aliases to ~/.zshrc (see Section 6.1)"
echo ""
echo "See full guide at: ~/.claude/docs/CLAUDE_CODE_SETUP_GUIDE.md"
```

---

## Appendix B: Power User Tips

Habits that consistently raise output quality with Claude Code:

1. **Run multiple Claudes in parallel** - Use git worktrees
2. **Start complex tasks in Plan mode** (Shift+Tab twice)
3. **Invest in your CLAUDE.md** - Update it after every correction
4. **Create slash commands** for workflows you do multiple times a day
5. **Use subagents** for complex, multi-step tasks
6. **Give Claude verification loops** - Tests, lint, typecheck = 2-3x quality
7. **Use voice dictation** (fn x2 on macOS) - 3x faster than typing

---

## Appendix C: Workflow Orchestration Principles

Advanced principles for Claude's behavior (include in your CLAUDE.md):

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately – don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `.claude/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons when relevant (via `/lessons`)

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes – don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests – then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

### Task Management Flow

1. **Plan First**: Write plan to `.claude/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `.claude/todo.md`
6. **Capture Lessons**: Update `.claude/lessons.md` after corrections

### Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

---

**End of Guide**
