Invoked by /claudna:neon in branch mode — do not load this file for any other verb. Pre-flight (neon + psql checks, auth probe, discovery of `<PROJECT_ID>` and `<ORG_ID>`) has already run per SKILL.md. It made the private directory `<scratch>` and chose `<NEON>`, the form every neon command below runs as.

Branches are instant copy-on-write snapshots — use them for safe experimentation, pre-migration testing, and disposable dev environments.

## Command conventions

- Every neon command requires `--project-id "<PROJECT_ID>" --org-id "<ORG_ID>"`. If either is missing after discovery, ask the user.
- The CLI reads `NEON_API_KEY` from its environment, and `<NEON>` already hands it over when the key is in use. Never add `--api-key`.
- A branch's connection string is a credential, so it goes into a file in `<scratch>` and never onto the screen or into a command. Write it there with `>`, and delete `<scratch>` with `rm -r <scratch>` when the branch work ends. `branches create` prints the new branch's connection strings too, so its output goes to a file as well. Never use the CLI's `--psql` option (it passes the URL to psql as an argument) or `connection-string --extended` (it prints the password).

## Auth recovery

Branch operations hard-require auth. If the pre-flight probe printed "Awaiting authentication":

1. Tell the user auth is needed, then run `neon auth` (`npx neon@6.2.3 auth` when only the npx fallback passed pre-flight) — this opens a browser window (60-second timeout). After it completes, re-run the pre-flight probe.
2. If that also fails, tell the user:
   > No valid Neon credentials found. Options:
   > 1. Run `neon auth` to authenticate via browser
   > 2. Create an API key at https://console.neon.tech/app/settings/api-keys and add `NEON_API_KEY=<key>` to `.env`
   >
   > An API key enables fully headless operation (no browser needed).

## Commands

### List branches
```bash
<NEON> branches list --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

### Create branch (from production)
```bash
<NEON> branches create --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --name "<branch-name>" --output json > <scratch>/create.json
```

Then show only the branch's own fields (the file also holds its connection strings):
```bash
jq '(.branch // .) | {id, name, parent_id, created_at}' <scratch>/create.json
```

Name conventions:
- `claude/<purpose>` — for agent-created branches (e.g., `claude/debug-issue-123-2026-02-12`)
- `dev/<feature>` — for development work
- `test/<description>` — for testing

### Create branch at point-in-time
```bash
<NEON> branches create --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --name "<branch-name>" --parent "production@2026-02-12T00:00:00Z" --output json > <scratch>/create.json
```

Read it with the same `jq` command as above.

Note: Point-in-time branching is limited by the project's history retention window (varies per Neon plan).

### Get connection string for a branch
```bash
<NEON> connection-string "<branch-name>" --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --pooled --database-name <DB_NAME> --role-name neondb_owner > <scratch>/branch.url
```

Then write the SQL to `<sql-file>`, a file in `<scratch>` (`../_shared/orchestration-guide.md` §1), with the Write tool and run it against the branch. The bundled reader turns the URL in the file into psql's environment (`<claudna-root>` per `../_shared/claudna-root.md`):
```bash
python3 "<claudna-root>/scripts/env_from_file.py" --url-file <scratch>/branch.url -- psql -X -f <sql-file>
```

Working on more than one branch: one URL file per branch (`<scratch>/<name>.url`). psql's own errors can echo parts of a connection; scrub output per the contract before quoting it.

### Delete branch — destructive, gated (contract §5)

Present the §6 boxed summary (branch name, project, what is discarded) and ask "Ready to delete? (y/n)" — do not proceed without an explicit yes. No exceptions: `claude/*` cleanup branches gate too — "created this session" is unverifiable state (a compaction or a teammate's same-named branch makes it wrong), and contract §5 permits no ungated destructive operations. Batch the cleanup: one summary listing every `claude/*` branch to delete, one confirmation.

```bash
<NEON> branches delete "<branch-name>" --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```

**Always clean up agent-created branches when done**, then remove the connection strings: `rm -r <scratch>`.

### Reset branch — destructive, gated (contract §5)

Resets a branch to its parent's current state, discarding the branch's own changes. Always gate — boxed summary (branch, parent, data discarded) plus an explicit yes; no exceptions, the agent may not own what the branch holds.

```bash
<NEON> branches reset "<branch-name>" --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --parent
```

## Reporting (contract §6)

For create operations, report the branch name and id, never its connection string; the user can print it with `neon connection-string "<branch-name>"`. After any operation, box the outcome: status, branch, project, errors found.

## Workflow: safe experimentation

Run each step as its own Bash call.

**Step 1: Create a branch**
```bash
<NEON> branches create --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --name "claude/experiment-YYYYMMDD-HHMM" --output json > <scratch>/create.json
```
```bash
jq '(.branch // .) | {id, name, parent_id, created_at}' <scratch>/create.json
```

**Step 2: Get connection string**
```bash
<NEON> connection-string "claude/experiment-..." --project-id "<PROJECT_ID>" --org-id "<ORG_ID>" --pooled --database-name <DB_NAME> --role-name neondb_owner > <scratch>/branch.url
```

**Step 3: Run experimental queries (read-write OK on the disposable branch)**

Write each statement to `<sql-file>` in `<scratch>` with the Write tool (for example `DELETE FROM <STAGING_TABLE> WHERE ...;`), then:
```bash
python3 "<claudna-root>/scripts/env_from_file.py" --url-file <scratch>/branch.url -- psql -X -f <sql-file>
```

**Step 4: Clean up when done**
```bash
<NEON> branches delete "claude/experiment-..." --project-id "<PROJECT_ID>" --org-id "<ORG_ID>"
```
```bash
rm -r <scratch>
```

## Limits

Neon free tier allows up to 10 branches. Check current branch count before creating new ones. Always delete `claude/*` branches when analysis is complete.
