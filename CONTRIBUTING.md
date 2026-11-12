# Contributing to clauDNA

Thanks for your interest in improving clauDNA. This guide covers the ways you can contribute and the workflow for each.

## Ways to Contribute

### Report a Bug

Found a skill that errors out, a hook that misfires, or incorrect documentation? [Open a bug report](https://github.com/Claudfather/clauDNA/issues/new?template=bug-report.yml). Include the skill name, steps to reproduce, and what you expected vs. what happened.

### Request a Skill

Have a workflow that would benefit from a dedicated skill? [Open a skill request](https://github.com/Claudfather/clauDNA/issues/new?template=skill-request.yml). Describe the use case, when the skill should trigger, and what the output should look like.

Before requesting, ask whether the capability could be a lens or mode inside an existing skill — clauDNA treats skills as thinking frameworks, not SKUs, and favors consolidation over new entries (see the Design Philosophy in the [README](./README.md#design-philosophy)).

### Suggest an Improvement

See a way to make an existing skill better? [Open an improvement issue](https://github.com/Claudfather/clauDNA/issues/new?template=improvement.yml). Point to the skill, explain what's wrong or missing, and propose a fix.

### Contribute Code

Ready to write code? Read on.

## Development Workflow

### Setup

```bash
git clone https://github.com/Claudfather/clauDNA.git
cd clauDNA
```

No build step. The repo is a plugin — skills are markdown files, hooks are shell scripts, and validation is plain Python. One-time setup for the check toolchain (in your Python environment of choice):

```bash
make deps   # python3 -m pip install -r requirements-dev.txt
```

Every check-set target invokes its tool as `python3 -m <tool>` rather than by bare name. That is deliberate: `make deps` usually has no writeable system site-packages, so pip does a user install and the `ruff`/`pytest` console scripts land in `~/.local/bin`, which is not always on PATH. Going through the interpreter means `make check` works regardless, and resolves the tools in the same interpreter they were installed for. Keep new targets in that style.

Release qualification deliberately uses a private HOME and excludes user-site packages. For that maintainer workflow, install the same pinned dependencies in a Python 3.12 virtual environment as described in the [package release guide](documentation/guides/PACKAGE_RELEASE.md). Qualification preflights the selected interpreter; `release.sh` performs that check before changing files or committing a version bump. Ordinary `make check` retains its user-install support.

The unified CI workflow runs the check-set on pull requests (including stacked
branches) and pushes to `main`. Add validation commands to Makefile targets, not
standalone validation workflows; all use `requirements-dev.txt`.
Main pushes set `FULL_VALIDATE=1`, so an empty diff against `origin/main` cannot
demote skill errors to warnings. PRs retain touched-skill scoping and the
`full-validate` label override.

### Cloud Agents

[`.cursor/environment.json`](./.cursor/environment.json) makes the repo ready to work in from the first prompt in a [Cursor Cloud Agent](https://cursor.com/docs/cloud-agent/setup). It declares one `install` step — [`.cursor/install.sh`](./.cursor/install.sh), which runs `make deps` — so an agent boots with the same pinned toolchain CI uses. The requirements list is not duplicated there; the toolchain stays defined once, in `requirements-dev.txt`.

There is no `start` command and no `terminals`, because the repo has no server or service to run. The install script also creates `~/.local/bin` before pip installs into it, so login shells add it to PATH and a bare `ruff` works interactively. Nothing in it needs secrets.

### Making Changes

1. **Create a branch** off `main`:
   ```bash
   git checkout main && git pull --ff-only
   git checkout -b feat/your-change
   ```

2. **Edit the source files.** The repo structure:
   - `skills/<name>/SKILL.md` — skill definitions (see [SKILL_CONTRACT.md](./SKILL_CONTRACT.md))
   - `agents/` — agent persona definitions (see [AGENT_CONTRACT.md](./AGENT_CONTRACT.md))
   - `plugin-hooks/` — hook scripts + `hooks.json` wiring
   - `scripts/` — validation and release tooling

3. **Test locally** by loading the plugin from your checkout:
   ```bash
   claude --plugin-dir /path/to/clauDNA
   ```
   Then invoke the skill you changed (e.g. `/claudna:audit tech-debt`) and verify it works.

4. **Run the full check-set:**
   ```bash
   make check
   ```
   This is the exact set CI runs — `.github/workflows/ci.yml` executes this same target, so a green `make check` is a green CI run. The check-set is defined once, in the [`Makefile`](./Makefile) (`make -n check` lists it); individual sub-targets (`make lint`, `make test`, `make check-skills`, ...) are available while iterating. Among the checks, `integration-test.py` covers reference-file resolution, tool-name validity, body-structure conventions, and cross-skill uniqueness. CI additionally forwards PR labels; to reproduce a label-gated run: `PR_LABELS=full-validate make check`. When a description changes, check that skills still trigger from plain prompts: `make routing-eval` (paid; needs Claude Code and a login or `ANTHROPIC_API_KEY`), or add the `routing-eval` label to the PR.

5. **Update CHANGELOG.md** — add your change under the `[Unreleased]` section following the [Keep a Changelog](https://keepachangelog.com/) format.

6. **Open a PR** against `main`. Fill out the PR template.

### Writing a New Skill

Every skill must satisfy [SKILL_CONTRACT.md](./SKILL_CONTRACT.md). The short version:

- Lives in `skills/<name>/SKILL.md`
- Starts with YAML frontmatter: `name` (must match directory), `description` (20-500 chars, begins with `Use ` — when/at/before/after/to, per SKILL_CONTRACT §2.1 rule 1)
- Body is at least 200 characters of markdown
- No hardcoded paths to `~/.claude/skills/`, `~/.claude/commands/`, or `~/.claude/agents/`
- `name` is globally unique across the repo
- **Add it to `.cursor-plugin/plugin.json`'s `skills` list**, unless it's restricted to a host or a context (below) — the list is explicit, not directory-discovered (#340), so a new portable skill that's missing from it fails `make check-manifest` at CI time, not before. If the skill needs Claude Code's own plugin/hook internals, or a clone of this repo, mark it instead of listing it: `hosts: [claude-code]` or `requires-context: repo-clone` in its frontmatter (SKILL_CONTRACT §2.2) — the gate then requires it to be *absent* from the Cursor list.

Run `make check-skills` to catch contract violations while iterating, `make check-manifest` for the Cursor-list step specifically, and `make check` before pushing.

### Modifying Hooks

Hook scripts live in `plugin-hooks/` and are wired via `plugin-hooks/hooks.json`. If you add a new hook:

1. Add the script to `plugin-hooks/`
2. Wire it in `hooks.json` with the correct event type and matcher
3. Test by loading the plugin locally — hooks activate automatically

The directory is named `plugin-hooks/` (not `hooks/`) to work around a Claude Code bug. Don't rename it.

## Testing Requirements

Before opening a PR, verify:

- [ ] `make check` passes — the exact check-set CI runs, defined once in the `Makefile`
- [ ] You tested the affected skill/hook locally with `claude --plugin-dir`

### The Claudron contract

clauDNA drives the Claudron engine through its CLI, and mirrors a few parts of its schema (each memory home's sections, the capabilities harvest gates on, the summary schema's home enum). Two checks keep the two repos in step:

- **`make check`** checks those mirrors against `contracts/claudron.json`, a copy of `claudron contract --json` from the release `contracts/claudron.ref` names (`tests/test_claudron_contract.py`). No engine needed.
- **The `contract with Claudron` CI job** (`make deps-contract test-contract`) installs that release and runs `tests/test_claudron_live.py`: the copy must be exactly that engine's contract, and harvest must work end to end through it. Claudron's own CI runs the same file against every Claudron change (`CLAUDNA_CONTRACT=compat`), so a Claudron change that would break clauDNA fails there, before it ships.
- **The `harvest on Claudron <ref>` CI jobs** run the same file in `floor` mode against releases older than memory homes (`CLAUDRON_FLOOR_REFS` in the Makefile, down to the `claudron>=0.2` the skills declare), so the paths harvest keeps for older engines stay tested.

**Moving to a new Claudron release** is mostly automatic. When Claudron has a newer release, the daily `claudron-release` workflow moves to it on a `claudron/<tag>` branch and runs `make check` and the live suite there. GitHub Actions may not open PRs in this repo (#432), so the workflow then leaves one issue for the release, and a person or the fleet opens the PR from that branch, as the issue says. Later runs stop at that PR, or find the issue again while the branch waits. By hand: install the release, run `python3 scripts/sync_claudron_contract.py --ref <its tag>` (it writes the contract and the pin and re-renders output-guide §3's status table), and commit the result along with whatever the move changes here. `make check` then tells you which mirror has to follow.

CI runs the same `make check` target, so local green means CI green. If CI fails where local passed, your checkout is either behind `origin/main` or missing the pinned toolchain (`make deps`); CI runs Python 3.12.

## PR Expectations

- **One concern per PR.** A skill fix and an unrelated hook change should be separate PRs.
- **Descriptive title.** Use conventional commits: `feat:`, `fix:`, `docs:`, `chore:`.
- **Fill out the PR template.** The checkboxes are there for a reason.
- **Version bumps.** If your change affects what users get (new skill, changed behavior, hook change), bump `version` in **all three** `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json` and `.codex-plugin/plugin.json`. Marketplace users only receive updates on version bumps, and `make check-manifest` fails if these versions disagree. Bug fixes to docs or tests don't need a bump.
- **CI must pass.** CI runs `make check` — the same command you run locally, so there are no CI-only surprises. Run it before pushing.

## Release Process

Maintainers use `scripts/release.sh` to cut releases:

```bash
./scripts/release.sh patch   # 0.3.0 → 0.3.1
./scripts/release.sh minor   # 0.3.0 → 0.4.0
./scripts/release.sh major   # 0.3.0 → 1.0.0
```

The script preflights the isolated development interpreter and package support generator, bumps all three `plugin.json` manifests together, regenerates the support catalog/table, rewrites the CHANGELOG's `[Unreleased]` section under the new version, then commits the release outputs. It qualifies that exact commit before creating a local tag. It refuses to start if manifest versions disagree or the support projection is stale; set up the release virtual environment, run `make deps`, regenerate and commit as needed before releasing. `--dry-run` validates without changing files, commits or tags. See the [package release guide](documentation/guides/PACKAGE_RELEASE.md) for qualification commands, receipts, and native acceptance limits.

**What a marketplace user receives.** The Claude Code marketplace entry (`.claude-plugin/marketplace.json`) names `{"source": "github", "repo": "Claudfather/clauDNA"}` with no `ref` or `sha`, so it **tracks the default branch**: on a version bump a user fetches the head of the default branch at fetch time, not necessarily the exact commit that bumped the version. Package receipts bind release artifacts to a commit; they do not change this live catalog. Packaging emits a separate SHA-pinned Claude descriptor for owner review and promotion. Native installation and execution still require their own receipts. Cursor and Codex receive no guessed pin fields.

Contributors don't need to run this — just add your CHANGELOG entry and bump the version if applicable.

## Distribution

clauDNA ships to three hosts from one tree, and the manifests are not interchangeable.
The [generated support table and consumer lifecycle guide](documentation/guides/PACKAGE_SUPPORT.md)
derive inventory from these manifests and skill frontmatter. After changing those
inputs or a package version, run `python3 scripts/generate_package_support.py` and
commit its catalog/table updates. `make check-package-support` checks drift and is
part of `make check`; the generator's YAML dependency remains development-only.

| | Claude Code | Cursor | Codex |
|---|---|---|---|
| Manifest | `.claude-plugin/plugin.json` | `.cursor-plugin/plugin.json` | `.codex-plugin/plugin.json` |
| Marketplace manifest | `.claude-plugin/marketplace.json` (name `Claudfather`) | `.cursor-plugin/marketplace.json` (name `claudfather`) | `.agents/plugins/marketplace.json` (name `Claudfather`) |
| Components | `skills/`, `agents/`, `plugin-hooks/` | `skills/`, `agents/` — no hooks | Explicit skill list; store hooks + startup briefing; inert native agents |

These asymmetries are deliberate and gated by `scripts/validate-manifest.py`:

- **The marketplace names differ in case.** Claude Code's stays `Claudfather` because the documented install command is `/plugin install claudna@Claudfather`. Cursor's must be `claudfather` because Cursor's marketplace identifier grammar allows only lowercase alphanumerics and hyphens.
- **The Cursor manifest declares no hooks**, so the Claude Code shell hooks never fire in a Cursor-based environment. This is enforced two ways: the validator rejects a `hooks` field in the Cursor manifest, and it rejects a `hooks/hooks.json` at the repo root, which is where Cursor's folder discovery would find hooks with no manifest change to notice.
- **The Codex manifest explicitly selects its skill catalog**, preserving the Claude-only and source-checkout exclusions. All eight bundled role prompts map to a read-and-dispatch procedure. A route is supported only on execution hosts where actual same-host availability and its required fixture proof pass; unsupported routes remain explicit. No native agent registrations. Five store handlers plus the startup briefing are distinct from hook trust/execution. The generated support table owns the current per-host counts. Installing does not grant hook trust.

### Submitting to the Cursor marketplace

The repo is kept submission-ready; `make check-manifest` covers the mechanical half of [Cursor's submission checklist](https://cursor.com/docs/reference/plugins). To submit or re-submit:

1. Run `make check` and confirm it is green.
2. Confirm the plugin loads in Cursor from a local copy at `~/.cursor/plugins/local/claudna` (**Developer: Reload Window**, then check **Customize** for the expected skills and agents, and for the absence of hooks).
3. Submit the repository URL at [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish). Cursor reviews every plugin manually.

## Code of Conduct

Be respectful, constructive, and assume good intent. We're building tools that make developers more productive — that mission extends to how we treat each other in issues and PRs.

## Questions?

Open an [issue](https://github.com/Claudfather/clauDNA/issues) — no question is too small.

### Codex verification

`make routing-eval-codex` checks the deterministic catalog floor and is part of
`make check`. Explicit `--live` mode measures bounded `catalog_selection` choices
with isolated HOME/CODEX_HOME/work/tmp paths; see the runner's `--help`. The input is actual installed names, descriptions and invocation hints, with exact schema responses retained privately outside the public report. Prompt and schema define mode as the routing invocation suffix, preserving installed verbs/selector flags rather than an inferred semantic label. It does
not execute skills or prove native automatic routing. Keep `make routing-eval`
unchanged for Claude-only evaluation; do not run it in Codex-only verification.
Native skill-read/action, same-host fresh reviewer spawn/wait, and packaged startup
execution/context-delivery evidence are separate gates in the
[Codex workflow plan](documentation/planning/2026-10-16-codex-engineering-workflows.md).
Do not transfer desktop delegation proof to native CLI or mark the mixed-fleet
week complete from a local source/native canary.


## Held storage ownership qualification

Internal output uses `CLAUDNA_STATE_DIR` (absolute), default `~/.claudna`.
Maintainer scripts reuse the session-store resolver and allocator through
`scripts/release_toolchain.py`. A coherent real native context owns its scratch
and receipts; otherwise pass the actual `--session` and `--host` supplied by the
host. Outside all native workflows, explicitly opt into `--standalone` or
`STORAGE_OWNER_ARGS=--standalone` for Make targets. Missing/conflicting native
identity must never be repaired with an operation ID. Standalone operations are
typed separately under `R/operations/op-<32 hex>/` and create no session lifecycle.

Package/release output paths, routing report paths and canary `--dir` are explicit
exports. Canonical private receipts remain under the selected owner and bind the
export to its exact commit/archive or report digest. Private host fixture
`--home`, `--codex-home` and `--tmpdir` options do not redirect canonical output.
Owned checks disable Ruff/pytest/bytecode caches; dependency installation and
native host/tool cache policy remain unchanged. Use the pinned toolchain through
`python3 -m`; run fresh checks in isolated exports with private HOME/TMP and state.

The five-PR storage stack remains held outside main and the release path. Phase04
supplies native-session artifact defaults on the held draft stack; native
identity/write acceptance gates merge/release, with one smoke per materially
different identity-delivery mechanism. Static Markdown checks, executable fixtures, actual
native skill/publication execution and named external-consumer acceptance are
separate evidence. A fixture pass is not a complete package storage or cutover
verdict. Keep historical data in place. Readers must accept the new handoff/feed
protocol before writer cutover. A specific recovery artifact must read retained
new layout and write only under R, with native/consumer acceptance; otherwise an
approved forward-recovery plan is required. An arbitrary older package is not
qualified rollback. D6 requires a major release or an owner-approved exception,
and release/installation still need their own authorization. No intermediate
version bump or release is permitted.
