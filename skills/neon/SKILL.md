---
name: neon
user-invocable: true
description: "Use for Neon PostgreSQL operations — query (run SQL, explore schema), branch (create, list, delete, or reset database branches for safe experimentation), or info (connection and size overview). Replaces /neon-branch, /neon-info, /neon-query."
argument-hint: "[query|branch|info] [sql-or-args]"
requires:
  - cli: psql
    reason: "PostgreSQL client — query execution (query verb) and connection tests (branch/info verbs)"
  - cli: neon
    reason: "Neon CLI — branch management (branch verb) and project/branch listing (info verb)"
---

# Neon

One engine for Neon PostgreSQL — `query`, `branch`, and `info` as verb modes. Shared behavior lives in `../_shared/infra-cli-contract.md`; this file supplies only routing and the Neon deltas.

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

1. **CLI installed** — `query` needs `psql --version` only (neon is not required). `branch` and `info` need neon: probe `neon --version`, fallback `npx neon@6.2.3 --version` (separate parallel Bash calls); if only the fallback works, run every neon command as `npx neon@6.2.3` in place of `neon`. Both also use `psql`.
2. **Authenticated — non-interactive; never the device-code flow.** neon verbs only. A bare `neon me` with no credential drops into the interactive OAuth device-code login, which blocks forever in an unattended/tmux context (#222). The CLI reads `NEON_API_KEY` from its environment, so a key never goes on a command line (no `--api-key`). Two more things the CLI does shape the probe: its help, which it prints for `--help`, for a bare `neon` and for a command group without its subcommand (`neon branches`), shows `NEON_API_KEY`'s value as a default, so `<NEON>` runs complete verbs only, and anything else runs with the key removed (`env -u NEON_API_KEY neon ...`); and when a key is rejected, it deletes the stored `neon auth` login under `$XDG_CONFIG_HOME/neonctl` (default `~/.config/neonctl`). So first make a private directory with `mktemp -d` (only you can read it; `<scratch>` below is its path), then pick `<NEON>`, the form every neon command in the depth files runs as: `NEON_API_KEY` is non-empty in the environment (`[ -n "${NEON_API_KEY:-}" ] && echo set`) → `env XDG_CONFIG_HOME=<scratch> neon`, so a rejected key has no stored login to delete; else it is set in the project's `.env` (`python3 "<claudna-root>/scripts/env_from_file.py" .env --has NEON_API_KEY`; `<claudna-root>` per `../_shared/claudna-root.md`) → `python3 "<claudna-root>/scripts/env_from_file.py" .env NEON_API_KEY -- env XDG_CONFIG_HOME=<scratch> neon`; else → `neon`, which uses the stored login if there is one. With only the npx fallback, `npx neon@6.2.3` replaces `neon` in each form. Probe with `timeout 10 <NEON> me` (a bound, so a device-code fall-through can't hang — stored `neon auth` creds return in ~1s, an unauthenticated probe is killed at 10s). A non-zero exit (or "Awaiting authentication" in the output) means not logged in. On failure, stop: `Neon not authenticated — set NEON_API_KEY for headless use, or run neon auth interactively`. Verb deltas: `query` has no auth probe — the connection is the credential; `info` degrades on auth failure (skips its branch section with a note) instead of stopping; `branch` hard-requires auth and carries the recovery ladder in `branch.md`.
3. **Target discovery** — how `psql` reaches the database; the depth files call the chosen form `<PSQL>`. A connection string is a credential: it never goes into a command, the session, or any process's argv, so never Read `.env` for it and never `source` it. In order: a libpq service the user names, or `PGSERVICE` → `psql "service=<name>"`; `DATABASE_URL` set in the environment (`[ -n "${DATABASE_URL:-}" ] && echo set`) → `python3 "<claudna-root>/scripts/env_from_file.py" --url-env DATABASE_URL -- psql`; libpq's own variables (`PGHOST` and the like) already set → plain `psql`; a variable in the project's `.env` (then `.env.local`) → find its NAME with `python3 "<claudna-root>/scripts/env_from_file.py" .env --has DATABASE_URL NEON_PROD_URL NEON_DATABASE_URL POSTGRES_URL PG_URL NEON_DEV_URL` (it prints the first name that holds a value, never the value; ask with `NEON_DEV_URL` first when the user says dev/development), then `python3 "<claudna-root>/scripts/env_from_file.py" .env <NAME>=@libpq -- psql`; else ask the user. `--url-env` and `@libpq` turn the URL into libpq's own variables (`PGHOST`, `PGPASSWORD`, …), because psql does not read a URL from `PGDATABASE`. A match from a `DEV`-named variable is dev; any other is treated as production. neon verbs also need `NEON_PROJECT_ID` and `NEON_ORG_ID`. They are identifiers, not credentials, and they go into commands, so read one at a time — `printenv NEON_PROJECT_ID` from the environment, else `python3 "<claudna-root>/scripts/env_from_file.py" .env NEON_PROJECT_ID -- printenv NEON_PROJECT_ID` from the project's file — and use a value only if it matches `^[A-Za-z0-9-]+$`. Never inline a credential into a command.

Execution, output, and failure conventions are contract §5–§7; the depth files assume them. Neon's destructive set: `branch delete`, `branch reset`, and mutating SQL (INSERT/UPDATE/DELETE/DDL) inside `query` — each gates on the §6 boxed summary plus an explicit yes; read-only paths (`info`, listings, SELECT-only queries) never gate.
