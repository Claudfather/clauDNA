---
name: skill-health
user-invocable: true
description: "Use when you want to verify your clauDNA installation is healthy — correct version, hooks active, skills loadable, dependencies available."
---

# Skill Health

Diagnostic scan of the clauDNA plugin installation. Checks version currency, hook wiring, skill integrity, dependency availability, and telemetry state. Run after install, after updates, or when something feels off.

This is a **read-only** skill. It reads files and environment state. It does not modify anything.

## Procedure

Run all six checks sequentially, then present the combined findings table. Do not ask questions or pause between checks — run them all and present results.

### 1. Locate plugin installation

Find the clauDNA plugin root:

```bash
PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/Claudfather/claudna/*/ 2>/dev/null | sort -V | tail -1)
```

- If found, proceed with all checks against that path.
- If not found, check if running from a development checkout (look for `.claude-plugin/plugin.json` in the current working directory or its parents). If found, use that as the plugin root and note "running from source checkout" in the report.
- If neither found: report FAIL for this check ("clauDNA not installed — run `/plugin marketplace add Claudfather/clauDNA` then `/plugin install claudna@Claudfather`"), skip remaining checks, and present the abbreviated results table.

### 2. Check plugin version

Read `$PLUGIN_ROOT/.claude-plugin/plugin.json` and extract the `version` field.

Then attempt to fetch the latest release tag from GitHub:

```bash
gh release view --repo Claudfather/clauDNA --json tagName -q '.tagName' 2>/dev/null
```

Scoring:
- **PASS** — installed version matches latest release (strip leading `v` from tag for comparison)
- **WARN** — installed version is behind latest release. Recommendation: "Run `/plugin update claudna@Claudfather` to update."
- **PASS (offline)** — GitHub unreachable. Report installed version and note "could not check for updates (no network or `gh` not available)."

### 3. Verify hooks

Read `$PLUGIN_ROOT/plugin-hooks/hooks.json`. Verify the three default hook entries exist:

| Hook | Event | Matcher | Script |
|------|-------|---------|--------|
| pretooluse-permissions | PreToolUse | Bash | `pretooluse-permissions.sh` |
| auto-format | PostToolUse | Write\|Edit | `auto-format.sh` |
| notify | Notification | *(any)* | `notify.sh` |

For each hook entry found in the JSON, also verify the referenced `.sh` script file exists at the expected path under `$PLUGIN_ROOT/plugin-hooks/`.

Scoring:
- **PASS** — all 3 hooks present in JSON and all scripts exist on disk
- **WARN** — hooks.json exists but one or more entries are missing, or a script file is missing. List which hooks/scripts are absent.
- **FAIL** — hooks.json itself is missing or unparseable

Additionally, note any *extra* hooks beyond the three defaults (e.g., telemetry-emit, statusline) as informational — not scored.

### 4. Scan skills

List all skill directories under `$PLUGIN_ROOT/skills/` (excluding `_shared/`).

For each directory containing a `SKILL.md`, attempt to parse the YAML frontmatter (the block between the opening and closing `---` lines). Check:
- `name` field exists and matches the directory name
- `description` field exists and is non-empty

Count:
- Total skill directories
- Successfully parsed
- Failed to parse (list the failing skill names)

Scoring:
- **PASS** — all skills parse cleanly
- **WARN** — 1-2 skills fail parsing. List them.
- **FAIL** — 3+ skills fail parsing, or the skills directory is missing/empty.

### 5. Check dependencies

Check availability of tools that clauDNA hooks and commonly-used skills depend on:

```bash
for cmd in jq gh git node npx; do
  command -v "$cmd" &>/dev/null && echo "$cmd: found" || echo "$cmd: MISSING"
done
```

These are the baseline dependencies. Also check optional formatters used by the auto-format hook:

```bash
for cmd in prettier ruff sqlfluff; do
  command -v "$cmd" &>/dev/null && echo "$cmd: found (optional)" || echo "$cmd: not found (optional)"
done
```

Scoring:
- **PASS** — all baseline dependencies available
- **WARN** — one or more baseline dependencies missing. List them with install guidance.
- Formatter availability is informational only — missing formatters mean auto-format degrades gracefully for those languages, not a failure.

### 6. Telemetry state

Check the telemetry configuration:

```bash
echo "CLAUDNA_TELEMETRY=${CLAUDNA_TELEMETRY:-unset}"
```

If telemetry is enabled (`CLAUDNA_TELEMETRY=1`):
- Check if the event file exists at `${CLAUDNA_TELEMETRY_PATH:-~/.claude/telemetry/skill-events.jsonl}`
- Report file size and line count
- Report the timestamp of the most recent event (if file exists)

Scoring:
- **INFO** if disabled/unset — "Telemetry disabled. Set `CLAUDNA_TELEMETRY=1` to enable skill usage tracking."
- **PASS** if enabled and event file exists and is writable
- **WARN** if enabled but event file missing or directory not writable

## Presenting Results

After running all checks, present a single findings table:

```
clauDNA Health Check
===============================================================================

  Check                        Status    Notes
  -------------------------    ------    -----------------------------------------
  Plugin installed             PASS      v0.3.0 at ~/.claude/plugins/cache/...
  Version currency             PASS      v0.3.0 (latest)
  Hooks wired                  PASS      3/3 default hooks active
  Skills loadable              PASS      52 skills, all parsed cleanly
  Dependencies                 WARN      prettier not found (optional)
  Telemetry                    INFO      Disabled

===============================================================================
  6 checks: 4 passed, 1 warning, 0 failures, 1 info
```

Then, for each WARN or FAIL item, provide a brief recommendation with a concrete next step.

## Notes

- **No network required.** The version check degrades gracefully if `gh` is unavailable or GitHub is unreachable. All other checks are local.
- **Under 5 seconds.** All checks are filesystem reads and `command -v` lookups. No heavy computation.
- **Read-only.** Never modify any files, plugin state, or settings.
- **No subagents.** Run all checks directly and present findings in a single response.
- **Development mode.** If running from a source checkout instead of a marketplace install, the skill still works — it just notes the alternate install path.
