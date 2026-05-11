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

If connection strings found in `.env`:

- Neon: First, use the Read tool to read `.env` and find the database URL (look for `DATABASE_URL`, `NEON_PROD_URL`, `POSTGRES_URL`, or similar). Then run psql directly with the discovered URL:
  ```bash
  psql <discovered-database-url> -c "BEGIN TRANSACTION READ ONLY; SELECT count(*) FROM pg_stat_activity WHERE state = 'active'; SELECT * FROM pg_stat_activity WHERE state = 'active' AND query NOT LIKE '%pg_stat%'; COMMIT;"
  ```
- Snowflake: check for `~/.snowsql/config`, run `snowsql -c default -q "SHOW RUNNING QUERIES;"`
- Check for connection pool exhaustion, long-running queries, locks

## D. Codebase Context

- Recent git history: `git log --oneline -20`, `git diff HEAD~5 --stat`
- Error handling patterns: search for try/catch, error middleware, error boundaries
- Configuration files: `.env.example`, config modules
- Recently modified files: `git diff --name-only HEAD~5`

## E. Resource Metrics

- Railway: Query GraphQL API for CPU_USAGE, MEMORY_USAGE_GB, NETWORK_RX_GB, DISK_USAGE_GB. Read token from `~/.railway/config.json`
- Vercel: `vercel inspect <production-url>` for function config (memory, maxDuration, regions). Use `vercel httpstat /api/<route>` for HTTP timing. Use `vercel logs --source serverless --json --since 1h` for slow function detection (Claude can parse JSON output and filter for high-duration entries — do not pipe through jq). For advanced metrics, use REST API with token from `~/.config/com.vercel.cli/auth.json`
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
