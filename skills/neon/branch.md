Invoked by /claudna:neon in branch mode — do not load this file for any other verb. Pre-flight (neon + psql checks, auth probe, discovery of `<PROJECT_ID>`, `<ORG_ID>`, optional `<API_KEY>`) has already run per SKILL.md.

Branches are instant copy-on-write snapshots — use them for safe experimentation, pre-migration testing, and disposable dev environments.

## Command conventions

- Every neon command requires `--project-id "<PROJECT_ID>" --org-id "<ORG_ID>"`. If either is missing after discovery, ask the user.
- Include `--api-key "<API_KEY>"` only when `NEON_API_KEY` was discovered. If not found, omit the flag entirely.
- Examples below use `npx neon`; drop the `npx` prefix when the bare CLI passed pre-flight.

## Auth recovery

Branch operations hard-require auth. If the pre-flight probe printed "Awaiting authentication":

1. Tell the user auth is needed, then run `npx neon auth` — this opens a browser window (60-second timeout). After it completes, re-run the probe (`timeout 10 npx neon me`, with `--api-key` if available).
2. If that also fails, tell the user:
   > No valid Neon credentials found. Options:
   > 1. Run `npx neon auth` to authenticate via browser
   > 2. Create an API key at https://console.neon.tech/app/settings/api-keys and add `NEON_API_KEY=<key>` to `.env`
   >
   > An API key enables fully headless operation (no browser needed).

## Commands

### List branches
```bash
npx neon branches list --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

### Create branch (from production)
```bash
npx neon branches create --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --name "<branch-name>" --output json
```

Name conventions:
- `claude/<purpose>` — for agent-created branches (e.g., `claude/debug-issue-123-2026-02-12`)
- `dev/<feature>` — for development work
- `test/<description>` — for testing

### Create branch at point-in-time
```bash
npx neon branches create --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --name "<branch-name>" --parent "production@2026-02-12T00:00:00Z" --output json
```

Note: Point-in-time branching is limited by the project's history retention window (varies per Neon plan).

### Get connection string for a branch
```bash
npx neon connection-string "<branch-name>" --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --pooled --database-name <DB_NAME> --role-name neondb_owner
```

Then use the returned URL to query the branch:
```bash
psql "<BRANCH_URL>" -c "SELECT count(*) FROM <YOUR_TABLE> WHERE is_current = true;"
```

### Delete branch — destructive, gated (contract §5)

Present the §6 boxed summary (branch name, project, what is discarded) and ask "Ready to delete? (y/n)" — do not proceed without an explicit yes. No exceptions: `claude/*` cleanup branches gate too — "created this session" is unverifiable state (a compaction or a teammate's same-named branch makes it wrong), and contract §5 permits no ungated destructive operations. Batch the cleanup: one summary listing every `claude/*` branch to delete, one confirmation.

```bash
npx neon branches delete "<branch-name>" --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

**Always clean up agent-created branches when done.**

### Reset branch — destructive, gated (contract §5)

Resets a branch to its parent's current state, discarding the branch's own changes. Always gate — boxed summary (branch, parent, data discarded) plus an explicit yes; no exceptions, the agent may not own what the branch holds.

```bash
npx neon branches reset "<branch-name>" --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --parent
```

## Reporting (contract §6)

For create operations, always report back the branch name and its connection string. After any operation, box the outcome: status, branch, project, errors found.

## Workflow: safe experimentation

Run each step as its own Bash call.

**Step 1: Create a branch**
```bash
npx neon branches create --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --name "claude/experiment-YYYYMMDD-HHMM" --output json
```

**Step 2: Get connection string**
```bash
npx neon connection-string "claude/experiment-..." --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --pooled --database-name <DB_NAME> --role-name neondb_owner
```

**Step 3: Run experimental queries (read-write OK on the disposable branch)**
```bash
psql "<BRANCH_URL>" -c "DELETE FROM <STAGING_TABLE> WHERE ..."
```
```bash
psql "<BRANCH_URL>" -c "UPDATE <YOUR_TABLE> SET ..."
```

**Step 4: Clean up when done**
```bash
npx neon branches delete "claude/experiment-..." --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

## Limits

Neon free tier allows up to 10 branches. Check current branch count before creating new ones. Always delete `claude/*` branches when analysis is complete.
