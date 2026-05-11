---
name: data-model-audit
description: "Use when you want to audit how well a data model serves its application — traces code paths to database interactions, maps intent to schema, and identifies mismatches, gaps, and optimization opportunities."
---

# Data Model Audit

Audit how well a Python/Postgres application's data model serves its codebase — traces code paths to DB interactions, maps intent to schema, finds where the model fights the application.

**Persona:** Senior data architect who reads code. Evidence-driven — every finding cites specific code paths and schema elements.

## Procedure

Follow steps in order. Call `EnterPlanMode` first — the entire skill is diagnostic (no write phase). If user declines, proceed read-only by convention. Never exit plan mode.

Do NOT read CLAUDE.md or MEMORY.md — already in system prompt.

---

## Step 1: Scope & Context

Ask: (1) **"What's the pain point?"** and (2) **"Any specific area to focus on?"** Default to full codebase scan if no scope given.

### Target System Detection

Verify Python/Postgres/SQLAlchemy codebase. Run in parallel:

- Grep `declarative_base|DeclarativeBase|mapped_column` in `*.py`
- Glob `**/alembic/versions/*.py`
- Grep `psycopg|asyncpg|postgresql|postgres` in `*.{py,toml,cfg,txt,yml,yaml,env*}`

If none match, warn the user this skill targets Python/Postgres/SQLAlchemy and offer best-effort or alternative. Proceed on confirmation.

---

## Step 2: Parallel Discovery

**Scratch directory:** `/tmp/data-model-audit-<YYYY-MM-DD_HHMMSS>/research/`

Launch two `general-purpose` subagents in parallel (Agent tool, `subagent_type: "general-purpose"`). Each writes findings to scratch dir, returns 2-4 line summary. Orchestrator does NOT read full research files. (General-purpose because Explore lacks Write tool.)

### Subagent A: Schema Discovery

Discovers the complete data model — SQLAlchemy models, Alembic migrations, raw SQL, and discrepancies between them. Writes findings to `research/schema-discovery.md`.

### Subagent B: Code Path Tracing

Traces every code path from entry points (routes, CLI, tasks) through business logic to database interactions. Catalogs data access patterns, query patterns, and N+1 candidates. Writes findings to `research/code-path-tracing.md`.

**Full subagent prompts, instructions, and research file formats:** See `subagent-prompts.md` in this skill directory.

---

## Step 3: Convergence — Map Code to Schema

Launch a third `general-purpose` subagent that reads both research files, verifies against the codebase, and builds a code-to-schema convergence map (unused schema, write-only columns, read-hot tables, god-tables, structural workarounds, missing constraints, N+1 patterns). Writes to `research/convergence.md`.

**Full convergence subagent prompt and checklist:** See `subagent-prompts.md` in this skill directory.

**The orchestrator receives the convergence summary** (2-4 lines) and presents the code-to-schema map overview to the user for confirmation before proceeding to fit analysis.

---

## Step 4: Fit Analysis

Classify and rank findings into six categories: Schema Gaps, Schema Bloat, Structural Friction, Missing Constraints, Performance Anti-patterns, Model Drift. Use convergence summary + any user corrections from Step 3 gate.

**Category definitions, severity guidance, examples:** See `gap-analysis-categories.md`.

If convergence summary is insufficient, read specific sections of the research file — never the full file.

---

## Step 5: Ranked Findings Report

Print structured report: scope summary, code-to-schema map, ranked findings table, detailed findings with evidence/recommendations, total summary with top recommendation.

**Report structure and finding template:** See `gap-analysis-categories.md`.

---

## Notes

- **Subagent pattern.** Disk-write pattern per `~/.claude/skills/_shared/orchestration-guide.md` Sections 2 & 6. Three subagents: two parallel (Step 2), one sequential (Step 3). Orchestrator coordinates only.
- **Pass focus area** from Step 1 into both Step 2 subagent prompts.
- **Secrets masking.** Never include connection strings verbatim — file:line only.
- **User gates.** Confirmation required after Step 3 before fit analysis.
- **Terminal at report.** Diagnostic only — no artifacts. User acts via `/claudna:implement-plan` if desired.
- Orchestration guide: Section 9 N/A (no Plan subagents). Section 10: "Respect existing architecture" applies; doc/testing rules do not.
