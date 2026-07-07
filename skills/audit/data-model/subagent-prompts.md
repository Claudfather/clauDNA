# Subagent Prompt Templates

Reference material for the `/claudna:audit data-model` lens. These are the detailed instructions for each parallel subagent launched during the audit.

---

## Subagent A: Schema Discovery

Launch a general-purpose subagent:

**Prompt:** "Discover the complete data model in this codebase. Create the directory `/tmp/data-model-audit-<YYYY-MM-DD_HHMMSS>/research/` with mkdir -p, then write your findings to `/tmp/data-model-audit-<YYYY-MM-DD_HHMMSS>/research/schema-discovery.md` using the Write tool. Return a 2-4 line summary when done."

The subagent should:

1. **SQLAlchemy models** — grep for `declarative_base`, `DeclarativeBase`, `mapped_column`, `Column`, `relationship`, `ForeignKey`, `Index`, `UniqueConstraint`, `CheckConstraint`. Catalog all model classes with their columns, types, relationships, constraints, and indexes.
2. **Alembic migrations** — check `alembic/versions/` or similar. Read migration files to understand schema evolution. Note any columns/tables added in migrations but not reflected in ORM models.
3. **Raw SQL** — grep for `.sql` files, `text()` calls, `execute()` with SQL strings, `raw()` queries. Catalog any schema definitions or data access outside the ORM.
4. **Flag discrepancies** — if ORM models, migrations, and SQL files disagree about what exists, flag these as Model Drift.

**Research file format:**
```markdown
# Schema Discovery

## Entity Inventory
[For each model: name, file:line, columns with types, relationships, constraints, indexes]

## Migration History Summary
[Key schema changes, evolution pattern, most recent migration]

## Drift Findings
[Any discrepancies between ORM models, migrations, and SQL files]

## Raw SQL Catalog
[Any SQL outside the ORM, with file:line references]
```

---

## Subagent B: Code Path Tracing

Launch a general-purpose subagent:

**Prompt:** "Trace how this application interacts with its database. Write your findings to `/tmp/data-model-audit-<YYYY-MM-DD_HHMMSS>/research/code-path-tracing.md` using the Write tool (create the directory first with mkdir -p if needed). Return a 2-4 line summary when done."

The subagent should:

1. **Identify entry points** — API routes (FastAPI `@app.get`/`@router.post`, Flask `@app.route`), CLI commands (click/typer), background tasks (Celery `@app.task`, APScheduler), signal handlers, management commands.
2. **Trace through business logic** — for each entry point, follow the call chain through service layers, utilities, and helpers down to database interactions. Record the full path: endpoint → service → repository/query → table.
3. **Catalog data access** — every ORM query (`.query()`, `select()`, `session.execute()`), `db.session` call, raw SQL. For each, record: which tables/columns are read, which are written, what joins are performed, what filters are applied.
4. **Note query patterns** — eager vs lazy loading (`joinedload`, `selectinload`, `lazy='select'`), N+1 candidates (loops with lazy-loaded relationships), bulk vs individual operations, transaction boundaries (`session.commit()` placement).

**Scope management:** If the codebase has many entry points (>20), group by module/feature area. If the user specified a focus area in Step 1, prioritize depth there. For unfocused scans, prioritize breadth over depth.

**Research file format:**
```markdown
# Code Path Tracing

## Entry Points
[Grouped by type: API routes, CLI commands, background tasks, etc.]
[For each: file:line, HTTP method/path or command name]

## Data Access Patterns
[For each significant code path:]
[Entry point (file:line) → business logic (file:line) → DB call (file:line)]
[Tables/columns read, tables/columns written, joins, filters]

## Query Pattern Observations
[N+1 candidates with evidence]
[Eager/lazy loading patterns]
[Transaction boundary patterns]
[Bulk vs individual operation patterns]
```

---

## Subagent C: Convergence

Launch a third general-purpose subagent that reads both research files and builds the map.

**Prompt:** "Read the schema discovery and code path tracing research files in `/tmp/data-model-audit-<YYYY-MM-DD_HHMMSS>/research/`. Also read the codebase directly to verify and deepen the findings. Build a code-to-schema convergence map and write it to `/tmp/data-model-audit-<YYYY-MM-DD_HHMMSS>/research/convergence.md` using the Write tool. Return a summary of key findings (2-4 lines)."

The convergence subagent should:

- Build a matrix: which code paths touch which tables/columns
- Identify **unused schema elements**: columns/tables defined in ORM but never referenced in application code
- Identify **write-only columns**: written but never read back (possible dead data)
- Identify **read-hot tables**: tables queried by many different code paths
- Identify **god-tables**: tables accessed by many unrelated code paths (possible need for decomposition)
- Identify **structural workarounds**: code paths that do complex multi-step data assembly in Python when a simpler schema relationship would eliminate the need
- Identify **missing constraints**: business rules enforced only in Python (validation, uniqueness checks, allowed values) that have no corresponding DB constraint
- Identify **N+1 patterns**: code paths that lazy-load in loops where eager loading or a different query would be better
- Classify preliminary findings into the categories from the gap analysis categories reference
