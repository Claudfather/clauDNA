# Platform Detection Reference

Reference for Step 2 of `/investigate-app`. Detect deployment platforms by checking for config files and CLIs, then bootstrap any missing CLIs.

## Detection Checks

Run each check as a **separate Bash call** (never chain with `&&`). Interpret success/failure from the exit code and output:

**Railway:**
- `ls railway.toml railway.json .railway/` — if output, config found
- `railway status --json` — if succeeds, CLI linked

**Vercel:**
- `ls vercel.json .vercel/` — if output, config found
- `vercel --version` — if succeeds, CLI found

**Docker:**
- `ls docker-compose.yml docker-compose.yaml Dockerfile` — if output, config found
- `docker --version` — if succeeds, CLI found

**Modal:**
- Use Grep tool with pattern `modal` in `requirements.txt`, `pyproject.toml`, `setup.py` — if matches, deps found
- Use Grep tool with pattern `modal\.App|modal\.Stub|@app\.` and glob `*.py` with `output_mode: files_with_matches` — if matches, app files found
- `modal --version` — if succeeds, CLI found

## CLI Bootstrap

| Platform | Config Found | CLI Missing | Install Command |
|----------|-------------|-------------|-----------------|
| Railway | `railway.toml` / `.railway/` | `railway` not found | `npm install -g @railway/cli` or `brew install railway` |
| Vercel | `vercel.json` / `.vercel/` | `vercel` not found | `npm install -g vercel` |
| Modal | `modal` in deps | `modal` not found | `pip install modal` |
| Docker | `Dockerfile` / `docker-compose.yml` | `docker` not found | User must install Docker Desktop |

## Full CLI Bootstrap Sequences

**If Railway is detected:**
1. `railway --version` — check >= 4.27.3
2. `railway whoami --json` — check auth, guide `railway login` if needed
3. `railway status --json` — check project link, guide `railway link` if needed

**If Vercel is detected:**
1. `vercel --version` — check installed
2. `vercel whoami` — check auth, guide `vercel login` if needed
3. `ls .vercel/project.json` — check project link, guide `vercel link` if needed

**If Modal is detected:**
1. `modal --version` — check installed (fallback: `python -m modal --version`)
2. `modal token info` — check auth, guide `modal token new` if needed
3. `modal environment list --json` — identify environments
4. `modal app list --json` — identify deployed apps

## Detection Summary Format

Present what was detected:

```
Platform Detection
═══════════════════════════════════════════════════════
  Primary:    [Railway / Vercel / Docker / Modal / Unknown]
  CLI:        [installed / missing — installing...]
  Auth:       [authenticated / needs login]
  Project:    [linked / needs linking]
  Database:   [Neon / Snowflake / Other / None detected]
═══════════════════════════════════════════════════════
```
