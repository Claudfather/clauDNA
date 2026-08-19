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
| `allowed-tools` | string OR list | Tool names / Bash patterns. Two equivalent forms are accepted: comma-separated string (`Bash(git *), Bash(gh *), Read`) or YAML list (`- Bash(git *)` / `- Bash(gh *)`). Required for skills that need tool gating beyond the user's default permissions. Patterns must use the canonical form `Bash(cmd *)` — the colon syntax `Bash(cmd:*)` is deprecated and validator-rejected. Unknown tool *names* are not rejected (the surface evolves), but unparseable entries are. |
| `argument-hint` | string | Hint shown to the user when they type `/<skill>`. Convention: `[--flag] [positional-arg]`. Required if the skill accepts arguments. |
| `requires` | list | External dependencies the skill needs at runtime. Each entry is a mapping with exactly one of `cli` (tool name, optionally with `>=X.Y` version constraint) or `env` (environment variable name), plus an optional `reason` string. Skills with no external dependencies omit the field. See schema below. |
| `user-invocable` | boolean | Defaults to `true`. Set to `false` for context-only skills (loaded by name reference, not invoked as `/skill`). |

### 2.1. Description grammar

The `description` is a routing surface: it is what the model reads when choosing which skill to load, so it must state *when to reach for the skill* — never how the skill works internally. Rules:

1. **Trigger-first.** Open with the situation that calls for the skill — the description begins with `Use ` (`Use when …`, `Use at …`, `Use before …`, `Use after …`, `Use to …`). Descriptions that lead with a label or a capability summary hide the when-to-use signal. *(Advisory warning when missing.)*
2. **No CLI flags.** Flag surfaces (`--auto`, `--output …`) belong in `argument-hint`. Any `--flag` token in a description is selection noise and a **hard error**.
3. **No workflow summaries.** Never narrate the skill's internal process in the description ("dispatches lenses, folds comments, checks convergence"). A description that summarizes the workflow becomes a shortcut the model follows *instead of reading the body*.
4. **Negative routing.** When a skill has a confusable sibling, disambiguate inside the description itself: `For triaging known issues in an existing product, use /claudna:product-enhance.` The pair should partition the intent space so the picker cannot land wrong.
5. **Concrete anchors.** Temporal and state anchors ("Use when a PR has been merged…", "Use before starting substantive work…") and quoted trigger phrases ("Option A vs B") outperform topic labels. Include the symptoms and keywords a model would match on.
6. **Rename breadcrumbs.** A skill that supersedes older skills says so at the end: `Replaces /product-brainstorm.` Old muscle memory still resolves. Breadcrumbs to **removed** skills must use the bare slash form (`Replaces /old-name`), never `/claudna:old-name` — the reference check requires every `claudna:<name>` mention to resolve to an *existing* skill.

Cross-references to living skills use the `/claudna:<name>` form. Every `claudna:<name>` mention anywhere in a skill's markdown (or in `_shared/`) must resolve to an existing skill directory — dangling references are a **hard error** (see §5.1). Scope note: only the `claudna:<name>` form is checked; bare `/name` prose mentions are out of the check's scope by design (they are indistinguishable from generic slash-command prose), so load-bearing references should prefer the checked form.

### Frontmatter example

```yaml
---
name: product-vision
description: "Use when you want to explore what a codebase could become — candidate features one or two hops from existing infrastructure, compound plays, and a trajectory aligned to the project mission. For triaging known issues in an existing product, use /claudna:product-enhance. Replaces /product-brainstorm."
argument-hint: "[--auto] [--output github|session] [focus-area]"
allowed-tools: Bash(git *), Bash(gh *), Edit, Read, Grep, Glob
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
| **Skill-reference integrity** | any `claudna:<name>` mention in a skill's markdown (SKILL.md + support files) or in `_shared/` | The referenced name must be an existing `skills/<name>/` directory. Only the `claudna:`-prefixed form is checked (bare `/name` mentions are out of scope by design). | Cross-references are how skills route to each other (negative triggers, pipeline hand-offs); a dangling reference silently breaks that routing. In CI these register as cross-skill errors keyed to *both* the referring and the referenced skill, so a PR that deletes or renames a skill blocks on the dangling references it leaves behind. |

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
