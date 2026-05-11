# clauDNA

Claude Code plugin pack: curated skills, agents, and hooks distributed via the `Claudfather` marketplace. Also installable headlessly via a bash script for CI / fleet provisioning.

## Quick Start (marketplace install — recommended)

Inside Claude Code:

```
/plugin marketplace add chrisrogers37/claudna
/plugin install claudna@Claudfather
```

That's it. Skills become available as `/claudna:<skill-name>` (namespaced under the plugin). Hooks (auto-format, pretooluse permissions, notifications) activate automatically when the plugin is enabled.

### Headless install (CI, fleet, Docker images)

If you can't run interactive Claude Code commands:

```bash
git clone git@github.com:chrisrogers37/claudna.git
cd claudna
./install.sh
```

`install.sh` copies skills/agents/hooks directly into `~/.claude/`, plus interactively offers to add recommended permissions, sandbox config, and statusLine config to `~/.claude/settings.json`. Skills are invoked unnamespaced (`/<skill-name>`) in this mode.

### After install

1. **Snowflake setup** — Follow [SETUP_GUIDE.md Section 5](./SETUP_GUIDE.md#5-snowflake-key-pair-authentication) for key pair auth (optional, only if you use the Snowflake skills).
2. **Shell aliases** — `cat shell/zshrc-additions.sh >> ~/.zshrc && source ~/.zshrc` (optional).
3. **Project setup** — In any project, run `/init-project` (or `/claudna:init-project` if installed via marketplace) to generate `CLAUDE.md`, `CHANGELOG.md`, and `.claude/lessons.md`.

### Optional: enable the statusLine

The plugin ships a custom `statusline.sh` but Claude Code does not yet support statusLine declarations inside plugin manifests. To opt in, add this to your `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash ${HOME}/.claude/plugins/cache/Claudfather/claudna/0.2.0/plugin-hooks/statusline.sh"
  }
}
```

Update the version segment when bumping plugins.

## What ships with the plugin

| Directory | Count | Contents |
|-----------|-------|----------|
| `skills/` | 47 | 46 user-invocable slash commands + 1 context-only skill (`notifications`) |
| `agents/` | 8 | `snowflake-analyst`, `dbt-engineer`, `neon-analyst`, `modal-ops`, `railway-ops`, `vercel-ops`, `code-reviewer`, `spec-reviewer` |
| `plugin-hooks/` | 3 active + 1 opt-in | Auto-format on Write/Edit, pretooluse permission expansion, macOS notifications. (`statusline.sh` is opt-in — see above.) Named `plugin-hooks/` to avoid a Claude Code bug that deletes any project-root `hooks/` directory between tool calls. |
| `commands/` | 1 | `clauDNA-sync` (legacy; still useful for `install.sh` users) |

## Skills

User-invocable slash commands + 1 context-only skill (`notifications`).

### Workflow

| Skill | Description |
|-------|-------------|
| `/context-resume` | Pick up where you left off — scans git, PRs, plans, handoff notes |
| `/session-handoff` | End-of-session capture — decisions, learnings, next steps |
| `/repo-health` | Multi-repo dashboard — open PRs, CI status, stale branches |
| `/implement-plan` | Execute a design doc or GitHub Issue — browse, pick, challenge, build, test, PR |
| `/worktree` | Manage git worktrees for parallel Claude sessions |
| `/development-retro` | Post-merge retrospective — systemic patterns, friction, breadcrumb trails |
| `/name-session` | Label the current session so it shows up cleanly in `/resume` |
| `/weigh-development-paths` | Compare multiple viable approaches at a development junction |

### Code Quality

| Skill | Description |
|-------|-------------|
| `/tech-debt` | Scan for tech debt, generate phased remediation plans |
| `/security-audit` | Scan 8 vulnerability categories, generate remediation plans |
| `/review-pr` | Structured PR review with severity-categorized findings |
| `/review-changes` | Review uncommitted changes for bugs, conventions, security |
| `/lessons` | Capture and review lessons from corrections |
| `/verify-completion` | Verify work is actually complete before claiming success |
| `/frontend-performance-audit` | Trace re-render cascades, identify fetch/state/observer issues |
| `/cache-audit` | Check if CLAUDE.md and project config hurt prompt cache efficiency |
| `/access-path-audit` | Audit cross-cutting concern consistency across system interfaces (API, CLI, MCP, Slack) |
| `/visual-crawl` | Autonomous visual crawl — discover routes, screenshot at 3 viewports, file issues for findings |

### Product

| Skill | Description |
|-------|-------------|
| `/product-enhance` | Discover enhancements via intent interviews and gap analysis |
| `/product-vision` | Architecture-aware product vision — explore what the codebase could become |
| `/design-review` | Visual audit at 3 breakpoints with phased fix plans |
| `/docs-review` | Audit docs for accuracy, update plan statuses, archive stale docs |
| `/data-model-audit` | Audit code-to-schema fit — traces code paths to DB, identifies mismatches |

### Git

| Skill | Description |
|-------|-------------|
| `/quick-commit` | Stage all + commit with conventional commits format |
| `/commit-push-pr` | Commit, push, and open a PR |

### Data & Infrastructure

| Skill | Description |
|-------|-------------|
| `/dbt` | dbt build, test, compile, full-refresh |
| `/neon-query` | Run SQL against Neon PostgreSQL via psql |
| `/neon-info` | Neon dashboard — connection status, tables, branches |
| `/neon-branch` | Create and manage Neon database branches |

### Platform Operations

| Skill | Description |
|-------|-------------|
| `/modal-status` | Modal dashboard — apps, containers, secrets, GPU usage |
| `/modal-deploy` | Deploy Modal apps with health verification |
| `/modal-logs` | View and stream Modal app logs |
| `/railway-status` | Railway dashboard — services, deployments, environments |
| `/railway-deploy` | Deploy to Railway with build monitoring and rollback |
| `/railway-logs` | Filter Railway logs by level, time, patterns |
| `/vercel-status` | Vercel dashboard — deployments, domains, env vars |
| `/vercel-deploy` | Deploy to Vercel with health verification and rollback |
| `/vercel-logs` | Filter Vercel deployment logs |
| `/investigate-app` | Platform-agnostic production debugging |

### Utilities

| Skill | Description |
|-------|-------------|
| `/notes` | Persistent notes across sessions |
| `/notifications` | Configure macOS or iTerm2 notifications for Claude Code sessions |
| `/find-skills` | Discover and install new agent skills |
| `/heist` | Raid a GitHub repo for skills, config patterns, and novel approaches |
| `/init-project` | Set up CLAUDE.md, CHANGELOG.md, and .claude/ for a new or existing project |
| `/file-github-issue` | File a GitHub issue from a screenshot + short description |
| `/github-activity-report` | GitHub activity stats (PRs, commits, contributors) over a time window |
| `/clauDNA-migrate` | Migrate legacy commands to skills format |
| `/clauDNA-setup` | Bootstrap / sync (headless install only — marketplace users use `/plugin install`) |
| `/clauDNA-sync` | Diff repo against `~/.claude/` (headless install only — marketplace users use `/plugin update`) |

## Daily Workflow

The skills form a pipeline:

```
Morning
───────────────────────────────────────────────────
  /repo-health              → See what needs attention across all repos
  /context-resume           → Pick a repo, get a 30-second briefing

Planning (when starting new work)
───────────────────────────────────────────────────
  /tech-debt                → Find what's broken → generates phase docs
  /product-enhance          → Find what could be better → generates phase docs
  /product-vision           → Explore what the codebase could become

Building (the core loop)
───────────────────────────────────────────────────
  /implement-plan           → Point at a phase doc
                              ├── Challenge round (first principles review)
                              ├── Build & test
                              ├── PR with deliverable audit
                              └── Say "next" → auto-compacts → next phase

Reviewing
───────────────────────────────────────────────────
  /review-pr 42             → Structured review of any PR
  /review-changes           → Audit uncommitted work

End of Day
───────────────────────────────────────────────────
  /session-handoff          → Capture decisions, learnings, next steps
                              → Writes handoff file for tomorrow's /context-resume
```

**First time?** Start with `/repo-health` to see your repos, then `/context-resume` in any project.

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

**Marketplace install** is managed by Claude Code: plugins live under `~/.claude/plugins/cache/Claudfather/claudna/<version>/`. Updates land in a new version directory; old versions are kept for ~7 days before auto-cleanup.

**Headless install (`install.sh`)** backs up existing managed files before overwriting:

```
~/.local/share/clauDNA/backups/<YYYY-MM-DD_HHMMSS>/
```

This location is outside `~/.claude/` so Claude Code never discovers backup files.

**Never touched:**
- `~/.claude/settings.json` — user-managed, never overwritten (`install.sh`'s permissions merge only *adds* entries)
- `~/.claude/notes/` — personal data (lessons, decisions, patterns)
- `~/.claude/docs/` — installed once during setup, not synced afterward

## Project Template

`project-template/` provides a starter `.claude/` directory for individual projects. It is *not* shipped via the plugin — copy it manually or use `/init-project`:

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project instructions with workflow principles |
| `.claude/settings.json` | Project-specific permissions |
| `.claude/lessons.md` | Project-specific lessons from corrections |

## Contributing

1. Edit files in `skills/`, `agents/`, `commands/`, or `plugin-hooks/` (source of truth).
2. Test locally with `claude --plugin-dir /path/to/claudna` (loads the plugin for one session).
3. Run `python3 scripts/validate-skills.py` — CI enforces the same.
4. Bump `version` in `.claude-plugin/plugin.json` (marketplace users only get updates on version bumps).
5. Update `CHANGELOG.md`.
6. Submit PR — after merge, users update via `/plugin update claudna@Claudfather`.

## Documentation

| File | Description |
|------|-------------|
| [PROJECT_MISSION.md](./PROJECT_MISSION.md) | What clauDNA is, what it's becoming, and where it fits in the Claudfather ecosystem — read this first if you're an agent or contributor trying to understand the project's intent |
| [CLAUDE.md](./CLAUDE.md) | Operating rules for agents extending clauDNA — sync/install safety, standing permissions, what requires approval |
| [SKILL_CONTRACT.md](./SKILL_CONTRACT.md) | The binding contract every skill must satisfy. Enforced in CI by `scripts/validate-skills.py` |
| [SETUP_GUIDE.md](./SETUP_GUIDE.md) | Deep-dive setup companion to this README — Snowflake key-pair auth, configuration hierarchy, troubleshooting |
| [CLAUDE_MD_TEMPLATE.md](./CLAUDE_MD_TEMPLATE.md) | Template for project-level `CLAUDE.md` files (used by `/init-project`) |
| [CHANGELOG.md](./CHANGELOG.md) | All notable changes |
