---
name: vercel-status
description: "Use when you want an overview of your Vercel project -- deployments, domains, environment variables, and config."
---

# Vercel Status

Quick dashboard for your Vercel project. Shows project info, deployments, domains, environment variables, and framework details at a glance.

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

Format all output as a clean summary:

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
