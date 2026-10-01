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
   This is the exact set CI runs — `.github/workflows/ci.yml` executes this same target, so a green `make check` is a green CI run. The check-set is defined once, in the [`Makefile`](./Makefile) (`make -n check` lists it); individual sub-targets (`make lint`, `make test`, `make check-skills`, ...) are available while iterating. Among the checks, `integration-test.py` covers reference-file resolution, tool-name validity, body-structure conventions, and cross-skill uniqueness. CI additionally forwards PR labels; to reproduce a label-gated run: `PR_LABELS=full-validate make check`. To check that skills still trigger from plain prompts, `make routing-eval` runs the live routing evals (`scripts/routing_eval.py`: real `claude -p` runs, about $0.50, needs Claude Code and a login or `ANTHROPIC_API_KEY`); add the `routing-eval` label to run them on a PR, worth doing whenever a description changes.

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

CI runs the same `make check` target, so local green means CI green. If CI fails where local passed, your checkout is either behind `origin/main` or missing the pinned toolchain (`make deps`); CI runs Python 3.12.

## PR Expectations

- **One concern per PR.** A skill fix and an unrelated hook change should be separate PRs.
- **Descriptive title.** Use conventional commits: `feat:`, `fix:`, `docs:`, `chore:`.
- **Fill out the PR template.** The checkboxes are there for a reason.
- **Version bumps.** If your change affects what users get (new skill, changed behavior, hook change), bump `version` in **both** `.claude-plugin/plugin.json` and `.cursor-plugin/plugin.json`. Marketplace users only receive updates on version bumps, and `make check-manifest` fails if the two manifests disagree — bumping only one is worse than bumping neither. Bug fixes to docs or tests don't need a bump.
- **CI must pass.** CI runs `make check` — the same command you run locally, so there are no CI-only surprises. Run it before pushing.

## Release Process

Maintainers use `scripts/release.sh` to cut releases:

```bash
./scripts/release.sh patch   # 0.3.0 → 0.3.1
./scripts/release.sh minor   # 0.3.0 → 0.4.0
./scripts/release.sh major   # 0.3.0 → 1.0.0
```

The script bumps both `plugin.json` manifests together, rewrites the CHANGELOG's `[Unreleased]` section under the new version, commits, and tags. It refuses to start if the two manifests already disagree on the version, so reconcile them first.

**What a marketplace user receives.** The Claude Code marketplace entry (`.claude-plugin/marketplace.json`) names `{"source": "github", "repo": "Claudfather/clauDNA"}` with no `ref` or `sha`, so it **tracks the default branch**: on a version bump a user fetches the head of the default branch at fetch time, not necessarily the exact commit that bumped the version. Nothing binds a release to the reviewed commit. To bind them, set `sha` (a full commit) or a release-tag `ref` on the entry as part of the release change, and protect that tag separately — a pin is only a gate when the ref it names cannot be rewritten by whoever can write the default branch.

Contributors don't need to run this — just add your CHANGELOG entry and bump the version if applicable.

## Distribution

clauDNA ships to two hosts from one tree, and the manifests are not interchangeable:

| | Claude Code | Cursor |
|---|---|---|
| Manifest | `.claude-plugin/plugin.json` | `.cursor-plugin/plugin.json` |
| Marketplace manifest | `.claude-plugin/marketplace.json` (name `Claudfather`) | `.cursor-plugin/marketplace.json` (name `claudfather`) |
| Components | `skills/`, `agents/`, `plugin-hooks/` | `skills/`, `agents/` — no hooks |

Two asymmetries are deliberate and gated by `scripts/validate-manifest.py`:

- **The marketplace names differ in case.** Claude Code's stays `Claudfather` because the documented install command is `/plugin install claudna@Claudfather`. Cursor's must be `claudfather` because Cursor's marketplace identifier grammar allows only lowercase alphanumerics and hyphens.
- **The Cursor manifest declares no hooks**, so the Claude Code shell hooks never fire in a Cursor-based environment. This is enforced two ways: the validator rejects a `hooks` field in the Cursor manifest, and it rejects a `hooks/hooks.json` at the repo root, which is where Cursor's folder discovery would find hooks with no manifest change to notice.

### Submitting to the Cursor marketplace

The repo is kept submission-ready; `make check-manifest` covers the mechanical half of [Cursor's submission checklist](https://cursor.com/docs/reference/plugins). To submit or re-submit:

1. Run `make check` and confirm it is green.
2. Confirm the plugin loads in Cursor from a local copy at `~/.cursor/plugins/local/claudna` (**Developer: Reload Window**, then check **Customize** for the expected skills and agents, and for the absence of hooks).
3. Submit the repository URL at [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish). Cursor reviews every plugin manually.

## Code of Conduct

Be respectful, constructive, and assume good intent. We're building tools that make developers more productive — that mission extends to how we treat each other in issues and PRs.

## Questions?

Open an [issue](https://github.com/Claudfather/clauDNA/issues) — no question is too small.
