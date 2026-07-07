# Railway — Deploy

Invoked by /claudna:railway in deploy mode. Pre-flight (CLI install, >=4.27.3 version gate, auth, project link) has already passed per the engine contract — do not re-run it. Any remaining dispatch arguments name the target service or environment — apply them via `railway up`'s `--service` / `--environment` flags.

Deploy to Railway with pre-deploy checks, build monitoring, health verification, and post-deploy log review. Follow these steps exactly in order. **Do NOT skip the user confirmation gate in Step 2.**

## Step 1: Pre-Deploy Check

Gather context about what's about to be deployed.

**Railway context:**
```bash
railway status --json
```
Parse: project name, linked service, current environment.

**Git context** (separate Bash calls):
```bash
git log -1 --oneline
```
```bash
git status --porcelain
```

**Warn if uncommitted changes exist.** Railway deploys the working directory contents — uncommitted changes WILL be included in the deploy but NOT in git history, which causes drift.

Present a pre-deploy summary:

```
Deploy Summary
═══════════════════════════════════════════════════════
  Project:      [name]
  Service:      [service]
  Environment:  [env]
  Branch:       [git branch]
  Commit:       [short hash] [message]
  Uncommitted:  [Y/N — warn if Y]
═══════════════════════════════════════════════════════
```

## Step 2: User Confirmation Gate

**Ask the user: "Ready to deploy? (y/n)"**

Do NOT proceed until the user explicitly confirms. If they say no, stop and ask what they'd like to change.

## Step 3: Deploy

**CI mode (streams build logs inline):**
```bash
railway up --ci -m "<descriptive deploy message>"
```

Always use `-m` with a meaningful message. Derive it from:
- The most recent commit message, OR
- What the user described as the purpose of this deploy

**If the project uses auto-deploy on git push:**
Tell the user: "This project appears to use auto-deploy. Push your changes with `git push` and I'll monitor the deployment."

Then monitor:
```bash
railway deployment list --limit 1 --json
```
Poll until the deployment status changes from `BUILDING` to `SUCCESS` or `FAILED`.

## Step 4: Health Check

After the build completes and the deployment is live:

**Check public domains:**
```bash
railway status --json
```
Parse the JSON output to extract domain URLs.

For each domain:
```bash
curl -s -o /dev/null -w "%{http_code}" https://<domain>
```

- `200-299` → healthy
- `301-399` → redirect (follow it and check final destination)
- `4xx/5xx` → unhealthy, flag immediately
- Connection timeout → service may still be starting, wait 10s and retry once

If no public domain exists, ask the user: "No public domain found. Do you have a health endpoint I should check?"

## Step 5: Post-Deploy Log Review

```bash
railway logs --lines 50 --json
```

Check for:
- Any `@level:error` entries since deploy
- Startup failures or crash loops
- Connection errors to databases or external services
- OOM or memory warnings

## Step 6: Deploy Report

Present a final summary:

```
Deploy Report
═══════════════════════════════════════════════════════
  Status:       [SUCCESS / FAILED / DEGRADED]
  Service:      [service name]
  Environment:  [environment]
  Commit:       [hash] [message]
  Deploy msg:   [the -m message used]
  Build:        [duration if available]
  Health:       [HTTP status for each domain]
  Errors:       [count of error-level logs since deploy]
═══════════════════════════════════════════════════════
```

If the deploy failed or health checks are unhealthy:
- Show the relevant error logs
- Suggest checking `railway logs --filter "@level:error" --lines 100`
- Offer to roll back: `railway down -y` stops the current deployment (service stays, deploy stops) — this is destructive, so ask before running it
- Note: `railway down` stops the deployment but does NOT delete the service
