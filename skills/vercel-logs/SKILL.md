---
name: vercel-logs
user-invocable: true
description: "Use when you need to view, filter, or debug Vercel deployment logs."
argument-hint: "[deployment URL or filter]"
requires:
  - cli: vercel
    reason: "Vercel CLI for log access"
---

# Vercel Logs

View and filter Vercel deployment logs. The CLI supports native filtering by level, status code, source type, time range, and full-text search — with JSON output for parsing.

## Instructions

Follow these steps exactly in order.

---

### Step 0: Prerequisites

Run these checks in order. Stop at the first failure and guide the user.

**1. CLI installed?**
```bash
vercel --version
```
- If the command fails (non-zero exit code or "command not found"): tell the user to install with `npm install -g vercel`

**2. Authenticated?**
```bash
vercel whoami
```
- If the command fails: tell the user to run `vercel login`

**3. Project linked?**
```bash
ls .vercel/project.json
```
- If the file does not exist: tell the user to run `vercel link` to select a project

---

### Step 1: Fetch Logs

By default, `vercel logs` shows request logs from the last 24 hours for the linked project and current git branch.

**Default (last 100 logs for current branch):**
```bash
vercel logs
```

**Production environment only:**
```bash
vercel logs --environment production --limit 100
```

**Specific deployment:**
```bash
vercel logs --deployment <deployment-id-or-url> --limit 100
```

**Stream live runtime logs (up to 5 minutes):**
```bash
vercel logs --follow
```

**Build logs for a specific deployment:**
```bash
vercel inspect <deployment-url> --logs
```

### Step 2: Filter

The CLI has native filtering — prefer these over piping through grep.

**By log level:**
```bash
vercel logs --level error
vercel logs --level error --level warning
```
Valid levels: `error`, `warning`, `info`, `fatal`

**By HTTP status code:**
```bash
vercel logs --status-code 500
vercel logs --status-code 5xx
vercel logs --status-code 4xx
```

**By source type:**
```bash
vercel logs --source serverless
vercel logs --source edge-function
vercel logs --source edge-middleware
vercel logs --source static
```
Can combine multiple: `--source serverless --source edge-function`

**By time range:**
```bash
vercel logs --since 1h
vercel logs --since 30m
vercel logs --since 2h --until 1h
vercel logs --since 2026-01-15T10:00:00Z
```

**Full-text search:**
```bash
vercel logs --query "timeout"
vercel logs --query "ECONNREFUSED"
```

**By git branch:**
```bash
vercel logs --branch main
vercel logs --branch feature-x
vercel logs --no-branch  # all branches
```

**By request ID (trace a specific request):**
```bash
vercel logs --request-id req_xxxxx
```

### Step 3: JSON Output & Parsing

Use `--json` to get structured JSON Lines output. Do NOT pipe through `jq` — instead, parse the JSON output yourself to extract and filter the fields you need.

**JSON Lines format:**
```bash
vercel logs --json --level error --since 1h
```
Parse the JSON output to extract `.message`, `.level`, `.statusCode`, `.duration`, and other fields as needed.

**Expanded output (full log messages, not truncated):**
```bash
vercel logs --expand --limit 50
```

### Common Investigations

**Recent errors:**
```bash
vercel logs --level error --since 1h --expand
```

**5xx responses in production:**
```bash
vercel logs --environment production --status-code 5xx --since 1h
```

**Serverless function timeouts:**
```bash
vercel logs --source serverless --query "timeout" --since 1h
```

**Edge function / middleware issues:**
```bash
vercel logs --source edge-function --source edge-middleware --level error
```

**Cold start analysis:**
```bash
vercel logs --source serverless --json --since 1h
```
Parse the JSON output and filter for entries where `.duration > 3000` to identify slow cold starts.

**Memory / payload issues:**
```bash
vercel logs --query "FUNCTION_PAYLOAD_TOO_LARGE" --since 24h
vercel logs --query "memory" --level error --since 24h
```

**ISR / cache issues:**
```bash
vercel logs --query "revalidat" --since 1h
```

**Build failures:**
```bash
vercel inspect <deployment-url> --logs
```

### Step 4: Present Results

Format log output clearly:
- Group by severity (errors first, then warnings, then info)
- Highlight 5xx responses and timeouts
- Show request path, status code, and duration for each invocation
- Calculate summary stats: total requests, error rate, p50/p95 duration if enough data
- If logs are empty or the deployment has no recent activity, say so
- Suggest next steps based on what the logs show

### Advanced: Deployment Bisect

To find which deployment introduced a regression:
```bash
vercel bisect
vercel bisect --good <known-good-url> --bad <known-bad-url>
```
This performs a binary search across deployments — very useful for tracking down when an issue was introduced.

### Output Enrichment

**Get function-level detail for a specific deployment:**
```bash
vercel inspect <deployment-url>
```
Shows all serverless functions, edge functions, static assets, regions, runtimes, memory limits, and max durations.

**HTTP timing stats for a specific route:**
```bash
vercel httpstat /api/your-route
```

**Cross-reference with deployment list:**
```bash
vercel ls --limit 20
```

$ARGUMENTS
