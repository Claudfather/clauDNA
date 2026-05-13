---
name: railway-logs
user-invocable: true
description: "Use when you need to view, filter, or debug Railway service logs."
argument-hint: "[service name or filter]"
---

# Railway Logs

View and filter Railway service logs. Supports JSON output, level filtering, time ranges, and pattern matching.

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

### Step 1: Fetch Logs

**Default (last 100 lines):**
```bash
railway logs --lines 100 --json
```

**Specific service:**
```bash
railway logs --service <name> --lines 100 --json
```

**With level filter:**
```bash
railway logs --filter "@level:error" --lines 100 --json
```

**With time range (relative):**
```bash
railway logs --lines 100 --json  # then filter by timestamp
```

### Step 2: Filter & Analyze

Parse the JSON output and apply any user-requested filters.

**Built-in filters:**
- `@level:error` — errors only
- `@level:warn` — warnings only
- `@level:info` — info messages only

**Pattern-based filtering:**
```bash
railway logs --lines 200 --json
```
Parse the JSON output yourself to find entries whose `message` field matches the user's search pattern (case-insensitive). Do NOT pipe through jq -- read and filter the JSON directly.

### Common Investigations

**Recent errors:**
```bash
railway logs --filter "@level:error" --lines 100 --json
```

**Deployment startup issues:**
```bash
railway logs --lines 50 --service <name> --json
```

**Memory / OOM issues:**
```bash
railway logs --lines 200 --json
```
Parse the JSON output to find entries with messages matching: memory, oom, killed (case-insensitive).

**Connection issues:**
```bash
railway logs --lines 200 --json
```
Parse the JSON output to find entries with messages matching: ECONNREFUSED, timeout, ETIMEDOUT (case-insensitive).

**Crash loops:**
```bash
railway logs --lines 200 --json
```
Parse the JSON output to find entries with messages matching: exit, crash, restart, signal (case-insensitive).

### Step 3: Present Results

Format log output clearly:
- Group by severity if mixed levels
- Highlight errors and warnings
- Show timestamps in human-readable format
- If logs are empty or the service has no recent activity, say so
- Suggest next steps based on what the logs show

### Output Modes

**JSON (default — best for parsing):**
```bash
railway logs --lines 100 --json
```

**Save to file:**
```bash
railway logs --lines 500 --json
```
If the user wants logs saved to a file, write the output to `/tmp/railway-logs.json` using the Write tool.

**Structured view:**
```bash
railway logs --lines 100 --json
```
Parse the JSON output and present each entry as a structured record with timestamp, level, and message fields. Do NOT pipe through jq.

$ARGUMENTS
