---
name: railway-status
user-invocable: true
description: "Use when you want an overview of your Railway project -- services, deployments, environments, and metrics."
---

# Railway Status

Quick dashboard for your Railway project. Shows project info, services, recent deployments, environments, and resource metrics at a glance.

## Instructions

Follow these steps exactly in order.

---

### Step 0: Prerequisites

Run these checks in order. Stop at the first failure and guide the user.

**1. CLI installed?**
```bash
railway --version
```
- If the command fails (not found): tell the user to install with `npm install -g @railway/cli` or `brew install railway`

**2. Version check (minimum 4.27.3):**
```bash
railway --version
```
- If below 4.27.3: tell the user to update with `npm update -g @railway/cli`

**3. Authenticated?**
```bash
railway whoami --json
```
- If the command fails: tell the user to run `railway login`

**4. Project linked?**
```bash
railway status --json
```
- If the command fails: tell the user to run `railway link` to select a project

---

### Step 1: Project & Service Overview

```bash
railway status --json
```

Parse and present: project name, project ID, current environment, linked service.

### Step 2: All Services

```bash
railway service list --json
```

List all services with their current deployment status.

### Step 3: Recent Deployments

```bash
railway deployment list --limit 5 --json
```

Show the 5 most recent deployments: status, service, trigger, timestamp, commit.

### Step 4: Environments

```bash
railway environment list --json
```

List all environments (production, staging, PR environments, etc.).

### Step 5: Environment Variables

```bash
railway variables list --json
```

List variable **names only** — never display values. Note any common variables that appear unset.

### Step 6: Resource Metrics (if available)

Attempt to query Railway's GraphQL API for CPU and memory metrics of active services.

First, read the Railway config to get the auth token:
```bash
cat ~/.railway/config.json
```
Parse the JSON output to extract the value at `.user.token`. If the file doesn't exist or the token field is missing, skip this step and note: "GraphQL metrics unavailable -- token not found in ~/.railway/config.json"

Next, get the project ID:
```bash
railway status --json
```
Parse the JSON output to extract the `projectId` value.

Then, query the Railway GraphQL API using the extracted token and project ID (substitute the actual values into the command):
```bash
curl -s https://backboard.railway.com/graphql/v2 -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d "{\"query\": \"query { project(id: \\\"<PROJECT_ID>\\\") { services { edges { node { id name serviceInstances { edges { node { latestDeployment { id status } } } } } } } } }\"}"
```
Parse the JSON response to extract service names, deployment IDs, and statuses.

If the token is missing or any query fails, skip this step and note: "GraphQL metrics unavailable -- token not found in ~/.railway/config.json"

### Step 7: Present Dashboard

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
