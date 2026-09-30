# Evidence Gathering Checklist

Reference for Steps 3-4 of `/claudna:investigate-app`. Each category is gathered by a parallel Explore subagent that writes research to `/tmp/investigate-app-<timestamp>/research/<signal-slug>.md` and returns only a 2-4 line summary.

## A. Platform Logs

- Railway: `railway logs --lines 200 --json`, filter `@level:error`
- Vercel: Use native filtering — `vercel logs --environment production --level error --since 1h --expand`. For 5xx: `vercel logs --status-code 5xx --since 1h`. For function issues: `vercel logs --source serverless --level error --since 1h`. JSON mode: `vercel logs --json --level error` (Claude can parse the JSON output directly — do not pipe through jq)
- Docker: `docker compose logs --tail 200`
- Modal: `modal app logs <app-name> --timestamps` for app-level logs. `modal container logs <container-id> --timestamps` for specific containers. For verbose output: `MODAL_LOGLEVEL=DEBUG modal app logs <app-name>`
- If no platform detected: ask user for log access

## B. Deployment History

- Railway: `railway deployment list --limit 10 --json`
- Vercel: `vercel ls --limit 10`, then `vercel inspect <production-url>` for function details, regions, build duration. For build logs: `vercel inspect <production-url> --logs`
- Modal: `modal app list --json` for all apps, `modal app history <app-name> --json` for version history. `modal container list --json` for running containers.
- Docker: `docker compose ps`, check image tags/digests
- Git: `git log --oneline -20`

## C. Database State

If the project keeps a database connection (`.env`, a libpq service, `~/.snowsql/config`), query it read-only. Never Read `.env` for the connection string. Write the SQL to a file with the Write tool first:

```sql
BEGIN TRANSACTION READ ONLY;
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
SELECT * FROM pg_stat_activity WHERE state = 'active' AND query NOT LIKE '%pg_stat%';
COMMIT;
```

- Neon / Postgres: `python3 "<claudna-root>/scripts/env_from_file.py" .env --has DATABASE_URL NEON_PROD_URL POSTGRES_URL` names the variable. Then `python3 "<claudna-root>/scripts/env_from_file.py" .env <NAME>=@libpq -- psql -X -f <sql-file>` runs the query with the URL in psql's environment only (`@libpq` splits it into libpq's own variables; psql does not read a URL from `PGDATABASE`). A `DATABASE_URL` already in the environment: `python3 "<claudna-root>/scripts/env_from_file.py" --url-env DATABASE_URL -- psql -X -f <sql-file>`. Resolve `<claudna-root>` per `../_shared/claudna-root.md`. A libpq service works too: `psql "service=<name>" -X -f <sql-file>`.
- Snowflake: check for `~/.snowsql/config`, write `SHOW RUNNING QUERIES;` to a file, run `snowsql -c default -f <sql-file>`.
- Check for connection pool exhaustion, long-running queries, locks

## D. Codebase Context

- Recent git history: `git log --oneline -20`, `git diff HEAD~5 --stat`
- Error handling patterns: search for try/catch, error middleware, error boundaries
- Configuration files: `.env.example`, config modules
- Recently modified files: `git diff --name-only HEAD~5`

## E. Resource Metrics

- Railway: the metrics API takes the account's token, so leave it to the `railway-ops` agent (header sent on stdin, token never printed or put on a command line). Never read `~/.railway/config.json` into the session, and never hand its token to a subagent
- Vercel: `vercel inspect <production-url>` for function config (memory, maxDuration, regions). Use `vercel httpstat /api/<route>` for HTTP timing. Use `vercel logs --source serverless --json --since 1h` for slow function detection (Claude can parse JSON output and filter for high-duration entries — do not pipe through jq). For advanced metrics, leave the REST API to the `vercel-ops` agent (header sent on stdin)
- Modal: `modal container list --json` for running containers. For GPU workloads: `modal container exec <id> -- nvidia-smi` for GPU memory/utilization. `modal container exec <id> -- cat /proc/meminfo` for system memory. `modal container exec <id> -- df -h` for disk. For profiling: `modal shell <id>` then `py-spy top --pid 1`
- If unavailable, note it and move on

## F. Vercel-Specific Diagnostics

Only if Vercel detected:

- Cache issues: `vercel logs --query "revalidat" --since 1h`
- Function timeouts: `vercel logs --status-code 504 --source serverless --since 1h`
- Edge/middleware errors: `vercel logs --source edge-function --source edge-middleware --level error`
- Environment variable gaps: `vercel env ls` — compare Production vs Preview vs Development targets
- Regression bisect: `vercel bisect` — binary search across deployments to find when issue started

## G. Modal-Specific Diagnostics

Only if Modal detected:

- GPU OOM: `modal container exec <id> -- nvidia-smi` — check GPU memory utilization, look for processes consuming excessive VRAM
- Heartbeat timeout: GIL may be blocking heartbeat thread. Profile: `modal shell <id>` then `py-spy dump --pid 1`
- Cold start analysis: Check function config for `min_containers`, `scaledown_window`, `buffer_containers`. Check image size and initialization logic.
- Secret/volume gaps: `modal secret list --json` and `modal volume list --json` — verify resources exist in the correct environment
- Deployment regression: `modal app history <app-name> --json` — correlate version changes with when issues started
- GPU availability: Check if containers are queued waiting for GPU allocation. Consider GPU fallbacks or alternative regions.
- Container isolation: Check for side effects between invocations if using container reuse. Consider `single_use_containers=True` if state leaks.

## H. Codebase Investigation (Step 4)

Based on evidence gathered above, launch additional Explore subagents to trace errors through the code:

- Find the source of error messages seen in logs
- Trace the request path for failing endpoints
- Check error handling and recovery logic
- Look for recent changes to the affected code paths
- Check for configuration mismatches between environments
