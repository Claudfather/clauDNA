# Skill Contract

This is the binding contract for every skill in clauDNA. Adding or modifying a skill means satisfying these rules. Pull requests that violate the contract are rejected by CI ([`scripts/validate-skills.py`](./scripts/validate-skills.py), wired into `.github/workflows/validate-skills.yml`).

If you want to understand *what* a skill is conceptually, read this file. If you want to know *whether* a skill is valid, run the validator.

---

## 1. Directory layout

Every skill lives under `skills/<name>/`. The directory contents:

| File | Required? | Purpose |
|---|---|---|
| `SKILL.md` | **Yes** | The skill itself — frontmatter + procedural body |
| `<topic>.md` | Optional | Supporting reference files referenced from `SKILL.md` (e.g. `subagent-prompts.md`, `audit-checklist.md`, `severity-categories.md`) |
| `references/` | Optional | Subdirectory for grouped reference material (used by `init-project`) |

Hard rules:
- The directory **name** is the skill's slash-command name (e.g. `/product-vision` lives at `skills/product-vision/`).
- The directory name **must match** the `name` field inside `SKILL.md` exactly.
- One special directory exists: `skills/_shared/`. It holds shared orchestration material referenced by skills, contains no `SKILL.md`, and is not itself a skill. The validator skips it.
- **A path in skill text is relative to the file it is written in** (#336). That is plain markdown semantics, and it is what every reference between a skill's own files already does. A host that knows where it loaded a file can then follow the path without this repo's layout or working directory. So `_shared` material is written `../_shared/<path>` from a skill's top level and from `_shared/` itself, and `../../_shared/<path>` one directory further down: one `../` per directory between the file and `skills/`. The validator rejects any other spelling, and any path that names nothing under `skills/_shared/` (§5.1); `python3 scripts/fix_shared_paths.py` rewrites the spelling. Text that is copied elsewhere before anyone reads it, such as a template generated into a user's project, names the document instead, because no relative path survives the move. Text forwarded to another agent, or run as a command, uses the resolver form `<claudna-root>/skills/_shared/<path>` instead (§1.1), because it is read against someone else's working directory. A URL is not a path and is left alone. To name the directory itself rather than point into it, write it without a trailing slash (`_shared`).


### 1.1. Bundled scripts and `<claudna-root>`

A bundled script runs from wherever the plugin is installed, never from the user's working directory, so skill text writes it `python3 "<claudna-root>/scripts/<name>"` (#336). In a `SKILL.md` body, `${CLAUDE_PLUGIN_ROOT}` may stand in for `<claudna-root>`, because Claude Code fills it in there, fenced blocks included. It may do so only there, and only with the `<claudna-root>` fallback on the same line or in the paragraph after its code block. A skill that declares `requires-context: repo-clone` runs this repo's own tools as `python3 scripts/<name>`, and only such a skill may.

`<claudna-root>` is the directory that holds this plugin's `skills/` and `scripts/`. The candidate list below is copied byte for byte into `skills/_shared/claudna-root.md`, which is the copy a model reads at run time; `tests/test_host_portability.py` pins the two.

<!-- claudna-root:begin -->
Use the first of these candidates that contains the file you need:

1. **The path Claude Code filled in for `${CLAUDE_PLUGIN_ROOT}`.** Claude Code does this only in a `SKILL.md` body, fenced blocks included. In any other file the variable stays literal, and the shell never has it set.
2. **`$CLAUDNA_ROOT`**, when your host or operator sets it.
3. **`<skill-dir>/../..`**, two directories above the directory of the skill you are running. Claude Code prints that directory as "Base directory for this skill"; any other host knows where it loaded `SKILL.md` from.
4. **The highest-versioned `~/.claude/plugins/cache/Claudfather/claudna/*/`**, Claude Code's plugin cache. Compare the version directories as version numbers, not as text: `0.19.0` is above `0.9.0` (`sort -V` orders them so). It comes last because it can hold a newer copy than the one that is loaded.

If none of them contains the file, stop and say so. Never fall back to a path in the working directory, which is the user's project, not this plugin. Write the resolved absolute path into the command, and keep the command a bare one. In a prompt you forward to another agent, replace `<claudna-root>` with the absolute path before you send it, because the receiving agent has no skill directory to resolve against.
<!-- claudna-root:end -->

---

## 2. `SKILL.md` frontmatter

`SKILL.md` begins with YAML frontmatter delimited by `---` lines, followed by markdown body.

### Required fields

| Field | Type | Rules |
|---|---|---|
| `name` | string | Letters (any case), digits, and hyphens only. Must match the parent directory name exactly. Globally unique across the repo (no two skills share a `name`). Convention is `kebab-case`. |
| `description` | string | When-to-use trigger statement — the routing surface the model reads when deciding whether to load the skill. Length: 20–500 characters. Grammar rules in §2.1 (trigger-first, no flag tokens, no workflow summaries, negative routing). |

### Optional fields

| Field | Type | Rules |
|---|---|---|
| `allowed-tools` | string OR list | Tool names / Bash patterns. Two equivalent forms are accepted: comma-separated string (`Bash(git status *), Bash(git diff *), Read`) or YAML list (`- Bash(git status *)` / `- Bash(gh pr view *)`). Required for skills that need tool gating beyond the user's default permissions. Patterns must use the canonical form `Bash(cmd *)` — the colon syntax `Bash(cmd:*)` is deprecated and validator-rejected. Grants are checked against an allowlist (`check_grant_scope`): an exact command, an interpreter running a fixed script, a read-only git/gh subcommand, or a read-only utility. A whole-command-family wildcard (`Bash(git *)`, `Bash(gh *)`, `Bash(python3 *)`), a package runner, or a project build/test tool is rejected; a skill that must keep one sets `disable-model-invocation: true`. Unknown tool *names* are not rejected (the surface evolves), but unparseable entries are. |
| `argument-hint` | string | Hint shown to the user when they type `/<skill>`. Convention: `[--flag] [positional-arg]`. Required if the skill accepts arguments. |
| `requires` | list | External dependencies the skill needs at runtime. Each entry is a mapping with exactly one of `cli` (tool name, optionally with `>=X.Y` version constraint) or `env` (environment variable name), plus an optional `reason` string. Skills with no external dependencies omit the field. See schema below. |
| `user-invocable` | boolean | Defaults to `true`. Set to `false` for context-only skills (loaded by name reference, not invoked as `/skill`). |
| `hosts` | list | Hosts the skill is known to function on. Values: `claude-code`, `cursor`. Omit for "no restriction" — most skills need no marker. See §2.2. |
| `requires-context` | string | A special execution context the skill needs beyond "any project directory". Values: `repo-clone` (must run from inside a clone of this repo). Omit for "no restriction". Not `context` — that key is Claude Code's own (`context: fork`, §2.2). See §2.2. |

### 2.1. Description grammar

The `description` is a routing surface: it is what the model reads when choosing which skill to load, so it must state *when to reach for the skill* — never how the skill works internally. Rules:

1. **Trigger-first.** Open with the situation that calls for the skill — the description begins with `Use ` (`Use when …`, `Use at …`, `Use before …`, `Use after …`, `Use to …`). Descriptions that lead with a label or a capability summary hide the when-to-use signal. *(Advisory warning when missing.)*
2. **No CLI flags.** Flag surfaces (`--auto`, `--output …`) belong in `argument-hint`. Any `--flag` token in a description is selection noise and a **hard error**.
3. **No workflow summaries.** Never narrate the skill's internal process in the description ("dispatches lenses, folds comments, checks convergence"). A description that summarizes the workflow becomes a shortcut the model follows *instead of reading the body*.
4. **Negative routing.** When a skill has a confusable sibling, disambiguate inside the description itself: `For triaging known issues in an existing product, use /claudna:product-enhance.` The pair should partition the intent space so the picker cannot land wrong.
5. **Concrete anchors.** Temporal and state anchors ("Use when a PR has been merged…", "Use before starting substantive work…") and quoted trigger phrases ("Option A vs B") outperform topic labels. Include the symptoms and keywords a model would match on.
6. **Rename breadcrumbs.** A skill that supersedes older skills says so at the end: `Replaces /product-brainstorm.` Old muscle memory still resolves. Breadcrumbs to **removed** skills must use the bare slash form (`Replaces /old-name`), never `/claudna:old-name` — the reference check requires every `claudna:<name>` mention to resolve to an *existing* skill.

Cross-references to living skills use the `/claudna:<name>` form. Every `claudna:<name>` mention anywhere in a skill's markdown (or in `_shared/`) must resolve to an existing skill directory — dangling references are a **hard error** (see §5.1). Scope note: only the `claudna:<name>` form is checked; bare `/name` prose mentions are out of the check's scope by design (they are indistinguishable from generic slash-command prose), so load-bearing references should prefer the checked form.

**On a host without Claude Code's namespaced commands, read `/claudna:<name> [args]` as "invoke the skill `<name>` with `[args]`"**, through that host's own way of invoking a skill (#336). The skill's file is `../<name>/SKILL.md` from any skill directory. The rule covers every reference, because the validator refuses a `claudna:<name>` whose `<name>` has no skill directory (§5.1), and `tests/test_inter_skill_rule.py` pins that premise across `skills/`.

### Frontmatter example

```yaml
---
name: product-vision
description: "Use when you want to explore what a codebase could become — candidate features one or two hops from existing infrastructure, compound plays, and a trajectory aligned to the project mission. For triaging known issues in an existing product, use /claudna:product-enhance. Replaces /product-brainstorm."
argument-hint: "[--auto] [--output github|session] [focus-area]"
allowed-tools: Bash(git status *), Bash(git diff *), Bash(gh pr view *), Edit, Read, Grep, Glob
requires:
  - cli: gh>=2.0
    reason: "GitHub API operations (issues, PRs)"
---
```

### `requires` entry schema

Each entry in the `requires` list must be a mapping with:

| Key | Required | Type | Description |
|---|---|---|---|
| `cli` | One of `cli`/`env` | string | CLI tool name, optionally with `>=X.Y` version constraint. The tool must exist on `$PATH` for the skill to function. |
| `env` | One of `cli`/`env` | string | Environment variable that must be set (non-empty) for the skill to function. |
| `reason` | No | string | Human-readable explanation of why this dependency is needed. |

Exactly one of `cli` or `env` must be present per entry. Examples:

```yaml
requires:
  - cli: gh>=2.0
    reason: "GitHub API operations"
  - cli: vercel
    reason: "Deployment management"
  - env: VERCEL_TOKEN
    reason: "Vercel authentication"
```

Skills that only use built-in Claude Code tools (Read, Write, Bash, Grep, etc.) and universally-available commands (git, curl, jq) do not need a `requires` field.

### 2.2. Host and context scoping

`hosts` and `requires-context` (#340) describe facts about a skill, not a distribution decision — whether it needs Claude Code's own plugin/hook internals, or a clone of this repo, versus running the same way anywhere. Both are optional and additive; omitting both means "no restriction," which is why most skills carry neither.

**Not named `context`.** Claude Code's own skills reference already defines `context` (set to `fork` to run in a forked subagent context, paired with `agent:` naming the subagent type). A same-named field here would collide: this repo's validator would reject Claude Code's own `fork` value as an unknown context, and the exclusion predicate below would treat any skill that later adopts `context: fork` for its native meaning as needing a repo clone (#343). `requires-context` is a key Claude Code does not define.

The one consumer of these fields today is `scripts/check_cursor_scope.py` (`make check-manifest`), which excludes a skill from `.cursor-plugin/plugin.json`'s declared skill set when either applies:

- `hosts` is set and does not include `cursor` (the skill is Claude-Code-only by definition — it inspects the plugin cache, hooks, or similar).
- `requires-context` is set at all (the skill needs to run from inside a clone of this repo; Cursor's marketplace install gives no such guarantee).

**Claude Code's own manifest is unaffected by either field** — it ships every skill regardless, as it always has. That is a deliberate, conservative scoping choice for #340 (limit the fix to the surface the issue is actually about), not a claim that Claude Code is somehow exempt from what the fields describe: a `requires-context: repo-clone` skill installed via marketplace onto a random project is just as non-functional there as it would be on Cursor. If a second distribution channel ever needs the same curation Claude Code currently skips, extend `check_cursor_scope.py`'s caller rather than overloading `cursor_should_exclude()`'s scope.

`scripts/skill_checks.py` validates the field *shapes* (`validate_hosts`, `validate_requires_context`) as part of `make check-skills` — unknown values are rejected there, independent of what any one consumer does with them.

The two fields also carry two of the host-portability exemptions (§1.1, §5.1): a `hosts: [claude-code]` skill may name Claude Code's plugin cache, and a `requires-context: repo-clone` skill may run this repo's own tools from the working directory. Each field also drops the skill from the Cursor build, so neither is a way to quiet a check.

---

## 3. `SKILL.md` body

The body is markdown. There is no rigid template, but the following conventions hold across the canonical set:

1. **Lead with a one-line restatement** of what the skill does. Useful for the agent loading the file.
2. **`## Procedure`** is the standard heading for the executable steps. Skills that don't fit a linear procedure — verb-dispatch engines like `/claudna:session`, phase-based workflows — use other headings.
3. **Numbered steps** when ordering matters. Subagent-driven skills often have an explicit `EnterPlanMode` step early.
4. **Reference long supporting material via filename** rather than inlining (`See subagent-prompts.md in this skill directory`). This keeps `SKILL.md` scannable; the orchestrator reads the file, subagents read the deep references at runtime.
5. **Hard gates** — when a step blocks proceeding without evidence, mark it with `<HARD-GATE>` tags or "Iron Law" language. See `/build` and `/review-work` for examples.
6. **Red Flags / Common Rationalizations tables** — for skills that get rationalized away ("this case is special"), include a short table mapping common excuses to counter-arguments.

Minimum body length: 200 characters of non-frontmatter content. Skills shorter than that are stubs and fail validation.

---

## 4. Naming conventions

- Skill names use `kebab-case`: `product-vision`, `review-work`, `build`.
- Slash commands are the skill name with a `/` prefix: `/product-vision`.
- Codebase audits are **lenses of the one `/audit` engine** (`skills/audit/<lens>/`, per `skills/_shared/audit-lens-contract.md`) — a new audit concern is a new lens directory + table row, never a new `-audit` skill. Review skills for plans/PRs use `-review` or a plain action verb (`heist`, `ship`).
- Skills that wrap a third-party tool are **one engine named for the tool, with verb modes** — `dbt`, `modal`, `railway`, `vercel`, `neon` — never one skill per tool×verb (`<tool>-deploy` / `<tool>-logs` / …). Engines follow `skills/_shared/infra-cli-contract.md`: thin body, first-token verb dispatch, per-verb depth in support files. A new capability for a tool is a new verb row + depth file, not a new skill.

Naming is not validator-enforced today — it's a guideline. Conflicts and confusion (e.g. duplicate names) are validator-enforced.

---

## 5. Validation

Run locally:

```bash
python scripts/validate-skills.py
```

The validator returns non-zero on any violation and prints a structured report. Every push and pull request runs the same script in CI via `.github/workflows/validate-skills.yml`.

To intentionally introduce a non-conforming skill (e.g. an experimental in-progress skill), add it to `scripts/validate-skills.py`'s `SKIP` set — but `SKIP` exists for genuinely transitional cases, not as a workaround for unwanted rules. Prefer fixing the skill.

### 5.1. Behavioral checks (hard errors)

Beyond frontmatter structure, the validator enforces behavioral consistency between what a skill *claims* and what its body *implements*:

| Check | Trigger | Rule | Rationale |
|---|---|---|---|
| **`--output github` reference** | `argument-hint` contains `--output github` | Body must reference `output-guide` (matching `skills/_shared/output-guide.md`). | Skills claiming GitHub output must follow the shared output guide so consumers get consistent issue formatting. |
| **`--auto` / `AskUserQuestion` conflict** | `argument-hint` contains `--auto` | Body must NOT contain the literal string `AskUserQuestion`. | `--auto` means non-interactive execution. `AskUserQuestion` blocks on user input, which contradicts the contract. |
| **Description grammar** | always | `description` must not contain `--flag` tokens — CLI surfaces live in `argument-hint` (§2.1 rule 2). | The description is the model's routing surface; flag inventories add selection noise without trigger value. |
| **Claudron dependency declaration** | any file in the skill directory invokes the `claudron` CLI — `claudron <verb>` for a CLI verb, or `command -v claudron` | `SKILL.md`'s frontmatter must declare it in `requires:` as `- cli: claudron` (optionally version-constrained), with a `reason` naming whether the dependency is hard or soft and which path needs it. Skill-level references (`/claudna:claudron`, `/claudron <verb>`) are routing, not invocation, and require nothing. | Claudron is an optional external CLI, and every consumer degrades when it is absent ([`skills/_shared/claudron-engine.md`](./skills/_shared/claudron-engine.md) §3, whose §3.1 holds the one user-facing notice every fallback branch emits). An undeclared dependency is how that degradation goes invisible: nothing in the frontmatter says the skill has a soft edge, so a reader — or a host installing skills onto a machine with no Claudron — only discovers the fallback by hitting it. The declaration does not gate execution (§1's detection ladder is the only runtime gate); it makes the dependency reviewable. The check reads the whole skill directory, because verb engines keep their invocations in depth files rather than in `SKILL.md`. |
| **Skill-reference integrity** | any `claudna:<name>` mention in a skill's markdown (SKILL.md + support files) or in `_shared/` | The referenced name must be an existing `skills/<name>/` directory. Only the `claudna:`-prefixed form is checked (bare `/name` mentions are out of scope by design). | Cross-references are how skills route to each other (negative triggers, pipeline hand-offs); a dangling reference silently breaks that routing. In CI these register as cross-skill errors keyed to *both* the referring and the referenced skill, so a PR that deletes or renames a skill blocks on the dangling references it leaves behind. |
| **`_shared` path spelling** | any `_shared/` path in a skill's markdown (SKILL.md + support files) or in `_shared/` | Must be written relative to its own file (one `../` per directory between the file and `skills/`, then `_shared/<path>`), or in the resolver form `<claudna-root>/skills/_shared/<path>` (§1.1), and must name an existing file or directory under `skills/_shared/`. A `${...}`, `~` or absolute prefix is rejected; a URL is not a path and is skipped. | A path written from the repo root or the working directory resolves only on a host that reproduces this repo's layout and working directory. A file-relative path resolves wherever the file is (#336). |
| **Plugin variables** | `${CLAUDE_PLUGIN_ROOT}` or `${CLAUDE_SKILL_DIR}` in a skill's markdown or in `_shared/` | Only in a `SKILL.md` body, with `<claudna-root>` on the same line or in the paragraph after its code block. | Claude Code fills these in only in an expanded `SKILL.md` body. Elsewhere they stay literal, and the shell never has them set (§1.1). |
| **Plugin-cache paths** | `plugins/cache/Claudfather/claudna` in a skill's markdown or in `_shared/` | Only inside the `<claudna-root>` definition (between its markers), or in a skill whose `hosts` is `[claude-code]`. | The cache is Claude Code's, and it can hold a newer copy than the loaded one. It is the last `<claudna-root>` candidate, not a path to write (§1.1). |
| **Working-directory script calls** | `python3`, `bash` or `sh` followed by `scripts/<name>` or `./scripts/<name>` | Only in a skill that declares `requires-context: repo-clone`. | The working directory is the user's project, not this plugin; everywhere else the call is `python3 "<claudna-root>/scripts/<name>"` (§1.1). |
| **Resolver pointer** | `<claudna-root>` in a skill's markdown or in `_shared/` | The same file must also name `claudna-root.md`. | A reader who meets the placeholder, or an orchestrator filling it into a prompt it forwards, needs the candidate list; a pointer in another file is not found (§1.1). |

All checks produce hard errors that fail CI.

### 5.2. Advisory warnings (non-blocking)

The validator also emits advisory warnings that surface potential staleness but do not fail CI:

| Check | Trigger | Rule | Rationale |
|---|---|---|---|
| **`allowed-tools` body usage** | `allowed-tools` field is present | Each declared tool (or Bash command) should appear somewhere in the body text. Tools with zero mentions produce a `[WARN]`. | Catches stale `allowed-tools` lists where a tool was declared but the body no longer uses it. Some tools (e.g. `Read`, `Glob`) may be used implicitly — the warning is advisory, not CI-blocking. |
| **Trigger-first description** | always | `description` should begin with `Use ` per §2.1 rule 1. | Trigger-first descriptions make the picker's choice cheap; labels and capability summaries hide when-to-use. Advisory so legitimately atypical skills aren't blocked. |

Warnings print in the validator output but do not affect the exit code.

---

## 6. Changing this contract

This file is authoritative. If you want to relax, tighten, or add a rule:

1. Update `SKILL_CONTRACT.md` with the new rule and rationale.
2. Update `scripts/validate-skills.py` to enforce it.
3. Run the validator and fix any pre-existing violations — or document them as `SKIP` entries with a tracking issue.
4. Note the change in `CHANGELOG.md` under the next release.

Contract changes that tighten rules are breaking for contributors with in-flight skills — call them out in the changelog.

---

## 7. Reference payloads: closure vs library (Q-closure)

A skill may embed reference material — a rubric, a checklist, a vendor-CLI cheat-sheet, a stamped template — in its `SKILL.md` body or in a supporting `<topic>.md` / `references/` file (§1). Before embedding, apply the **Q-closure** rule: **reference that tracks your *method* belongs in your skill; reference that tracks the *world* belongs in the vault.** A payload that versions with the *procedure* — the method's own judgment criteria, the operands its steps invoke, the artifacts it stamps — is **closure**: it stays with the skill, because it changes when you change how the skill works. A payload that versions with the *world or an external SSOT* — a domain fact, a service inventory, a schema table — is **library**: it is referential, and it belongs in a Claudron vault note (captured via `/claudna:capture`, deduped, recall-able) or, if it must live here, as a rendered copy behind a CI drift gate (the [`skills/_shared/output-guide.md`](./skills/_shared/output-guide.md) §3 pattern, gated by [`scripts/check_schema_drift.py`](./scripts/check_schema_drift.py)) — never a bare fork of the SSOT. The default posture is **closure-stays**: an embedded rubric is presumed method-coupled, and it moves to the vault only once it is observed being *consulted outside the skill's execution* (session evidence, or a capture-dedup hit naming it) — never pre-emptively, since moving a live rubric breaks the skill for no boundary gain. The standing triage of today's payloads is the D2 ledger (`documentation/planning/2026-07-22-d2-closure-triage-ledger.md`); the same rule is stated as placement guidance at the seam in [`skills/CLAUDE.md`](./skills/CLAUDE.md). The inverse door is already enforced: `/claudna:capture` rejects skill-shaped (procedural) content from the vault.
