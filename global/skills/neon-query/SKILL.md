---
name: neon-query
description: "Use when you need to run SQL queries against Neon PostgreSQL or explore database schema and data."
argument-hint: "[SQL query or exploration request]"
---

# Neon Query

Run ad-hoc SQL queries against Neon PostgreSQL databases using `psql`.

## Connection Discovery

Before running any command, discover the database connection URL:

1. Use the **Read tool** to read `.env` in the project root (and `.env.local` if it exists)
2. Look for a database URL variable. Check these names in order: `DATABASE_URL`, `NEON_PROD_URL`, `NEON_DATABASE_URL`, `POSTGRES_URL`, `PG_URL`, `NEON_DEV_URL`
3. Use the first matching URL you find as the connection string for all subsequent commands
4. If no database URL is found, ask the user for the connection string

When the user says "dev database" or "development", look for variables containing `DEV` (e.g., `NEON_DEV_URL`, `DATABASE_DEV_URL`). Otherwise default to the first URL found (typically production).

Store the discovered URL and use it directly in all `psql` commands — never use `source .env`.

## Usage

**CRITICAL: All production queries MUST be wrapped in a read-only transaction:**

```bash
psql "<DB_URL>" -c "BEGIN TRANSACTION READ ONLY; YOUR SQL HERE; COMMIT;"
```

For multi-line or complex queries, use a heredoc:
```bash
psql "<DB_URL>" <<'EOF'
BEGIN TRANSACTION READ ONLY;

SELECT
    schemaname,
    tablename,
    n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC
LIMIT 10;

COMMIT;
EOF
```

For development database (read-write allowed):
```bash
psql "<DB_URL>" -c "YOUR SQL HERE;"
```

## Output Formats

- Default: psql table format
- `--csv` - CSV output
- `-x` - Expanded/vertical format (one column per line)
- `-t` - Tuples only (no headers/footers)
- `-A` - Unaligned output (useful with `--csv`)

Examples:
```bash
psql "<DB_URL>" --csv -c "BEGIN TRANSACTION READ ONLY; SELECT * FROM <YOUR_TABLE> WHERE is_current = true LIMIT 10; COMMIT;"
```
```bash
psql "<DB_URL>" -x -c "BEGIN TRANSACTION READ ONLY; SELECT * FROM <YOUR_TABLE> WHERE is_current = true LIMIT 1; COMMIT;"
```

## Common Explorations

**IMPORTANT: psql meta-commands (`\dt`, `\d+`, etc.) do NOT work with the `-c` flag when using a connection URL. Use heredoc or SQL equivalents instead.**

**List all tables with sizes:**
```bash
psql "<DB_URL>" -c "BEGIN TRANSACTION READ ONLY;
SELECT
    relname AS table_name,
    n_live_tup AS row_count,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
COMMIT;"
```

**Describe a table (columns, types, nullability):**
```bash
psql "<DB_URL>" -c "BEGIN TRANSACTION READ ONLY;
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = '<YOUR_TABLE>'
ORDER BY ordinal_position;
COMMIT;"
```

**List indexes on a table:**
```bash
psql "<DB_URL>" -c "BEGIN TRANSACTION READ ONLY;
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = '<YOUR_TABLE>';
COMMIT;"
```

**Sample data from a table:**
```bash
psql "<DB_URL>" -c "BEGIN TRANSACTION READ ONLY; SELECT * FROM <YOUR_TABLE> WHERE is_current = true LIMIT 5; COMMIT;"
```

**If you need psql meta-commands** (`\dt+`, `\d+ tablename`, etc.), use heredoc:
```bash
psql "<DB_URL>" <<'EOF'
\dt+
EOF
```

## Instructions

When the user asks to query Neon:

1. **Discover the connection URL** by reading `.env` (and `.env.local` if it exists) with the Read tool. Look for `DATABASE_URL`, `NEON_PROD_URL`, `NEON_DATABASE_URL`, `POSTGRES_URL`, `PG_URL`, or `NEON_DEV_URL`. If none found, ask the user.
2. Default to the production URL unless the user specifies dev
3. **Always wrap production queries in `BEGIN TRANSACTION READ ONLY; ... COMMIT;`**
4. Use SQL equivalents for schema inspection (not `\dt`, `\d+`) — meta-commands don't work with `-c` + URL
5. Run the `psql` command with the URL inlined directly (no `source .env`, no shell variables)
6. Present results clearly
7. Offer to refine or expand the query

$ARGUMENTS
