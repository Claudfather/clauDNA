---
name: dbt
user-invocable: true
description: "Use when you need to run dbt commands against Snowflake -- build, test, compile, or full-refresh."
argument-hint: "[dbt command or model name]"
requires:
  - cli: dbt
    reason: "dbt CLI for model builds, tests, and compilation"
---

# dbt Command Runner

Quick dbt operations.

## Authentication

dbt typically needs Snowflake credentials available in the shell before any command runs. Most projects use one of:
- A `.env` file sourced via `source .env`
- A project-specific helper (e.g., `source <auth-helper>`) that exports `SNOWFLAKE_*` vars
- Direct env vars exported in `~/.zshrc` / `~/.bashrc`

If the project's CLAUDE.md documents an auth helper, use that. Otherwise ask the user how their dbt profile expects to authenticate.

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
2. Confirm Snowflake auth is loaded (check the project's auth helper or `.env`); see "Authentication" above
3. Run the appropriate command
4. Report results and any test failures
