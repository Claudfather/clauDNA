Invoked by /claudna:modal in deploy mode — pre-flight (contract §4) has already run; the remaining args name the app or module to deploy plus any environment, tag, or name the user specified.

# Deploy

Deploy a Modal app with pre-deploy checks, log streaming, health verification, and deployment history review. Follow these steps exactly in order. **Do NOT skip the user confirmation gate in Step 2.**

## Step 1: Pre-Deploy Check

Gather context about what's about to be deployed. If target discovery surfaced multiple candidate app files and the remaining args don't pick one, ask the user which file to deploy.

**Current deployment state:**
```bash
modal app list --json
```
Note any existing deployment with the same name — it will be updated in place.

**Git context** (two separate Bash calls):
```bash
git log -1 --oneline
```
```bash
git status --porcelain
```

**Check for environment specification:**
- If the user mentioned a specific environment → use `--env <name>`
- If a `.modal.toml` has a default environment → use that
- Otherwise → use the default environment

**Check for deployment tag:**
- If the user wants to tag this deployment → use `--tag <tag>`
- Otherwise → no tag

**Local syntax check (optional but recommended):**
```bash
python -c "import ast; ast.parse(open('<app-file>').read())"
```
If the syntax check fails, warn the user before proceeding.

Present a pre-deploy summary:

```
Deploy Summary
═══════════════════════════════════════════════════════
  App file:     [filename.py]
  App name:     [app name from file or --name flag]
  Environment:  [env name or "default"]
  Tag:          [tag or "none"]
  Branch:       [git branch]
  Commit:       [short hash] [message]
  Uncommitted:  [Y/N — warn if Y]
  Existing:     [Y/N — will update existing deployment]
═══════════════════════════════════════════════════════
```

## Step 2: User Confirmation Gate (contract §5)

**Ask the user: "Ready to deploy? (y/n)"**

Do NOT proceed until the user explicitly confirms. If they say no, stop and ask what they'd like to change.

## Step 3: Deploy

**Standard deployment:**
```bash
modal deploy <app-file.py> --stream-logs
```

**With custom name:**
```bash
modal deploy <app-file.py> --name <deployment-name> --stream-logs
```

**With environment:**
```bash
modal deploy <app-file.py> --env <environment> --stream-logs
```

**With tag:**
```bash
modal deploy <app-file.py> --tag <version-tag> --stream-logs
```

**With timestamps:**
```bash
modal deploy <app-file.py> --stream-logs --timestamps
```

The `--stream-logs` flag streams app logs after deployment completes. Monitor for:
- Build/image creation errors
- Import errors
- Function registration failures
- Secret mount failures

## Step 4: Health Check

After deployment completes:

**Check the app is listed:**
```bash
modal app list --json
```
Verify the app appears with the correct state.

**If the app has web endpoints, test them:**
The deployment output will show endpoint URLs. Test each one:
```bash
curl -s -o /dev/null -w "%{http_code}" <endpoint-url>
```

- `200-299` → healthy
- `4xx/5xx` → unhealthy, flag immediately
- Note: Modal web endpoints have a `-dev` suffix when using `modal serve`; production deploys do not

**Check for running containers:**
```bash
modal container list --json
```
If the app has `min_containers` set, verify containers are running.

## Step 5: Post-Deploy Log Review

```bash
modal app logs <app-name> --timestamps
```

Check for:
- Function initialization errors
- GPU allocation failures
- OOM kills
- Heartbeat timeouts
- Secret access errors
- Volume mount failures
- Import errors in container

## Step 6: Deployment History

```bash
modal app history <app-name> --json
```

Show recent deployment versions, useful for confirming the deploy and for rollback reference.

## Step 7: Deploy Report

Present a final summary:

```
Deploy Report
═══════════════════════════════════════════════════════
  Status:       [deployed / failed]
  App:          [app name]
  Environment:  [environment]
  Tag:          [tag if set]
  Version:      [version number from history]
  Commit:       [hash] [message]
  Endpoints:    [list URLs if web endpoints exist]
  Health:       [HTTP status for each endpoint]
  Containers:   [count running]
  Errors:       [count of errors in logs]
═══════════════════════════════════════════════════════
```

If the deploy failed:
- Show the relevant error logs
- Suggest checking `modal app logs <app-name> --timestamps`
- Offer to rollback: `modal app rollback <app-name> <version>` (Team/Enterprise plans only)
- Offer to stop: `modal app stop <app-name>` (permanent — requires redeployment)
