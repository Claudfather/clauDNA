Invoked by /claudna:neon in info mode — do not load this file for any other verb. Pre-flight has already run per SKILL.md: it chose `<PSQL>`, how psql reaches the database, and `<NEON>`, the form neon commands run as, plus `<PROJECT_ID>` / `<ORG_ID>` when present. Everything here is read-only and never gates (contract §5).

Quick database dashboard for Neon PostgreSQL: connection status, table inventory, database size, and branch overview at a glance. Run the steps below and present the output in a clean, formatted summary.

## Step 1: Connection test and database overview

Write this to `<sql-file>`, a file in `<scratch>` (`../_shared/orchestration-guide.md` §1), with the Write tool:

```sql
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
```

Then run it:

```bash
<PSQL> -X -f <sql-file>
```

Exit status 2 means the connection failed: report `Connection: FAILED` and carry on with Step 2. psql's error can echo parts of the connection; scrub it per the contract before quoting it.

## Step 2: Branch overview (degrades, never blocks)

Requires `<PROJECT_ID>` and `<ORG_ID>` from discovery. If either is missing, skip this step.

```bash
timeout 10 <NEON> branches list --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

If the output contains "Awaiting authentication", skip and note "Branch listing: neon auth required".

## Step 3: Present results (contract §6 report)

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
(or "neon auth required — run `neon auth` to enable branch listing")
```
