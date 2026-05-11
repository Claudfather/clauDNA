---
name: modal-logs
description: "Use when you need to view, stream, or debug Modal app or container logs."
argument-hint: "[app name or container ID]"
---

# Modal Logs

View and stream Modal app and container logs. Supports app-level logs, per-container logs, and deployment log streaming.

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
If both fail, tell the user to install with `pip install modal`.

**2. Authenticated?**
```bash
modal token info
```
If the command fails, tell the user to run `modal token new`.

---

### Step 1: Identify Target

Determine what to fetch logs for.

**List deployed apps:**
```bash
modal app list --json
```

**List running containers:**
```bash
modal container list --json
```

If the user specified an app name, container ID, or environment, use that. Otherwise, ask which app they want logs for.

### Step 2: Fetch Logs

**App-level logs (streams while app is active):**
```bash
modal app logs <app-name>
```

**App logs with timestamps:**
```bash
modal app logs <app-name> --timestamps
```

**App logs in a specific environment:**
```bash
modal app logs <app-name> --env <environment>
```

**Container-level logs (specific container):**
```bash
modal container logs <container-id>
```

**Container logs with timestamps:**
```bash
modal container logs <container-id> --timestamps
```

**Stream logs during a run:**
```bash
modal run <app-file.py> --timestamps
```

**Stream logs during deployment:**
```bash
modal deploy <app-file.py> --stream-logs --timestamps
```

### Step 3: Debug Deeper

If app-level logs aren't enough, investigate individual containers.

**List running containers for the app:**
```bash
modal container list --json
```

**Get specific container logs:**
```bash
modal container logs <container-id> --timestamps
```

**Execute diagnostic commands inside a container:**
```bash
modal container exec <container-id> -- nvidia-smi          # GPU status
modal container exec <container-id> -- ps aux              # Process list
modal container exec <container-id> -- cat /proc/meminfo   # Memory info
modal container exec <container-id> -- df -h               # Disk usage
```

**Shell into a container for interactive debugging:**
```bash
modal shell <container-id>
```
The shell container has preinstalled tools: vim, nano, ps, strace, curl, py-spy.

### Common Investigations

**GPU OOM detection:**
```bash
modal container exec <container-id> -- nvidia-smi
```
Check for high GPU memory utilization. OOM kills appear in app logs as container termination events.

**Heartbeat timeout diagnosis:**
The GIL may be blocking the heartbeat thread. Profile with py-spy:
```bash
modal shell <container-id>
# Inside the shell:
py-spy dump --pid 1
```

**Function initialization failures:**
Check app logs for import errors, missing dependencies, or secret access failures:
```bash
modal app logs <app-name> --timestamps
```

**Cold start analysis:**
Look for container startup events in logs — compare startup times across containers. Check if `min_containers` is configured to prevent cold starts.

**Volume access issues:**
```bash
modal volume ls <volume-name>
```
Verify the volume exists and has expected contents.

**Secret access issues:**
```bash
modal secret list --json
```
Verify the secret exists in the correct environment. Don't display values.

### Step 4: Present Results

Format log output clearly:
- Group by severity (errors first, then warnings, then info)
- Highlight container termination events (OOM, heartbeat timeout)
- Show GPU utilization if containers use GPUs
- Note any patterns (recurring errors, degrading performance)
- If logs are empty or the app has no recent activity, say so
- Suggest next steps based on what the logs show

### Debug Environment Variables

For more verbose logging, suggest the user set:
```bash
MODAL_LOGLEVEL=DEBUG modal run <app-file.py>
```

For full tracebacks:
```bash
MODAL_TRACEBACK=1 modal run <app-file.py>
```

$ARGUMENTS
