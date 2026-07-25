# Agent Contract

This is the binding contract for every agent in clauDNA. Adding or modifying an agent means satisfying these rules. Pull requests that violate the contract are rejected by CI ([`scripts/validate-agents.py`](./scripts/validate-agents.py), wired into the `validate-agents` job of `.github/workflows/ci.yml`).

If you want to understand *what* an agent is conceptually, read this file. If you want to know *whether* an agent is valid, run the validator.

---

## 1. File layout

Every agent is a single Markdown file at `agents/<name>.md`. Unlike skills (which live in directories), agents are standalone files — each file is the complete agent definition.

Hard rules:
- The filename (without `.md`) **must match** the `name` field inside the file exactly.
- No subdirectories inside `agents/`.

---

## 2. Frontmatter

Each agent file begins with YAML frontmatter delimited by `---` lines, followed by a markdown body.

### Required fields

| Field | Type | Rules |
|---|---|---|
| `name` | string | Letters (any case), digits, and hyphens only. Must match the filename (minus `.md`) exactly. Globally unique across the repo. Convention is `kebab-case`. |
| `description` | string | One sentence describing the agent's role. Length: 20–500 characters. Surfaces in the agent picker — keep it specific. |

### Optional fields

| Field | Type | Rules |
|---|---|---|
| `model` | string | Model hint for the agent runtime (e.g. `opus`, `sonnet`, `haiku`). |
| `memory` | string | Memory scope: `none`, `user`, or `project`. |
| `tools` | list | List of tool names available to the agent (e.g. `Read`, `Grep`, `Glob`, `Bash`, `Write`, `Edit`). Must be a YAML list of strings. |
| `background` | boolean | Whether the agent runs in the background. |
| `isolation` | string | Isolation mode (e.g. `worktree`). |

### Frontmatter example

```yaml
---
name: code-reviewer
description: "Code quality reviewer. Evaluates implementation for correctness, clean design, test coverage, and maintainability."
memory: none
model: opus
tools:
  - Read
  - Grep
  - Glob
  - Bash
---
```

---

## 3. Body

The body is markdown. There is no rigid template, but the following conventions hold across the canonical set:

1. **Lead with an H1 heading** that names the agent role.
2. **Purpose section** explaining what the agent does and its boundaries.
3. **Procedure or process section** with the agent's investigation/execution steps.
4. **Key knowledge or reference tables** for domain-specific information (CLI commands, failure modes, platform details).
5. **Best practices** for how the agent should operate.
6. **Example** showing a typical interaction flow.

Minimum body length: 200 characters of non-frontmatter content. Agents shorter than that are stubs and fail validation.

---

## 4. Naming conventions

- Agent names use `kebab-case`: `code-reviewer`, `railway-ops`, `dbt-engineer`.
- Agents that wrap a third-party platform end in `-ops` (SRE persona) or `-analyst` (data persona): `modal-ops`, `neon-analyst`.
- Agents focused on code review end in `-reviewer`: `code-reviewer`, `spec-reviewer`.

Naming is not validator-enforced today — it's a guideline.

---

## 5. Validation

Run locally:

```bash
python scripts/validate-agents.py
```

The validator returns non-zero on any violation and prints a structured report. Every pull request runs the same script in CI via the `validate-agents` job in `.github/workflows/ci.yml`.

---

## 6. Changing this contract

This file is authoritative. If you want to relax, tighten, or add a rule:

1. Update `AGENT_CONTRACT.md` with the new rule and rationale.
2. Update `scripts/validate-agents.py` to enforce it.
3. Run the validator and fix any pre-existing violations.
4. Note the change in `CHANGELOG.md` under the next release.
