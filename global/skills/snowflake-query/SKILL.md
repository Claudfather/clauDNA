---
name: snowflake-query
description: "Use when you need to run SQL queries against Snowflake or explore Snowflake schema and data."
---

# Snowflake Query

Execute ad-hoc Snowflake queries using SnowSQL with key pair authentication. Accepts raw SQL or natural language descriptions.

## Connection

Authentication uses key pair auth via connection profiles in `~/.snowsql/config`:
- **default** — General queries (warehouse=`<YOUR_WAREHOUSE>`, role=`<YOUR_ROLE>`)
- **dbt** — dbt models (database=`<YOUR_DATABASE>.PROD`)

Run a query:
```bash
snowsql -c default -q "YOUR SQL HERE"
```

For multi-line or complex queries, use a heredoc:
```bash
snowsql -c default -q "$(cat <<'EOF'
SELECT table_schema, table_name, row_count
FROM information_schema.tables
WHERE table_schema = 'PROD'
ORDER BY row_count DESC
LIMIT 10;
EOF
)"
```

## Procedure

### Step 1: Parse the Request

**If raw SQL provided:**
- Validate the query has an appropriate LIMIT clause
- Add LIMIT if missing (default: 100 for SELECT *, 1000 for aggregations)

**If natural language description:**
- Identify the target table(s)
- Construct appropriate SQL query
- Always include LIMIT clause

### Step 2: Validate Query Safety

**MUST include LIMIT for:**
- `SELECT *` queries
- Non-aggregated queries on fact tables
- Any query that could return unbounded rows

**Exceptions (LIMIT optional):**
- Aggregations with `GROUP BY` and constrained date range
- `COUNT(*)` queries
- `INFORMATION_SCHEMA` queries
- `SHOW` and `DESCRIBE` commands

**NEVER execute:**
- DROP, DELETE, TRUNCATE, CREATE statements
- Queries without schema qualification (must use `DATABASE.SCHEMA.TABLE`)

**LIMIT guidance:**

| Purpose | LIMIT |
|---------|-------|
| Quick sanity check | 10 |
| Pattern exploration | 100 |
| Sample analysis | 1,000 |
| Full export (rare) | User must explicitly request |

### Step 3: Execute Query

```bash
snowsql -c default -q "<SQL_QUERY>"
```

Use `-o output_format=FORMAT` for different output:
- `psql` (default) — PostgreSQL-style tables
- `csv` — comma-separated
- `tsv` — tab-separated
- `json` — JSON format

### Step 4: Format Results

- Use markdown tables for small result sets (<20 rows)
- Summarize large result sets with key statistics
- Highlight NULL values and data quality issues
- Offer to refine or expand the query

---

## Common Query Patterns

**Check table freshness:**
```sql
SELECT MAX(date) as latest_date, MIN(date) as earliest_date, COUNT(*) as total_rows
FROM <YOUR_DATABASE>.PROD.<TABLE_NAME>;
```

**Check data by category:**
```sql
SELECT <category_column>, COUNT(*) as row_count, MAX(date) as latest_date
FROM <YOUR_DATABASE>.PROD.<TABLE_NAME>
GROUP BY <category_column>
ORDER BY row_count DESC
LIMIT 50;
```

**Sample recent data:**
```sql
SELECT * FROM <YOUR_DATABASE>.PROD.<TABLE_NAME>
WHERE date >= CURRENT_DATE - 7
ORDER BY date DESC
LIMIT 100;
```

**Check for NULLs:**
```sql
SELECT
    COUNT(*) as total,
    COUNT(<COLUMN>) as non_null,
    COUNT(*) - COUNT(<COLUMN>) as null_count,
    ROUND(100.0 * (COUNT(*) - COUNT(<COLUMN>)) / COUNT(*), 2) as null_pct
FROM <YOUR_DATABASE>.PROD.<TABLE_NAME>;
```

**Compare dev vs prod:**
```sql
SELECT 'dev' as env, COUNT(*) as rows FROM <YOUR_DATABASE>.DEV.DEV_<USER>.<MODEL>
UNION ALL
SELECT 'prod' as env, COUNT(*) as rows FROM <YOUR_DATABASE>.PROD.<MODEL>;
```

**Table metadata:**
```sql
SELECT table_name, row_count, bytes / (1024*1024*1024) as size_gb, created, last_altered
FROM <YOUR_DATABASE>.INFORMATION_SCHEMA.TABLES
WHERE table_schema = 'PROD' AND table_name ILIKE '%<PATTERN>%'
ORDER BY row_count DESC
LIMIT 20;
```

**Column info:**
```sql
SELECT column_name, data_type, is_nullable
FROM <YOUR_DATABASE>.INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = 'PROD' AND table_name = '<TABLE_NAME>'
ORDER BY ordinal_position;
```

**List databases / schemas / tables:**
```bash
snowsql -c default -q "SHOW DATABASES;"
snowsql -c default -q "SHOW SCHEMAS IN DATABASE <YOUR_DATABASE>;"
snowsql -c default -q "SHOW TABLES IN SCHEMA <YOUR_DATABASE>.PROD;"
snowsql -c default -q "DESCRIBE TABLE <YOUR_DATABASE>.PROD.<TABLE_NAME>;"
```

---

## Troubleshooting

**Query timeout:**
- Add date filters to reduce scan
- Use smaller warehouse for simple queries
- Check if table is clustered and filter by cluster key

**Large result set:**
- Add or reduce LIMIT
- Use aggregations instead of raw SELECT
- Filter by date range

**Connection issues:**
- Verify `~/.snowsql/config` has the connection profile
- Check key pair files exist at the paths referenced in config
- Run `snowsql -c default -q "SELECT 1;"` to test connectivity
