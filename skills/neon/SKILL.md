---
name: neon
user-invocable: true
description: "Use for Neon PostgreSQL operations — query (run SQL, explore schema), branch (create, list, delete, or reset database branches for safe experimentation), or info (connection and size overview). Replaces /neon-branch, /neon-info, /neon-query."
argument-hint: "[query|branch|info] [sql-or-args]"
requires:
  - cli: psql
    reason: "PostgreSQL client — query execution (query verb) and connection tests (branch/info verbs)"
  - cli: neonctl
    reason: "Neon CLI — branch management (branch verb) and project/branch listing (info verb)"
---

# Neon

One engine for Neon PostgreSQL — `query`, `branch`, and `info` as verb modes. Shared behavior lives in `skills/_shared/infra-cli-contract.md`; this file supplies only routing and the Neon deltas.

## Mode dispatch (contract §3)

Arguments to dispatch (first token = verb, the rest belong to the verb): $ARGUMENTS

No verb token → infer only when the request wording is unambiguous (a bare SQL statement or schema question → `query`); otherwise print this table and stop — never guess a destructive verb.

| Verb | When | Depth file |
|------|------|------------|
| `query` | Ad-hoc SQL, schema/data exploration, output formats | `query.md` |
| `branch` | Create, list, delete, or reset branches; branch connection strings | `branch.md` |
| `info` | Dashboard — connection status, DB size, tables, branch overview | `info.md` |

For the selected verb, read ONLY its depth file in this skill directory and follow it exactly — never load another verb's depth (contract §1, §3).

## Pre-flight deltas (contract §4)

Neon is the family's structural outlier: two CLIs instead of one, and the target is a connection string discovered from the environment, not a vendor config file. Check only what the selected verb needs:

1. **CLI installed** — `query` needs `psql --version` only (neonctl is not required). `branch` and `info` need neonctl: probe `neonctl --version`, fallback `npx neonctl --version` (separate parallel Bash calls); if only the fallback works, prefix every neonctl command with `npx`. Both also use `psql`/`pg_isready` for connection tests.
2. **Authenticated — non-interactive; never the device-code flow.** neonctl verbs only. A bare `neonctl me` (and `neonctl me --api-key ""`) drops into the interactive OAuth device-code login, which blocks forever in an unattended/tmux context (#222). Probe without it: a **non-empty** `NEON_API_KEY` was discovered → `neonctl me --api-key "<NEON_API_KEY>"` (rejects an invalid key at once); empty or unset → `timeout 10 neonctl me` (a bound, so a device-code fall-through can't hang — stored `neonctl auth` creds return in ~1s, an unauthenticated probe is killed at 10s). A non-zero exit (or "Awaiting authentication" in the output) means not logged in. On failure, stop: `Neon not authenticated — set NEON_API_KEY for headless use, or run neonctl auth interactively`. Verb deltas: `query` has no auth probe — the connection string is the credential; `info` degrades on auth failure (skips its branch section with a note) instead of stopping; `branch` hard-requires auth and carries the recovery ladder in `branch.md`.
3. **Target discovery** — connection string first: the `DATABASE_URL` environment variable; else Read `.env` then `.env.local` in the project root and take the first of `DATABASE_URL`, `NEON_PROD_URL`, `NEON_DATABASE_URL`, `POSTGRES_URL`, `PG_URL`, `NEON_DEV_URL` — prefer a `DEV`-named variable when the user says dev/development, otherwise the first match is treated as production; else ask the user. neonctl verbs additionally collect `NEON_PROJECT_ID`, `NEON_ORG_ID`, and optional `NEON_API_KEY` from the same sources — a set-but-empty `NEON_API_KEY` counts as **absent** (treat as unset; never inline a bare `--api-key ""`, which itself device-code-hangs, into the probe or any downstream command). Inline every discovered value directly into commands — never `source .env`, never shell variables.

Execution, output, and failure conventions are contract §5–§7; the depth files assume them. Neon's destructive set: `branch delete`, `branch reset`, and mutating SQL (INSERT/UPDATE/DELETE/DDL) inside `query` — each gates on the §6 boxed summary plus an explicit yes; read-only paths (`info`, listings, SELECT-only queries) never gate.
