# Infra CLI Engine Contract

The shared skeleton for the infra engines — `/modal`, `/railway`, `/vercel`, `/neon`. Each engine is one skill with verb modes over one vendor CLI. Engines reference the sections below and supply only their CLI deltas; this file is the single place the shared behavior is defined.

## 1. Thin-body rule

An engine's `SKILL.md` contains routing and contract references only: frontmatter, the mode-dispatch table, and the tool-specific pre-flight deltas. Per-verb depth (procedures, command variants, health checks, report formats) lives in one support file per verb inside the skill directory (`deploy.md`, `logs.md`, `status.md`, …). **Read only the selected verb's file** — invoking `/modal status` must never load deploy/rollback text. Invocation-time body context is the cost this rule controls; the picker-time cost is controlled by the description.

## 2. Frontmatter conventions

- `name`: the bare tool name (`modal`, `railway`, `vercel`, `neon`).
- `description`: per SKILL_CONTRACT §2.1 — trigger-first, **every verb named in the description text** (fuzzy search must hit "logs" or "deploy" even though the verbs are positional args, not skills), and the rename breadcrumb last: `Replaces /<tool>-deploy, /<tool>-logs, /<tool>-status.` (bare slash form — the referenced skills no longer exist).
- `argument-hint`: `"[<verb>|<verb>|<verb>] [args]"` — first positional token is the verb.
- `requires`: the union of the verbs' dependencies, each with a reason. A verb that needs a dependency the others don't (e.g. neon's `psql`) keeps the reason verb-scoped so `check_dependencies` output stays interpretable.

## 3. Mode dispatch

1. Parse `$ARGUMENTS`. If the first token is a verb from the engine's table, that is the mode; the rest of the arguments belong to the verb.
2. No verb token → infer from the request wording only when one verb is unambiguous (e.g. "show me the logs" → `logs`). Otherwise **print the engine's mode table and stop** — never guess a destructive verb, and never block on a free-form question when a listed menu answers it.
   - **Headless / non-interactive contexts** (`claude -p`, subagent dispatch): the verb is **required** — never infer. A destructive verb invoked headlessly stops at its confirmation gate by design; report that the operation needs an interactive confirmation rather than proceeding.
3. The dispatch table maps each verb to its depth file: `<verb> → read <verb>.md in this skill directory and follow it exactly`.

## 4. Pre-flight ladder

Run before any verb, in order, stopping at the first failure with concrete guidance:

1. **CLI installed** — `<tool> --version`. Engines declare their fallback (e.g. modal: `python -m modal --version`; if only the fallback works, prefix all subsequent commands accordingly) and their minimum-version gate where one exists (e.g. railway ≥ 4.27.3 → `npm update -g @railway/cli`). Run candidate checks as separate parallel Bash calls, never chained.
2. **Authenticated** — the tool's auth probe (`modal token info`, `railway whoami --json`, `vercel whoami --token "$VERCEL_TOKEN"`, `neon me --api-key "$NEON_API_KEY"`). The probe **must be non-interactive**: fail fast on missing/invalid credentials — never launch an interactive or device-code login, which blocks forever unattended (#216, #222). Where a bare probe would fall through to interactive login (vercel, neon), the engine's delta supplies the guarded form. On failure, give the tool's login command; do not continue.
3. **Target discovery** — the verb's subject (app file, service, project, connection string) per the engine's delta: config files first (`.modal.toml`, `railway.json`, `vercel.json`, `.env`/`DATABASE_URL`), then codebase search, then ask the user.

## 5. Execution conventions

- Run commands as **separate Bash calls — never chain with `&&`, `||`, or `;`** (permission rules match per-command; chaining defeats them).
- Prefer `--json` output flags where the CLI offers them; parse rather than scrape.
- **Destructive verbs gate on explicit user confirmation** (deploy, delete, reset, rollback): present the boxed pre-action summary (§6) and ask "Ready to <verb>? (y/n)" — do not proceed without an explicit yes. Read-only verbs (logs, status, info, list, SELECT-only queries) never gate.
- Mutating SQL (INSERT/UPDATE/DELETE/DDL) counts as destructive even inside a "query" verb.

## 6. Output conventions

- **Before a destructive action:** a boxed summary (target, environment, git branch/commit, uncommitted-changes warning, whether an existing deployment will be updated).
- **After any verb:** a boxed report (status, target, key metrics, errors found), followed by concrete next steps on failure — the exact diagnostic command, and the rollback/stop options with their plan caveats.
- **Secrets are names, never values:** status/list output shows secret and env-var *names* (and timestamps) only — never their values. Verbs whose purpose is returning a credential (e.g. a branch connection string) are exempt by design.
- **Scrub CLI output before surfacing it.** The rule above is prose, and prose has leaked keys — this contract inlines `--api-key`/`--token` and connection strings into commands (§4/§5), so a raw stdout/stderr echo carries a live credential. Before quoting any command output in a report or error, scrub it with the shared redactor: capture the output to a file and run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/redact.py" <file>` — a bare command, no pipe (falls back to the highest-versioned `~/.claude/plugins/cache/Claudfather/claudna/*/scripts/redact.py` when `${CLAUDE_PLUGIN_ROOT}` is unset). It masks inlined credential-flag values, `scheme://user:pass@host` connection strings, and vendor key shapes while leaving hosts, project IDs, and `file:line` intact — the same convention as orchestration-guide §7. The credential-returning verbs exempted above are the only exception.

## 7. Failure handling

- Surface the CLI's stderr, scrubbed through the redactor (§6) — never paraphrase an error into vagueness, but never paste it raw either. An auth failure that echoes an inlined `--api-key`/`--token`, or a connection string in a DSN error, is a live credential: redact it, then show the rest verbatim.
- One retry for transient network failures; anything else stops with the error and the next diagnostic step.
- A failed health check after a deploy is a loud flag, not a footnote — show the failing endpoint/status first.

## 8. Adding a verb

New capability = a new row in the engine's dispatch table + a new `<verb>.md` depth file. It is never a new skill — that is the SKU anti-pattern this contract exists to prevent (see the Design Philosophy in the README).
