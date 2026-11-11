---
name: using-claudna
user-invocable: true
description: "Use to verify clauDNA installation is healthy — hooks, skills and capture — or orient at conversation start and choose an installed skill for a task. For discovering third-party skills from the public ecosystem, use /claudna:find-skills. Replaces /skill-health."
hosts: [claude-code, codex]
argument-hint: "[health]"
---

# Using clauDNA

> **Codex:** Read `../_shared/codex-tools.md` before following this skill. Apply its tool, root and dispatch mappings throughout.

The orientation skill: how to find the right installed skill for a task, and how to verify the installation itself. Injected as a pointer by the SessionStart briefing; also directly invocable (`/claudna:using-claudna health` jumps straight to Installation Health).

**If you were dispatched as a subagent to execute a specific task, skip this skill** — orientation is the orchestrator's job; your task prompt is your routing.

## Finding Skills

1. Resolve the loaded plugin root per `../_shared/claudna-root.md`. Use that installed copy, never a newer cache inferred from the project cwd.
2. Enumerate the host's declared set: on Codex read `.codex-plugin/plugin.json`'s explicit `skills` paths; on Claude Code enumerate the canonical skill directories. Derive counts from this installation, not a remembered release. `_shared` is supporting material.
3. Match intent against frontmatter descriptions. Read the complete matching SKILL.md before action. Infra engines carry verbs, `audit` carries lenses, `session` carries modes, and `review-work` carries review modes; preserve arguments.
4. Nothing fits → use `find-skills` for third-party discovery. On Codex, a new executable procedure belongs in a clauDNA source checkout and its contribution workflow; the repo-clone-only `skill-scaffold` is excluded from this installed catalog. Claude Code can use `/claudna:skill-scaffold` from its required source context.

Newly installed names may require a catalog refresh or session restart on the execution host. Readback from the current session is the test; an updated cache alone is not registration evidence. This skill does not impose skill-first invocation before every response.

## Installation Health

Read-only diagnostics: inspect the loaded local package first. Do not install dependencies, modify trust or launch agents. Report the observed duration rather than promising every environment finishes in five seconds.

### Package doctor (default)

Resolve the actual loaded root per `../_shared/claudna-root.md`, then run the bundled directory entrypoint with the current host explicitly selected:

```sh
python3 -B "<claudna-root>/lib/claudna/package_support" doctor --host codex --json
```

Use `--host claude-code` on Claude Code. Add `--skill <canonical-name>` only for the selected workflow's prerequisites. The root defaults to the loaded package, never cwd or a guessed cache. An absent entrypoint on an older package is a version gap; do not borrow another checkout's doctor. Report the package version, check rows and limits. Exit 0 means no concrete local issue observed (unknowns remain unknown), 1 means attention, and 2 means invalid request or package diagnosis. Source hashes establish consistency, not authenticity. Found versioned PATH binaries remain version-unverified; the doctor never launches them. Missing baseline tools affect only their consumers.

The default does not scan other caches, standalone skills, telemetry or the session store. To include retained pipeline evidence, the operator must select an explicit store root; add `--store-root /absolute/selected/store`. This calls the existing read-only health report without creating a store, records or workers. Never infer installed/discovered, trusted or executed from a declared manifest.

The following sections are targeted follow-ups when the user requests that evidence, not extra default scans. Cursor can use the direct CLI with `--host cursor`; this skill remains excluded from Cursor's manifest. See [package support](../../documentation/guides/PACKAGE_SUPPORT.md#local-package-doctor) for the full command and output contract.

Keep `-B`: CPython otherwise may write an entrypoint bytecode cache before the doctor starts.

### 1. Locate and identify the installation

Resolve the actual loaded root per `../_shared/claudna-root.md`, verifying the host manifest exists. Read `.codex-plugin/plugin.json` on Codex or `.claude-plugin/plugin.json` on Claude Code. Report installed version and execution surface (native CLI or desktop). If absent, report the specific missing path and the host's supported plugin install procedure; do not search unrelated user caches.

### 2. Version

Report the installed version. Only for a requested remote update check, if `gh` is available and a bounded read is permitted, run `gh release view --repo Claudfather/clauDNA --json tagName` with a three-second subprocess timeout. Compare versions semantically. Offline/timeout → INFO with installed version, not a claim of latest release. Updating remains a separate authorized action.

### 3. Hook declaration, trust and observation

On Codex, inspect `plugin-hooks/codex-hooks.json`:

| Event | Handler | Matcher | Timeout |
|---|---|---|---|
| SessionStart | session-store.sh --host codex | absent (all supported starts) | native default |
| SessionStart | session-start.sh | startup | 5 |
| UserPromptSubmit | session-store.sh --host codex | absent | native default |
| PostToolUse | session-store.sh --host codex | Skill | native default |
| PreCompact | session-store.sh --host codex | absent | native default |
| SessionEnd | session-store.sh --host codex | absent | 3 |

Verify the quoted PLUGIN_ROOT command paths and all referenced files. There are five events and six handlers. Distinguish **declared**, **installed/discovered**, **trusted/enabled**, and **observed executing**. If the current host exposes hook listing, read its trust state; otherwise say trust is unknown. A manifest or file existing does not prove firing or stdout delivery. Never enable hooks as part of health. Compact capture policy belongs to Claudron, not this startup briefing.

On Claude Code, inspect `plugin-hooks/hooks.json` and each referenced script. Preserve all wired event/matcher checks:

| Hook | Event | Matcher |
|---|---|---|
| session-start | SessionStart | startup\|clear |
| pretooluse-permissions | PreToolUse | Bash |
| auto-format | PostToolUse | Write\|Edit |
| precompact-reflect | PreCompact | any |
| notify | Notification | any |
| session-store | SessionStart, PreCompact, SessionEnd | any |
| session-store (async) | UserPromptSubmit, PostToolUseFailure; PostToolUse | any; Skill |
| telemetry-emit (async) | PostToolUse, PostToolUseFailure | Skill |

PASS when every wired entry and referenced script exists; WARN for missing entries/scripts, listing each; FAIL for missing/unparseable hooks.json. The opt-in statusline is informational. These Claude-specific hooks are not inferred to exist on Codex. Cursor remains hook-free.

### 4. Catalog

On Codex, validate each declared path exists, has a matching `name` and a nonempty description. No folder discovery or empty list is acceptable. Exclude `cleanup-legacy-install` (Claude-only), `promotion-intake` and `skill-scaffold` (source-checkout context). If native skill listing is exposed, compare the discovered plugin names against the declared set and report missing/extra names. Local parsing is only static health; do not claim native discovery from it. Agents remain inert prompt files: use the read-and-dispatch mapping only when actual same-host controls exist.

On Claude Code scan all canonical skills: parse frontmatter, match `name` to directory and require a nonempty description. PASS when all parse; WARN for 1–2 failures, listing them; FAIL for 3+ failures or a missing/empty skill directory. Report parsed, failed and discovered counts separately where available.

Check for competing copies of the declared names in the host's standalone skill roots (including `~/.agents/skills` on Codex and `~/.claude/skills` on Claude), and project-local roots when relevant. Record the declared name, absolute path, resolved symlink target and content hash; compare with the loaded plugin. Equal names alone establish overlap, not which copy wins. Different bytes may be intentional custom work. Report WARN for ambiguous provenance and keep all copies intact during health. A native read/invocation receipt must identify the selected copy before claiming routing works. Prefer explicit `claudna:` selection where the host exposes it; an update or restart alone does not remove standalone copies.

### 5. Dependencies

On Codex, read `requires` for the skill the user needs, and use `command -v` for its CLIs; report missing environment variables by presence only, never values. Codex needs `git` and a supported Python 3.9+ for the packaged store/briefing. Claude-only formatters and Node tooling are not universal Codex prerequisites. A missing optional service CLI limits only that workflow. No automatic installation or outbound service action.

On Claude Code, retain all baseline dependency diagnostics:

```bash
for cmd in jq gh git node npx; do
  command -v "$cmd" >/dev/null 2>&1 && printf '%s: found\n' "$cmd" || printf '%s: MISSING\n' "$cmd"
done
```

PASS when all baseline commands exist; WARN with the missing command names and manual install guidance otherwise. In particular, missing `jq` silently disables the Claude permission hook, so report that consequence. Optional formatters (`prettier`, `ruff`, `sqlfluff`) are informational; auto-format degrades when absent. Skills' own `requires` still apply. Do not install anything during health.

These baseline diagnostics are not a single dependency gate: missing `gh`, `git`, `node` or `npx` does not disable the permission hook. Attribute each missing dependency to the particular workflow that uses it.

### 6. Telemetry and continuity

On either supported capture host, run `python3 -B "<loaded-plugin-root>/lib/claudna/session_store" health --json` against its configured store. Older installed copies may lack this verb: report that version gap rather than silently using the source checkout. The view reads existing lifecycle logs, worker receipts and draft review decisions without writing, starting workers or contacting a provider. Report recorded opt-outs/unknown policy, final summary failures, harvest backlog and proximity to retention, latest worker problems, and the number of explicitly decided draft revisions. `no_evidence` is unknown coverage; `observed` is not a whole-system PASS. An acceptance fraction with no decisions is null, not zero, and cannot rank skill usefulness. Use `runs` for a reported worker problem and `digest` / `/claudna:capture --review` for human review; health itself never promotes or discards drafts. Historical capture choices and retained evidence do not establish the defaults of the currently installed package.

On Codex, report Claude Skill telemetry as unsupported by this hook set. The shared Codex procedure records local agent procedure entries by default, with `CLAUDNA_SKILL_LOG=0` as opt-out; they prove neither completion nor task success. Report missing identity/store as a capture gap. A trusted `Skill` matcher does not establish native skill capture, and a Claude telemetry file is not Codex activity proof. Inspect only the authorized project's `.claude/session.md` when continuity is relevant; it is shared per-cwd compatibility state. Actual packaged startup execution and stdout delivery require a separate native canary; health does not assert them.

On Claude Code, telemetry defaults on. Report INFO when `CLAUDNA_TELEMETRY=0`, `CLAUDNA_SKILL_LOG=0`, a private session, or a clauDNA child suppresses it; `CLAUDNA_SESSION_STORE=0` also suppresses the default unless `CLAUDNA_TELEMETRY=1` explicitly requests the compatibility file. When enabled, resolve `CLAUDNA_TELEMETRY_PATH` if set, else `~/.claude/telemetry/skill-events.jsonl`. Read-only: check the file exists, check writability with `test -w` without writing a probe, and report its size, line count and latest timestamp (parse the last event's timestamp only; never print its full body). PASS when enabled with a writable output file; INFO when no Skill event has created it yet; WARN when an existing file/directory is unreadable or not writable. Do not create or repair it during health. Do not print raw events or personal paths in a public receipt.

### Results

Present one table: Check / Status / Observed evidence / Limitation. Use PASS only for the particular measured check, WARN/FAIL for concrete defects and INFO for unavailable optional evidence. Give a concrete next step for each defect. Never turn diagnostics into global config, authentication or trust writes.
