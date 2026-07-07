Invoked by /claudna:neon in query mode — do not load this file for any other verb. Pre-flight (psql check, connection discovery) has already run per SKILL.md; `<DB_URL>` below is the discovered connection string, inlined directly into every command.

## Read-only guard

- The discovered URL counts as **production** unless it came from a `DEV`-named variable or the user explicitly targeted the dev database.
- **CRITICAL: All production queries MUST be wrapped in a read-only transaction:**

```bash
psql "<DB_URL>" -c "BEGIN TRANSACTION READ ONLY; YOUR SQL HERE; COMMIT;"
```

- **Mutating SQL (INSERT / UPDATE / DELETE / DDL) is destructive even inside this verb** (contract §5): before running it, present the §6 boxed summary (target database, environment, the exact statement) and ask "Ready to run? (y/n)" — do not proceed without an explicit yes.
- Production never runs mutating SQL — it stays read-only-wrapped, no exceptions. If the user wants to mutate, point at a development connection or a disposable Neon branch (`/claudna:neon branch`) instead.
- Development database (read-write allowed, after the gate above for mutations):

```bash
psql "<DB_URL>" -c "YOUR SQL HERE;"
```

## Running queries

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

## Output formats

- Default: psql table format
- `--csv` — CSV output
- `-x` — expanded/vertical format (one column per line)
- `-t` — tuples only (no headers/footers)
- `-A` — unaligned output (useful with `--csv`)

Examples:
```bash
psql "<DB_URL>" --csv -c "BEGIN TRANSACTION READ ONLY; SELECT * FROM <YOUR_TABLE> WHERE is_current = true LIMIT 10; COMMIT;"
```
```bash
psql "<DB_URL>" -x -c "BEGIN TRANSACTION READ ONLY; SELECT * FROM <YOUR_TABLE> WHERE is_current = true LIMIT 1; COMMIT;"
```

## Common explorations

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

## Flow

1. Confirm which environment the discovered URL targets — production by default, dev only when a `DEV`-named variable or the user's wording says so
2. **Always wrap production queries in `BEGIN TRANSACTION READ ONLY; ... COMMIT;`**
3. Gate mutating SQL per the read-only guard above before running anything
4. Use SQL equivalents for schema inspection (not `\dt`, `\d+`) — meta-commands don't work with `-c` + URL
5. Run the `psql` command with the URL inlined directly
6. Present results clearly (contract §6 report: status, target database, rows returned, any errors)
7. Offer to refine or expand the query
