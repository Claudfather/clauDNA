---
name: railway
user-invocable: true
description: "Use for Railway operations — deploy or roll back a service, view, filter, or debug logs, or check project status (services, deployments, environments, metrics). Replaces /railway-deploy, /railway-logs, /railway-status."
argument-hint: "[deploy|logs|status] [service-or-args]"
requires:
  - cli: railway
    reason: "Railway CLI (>=4.27.3 for deploy) for deployment, logs, and project inspection"
---

# Railway

One engine for Railway — `deploy`, `logs`, and `status` as verb modes over the Railway CLI. Shared behavior lives in `skills/_shared/infra-cli-contract.md`; this file supplies only routing and the Railway deltas.

## Mode dispatch (contract §3)

Arguments to dispatch (first token = verb, the rest belong to the verb): $ARGUMENTS

No verb token → infer only when the request wording is unambiguous (e.g. "show me the service logs" → `logs`); otherwise print this table and stop — never guess a destructive verb.

| Verb | When | Depth file |
|------|------|------------|
| `deploy` | Deploy a service, update an existing deployment, or roll back | `deploy.md` |
| `logs` | View, filter, or debug service logs | `logs.md` |
| `status` | Project overview — services, deployments, environments, metrics | `status.md` |

For the selected verb, read ONLY its depth file in this skill directory and follow it exactly — never load another verb's depth (contract §1, §3).

## Pre-flight deltas (contract §4)

Run the ladder before any verb, stopping at the first failure with concrete guidance:

1. **CLI installed** — `railway --version`. Not found → install with `npm install -g @railway/cli` or `brew install railway`. No fallback invocation exists.
2. **Minimum version >= 4.27.3** — parse the version from the same output. Below the gate → update with `npm update -g @railway/cli`.
3. **Authenticated** — `railway whoami --json`. Fails → run `railway login`.
4. **Target discovery** — `railway status --json` confirms a linked project. Fails → run `railway link` to select one. Service-level targets come from the verb arguments or the depth file.

Execution, output, and failure conventions are contract §5–§7; the depth files assume them. `deploy` is this engine's destructive verb — its confirmation gate lives in `deploy.md`; `logs` and `status` are read-only and never gate.
