Invoked by /claudna:modal in status mode — pre-flight (contract §4) has already run; the remaining args may name an environment to scope to (`--env`).

# Status

Quick dashboard for the Modal workspace. Shows deployed apps, running containers, secrets, volumes, environments, and GPU usage at a glance. Read-only — never gates. Follow these steps exactly in order.

## Step 1: Environments

```bash
modal environment list --json
```

List all environments and their web suffixes. Note which is active — the default is used if `--env` is not specified.

## Step 2: Deployed Apps

```bash
modal app list --json
```

List all deployed and running apps: name, state, creation time.

## Step 3: Running Containers

```bash
modal container list --json
```

List all currently running containers: container ID, app, function, GPU type (if any).

## Step 4: Secrets

```bash
modal secret list --json
```

List secret **names only** — never display values. Note which environment each secret belongs to.

## Step 5: Volumes

```bash
modal volume list --json
```

List all volumes: name, creation time, environment.

## Step 6: Check for Modal Config

Use the Read tool to check for project-level Modal configuration:
- Read `.modal.toml` (skip if it doesn't exist)
- Read `modal.toml` (skip if it doesn't exist)

Also check for Modal app files:
- Use the Glob tool with pattern `*.py` to find Python files
- Use the Grep tool with pattern `modal\.App|modal\.Stub|@app\.` and glob `*.py` with `output_mode: files_with_matches` to find Modal app files

## Step 7: Present Dashboard

Format all output as a clean summary (workspace name comes from the pre-flight `modal token info`):

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
