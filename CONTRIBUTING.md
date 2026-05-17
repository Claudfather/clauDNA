# Contributing to clauDNA

Thanks for your interest in improving clauDNA. This guide covers the ways you can contribute and the workflow for each.

## Ways to Contribute

### Report a Bug

Found a skill that errors out, a hook that misfires, or incorrect documentation? [Open a bug report](https://github.com/Claudfather/clauDNA/issues/new?template=bug-report.yml). Include the skill name, steps to reproduce, and what you expected vs. what happened.

### Request a Skill

Have a workflow that would benefit from a dedicated skill? [Open a skill request](https://github.com/Claudfather/clauDNA/issues/new?template=skill-request.yml). Describe the use case, when the skill should trigger, and what the output should look like.

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

No build step. The repo is a Claude Code plugin — skills are markdown files, hooks are shell scripts, and validation is plain Python (requires `pyyaml`).

### Making Changes

1. **Create a branch** off `main`:
   ```bash
   git checkout main && git pull --ff-only
   git checkout -b feat/your-change
   ```

2. **Edit the source files.** The repo structure:
   - `skills/<name>/SKILL.md` — skill definitions (see [SKILL_CONTRACT.md](./SKILL_CONTRACT.md))
   - `agents/` — agent persona definitions
   - `plugin-hooks/` — hook scripts + `hooks.json` wiring
   - `scripts/` — validation and release tooling

3. **Test locally** by loading the plugin from your checkout:
   ```bash
   claude --plugin-dir /path/to/clauDNA
   ```
   Then invoke the skill you changed (e.g. `/claudna:tech-debt`) and verify it works.

4. **Run the validators:**
   ```bash
   pip install pyyaml  # one-time
   python3 scripts/validate-skills.py
   python3 scripts/validate-manifest.py
   ```
   CI runs these on every PR — they must pass before merge.

5. **Update CHANGELOG.md** — add your change under the `[Unreleased]` section following the [Keep a Changelog](https://keepachangelog.com/) format.

6. **Open a PR** against `main`. Fill out the PR template.

### Writing a New Skill

Every skill must satisfy [SKILL_CONTRACT.md](./SKILL_CONTRACT.md). The short version:

- Lives in `skills/<name>/SKILL.md`
- Starts with YAML frontmatter: `name` (must match directory), `description` (20-500 chars, starts with "Use when...")
- Body is at least 200 characters of markdown
- No hardcoded paths to `~/.claude/skills/`, `~/.claude/commands/`, or `~/.claude/agents/`
- `name` is globally unique across the repo

Run `python3 scripts/validate-skills.py` to catch violations before pushing.

### Modifying Hooks

Hook scripts live in `plugin-hooks/` and are wired via `plugin-hooks/hooks.json`. If you add a new hook:

1. Add the script to `plugin-hooks/`
2. Wire it in `hooks.json` with the correct event type and matcher
3. Test by loading the plugin locally — hooks activate automatically

The directory is named `plugin-hooks/` (not `hooks/`) to work around a Claude Code bug. Don't rename it.

## Testing Requirements

Before opening a PR, verify:

- [ ] `python3 scripts/validate-skills.py` passes (skill contract)
- [ ] `python3 scripts/validate-manifest.py` passes (plugin manifest)
- [ ] You tested the affected skill/hook locally with `claude --plugin-dir`
- [ ] CHANGELOG.md has an entry under `[Unreleased]`

For changes that add or modify validation scripts, also run:
```bash
python3 -m pytest tests/
```

## PR Expectations

- **One concern per PR.** A skill fix and an unrelated hook change should be separate PRs.
- **Descriptive title.** Use conventional commits: `feat:`, `fix:`, `docs:`, `chore:`.
- **Fill out the PR template.** The checkboxes are there for a reason.
- **Version bumps.** If your change affects what users get (new skill, changed behavior, hook change), bump `version` in `.claude-plugin/plugin.json`. Marketplace users only receive updates on version bumps. Bug fixes to docs or tests don't need a bump.

## Release Process

Maintainers use `scripts/release.sh` to cut releases:

```bash
./scripts/release.sh patch   # 0.3.0 → 0.3.1
./scripts/release.sh minor   # 0.3.0 → 0.4.0
./scripts/release.sh major   # 0.3.0 → 1.0.0
```

Contributors don't need to run this — just add your CHANGELOG entry and bump the version if applicable.

## Code of Conduct

Be respectful, constructive, and assume good intent. We're building tools that make developers more productive — that mission extends to how we treat each other in issues and PRs.

## Questions?

Open a [discussion](https://github.com/Claudfather/clauDNA/discussions) or ask in an issue. No question is too small.
