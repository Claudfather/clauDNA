---
name: vercel
user-invocable: true
description: "Use for Vercel operations — deploy to production or preview (or roll back), view, filter, or debug deployment logs, or check project status (deployments, domains, env vars, config). Replaces /vercel-deploy, /vercel-logs, /vercel-status."
argument-hint: "[deploy|logs|status] [args]"
requires:
  - cli: vercel
    reason: "Vercel CLI for deployments, logs, and project inspection"
---

# Vercel

One engine for Vercel — `deploy`, `logs`, and `status` as verb modes over the `vercel` CLI. Shared behavior lives in `skills/_shared/infra-cli-contract.md`; this file supplies only routing and the Vercel deltas.

## Mode dispatch (contract §3)

Arguments to dispatch (first token = verb, the rest belong to the verb): $ARGUMENTS

No verb token → infer only when the request wording is unambiguous (e.g. "pull the deployment logs" → `logs`); otherwise print this table and stop — never guess a destructive verb.

| Verb | When | Depth file |
|------|------|------------|
| `deploy` | Deploy to production or preview; update an existing deployment; roll back | `deploy.md` |
| `logs` | View, filter, or debug deployment logs | `logs.md` |
| `status` | Project overview — deployments, domains, env vars, config | `status.md` |

For the selected verb, read ONLY its depth file in this skill directory and follow it exactly — never load another verb's depth (contract §1, §3).

## Pre-flight deltas (contract §4)

Run the ladder before any verb, stopping at the first failure with concrete guidance:

1. **CLI installed** — `vercel --version`. No fallback command, no minimum-version gate. On failure: install with `npm install -g vercel`.
2. **Authenticated — non-interactive; never the device-code flow.** Bare `vercel whoami` (and `vercel whoami --token ""`) fall into the interactive device-code login, which blocks forever in an unattended/tmux context (#216). Probe without it: `$VERCEL_TOKEN` set → `vercel whoami --token "$VERCEL_TOKEN"` (rejects an invalid token at once); unset → `timeout 10 vercel whoami` (a bound, so a device-code fall-through can't hang — a stored `vercel login` returns in ~1s, an unauthenticated probe is killed at 10s). On failure, stop: `Vercel not authenticated — set VERCEL_TOKEN for headless use, or run vercel login interactively`.
3. **Target discovery** — the linked project: check `.vercel/project.json` (project is linked), then `vercel.json` at the repo root. If neither resolves it, have the user run `vercel link`, and ask which project only if discovery still fails.

Execution, output, and failure conventions are contract §5–§7; the depth files assume them. `deploy` is this engine's destructive verb — its confirmation gate lives in `deploy.md`; `logs` and `status` are read-only and never gate.
