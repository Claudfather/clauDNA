# AGENTS.md

## Cursor Cloud specific instructions

clauDNA is a plugin pack (markdown skills/agents + shell hooks) shipped to Claude Code via the `Claudfather` marketplace and to Cursor via `.cursor-plugin/`. There is **no long-running server or web app** to start — the "application" is the plugin, whose runtime pieces are the shell hooks in `plugin-hooks/`. The development gate is the Python validator/test toolchain.

`.cursor/environment.json` declares one `install` step, `./.cursor/install.sh`, which runs `make deps` to install the pinned toolchain from `requirements-dev.txt`. **A fresh agent should already be able to run `make check`** — no `start` command and no services, because there is nothing to serve. If `ruff` or `pytest` is missing, the install step did not run (check `/tmp/cursor/async-install/install-user.log`); run `make deps` yourself and carry on.

### Dev toolchain and the one check-set

- `make check` is the single source of truth for lint/test/validation and is exactly what CI runs (see `.github/workflows/ci.yml` and the `Makefile`). A green `make check` locally == a green CI run. Add or change checks in the `Makefile`, never in the workflow.
- The check-set runs: `validate-skills.py`, `integration-test.py`, `validate-agents.py`, `validate-manifest.py`, `check-changelog.sh`, `python3 -m ruff check scripts/ tests/`, and `python3 -m pytest tests/`.
- `integration-test.py` emits non-fatal warnings (e.g. "missing `## Procedure` heading"); these are expected and do not fail the run. It ends with `OK: N skills passed`.
- Individual targets exist if you want to scope a run: `make lint`, `make test`, `make check-skills`, `make check-agents`, `make check-manifest`, `make check-changelog`.

### Non-obvious gotchas

- **The check-set never invokes a tool by bare name, and it must stay that way.** `make deps` has no writeable system site-packages here, so pip does a user install and the `ruff`/`pytest` console scripts land in `~/.local/bin` — which the stock `~/.profile` adds to PATH only `if [ -d ... ]`, evaluated per login shell. On a VM where that directory has never existed, the first shell drops it, so a bare `ruff` is not found no matter which shell you use. Every target therefore goes through `python3 -m <tool>`, which needs no PATH entry and resolves in the same interpreter the tools were installed for. `./.cursor/install.sh` additionally creates `~/.local/bin` before installing into it, so later login shells do pick it up and a bare `ruff` works interactively too.
- Toolchain versions in `requirements-dev.txt` are pinned deliberately (a new `ruff` release can turn CI red). Bump only in a dedicated change.
- `check-changelog.sh` diffs against `origin/main`. On a branch it enforces that non-trivial changes touch `CHANGELOG.md`; on `main` with no diff it no-ops (`HEAD == origin/main; nothing to gate`). If a validation-only branch fails this gate, add a `CHANGELOG.md` entry.
- Hooks are plain executables that read a JSON event on stdin. To exercise one directly (no Claude Code needed), pipe an event in, e.g.:
  `echo '{"tool_name":"Bash","tool_input":{"command":"git status && ls -la"}}' | bash plugin-hooks/pretooluse-permissions.sh`
- `pretooluse-permissions.sh` requires `jq` and silently no-ops (exit 0) if it is absent; it only ever emits an `allow` decision or falls through — it never denies.
- This repo is the source of truth for the plugin. Do not edit the installed plugin cache under `~/.claude/plugins/cache/...`; make changes here and (for releases) bump `version` in **both** `.claude-plugin/plugin.json` and `.cursor-plugin/plugin.json` — `scripts/release.sh` does both, and `make check-manifest` fails if they disagree.
