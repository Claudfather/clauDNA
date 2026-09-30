Invoked by /claudna:neon in query mode — do not load this file for any other verb. Pre-flight (psql check, connection discovery) has already run per SKILL.md, and it chose `<PSQL>`, how `psql` reaches the database: a libpq service, a URL handed to psql's environment by `env_from_file.py`, or plain `psql`.

The connection string never appears in a command, in the session, or in any process's argv. Every statement goes in a file in `<scratch>` (`../_shared/orchestration-guide.md` §1), written with the Write tool, and runs with `-f`, so SQL is never parsed as shell. `-X` skips the user's `.psqlrc`.

## Read-only guard

- The target counts as **production** unless it came from a `DEV`-named variable or the user explicitly targeted the dev database.
- **CRITICAL: All production queries MUST be wrapped in a read-only transaction**, inside the SQL file:

```sql
BEGIN TRANSACTION READ ONLY;
-- your SQL here
COMMIT;
```

```bash
<PSQL> -X -f <sql-file>
```

- **Mutating SQL (INSERT / UPDATE / DELETE / DDL) is destructive even inside this verb** (contract §5): before running it, present the §6 boxed summary (target database, environment, the exact statement) and ask "Ready to run? (y/n)" — do not proceed without an explicit yes.
- Production never runs mutating SQL — it stays read-only-wrapped, no exceptions. If the user wants to mutate, point at a development connection or a disposable Neon branch (`/claudna:neon branch`) instead.
- Development database (read-write allowed, after the gate above for mutations): the same command, with the statement in the file unwrapped.

## Running queries

Write the query to `<sql-file>` in `<scratch>` with the Write tool, then run it:

```sql
BEGIN TRANSACTION READ ONLY;

SELECT
    schemaname,
    tablename,
    n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC
LIMIT 10;

COMMIT;
```

```bash
<PSQL> -X -f <sql-file>
```

## Output formats

- Default: psql table format
- `--csv` — CSV output
- `-x` — expanded/vertical format (one column per line)
- `-t` — tuples only (no headers/footers)
- `-A` — unaligned output (useful with `--csv`)

Examples:
```bash
<PSQL> -X --csv -f <sql-file>
```
```bash
<PSQL> -X -x -f <sql-file>
```

## Common explorations

Each block below is the content of `<sql-file>`; run it with `<PSQL> -X -f <sql-file>`. psql meta-commands (`\dt+`, `\d+ tablename`) work in a file too.

**List all tables with sizes:**
```sql
BEGIN TRANSACTION READ ONLY;
SELECT
    relname AS table_name,
    n_live_tup AS row_count,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
COMMIT;
```

**Describe a table (columns, types, nullability):**
```sql
BEGIN TRANSACTION READ ONLY;
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = '<YOUR_TABLE>'
ORDER BY ordinal_position;
COMMIT;
```

**List indexes on a table:**
```sql
BEGIN TRANSACTION READ ONLY;
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = '<YOUR_TABLE>';
COMMIT;
```

**Sample data from a table:**
```sql
BEGIN TRANSACTION READ ONLY;
SELECT * FROM <YOUR_TABLE> WHERE is_current = true LIMIT 5;
COMMIT;
```

**psql meta-commands:**
```sql
\dt+
```

## Flow

1. Confirm which environment the target is — production by default, dev only when a `DEV`-named variable or the user's wording says so
2. **Always wrap production queries in `BEGIN TRANSACTION READ ONLY; ... COMMIT;`**, in the SQL file
3. Gate mutating SQL per the read-only guard above before running anything
4. Write the SQL to a file in `<scratch>` with the Write tool; run `<PSQL> -X -f <sql-file>`
5. Present results clearly (contract §6 report: status, target database, rows returned, any errors). psql's own errors can echo parts of a connection string; scrub output per the contract before quoting it
6. Offer to refine or expand the query
