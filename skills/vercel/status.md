# Vercel — Status

Invoked by /claudna:vercel in status mode. Pre-flight (CLI installed, authenticated, project linked) has already passed per the engine SKILL.md. Execution, output, and failure conventions: `skills/_shared/infra-cli-contract.md` §§5–7 — separate Bash calls, redactor-scrubbed stderr (§7). Status is read-only: it never gates on confirmation (contract §5).

Quick dashboard for your Vercel project. Shows project info, deployments, domains, environment variables, and framework details at a glance.

Follow these steps exactly in order.

---

### Step 1: Project Overview

```bash
vercel project inspect
```

Also use the Read tool to read `.vercel/project.json` (skip if it doesn't exist).

Parse and present: project name, project ID, org ID, framework, Node.js version.

Also check for framework configuration using the Read tool:
- Read `vercel.json` (skip if it doesn't exist)
- Read `next.config.js`, `next.config.mjs`, or `next.config.ts` — check each in order (skip if none exist)

### Step 2: Recent Deployments

```bash
vercel ls --limit 10
```

Show the 10 most recent deployments: status, URL, environment (production/preview), age/timestamp, and commit.

### Step 3: Inspect Latest Production Deployment

Get the most recent production deployment URL from Step 2 and inspect it:

```bash
vercel inspect <production-url>
```

Parse and present: deployment ID, state, target (production/preview), creator, build duration, regions, routes, serverless function details.

### Step 4: Domains

```bash
vercel domains ls
```

List all domains with their configuration status (valid, invalid, pending).

### Step 5: Environment Variables

```bash
vercel env ls
```

List variable **names and targets** (Production, Preview, Development) — never display values. Note any variables that exist only in some environments.

### Step 6: Present Dashboard

Format all output as a clean summary (the contract §6 boxed post-verb report):

```
Vercel Dashboard
═══════════════════════════════════════════════════════
  Project:      [name] ([id])
  Framework:    [Next.js / Remix / Nuxt / Static / etc.]
  Node.js:      [version if detected]
  Region:       [primary region]
═══════════════════════════════════════════════════════

Recent Deployments
┌────────────────────────────┬────────────┬────────────┬──────────┐
│ URL                        │ Status     │ Target     │ When     │
├────────────────────────────┼────────────┼────────────┼──────────┤
│ ...                        │ ...        │ ...        │ ...      │
└────────────────────────────┴────────────┴────────────┴──────────┘

Production Deployment
  URL:        [url]
  State:      [READY / ERROR / BUILDING / QUEUED]
  Created:    [timestamp]
  Build:      [duration]
  Functions:  [count] serverless, [count] edge

Domains
┌──────────────────────────┬────────────┬─────────────────────┐
│ Domain                   │ Status     │ Configuration       │
├──────────────────────────┼────────────┼─────────────────────┤
│ ...                      │ ...        │ ...                 │
└──────────────────────────┴────────────┴─────────────────────┘

Environment Variables: [count per target]
  Production: [count]
  Preview:    [count]
  Development:[count]
```
