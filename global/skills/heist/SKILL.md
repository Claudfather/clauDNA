---
name: heist
description: "Use when you want to raid a GitHub repo for skills, config patterns, or novel approaches worth adopting into clauDNA."
argument-hint: "[org/repo or GitHub URL]"
allowed-tools:
  - Bash(gh *)
  - Bash(git *)
  - Bash(rm -rf /tmp/heist-*)
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
  - WebFetch
---

# Heist — Raid a Repo for Good Ideas

Point at any GitHub repo and extract what's worth adopting — skills, config patterns, novel approaches. Works on skill repos, dotfile configs, and regular projects alike.

**Persona:** A crew boss running a heist. Send scouts to case the target, review what they find, take only what genuinely improves the family.

## Process

```
Parse target → Confirm? →[no]→ Abort
                  ↓ yes
            Fetch file tree → ≤30 files? →[yes]→ API browse scouts
                                ↓ no
                          Clone → Local scouts
                                    ↓
            Present catalog → User picks →[none]→ Abort
                                    ↓
            Deep-dive comparison (per item)
                  ↓
            Present → Approve? →[yes]→ ADOPT/ENHANCE → More? → loop/done
                        ↓ skip
                      More? → loop/done
                                    ↓
                          Summary & cleanup
```

## Procedure

Follow these steps exactly. Do NOT read CLAUDE.md or MEMORY.md — already in system prompt.

### Step 1: Parse & Validate

Accept `org/repo` or full GitHub URL (extract `org/repo`). Validate with `gh repo view <org/repo> --json name,description,stargazerCount,pushedAt`. Present repo name, description, stars, last push date. Wait for user confirmation.

### Step 2: Recon

Create scratch dir `/tmp/heist-<YYYY-MM-DD_HHMMSS>/`. Fetch file tree via `gh api repos/<org>/<repo>/git/trees/<default-branch>?recursive=1`.

Count interesting files (`SKILL.md`, `CLAUDE.md`, `.claude/**`, `hooks/*`, `agents/*`, `commands/*`, root `*.md`, `settings.json`, etc.). If ≤30 → API browse. If >30 → recommend `git clone --depth 1`; if declined, API browse.

Launch 3 parallel `general-purpose` subagents. Read `scout-prompts.md` in this skill directory for full prompt templates. Pass each the browse mode, file tree, and scratch path. Each returns a 2-4 line summary only.

### Step 3: Present Catalog

Read **only scout summaries** — never full research files. Check each item's similarity to clauDNA via Glob/Grep on `global/skills/`. Assign **NEW**, **SIMILAR**, or **PARTIAL**. Present numbered catalog grouped by Skills & Commands, Config Patterns, Novel Approaches. Prompt: pick by number, `all`, or `none`.

### Step 4: User Picks

**Gate:** Wait for explicit selection. Accept numbers, ranges, `all`, or `none`.

### Step 5: Deep-Dive Comparison

For each pick, launch a parallel `general-purpose` comparison subagent. Read `comparison-template.md` in this skill directory for the prompt template and report format.

### Step 6: Present & Execute

For each comparison, show: theirs (one-line), ours (one-line), recommendation (ADOPT/ENHANCE/SKIP), reasoning. Prompt: approve / modify / skip.

- **Approve:** Launch subagent per ADOPT or ENHANCE template in `comparison-template.md`.
- **Modify:** Ask user what to change, re-launch.
- **Skip:** Next item.

Naming collision on adopt: ask for alternative name.

### Step 7: Summary & Cleanup

Present target, counts (scanned/selected), actions (ADOPTED with paths, ENHANCED with changes, SKIPPED). Next steps: `git diff`, `/clauDNA-setup`, update CHANGELOG.md. Cleanup: `rm -rf /tmp/heist-<timestamp>/`

---

## Notes

- **API-first** — Clone only when >30 interesting files. Threshold: shallow clone (~3-5s) beats sequential API reads.
- **No plan mode** — Writes interleaved with user gates. Plan mode would block Write/Edit.
- **Orchestration** — Per `_shared/orchestration-guide.md`: scratch dir, disk writes, summaries only.
- **No shell operators** — Separate tool calls. No `&&`, `|`, `;`, `2>&1`, `2>/dev/null`.
- **Self-contained adoptions** — Inline or remove foreign dependencies.
- **Works on any repo** — Not just skill repos. Scouts find patterns in any codebase.
- **Attribution** — HTML comment linking source repo/path in all adopted/enhanced content.
- **vs `/find-skills`** — `/find-skills` searches skills.sh registry. `/heist` targets one repo, compares, and can enhance existing skills.
