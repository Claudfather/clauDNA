# AGENTS.md

## Cursor Cloud specific instructions

clauDNA is a Claude Code plugin pack (markdown skills/agents + shell hooks distributed via the `Claudfather` marketplace). There is **no long-running server or web app** to start — the "application" is the plugin, whose runtime pieces are the shell hooks in `plugin-hooks/`. The development gate is the Python validator/test toolchain.

### Dev toolchain and the one check-set

- `make check` is the single source of truth for lint/test/validation and is exactly what CI runs (see `.github/workflows/ci.yml` and the `Makefile`). A green `make check` locally == a green CI run. Add or change checks in the `Makefile`, never in the workflow.
- The check-set runs: `validate-skills.py`, `integration-test.py`, `validate-agents.py`, `validate-manifest.py`, `check-changelog.sh`, `ruff check scripts/ tests/`, and `pytest tests/`.
- `integration-test.py` emits non-fatal warnings (e.g. "missing `## Procedure` heading"); these are expected and do not fail the run. It ends with `OK: N skills passed`.
- Individual targets exist if you want to scope a run: `make lint`, `make test`, `make check-skills`, `make check-agents`, `make check-manifest`, `make check-changelog`.

### Non-obvious gotchas

- The update script installs the pinned toolchain from `requirements-dev.txt` into the user site; the `ruff`/`pytest` console scripts land in `~/.local/bin`. Run `make check` from a **login shell** (the default here) so `~/.local/bin` is on PATH — the `lint` target calls the `ruff` binary directly. `pytest` is invoked as `python3 -m pytest`, so it works regardless of PATH.
- Toolchain versions in `requirements-dev.txt` are pinned deliberately (a new `ruff` release can turn CI red). Bump only in a dedicated change.
- `check-changelog.sh` diffs against `origin/main`. On a branch it enforces that non-trivial changes touch `CHANGELOG.md`; on `main` with no diff it no-ops (`HEAD == origin/main; nothing to gate`). If a validation-only branch fails this gate, add a `CHANGELOG.md` entry.
- Hooks are plain executables that read a JSON event on stdin. To exercise one directly (no Claude Code needed), pipe an event in, e.g.:
  `echo '{"tool_name":"Bash","tool_input":{"command":"git status && ls -la"}}' | bash plugin-hooks/pretooluse-permissions.sh`
- `pretooluse-permissions.sh` requires `jq` and silently no-ops (exit 0) if it is absent; it only ever emits an `allow` decision or falls through — it never denies.
- This repo is the source of truth for the plugin. Do not edit the installed plugin cache under `~/.claude/plugins/cache/...`; make changes here and (for releases) bump `version` in `.claude-plugin/plugin.json`.
