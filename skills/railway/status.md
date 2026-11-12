# Railway — Status

Invoked by /claudna:railway in status mode. Pre-flight (CLI install, version gate, auth, project link) has already passed per the engine contract — do not re-run it.

Quick dashboard for your Railway project. Shows project info, services, recent deployments, environments, and resource metrics at a glance. Follow these steps in order.

Follow `../_shared/orchestration-guide.md` §1 before any file write. Raw variable output and private working data go only under native-session `<scratch>`; a sanitized requested dashboard report defaults to `<artifacts>/railway/status/<run>.md`. Never use cwd, operation IDs, or OS-temp paths as durable owners. Preserve the rule never to reveal variable values or Railway credentials. Finalize only the exact owned scratch after its writer exits, retaining any canonical artifact.

## Step 1: Project & Service Overview

```bash
railway status --json
```

Parse and present: project name, project ID, current environment, linked service.

## Step 2: All Services

```bash
railway service list --json
```

List all services with their current deployment status.

## Step 3: Recent Deployments

```bash
railway deployment list --limit 5 --json
```

Show the 5 most recent deployments: status, service, trigger, timestamp, commit.

## Step 4: Environments

```bash
railway environment list --json
```

List all environments (production, staging, PR environments, etc.).

## Step 5: Environment Variables

Its output holds the values, so send it to `<scratch>/vars.json` in the native-session private directory allocated per orchestration-guide §1 and show only the names:

```bash
railway variables list --json > <scratch>/vars.json
```

```bash
jq 'keys' <scratch>/vars.json
```

Never display a value. Note any common variables that appear unset. After the CLI and `jq` have exited, finalize only the exact scratch allocation and verify cleanup; retain the sanitized canonical report if one was requested.

## Step 6: Resource Metrics

The Railway CLI reports no CPU or memory figures, and reading them from the API would need the account's token. Do not read `~/.railway/config.json` or send its token: it covers every project on the account. Report metrics as "unavailable from the CLI; see the service's Metrics tab in the Railway dashboard".

## Step 7: Present Dashboard

Format all output as a clean summary:

```
Railway Dashboard
═══════════════════════════════════════════════════════
  Project:      [name] ([id])
  Environment:  [current env]
  Linked:       [service name]
═══════════════════════════════════════════════════════

Services
┌──────────────────┬───────────┬─────────────────────┐
│ Service          │ Status    │ Last Deploy         │
├──────────────────┼───────────┼─────────────────────┤
│ ...              │ ...       │ ...                 │
└──────────────────┴───────────┴─────────────────────┘

Recent Deployments
┌──────────────────┬───────────┬──────────┬──────────┐
│ Service          │ Status    │ Trigger  │ When     │
├──────────────────┼───────────┼──────────┼──────────┤
│ ...              │ ...       │ ...      │ ...      │
└──────────────────┴───────────┴──────────┴──────────┘

Environments: [list]
Variables: [count] variables set (names only shown above)
Metrics: [CPU/memory if available, or "unavailable"]
```
