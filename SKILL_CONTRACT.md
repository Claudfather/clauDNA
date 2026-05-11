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
| `references/` | Optional | Subdirectory for grouped reference material (used by `context-resume`, `session-handoff`) |

Hard rules:
- The directory **name** is the skill's slash-command name (e.g. `/tech-debt` lives at `skills/tech-debt/`).
- The directory name **must match** the `name` field inside `SKILL.md` exactly.
- One special directory exists: `skills/_shared/`. It holds shared orchestration material referenced by skills, contains no `SKILL.md`, and is not itself a skill. The validator skips it.

---

## 2. `SKILL.md` frontmatter

`SKILL.md` begins with YAML frontmatter delimited by `---` lines, followed by markdown body.

### Required fields

| Field | Type | Rules |
|---|---|---|
| `name` | string | Letters (any case), digits, and hyphens only. Must match the parent directory name exactly. Globally unique across the repo (no two skills share a `name`). Convention is `kebab-case`; the project-branded skills (`clauDNA-setup`, `clauDNA-sync`, `clauDNA-migrate`) intentionally use mixed case. |
| `description` | string | One sentence describing when to use the skill. Begins with "Use when…" by convention. Length: 20–500 characters. Surfaces in the skill picker — keep it specific enough that the loader can decide relevance. |

### Optional fields

| Field | Type | Rules |
|---|---|---|
| `allowed-tools` | string OR list | Tool names / Bash patterns. Two equivalent forms are accepted: comma-separated string (`Bash(git *), Bash(gh *), Read`) or YAML list (`- Bash(git *)` / `- Bash(gh *)`). Required for skills that need tool gating beyond the user's default permissions. Patterns must use the canonical form `Bash(cmd *)` — the colon syntax `Bash(cmd:*)` is deprecated and validator-rejected. Unknown tool *names* are not rejected (the surface evolves), but unparseable entries are. |
| `argument-hint` | string | Hint shown to the user when they type `/<skill>`. Convention: `[--flag] [positional-arg]`. Required if the skill accepts arguments. |
| `user-invocable` | boolean | Defaults to `true`. Set to `false` for context-only skills (loaded by name reference, not invoked as `/skill`). Currently only `notifications` uses this. |

### Frontmatter example

```yaml
---
name: tech-debt
description: "Use when you want to find and plan remediation of technical debt in the codebase. Supports --output github to create issues and --output session for chat-only analysis."
argument-hint: "[--auto] [--output github|session] [focus-area]"
allowed-tools: Bash(git *), Bash(gh *), Edit, Read, Grep, Glob
---
```

---

## 3. `SKILL.md` body

The body is markdown. There is no rigid template, but the following conventions hold across the canonical set:

1. **Lead with a one-line restatement** of what the skill does. Useful for the agent loading the file.
2. **`## Procedure`** is the standard heading for the executable steps. Skills that don't fit a linear procedure (`/notes`, `/notifications`) use other headings.
3. **Numbered steps** when ordering matters. Subagent-driven skills often have an explicit `EnterPlanMode` step early.
4. **Reference long supporting material via filename** rather than inlining (`See subagent-prompts.md in this skill directory`). This keeps `SKILL.md` scannable; the orchestrator reads the file, subagents read the deep references at runtime.
5. **Hard gates** — when a step blocks proceeding without evidence, mark it with `<HARD-GATE>` tags or "Iron Law" language. See `/implement-plan`, `/review-changes`, `/review-pr` for examples.
6. **Red Flags / Common Rationalizations tables** — for skills that get rationalized away ("this case is special"), include a short table mapping common excuses to counter-arguments.

Minimum body length: 200 characters of non-frontmatter content. Skills shorter than that are stubs and fail validation.

---

## 4. Naming conventions

- Skill names use `kebab-case`: `tech-debt`, `review-pr`, `frontend-performance-audit`.
- Slash commands are the skill name with a `/` prefix: `/tech-debt`.
- Skills that file or read GitHub issues end in `-audit` or `-review` (planning) or use a plain action verb (`heist`, `commit-push-pr`).
- Skills that wrap a third-party tool start with the tool's name: `dbt`, `neon-info`, `modal-deploy`, `railway-logs`, `vercel-status`.

Naming is not validator-enforced today — it's a guideline. Conflicts and confusion (e.g. duplicate names) are validator-enforced.

---

## 5. Validation

Run locally:

```bash
python scripts/validate-skills.py
```

The validator returns non-zero on any violation and prints a structured report. Every push and pull request runs the same script in CI via `.github/workflows/validate-skills.yml`.

To intentionally introduce a non-conforming skill (e.g. an experimental in-progress skill), add it to `scripts/validate-skills.py`'s `SKIP` set — but `SKIP` exists for genuinely transitional cases, not as a workaround for unwanted rules. Prefer fixing the skill.

---

## 6. Changing this contract

This file is authoritative. If you want to relax, tighten, or add a rule:

1. Update `SKILL_CONTRACT.md` with the new rule and rationale.
2. Update `scripts/validate-skills.py` to enforce it.
3. Run the validator and fix any pre-existing violations — or document them as `SKIP` entries with a tracking issue.
4. Note the change in `CHANGELOG.md` under the next release.

Contract changes that tighten rules are breaking for contributors with in-flight skills — call them out in the changelog.
