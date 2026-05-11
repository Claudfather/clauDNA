# Worktree Bootstrap Commands

Worktrees only contain git-tracked files — no venv, no node_modules, no .env.

**IMPORTANT:** Run each command as a separate Bash call. Never chain with `&&` — shell operators break permission matching.

**Step 1 — Set working directory (do this ONCE, it persists):**
```bash
cd /absolute/path/to/repo-worktrees/<branch>
```

**Step 2 — Copy .env from main repo (if it exists):**
```bash
cp <MAIN REPO>/.env .
```

**Step 3 — Install dependencies:**

For Python projects (run each as a separate Bash call):
```bash
python -m venv venv
```
```bash
./venv/bin/pip install -e ".[dev]"
```

For Node projects:
```bash
npm install
```

**Step 4 — Run all subsequent commands normally** (working directory is already set).

For Python: use `./venv/bin/python` and `./venv/bin/pytest` directly — never `source venv/bin/activate`.

Adapt to the project — check pyproject.toml, package.json, Makefile, etc. for the correct setup steps.
