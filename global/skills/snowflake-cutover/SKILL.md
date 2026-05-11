---
name: snowflake-cutover
description: "Use when you need to migrate a project's Snowflake connection to use artemis-python-tools with RSA key-pair auth support."
argument-hint: "[service account name or project context]"
allowed-tools:
  - "Bash(pip *)"
  - "Bash(python *)"
  - "Bash(pytest *)"
  - "Bash(git *)"
  - "Read(*)"
  - "Write(*)"
  - "Edit(*)"
  - "Grep(*)"
  - "Glob(*)"
---

# Snowflake Connection Cutover to artemis-python-tools

Migrate a project from custom Snowflake connection logic to the centralized
`artemis-python-tools` credential adapter pattern with RSA key-pair auth support.

Read `migration-steps.md` for the full procedure with code templates and commands.

## When to use

- Project has its own `snowflake.connector.connect()` calls
- Need to add RSA key-pair auth for service accounts
- Standardizing on `SYSTEM_SNOWFLAKE_*` env var naming
- Deploying to Railway/production where key files aren't on disk

## Pre-flight checks

Before starting, confirm:
- [ ] You have access to the project's deployment platform (Railway, etc.)
- [ ] You know whether the project uses a central Settings class or bare env vars
- [ ] Service account credentials are available (for RSA key-pair auth)

## Migration steps

Follow each step in `migration-steps.md` in order:

1. **Discover current connection code** — Find all `snowflake.connector.connect()` call sites, credential config, Settings classes, and test mocks
2. **Check artemis-python-tools dependency** — Install with `--no-deps` if missing; add to build command, not pyproject.toml deps
3. **Create credentials adapter** — Pattern A (Settings class, preferred) or Pattern B (bare env vars). The adapter MUST respect the project's existing settings management
4. **Refactor connection code** — Replace manual connection builders with `create_snowflake_connection()` calls; remove dead auth methods
5. **Rename env vars** — Migrate `SNOWFLAKE_*` to `SYSTEM_SNOWFLAKE_*`; add RSA key fields to Settings class if using Pattern A
6. **Update tests** — Mock the new adapter, drop auth-specific test coverage
7. **Deploy** — Set new env vars FIRST, deploy code, verify, then remove old vars

## Rollback guidance

If issues arise after deployment:
- The old `SNOWFLAKE_*` env vars are still present until Step 7.4 — revert the code deploy and the old config still works
- If old env vars were already removed, re-add them and revert the code change
- The credentials adapter is a single file — removing it and restoring the old connection methods is a clean revert

## Notes

- artemis-python-tools pins `fastapi==0.115.12` — always install with `--no-deps` to avoid conflicts
- Raw PEM content support (`SYSTEM_SNOWFLAKE_PRIVATE_KEY`) enables key-pair auth in environments where key files aren't on disk (Railway, containers)
- If a central Settings class exists, never bypass it with `SnowflakeCredentials.from_env()` — that creates a parallel config path
