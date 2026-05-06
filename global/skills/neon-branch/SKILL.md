---
name: neon-branch
description: "Use when you need to create, list, delete, or reset Neon database branches for safe experimentation."
argument-hint: "[branch action: create, list, delete, reset]"
---

# Neon Branch

Create, list, and manage Neon database branches. Branches are instant copy-on-write snapshots — use them for safe experimentation, pre-migration testing, and disposable dev environments.

## Connection Discovery

Before running any command, discover connection details:

1. Use the **Read tool** to read `.env` in the project root (and `.env.local` if it exists)
2. Look for these variables:
   - **Database URL**: `DATABASE_URL`, `NEON_PROD_URL`, `NEON_DATABASE_URL`, `POSTGRES_URL`, `PG_URL`, `NEON_DEV_URL`
   - **Project config**: `NEON_PROJECT_ID`, `NEON_ORG_ID`
   - **API key** (optional): `NEON_API_KEY`
3. If `NEON_PROJECT_ID` or `NEON_ORG_ID` is missing, ask the user
4. If `NEON_API_KEY` is found, include `--api-key "<API_KEY>"` in all `neonctl` commands. If not found, omit the flag entirely.

Store all discovered values and use them directly in commands — never use `source .env`.

## Authentication

The `neonctl` CLI supports multiple auth methods. **Try them in this order — stop at the first one that works:**

### Step 1: Check existing auth

**With API key (if found in .env):**
```bash
timeout 10 npx neonctl me --api-key "<API_KEY>"
```

**Without API key:**
```bash
timeout 10 npx neonctl me
```

- If output shows a table with Login/Email/Name — **auth is good**, proceed to Commands
- If output contains "Awaiting authentication" — auth is needed, continue to Step 2

### Step 2: Try browser OAuth
Tell the user auth is needed, then run:
```bash
npx neonctl auth
```
This opens a browser window (60-second timeout). After auth completes, re-run the check from Step 1.

### Step 3: If all else fails
Tell the user:
> No valid Neon credentials found. Options:
> 1. Run `npx neonctl auth` to authenticate via browser
> 2. Create an API key at https://console.neon.tech/app/settings/api-keys and add `NEON_API_KEY=<key>` to `.env`
>
> An API key enables fully headless operation (no browser needed).

## Project Details

These values are discovered from `.env` at runtime. Example shape:

```
Project: <PROJECT_NAME>
Project ID: <NEON_PROJECT_ID>
Org ID: <NEON_ORG_ID>
Production branch: production (default, primary)
Development branch: development
```

## Commands

All neonctl commands require `--project-id` and `--org-id`. Use the values discovered from `.env`.

In all examples below, include `--api-key "<API_KEY>"` only if `NEON_API_KEY` was found in `.env`. Otherwise omit that flag.

### List Branches
```bash
npx neonctl branches list --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

### Create Branch (from production)
```bash
npx neonctl branches create --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --name "<branch-name>" --output json
```

Name conventions:
- `claude/<purpose>` — for agent-created branches (e.g., `claude/debug-issue-123-2026-02-12`)
- `dev/<feature>` — for development work
- `test/<description>` — for testing

### Create Branch at Point-in-Time
```bash
npx neonctl branches create --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --name "<branch-name>" --parent "production@2026-02-12T00:00:00Z" --output json
```

Note: Point-in-time branching is limited by the project's history retention window (varies per Neon plan).

### Get Connection String for Branch
```bash
npx neonctl connection-string "<branch-name>" --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --pooled --database-name <DB_NAME> --role-name neondb_owner
```

Then use the returned URL to query the branch:
```bash
psql "<BRANCH_URL>" -c "SELECT count(*) FROM <YOUR_TABLE> WHERE is_current = true;"
```

### Delete Branch
```bash
npx neonctl branches delete "<branch-name>" --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

**Always clean up agent-created branches when done.**

## Instructions

When the user asks to manage branches:

1. **Discover connection details** by reading `.env` (and `.env.local`) with the Read tool. Extract `NEON_PROJECT_ID`, `NEON_ORG_ID`, and optionally `NEON_API_KEY`.
2. **Check auth** — run the auth check from Step 1 above; if it fails, walk through the fallback chain
3. **Execute the requested operation** using the commands above, with all values inlined directly (no `source .env`, no shell variables)
4. **For create operations**, always report back the branch name and connection string
5. **For destructive operations** (delete), confirm with the user first unless it's a `claude/*` branch the agent created in this session

## Workflow: Safe Experimentation

This workflow uses multiple separate commands. Run each as its own Bash call (do not chain with `&&`).

**Step 1: Create a branch**
```bash
npx neonctl branches create --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --name "claude/experiment-YYYYMMDD-HHMM" --output json
```

**Step 2: Get connection string**
```bash
npx neonctl connection-string "claude/experiment-..." --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --pooled --database-name <DB_NAME> --role-name neondb_owner
```

**Step 3: Run experimental queries (read-write OK on branches)**
```bash
psql "<BRANCH_URL>" -c "DELETE FROM <STAGING_TABLE> WHERE ..."
```
```bash
psql "<BRANCH_URL>" -c "UPDATE <YOUR_TABLE> SET ..."
```

**Step 4: Clean up when done**
```bash
npx neonctl branches delete "claude/experiment-..." --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

## Limits

Neon free tier allows up to 10 branches. Check current branch count before creating new ones. Always delete `claude/*` branches when analysis is complete.

$ARGUMENTS
