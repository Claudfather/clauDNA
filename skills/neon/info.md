Invoked by /claudna:neon in info mode — do not load this file for any other verb. Pre-flight has already run per SKILL.md; `<DB_URL>` is the discovered connection string, plus `<PROJECT_ID>` / `<ORG_ID>` / optional `<API_KEY>` when present. Everything here is read-only and never gates (contract §5).

Quick database dashboard for Neon PostgreSQL: connection status, table inventory, database size, and branch overview at a glance. Run the steps below and present the output in a clean, formatted summary.

## Step 1: Connection test

```bash
pg_isready -d "<DB_URL>"
```

## Step 2: Database overview

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

## Step 3: Branch overview (degrades, never blocks)

Requires `<PROJECT_ID>` and `<ORG_ID>` from discovery. If either is missing, skip this step.

**With API key:**
```bash
timeout 10 npx neon branches list --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --api-key "<API_KEY>"
```

**Without API key:**
```bash
timeout 10 npx neon branches list --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

If the output contains "Awaiting authentication", skip and note "Branch listing: neon auth required".

## Step 4: Present results (contract §6 report)

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
(or "neon auth required — run `npx neon auth` to enable branch listing")
```
