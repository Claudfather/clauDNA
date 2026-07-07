---
name: modal
user-invocable: true
description: "Use for Modal serverless operations — deploy or roll back an app, stream, search, or debug logs, or check workspace status (apps, containers, secrets, volumes). Replaces /modal-deploy, /modal-logs, /modal-status."
argument-hint: "[deploy|logs|status] [app-or-args]"
requires:
  - cli: modal
    reason: "Modal CLI for deployment, log streaming, and workspace inspection"
---

# Modal

One engine for Modal serverless operations — `deploy`, `logs`, and `status` as verb modes over the `modal` CLI. Shared behavior lives in `skills/_shared/infra-cli-contract.md`; this file supplies only routing and the Modal deltas.

## Mode dispatch (contract §3)

Arguments to dispatch (first token = verb, the rest belong to the verb): $ARGUMENTS

No verb token → infer only when the request wording is unambiguous (e.g. "show me the logs" → `logs`); otherwise print this table and stop — never guess a destructive verb.

| Verb | When | Depth file |
|------|------|------------|
| `deploy` | Deploy an app to production, update an existing deployment, or roll back | `deploy.md` |
| `logs` | View, stream, or debug app or container logs | `logs.md` |
| `status` | Workspace dashboard — apps, containers, secrets, volumes, environments | `status.md` |

For the selected verb, read ONLY its depth file in this skill directory and follow it exactly — never load another verb's depth (contract §1, §3).

## Pre-flight deltas (contract §4)

Run the ladder before any verb, stopping at the first failure with concrete guidance:

1. **CLI installed** — `modal --version`; fallback `python -m modal --version` (separate parallel Bash calls, never chained). If both fail, tell the user to install with `pip install modal`. If only the fallback works, prefix all subsequent `modal` commands with `python -m modal`.
2. **Authenticated** — `modal token info`. On failure: `modal token new` (opens browser) or `modal token set --token-id <id> --token-secret <secret>` for headless auth; do not continue.
3. **Target discovery** (deploy and logs need a subject) — remaining args first, then config (`.modal.toml` / `modal.toml`), then the Grep tool with pattern `modal\.App|modal\.Stub|@app\.` and glob `*.py` with `output_mode: files_with_matches`, then ask the user.

Execution, output, and failure conventions are contract §5–§7; the depth files assume them. `deploy` is this engine's destructive verb — its confirmation gate lives in `deploy.md`; `logs` and `status` are read-only and never gate.
