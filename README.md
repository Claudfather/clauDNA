# clauDNA

Claude Code plugin pack: curated skills, agents, and hooks distributed via the `Claudfather` marketplace.

## Quick Start

Requires [Claude Code](https://claude.ai/download) (`npm install -g @anthropic-ai/claude-code`).

Inside Claude Code:

```
/plugin marketplace add Claudfather/clauDNA
/plugin install claudna@Claudfather
```

That's it. Skills become available as `/claudna:<skill-name>` (namespaced under the plugin). Tab completion works — type `/claudna:` and press Tab to browse, or `/claudna:tech` and Tab to narrow. Hooks (auto-format, pretooluse permission expansion, notifications) activate automatically when the plugin is enabled.

### After install

Optional, in any order:

1. **Recommended `settings.json` tweaks** — permissions, statusLine, sandbox config. See [SETUP_GUIDE §3](./SETUP_GUIDE.md#3-bootstrapping-claudesettingsjson).
2. **Snowflake setup** — only if you use the Snowflake skills. See [SETUP_GUIDE §5](./SETUP_GUIDE.md#5-snowflake-key-pair-authentication).
3. **Shell aliases** — power-user worktree commands. See [SETUP_GUIDE §6](./SETUP_GUIDE.md#6-shell-configuration).
4. **Project setup** — in any project, run `/claudna:init-project` to generate `CLAUDE.md` and `CHANGELOG.md`.

### Headless / CI / Docker

For bots, CI runners, and Docker images, drop a `settings.json` with `enabledPlugins` + `extraKnownMarketplaces`, then set `CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1` and run `claude -p`. Full recipe in [SETUP_GUIDE §4](./SETUP_GUIDE.md#4-headless--ci--docker-provisioning).

## What ships with the plugin

| Directory | Count | Contents |
|-----------|-------|----------|
| `skills/` | 36 | User-invocable slash commands |
| `agents/` | 8 | `snowflake-analyst`, `dbt-engineer`, `neon-analyst`, `modal-ops`, `railway-ops`, `vercel-ops`, `code-reviewer`, `spec-reviewer` |
| `plugin-hooks/` | 6 wired + 1 opt-in | SessionStart briefing (opt-out `CLAUDNA_SESSION_BRIEFING=0`), auto-format on Write/Edit, PreToolUse permission expansion, PreCompact capture gate, opt-in skill telemetry, macOS notifications. (`statusline.sh` is opt-in — see [SETUP_GUIDE §3.2](./SETUP_GUIDE.md#32-statusline-optional).) Named `plugin-hooks/` to avoid a Claude Code bug that deletes any project-root `hooks/` directory between tool calls. |

## Design Philosophy

**Skills are thinking frameworks, not SKUs.** Before adding a new skill, ask: can this be a lens or mode inside an existing skill? Every skill description loads into every session, so fragmenting one capability into per-action skills bloats context and hides the framework the agent should be thinking in. Prefer one skill with modes over N near-duplicates — `/adversarial-review` runs single, dispatch, and respond modes; `/ironclad` fields an entire review panel through one entry point.

**Descriptions are routing surfaces.** The `description` field is what the model reads when choosing a skill, so it states *when to reach for the skill*, never how the skill works internally: trigger conditions first, confusable siblings disambiguated in place ("For X, use /claudna:Y"), CLI flags documented only in `argument-hint`. The grammar is contract-bound and validator-enforced — see [SKILL_CONTRACT.md §2.1](./SKILL_CONTRACT.md).

## Skills

Invocable as `/claudna:<name>` after marketplace install (e.g. `/claudna:audit tech-debt`). Bare names below are shown without the prefix for readability.

### Workflow

| Skill | Description |
|-------|-------------|
| `/session` | Session-continuity engine — `resume` / `handoff` / `checkpoint` / `name` modes (replaces the three `session-*`/`name-session` skills) |
| `/implement-plan` | Execute a design doc or GitHub Issue — browse, pick, challenge, build, test, PR |
| `/worktree` | Manage git worktrees for parallel Claude sessions |
| `/development-retro` | Post-merge retrospective — systemic patterns, friction, breadcrumb trails |
| `/weigh-development-paths` | Compare multiple viable approaches at a development junction |
| `/adversarial-review` | Structured plan challenge with evidence and anti-groupthink guards |
| `/forge` | Plan a multi-phase workstream — decision forks, phasing, spec/roadmap authoring |
| `/ironclad` | Harden a plan Issue or PR with a panel of independent review lenses — seven panel lenses built in; `--lens <name>` for a single-lens report |

### Code Quality

| Skill | Description |
|-------|-------------|
| `/audit` | Codebase-audit engine — `security` / `tech-debt` / `docs` / `design` / `access-path` / `data-model` / `frontend-perf` / `repo-health` lenses (replaces the eight standalone audit skills) |
| `/review-work` | Review engine — `changes` (uncommitted work) / `pr` (one PR) / `multi-pr` (parallel subagent reviews + synthesis) modes (replaces the two review skills) |
| `/verify-completion` | Verify work is actually complete before claiming success |
| `/visual-crawl` | Autonomous visual crawl — discover routes, screenshot at 3 viewports, file issues for findings |

### Product

| Skill | Description |
|-------|-------------|
| `/product-enhance` | Discover enhancements via intent interviews and gap analysis |
| `/product-vision` | Architecture-aware product vision — explore what the codebase could become |

### Knowledge

| Skill | Description |
|-------|-------------|
| `/capture` | Save knowledge to the vault — a note you write, external content (URL / file / text), or the current session's learnings (bare `/capture`) |
| `/index` | Organize the shared knowledge store; regenerate INDEX.md |
| `/recall` | Orientation briefing — what the fleet and this project already know, before you start |
| `/publish` | Distribute knowledge to other surfaces (bots, docs sites) |
| `/claudron` | Claudron vault engine — `lookup` / `status` over the shared knowledge vault (needs the Claudron CLI); save via `/capture` |

### Git

| Skill | Description |
|-------|-------------|
| `/quick-commit` | Stage all + commit with conventional commits format |
| `/commit-push-pr` | Commit, push, and open a PR |

### Data & Infrastructure

| Skill | Description |
|-------|-------------|
| `/dbt` | dbt build, test, compile, full-refresh |
| `/neon` | Neon PostgreSQL engine — `query` / `branch` / `info` modes (replaces the three `neon-*` skills) |

### Platform Operations

| Skill | Description |
|-------|-------------|
| `/modal` | Modal engine — `deploy` / `logs` / `status` modes (replaces the three `modal-*` skills) |
| `/railway` | Railway engine — `deploy` / `logs` / `status` modes (replaces the three `railway-*` skills) |
| `/vercel` | Vercel engine — `deploy` / `logs` / `status` modes (replaces the three `vercel-*` skills) |
| `/investigate-app` | Platform-agnostic production debugging |

### Utilities

| Skill | Description |
|-------|-------------|
| `/find-skills` | Discover and install new agent skills |
| `/heist` | Raid a GitHub repo for skills, config patterns, and novel approaches |
| `/init-project` | Set up CLAUDE.md, CHANGELOG.md, and .claude/ for a new or existing project |
| `/file-github-issue` | File a GitHub issue from a screenshot + short description |
| `/github-activity-report` | GitHub activity stats (PRs, commits, contributors) over a time window |
| `/using-claudna` | Orient in the skill set + Installation Health diagnostic (replaces the old skill-health diagnostic) |
| `/promotion-intake` | Land a Claudosseum promotion package as a reviewable PR (validator-gated) |
| `/skill-scaffold` | Scaffold a new clauDNA skill directory with valid frontmatter |
| `/cleanup-legacy-install` | Remove a legacy pre-plugin `~/.claude/` overlay after upgrading |

## Daily Workflow

The skills form a pipeline:

```
Morning
───────────────────────────────────────────────────
  /claudna:audit repo-health     → See what needs attention across all repos
  /claudna:session resume        → Pick a repo, get a 30-second briefing

Planning (when starting new work)
───────────────────────────────────────────────────
  /claudna:audit tech-debt       → Find what's broken → generates phase docs
  /claudna:product-enhance       → Find what could be better → generates phase docs
  /claudna:product-vision        → Explore what the codebase could become

Building (the core loop)
───────────────────────────────────────────────────
  /claudna:implement-plan        → Point at a phase doc
                                   ├── Challenge round (first principles review)
                                   ├── Build & test
                                   ├── PR with deliverable audit
                                   └── Say "next" → auto-compacts → next phase

Reviewing
───────────────────────────────────────────────────
  /claudna:review-work pr 42     → Structured review of any PR
  /claudna:review-work changes   → Audit uncommitted work

End of Day
───────────────────────────────────────────────────
  /claudna:session handoff       → Capture decisions, learnings, next steps
                                   → Writes handoff file for tomorrow's /claudna:session resume
```

**First time?** Start with `/claudna:audit repo-health` to see your repos, then `/claudna:session resume` in any project.

## Agents

Specialized personas invoked by skills or directly:

```
"Use snowflake-analyst to find the largest tables"
"Use dbt-engineer to review this model"
"Use neon-analyst to check table sizes"
"Use railway-ops to diagnose the deployment failure"
"Use vercel-ops to investigate the 500 errors"
"Use modal-ops to check GPU utilization"
```

## Safety

The marketplace install is managed by Claude Code: plugins live under `~/.claude/plugins/cache/Claudfather/claudna/<version>/`. Updates land in a new version directory; old versions are kept for ~7 days before auto-cleanup.

**Never touched by claudna:**
- `~/.claude/settings.json` — user-managed. claudna never writes here. Recommended snippets are documented in SETUP_GUIDE for you to merge manually.
- `~/.claude/notes/` — your personal files. claudna never reads or writes here.

## Project Template

`project-template/` provides a starter `.claude/` directory for individual projects. It's not shipped via the plugin — copy it manually or use `/claudna:init-project`:

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project instructions with workflow principles |
| `.claude/settings.json` | Project-specific permissions |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full guide. Writing a new skill? Start with the [Skill Authoring Guide](./documentation/guides/SKILL_AUTHORING_GUIDE.md).

Quick version: branch off `main`, make your change, run `python3 scripts/validate-skills.py`, update CHANGELOG.md, open a PR.

## Documentation

| File | Description |
|------|-------------|
| [PROJECT_MISSION.md](./PROJECT_MISSION.md) | What clauDNA is, what it's becoming, and where it fits in the Claudfather ecosystem |
| [CLAUDE.md](./CLAUDE.md) | Operating rules for agents extending clauDNA |
| [SKILL_CONTRACT.md](./SKILL_CONTRACT.md) | The binding contract every skill must satisfy. Enforced in CI by `scripts/validate-skills.py` |
| [SETUP_GUIDE.md](./SETUP_GUIDE.md) | Deep-dive setup — settings.json bootstrap, headless/CI provisioning, Snowflake key-pair auth, troubleshooting |
| [SKILL_AUTHORING_GUIDE.md](./documentation/guides/SKILL_AUTHORING_GUIDE.md) | How to write, test, and submit a skill — patterns, examples, anti-patterns |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Contribution workflow — bug reports, PRs, testing requirements |
| [CLAUDE_MD_TEMPLATE.md](./CLAUDE_MD_TEMPLATE.md) | Template for project-level `CLAUDE.md` files (used by `/claudna:init-project`) |
| [CHANGELOG.md](./CHANGELOG.md) | All notable changes |
