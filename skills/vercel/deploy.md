# Vercel — Deploy

Invoked by /claudna:vercel in deploy mode. Pre-flight (CLI installed, authenticated, project linked) has already passed per the engine SKILL.md. Execution, output, and failure conventions: `skills/_shared/infra-cli-contract.md` §§5–7 — separate Bash calls, boxed summaries, redactor-scrubbed stderr (§7).

Deploy to Vercel with pre-deploy checks, build monitoring, health verification, and post-deploy review. Deploy is this engine's destructive verb: it gates on explicit user confirmation (contract §5).

Follow these steps exactly in order. **Do NOT skip the user confirmation gate in Step 2.**

---

### Step 1: Pre-Deploy Check

Gather context about what's about to be deployed — run each command as its own Bash call.

**Vercel context:**
```bash
vercel ls --limit 1
```
Parse: project name, current production URL, last deployment status.

**Git context:**
```bash
git log -1 --oneline
```
```bash
git status --porcelain
```

**Warn if uncommitted changes exist.** By default `vercel` deploys from the working directory — uncommitted changes WILL be included in a CLI deploy but NOT in git-triggered deploys. This causes drift.

**Check deploy target:**
- If the verb arguments or the user's request say "production" → `--prod` flag
- If nothing was specified → default is preview deployment
- Ask if unclear: "Deploy to production or preview?"

**Check for build errors locally (optional but recommended):**
```bash
npm run build
```
If the build fails locally, warn the user before proceeding.

Present the boxed pre-action summary (contract §6):

```
Deploy Summary
═══════════════════════════════════════════════════════
  Project:      [name]
  Target:       [production / preview]
  Branch:       [git branch]
  Commit:       [short hash] [message]
  Uncommitted:  [Y/N — warn if Y]
  Local build:  [passed / failed / skipped]
═══════════════════════════════════════════════════════
```

### Step 2: User Confirmation Gate

**Ask the user: "Ready to deploy? (y/n)"**

Do NOT proceed until the user explicitly confirms. If they say no, stop and ask what they'd like to change. The gate applies to every deploy and is non-negotiable for production targets.

### Step 3: Deploy

**Preview deployment (default):**
```bash
vercel deploy
```

**Production deployment:**
```bash
vercel deploy --prod
```

The CLI streams build output. Monitor for:
- Build errors (exit code != 0)
- Function bundling warnings
- Size limit warnings (serverless functions > 50MB compressed)

Capture the deployment URL from the CLI output.

**If the project uses Git Integration (auto-deploy on push):**
Tell the user: "This project uses Vercel Git Integration. Push your changes with `git push` and Vercel will build automatically. I'll check the deployment status."

Then monitor:
```bash
vercel ls --limit 1
```
Poll until the deployment state changes from `BUILDING` to `READY` or `ERROR`.

### Step 4: Health Check

After the deployment is ready:

**Get the deployment URL** (captured from Step 3 output or from `vercel ls`):
```bash
curl -s -o /dev/null -w "%{http_code}" <deployment-url>
```

- `200-299` → healthy
- `301-399` → redirect (follow and check final destination)
- `4xx/5xx` → unhealthy, flag immediately
- Connection timeout → deployment may still be propagating, wait 10s and retry once

**Check specific routes if known** (separate Bash calls):
```bash
curl -s -o /dev/null -w "%{http_code}" <deployment-url>/api/health
```
```bash
curl -s -o /dev/null -w "%{http_code}" <deployment-url>/api
```

If the project has API routes, test at least one.

A failed health check after a deploy is a loud flag, not a footnote (contract §7) — show the failing endpoint/status first.

### Step 5: Post-Deploy Log Review

```bash
vercel logs <deployment-url> --limit 50
```

Check for:
- Serverless function errors (timeouts, crashes)
- Edge function errors
- 500-level responses
- Cold start issues (function initialization errors)
- Missing environment variables (undefined/null config references)

### Step 6: Deploy Report

Present the boxed post-verb report (contract §6):

```
Deploy Report
═══════════════════════════════════════════════════════
  Status:       [READY / ERROR / BUILDING]
  Target:       [production / preview]
  URL:          [deployment URL]
  Commit:       [hash] [message]
  Build:        [duration if available]
  Health:       [HTTP status]
  Functions:    [count serverless, count edge]
  Errors:       [count of errors in logs]
═══════════════════════════════════════════════════════
```

If the deploy failed or health checks are unhealthy:
- Show the relevant error logs
- Suggest checking `vercel logs <url> --limit 100`
- Offer to rollback: `vercel rollback` restores the previous production deployment (destructive — confirm with the user before running, per contract §5)
- Offer to redeploy: `vercel redeploy` triggers a fresh build

**For production deployments that succeed:**
- Confirm the production domain is serving the new deployment
- Check that the preview URL also works (useful for sharing with the team)
