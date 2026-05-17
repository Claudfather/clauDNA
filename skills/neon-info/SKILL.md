---
name: neon-info
user-invocable: true
description: "Use when you want a quick overview of your Neon PostgreSQL database -- connection status, tables, sizes, and branches."
requires:
  - cli: neonctl
    reason: "Neon CLI for project and branch listing"
  - cli: psql
    reason: "PostgreSQL client for connection checks"
---

# Neon Info

Quick database dashboard for Neon PostgreSQL. Shows connection status, table inventory, database size, and branch overview at a glance.

## Connection Discovery

Before running any command, discover connection details:

1. Use the **Read tool** to read `.env` in the project root (and `.env.local` if it exists)
2. Look for a database URL variable. Check these names in order: `DATABASE_URL`, `NEON_PROD_URL`, `NEON_DATABASE_URL`, `POSTGRES_URL`, `PG_URL`, `NEON_DEV_URL`
3. Also look for: `NEON_PROJECT_ID`, `NEON_ORG_ID`, and `NEON_API_KEY`
4. If no database URL is found, ask the user for the connection string

Store all discovered values and use them directly in commands — never use `source .env`.

## Instructions

1. Discover the connection URL and project details by reading `.env` (and `.env.local`) with the Read tool
2. Run the following commands and present the output in a clean, formatted summary

### Step 1: Connection Test
```bash
pg_isready -d "<DB_URL>"
```

### Step 2: Database Overview
```bash
psql "<DB_URL>" <<'EOF'
BEGIN TRANSACTION READ ONLY;

-- Database size
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;

-- PostgreSQL version
SELECT version();

-- Table inventory: name, row count, total size
SELECT
    relname AS table_name,
    n_live_tup AS row_count,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;

-- Active connections
SELECT count(*) AS active_connections FROM pg_stat_activity WHERE state = 'active';

COMMIT;
EOF
```

### Step 3: Branch Overview (if neonctl auth is available)

Try to list branches. This step requires `NEON_PROJECT_ID` and `NEON_ORG_ID` from the `.env` file. If either is missing, skip this step.

If `NEON_API_KEY` was found in `.env`, include the `--api-key` flag. Otherwise omit it.

**With API key:**
```bash
timeout 10 npx neonctl branches list --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --api-key "<API_KEY>"
```

**Without API key:**
```bash
timeout 10 npx neonctl branches list --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

If the output contains "Awaiting authentication", skip and note "Branch listing: neonctl auth required".

### Step 4: Present Results

Format the output as a summary:

```
## Neon Database Dashboard

**Connection:** [OK/FAILED]
**Database size:** [size]
**PostgreSQL version:** [version]
**Active connections:** [count]

### Tables
| Table | Rows | Size |
|-------|------|------|
| ...   | ...  | ...  |
| **Total** | **N** | **size** |

### Branches
| Name | State | Created |
|------|-------|---------|
| ...  | ...   | ...     |
(or "neonctl auth required — run `npx neonctl auth` to enable branch listing")
```
