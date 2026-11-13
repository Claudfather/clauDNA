---
name: heist
user-invocable: true
disable-model-invocation: true
description: "Use when you want to raid a GitHub repo for skills, config patterns, or novel approaches worth adopting into clauDNA. For browsing or installing published skills from the open ecosystem, use /claudna:find-skills."
argument-hint: "[org/repo or GitHub URL]"
allowed-tools:
  - Bash(git diff *)
  - Bash(git log *)
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
  - WebFetch
requires:
  - cli: "gh"
    reason: "GitHub API access for fetching repo contents and file trees"
---

# Heist — Raid a Repo for Good Ideas

> **Codex:** Read `../_shared/codex-tools.md` before following this skill. Apply its tool, root and dispatch mappings throughout.

Point at any GitHub repo and extract what's worth adopting — skills, config patterns, novel approaches. Works on skill repos, dotfile configs, and regular projects alike.

**Persona:** A crew boss running a heist. Send scouts to case the target, review what they find, take only what genuinely improves the family.

## Working files and output

Follow `../_shared/orchestration-guide.md` §1 for native session allocation and exact-owner cleanup. Clone/API working material, scout research, comparison notes, and any private candidate copies stay in `<scratch>`. The sanitized catalog, comparison report, and adoption summary default to `<artifacts>`. Any selected adoption remains an explicit user-approved project/repository edit; preserve that project ownership and never treat it as session output. Missing/conflicting/unverified native identity or ordinary-permission denial makes persistence unavailable; do not use cwd, an operation ID, or OS temp as fallback. Remove only the exact owned scratch after all scouts/children have exited; retain artifacts on every outcome.

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

Resolve `<scratch>` through orchestration-guide §1 before fetching the file tree via `gh api repos/<org>/<repo>/git/trees/<default-branch>?recursive=1`. Store only private working material there; write sanitized selected findings to `<artifacts>`.

Count interesting files (`SKILL.md`, `CLAUDE.md`, `.claude/**`, `hooks/*`, `agents/*`, `commands/*`, root `*.md`, `settings.json`, etc.). If ≤30 → API browse. If >30 → recommend `git clone --depth 1`; if declined, API browse.

Launch 3 parallel `general-purpose` subagents. Read `scout-prompts.md` in this skill directory for full prompt templates. Pass each the browse mode, file tree, and scratch path. Each returns a 2-4 line summary only.

### Step 3: Present Catalog

Read **only scout summaries** — never full research files. Check each item's similarity to clauDNA via Glob/Grep on `skills/`. Assign **NEW**, **SIMILAR**, or **PARTIAL**. Present numbered catalog grouped by Skills & Commands, Config Patterns, Novel Approaches. Prompt: pick by number, `all`, or `none`.

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

Present target, counts (scanned/selected), actions (ADOPTED with paths, ENHANCED with changes, SKIPPED), and the canonical artifact report path. Next steps: inspect `git diff`; if a skill was adopted or enhanced and the user requests a release, bump the version in `.claude-plugin/plugin.json`, update `CHANGELOG.md`, and push so `/plugin update` can pick it up. Finalize only the exact `<scratch>` after actual scout/worker exits; retain `<artifacts>` and any user-approved project adoption on every outcome.

---

## Notes

- **API-first** — Clone only when >30 interesting files. Threshold: shallow clone (~3-5s) beats sequential API reads.
- **No plan mode** — Writes interleaved with user gates. Plan mode would block Write/Edit.
- **Orchestration** — Per `../_shared/orchestration-guide.md`: scratch dir, disk writes, summaries only.
- **No shell operators** — Separate tool calls. No `&&`, `|`, `;`, `2>&1`, `2>/dev/null`.
- **Self-contained adoptions** — Inline or remove foreign dependencies.
- **Works on any repo** — Not just skill repos. Scouts find patterns in any codebase.
- **Provenance** — record what was adopted/enhanced and its source repo/path in the commit message and CHANGELOG. Do NOT add attribution comments to shipped skill content.
- **vs `/claudna:find-skills`** — `/claudna:find-skills` searches skills.sh registry. `/claudna:heist` targets one repo, compares, and can enhance existing skills.
