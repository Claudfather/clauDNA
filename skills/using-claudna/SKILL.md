---
name: using-claudna
user-invocable: true
description: "Use at conversation start to orient in the clauDNA skill set, when unsure which installed skill fits a task, or to verify the installation is healthy — version, hooks, skills loadable, dependencies (Installation Health section). For discovering third-party skills from the public ecosystem, use /claudna:find-skills. Replaces /skill-health."
argument-hint: "[health]"
---

# Using clauDNA

The orientation skill: how to find the right installed skill for a task, and how to verify the installation itself. Injected as a pointer by the SessionStart briefing; also directly invocable (`/claudna:using-claudna health` jumps straight to Installation Health).

**If you were dispatched as a subagent to execute a specific task, skip this skill** — orientation is the orchestrator's job; your task prompt is your routing.

## Finding Skills

When a task might have a matching skill and the picker didn't surface one:

1. **Enumerate the installed set.** The catalog is the skill directories of this plugin — marketplace install: `~/.claude/plugins/cache/Claudfather/claudna/<version>/skills/`; development checkout: `<repo>/skills/`. One directory per skill; `_shared/` is support material, not a skill.
2. **Match intent against `description` fields, not names.** Descriptions are the routing surface (SKILL_CONTRACT §2.1): trigger-first, with negative routing between confusable siblings. Read the frontmatter of plausible candidates; the description states *when* to reach for the skill.
3. **Engines carry verbs.** Consolidated capabilities live as modes, not skills: infra operations are `/claudna:modal|railway|vercel|neon <verb>`, audits are `/claudna:audit <lens>`, session continuity is `/claudna:session <mode>`, review is `/claudna:review-work <mode>`, shared-vault knowledge is `/claudna:claudron <verb>`, and the review panel's lenses run via `/claudna:ironclad --lens <name>`. If a remembered skill name is missing, its successor's description carries a `Replaces /old-name` breadcrumb — search descriptions for the old name.
4. **Nothing installed fits →** `/claudna:find-skills` searches the public ecosystem; a genuinely new repeatable workflow is a candidate for `/claudna:skill-scaffold`.

**A newly shipped skill *name* needs a session restart to register.** Claude Code enumerates the skill catalog once per process at session start, so a just-released name can return `Unknown skill` — a plugin/cache update refreshes existing skills' content in place but does not register net-new names. If a skill you know exists won't resolve, confirm the plugin cache is current (`/claudna:using-claudna health`), then restart the session.

A note on dispatch discipline: this skill deliberately does **not** mandate skill-first invocation before every response. That doctrine ships only if the routing-fixture record shows persistent misses (epic decision — the consolidated catalog is designed to route well on its own). Trust the picker; reach for this skill when it doesn't.

## Installation Health

Read-only diagnostic — run after install, after updates, or when something feels off. Run all six checks sequentially without pausing, then present the combined findings table. Under 5 seconds, no subagents, never modifies anything.

### 1. Locate plugin installation

```bash
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/Claudfather/claudna/*/ 2>/dev/null | sort -V | tail -1)
```

- If found, proceed with all checks against that path.
- If not found, check for a development checkout (`.claude-plugin/plugin.json` in cwd or parents); use it and note "running from source checkout".
- If neither: report FAIL ("clauDNA not installed — run `/plugin marketplace add Claudfather/clauDNA` then `/plugin install claudna@Claudfather`"), skip remaining checks, present the abbreviated table.

### 2. Check plugin version

Read `$PLUGIN_ROOT/.claude-plugin/plugin.json` → `version`. Then:

```bash
gh release view --repo Claudfather/clauDNA --json tagName -q '.tagName' 2>/dev/null
```

- **PASS** — installed matches latest release (strip leading `v`).
- **WARN** — behind latest. Recommend `/plugin update claudna@Claudfather`.
- **PASS (offline)** — GitHub unreachable; report installed version, note "could not check for updates".

### 3. Verify hooks

Read `$PLUGIN_ROOT/plugin-hooks/hooks.json`. Verify **all six wired hooks** and that each referenced script exists on disk:

| Hook | Event | Matcher |
|------|-------|---------|
| session-start | SessionStart | startup\|clear |
| pretooluse-permissions | PreToolUse | Bash |
| auto-format | PostToolUse | Write\|Edit |
| telemetry-emit | PostToolUse | Skill |
| precompact-reflect | PreCompact | *(any)* |
| notify | Notification | *(any)* |

- **PASS** — all six present in JSON, all scripts exist. **WARN** — entries or scripts missing (list them). **FAIL** — hooks.json missing/unparseable. `statusline.sh` is opt-in, informational only.

### 4. Scan skills

List skill directories under `$PLUGIN_ROOT/skills/` (excluding `_shared/`). For each `SKILL.md`, parse the frontmatter: `name` matches the directory, `description` non-empty. Count total / parsed / failed.

- **PASS** — all parse. **WARN** — 1–2 fail (list). **FAIL** — 3+ fail, or the directory is missing/empty.

### 5. Check dependencies

```bash
for cmd in jq gh git node npx; do
  command -v "$cmd" &>/dev/null && echo "$cmd: found" || echo "$cmd: MISSING"
done
```

Optional formatters (informational — auto-format degrades gracefully): `prettier`, `ruff`, `sqlfluff`. Skills declare their own runtime needs in `requires:` frontmatter — for a specific skill's dependencies, read its frontmatter and `command -v` each entry.

- **PASS** — all baseline available. **WARN** — baseline missing (list with install guidance).

### 6. Telemetry state

```bash
echo "CLAUDNA_TELEMETRY=${CLAUDNA_TELEMETRY:-unset}"
```

If enabled: check `${CLAUDNA_TELEMETRY_PATH:-~/.claude/telemetry/skill-events.jsonl}` exists and is writable; report size, line count, latest timestamp.

- **INFO** if disabled/unset. **PASS** if enabled + file writable. **WARN** if enabled but file/dir broken.

### Presenting results

One findings table (Check / Status / Notes), then a summary line (`6 checks: N passed, N warnings, N failures, N info`), then a concrete next step for each WARN/FAIL. Read-only, no network required (version check degrades), under 5 seconds, no subagents.
