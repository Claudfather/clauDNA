---
name: modal-status
user-invocable: true
description: "Use when you want an overview of your Modal workspace -- deployed apps, containers, secrets, and volumes."
requires:
  - cli: modal
    reason: "Modal CLI for workspace inspection"
---

# Modal Status

Quick dashboard for your Modal workspace. Shows deployed apps, running containers, secrets, volumes, environments, and GPU usage at a glance.

## Instructions

Follow these steps exactly in order.

---

### Step 0: Prerequisites

Run these checks in order. Stop at the first failure and guide the user.

**1. CLI installed?**

Run these as separate parallel Bash calls (never chain with `||` or `&&`):
```bash
modal --version
```
If that fails, try:
```bash
python -m modal --version
```
If both fail, tell the user to install with `pip install modal`. If only `python -m modal` works, note this and use `python -m modal` for all subsequent commands.

**2. Authenticated?**
```bash
modal token info
```
If the command fails, tell the user to run `modal token new` (opens browser) or `modal token set --token-id <id> --token-secret <secret>` for headless auth.

**3. Check environment:**
```bash
modal environment list --json
```
Note which environments exist and which is active. Default is used if `--env` is not specified.

---

### Step 1: Deployed Apps

```bash
modal app list --json
```

List all deployed and running apps: name, state, creation time.

### Step 2: Running Containers

```bash
modal container list --json
```

List all currently running containers: container ID, app, function, GPU type (if any).

### Step 3: Secrets

```bash
modal secret list --json
```

List secret **names only** — never display values. Note which environment each secret belongs to.

### Step 4: Volumes

```bash
modal volume list --json
```

List all volumes: name, creation time, environment.

### Step 5: Environments

```bash
modal environment list --json
```

List all environments and their web suffixes.

### Step 6: Check for Modal Config

Use the Read tool to check for project-level Modal configuration:
- Read `.modal.toml` (skip if it doesn't exist)
- Read `modal.toml` (skip if it doesn't exist)

Also check for Modal app files:
- Use the Glob tool with pattern `*.py` to find Python files
- Use the Grep tool with pattern `modal\.App|modal\.Stub|@app\.` and glob `*.py` with `output_mode: files_with_matches` to find Modal app files

### Step 7: Present Dashboard

Format all output as a clean summary:

```
Modal Dashboard
═══════════════════════════════════════════════════════
  Workspace:    [workspace name from token info]
  Environment:  [active environment]
  Environments: [list all]
═══════════════════════════════════════════════════════

Deployed Apps
┌──────────────────────────┬────────────┬─────────────────────┐
│ App                      │ State      │ Deployed            │
├──────────────────────────┼────────────┼─────────────────────┤
│ ...                      │ ...        │ ...                 │
└──────────────────────────┴────────────┴─────────────────────┘

Running Containers
┌──────────────────┬──────────────────┬────────────┬──────────┐
│ Container ID     │ App / Function   │ GPU        │ Status   │
├──────────────────┼──────────────────┼────────────┼──────────┤
│ ...              │ ...              │ ...        │ ...      │
└──────────────────┴──────────────────┴────────────┴──────────┘

Secrets: [count] configured
Volumes: [count] provisioned
  [list names and sizes if available]

Config: [.modal.toml found / not found]
App files: [list of .py files with modal imports]
```
