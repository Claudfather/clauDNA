# System-lens subagent briefs

Full briefs for the fan-out lanes in `system.md` Phases 2 (mapping) and 4 (concern sweep). The orchestrator inlines the relevant brief into each `general-purpose` subagent's prompt, **prepended with the intake brief it assembled in Phase 1** (subagents don't inherit the parent context, and — because Phases 1–5 run in plan mode — the intake is not yet on disk to read). Every subagent:

- Takes the inlined intake brief as its shared context (what the system does, entrypoints, data-surface flag, out-of-scope paths).
- Scopes to `[focus]` if the orchestrator passed one.
- Writes its output file to the scratch dir and returns **only** a 2-4 line summary (orchestration guide §2). Never returns full content.
- **Write-blocked fallback.** If the scratch write is rejected (some harnesses guard file writes), do NOT dump the full map/findings into the return — that reintroduces the context blowup the disk-write pattern prevents. Instead return a *compact* stand-in prefixed `SCRATCH-WRITE-BLOCKED:` — for a map, the section headings plus any `Unverified` claims; for a findings lane, one line per finding (`SEVERITY | title | file:line`). The orchestrator reconciles from this compact return when the file is absent (system.md Phase 5), and re-requests full per-finding detail from a fresh subagent only for the findings it actually drafts (Phase 6).
- Cites `file:line` for every claim and never prints a raw secret value. Report file:line + the variable name, and scrub the findings file **in place** through the redactor before returning it — `python3 "<redactor>" <file>`, where `<redactor>` is resolved per orchestration guide §7 (`${CLAUDE_PLUGIN_ROOT}/scripts/redact.py` or the plugin-cache path); **do not assume `scripts/redact.py` exists in the reviewed repo** — it is a clauDNA-bundled tool, and the target repo is arbitrary. It masks known token shapes and `SECRET=value` assignments to `[REDACTED]` while sparing `file:line`.

---

## Part A — Map lanes (Phase 2)

Each map lane ends with the **accuracy self-check**: before writing a load-bearing claim (an entry in the component inventory, a step in a critical-path flow, a key/constraint in the data model — anything a reader would act on), re-open **2 or more** of the cited files and confirm it against source. Label anything you cannot confirm from source `Unverified`. A map is only worth inheriting if a reader can trust it without re-deriving it.

### Lane 1 — Architecture & execution flow → `system/system-map.md`

Brief: Map how the system runs, from evidence. Produce these sections; omit one only if the repo genuinely lacks it (say so):

1. Executive architecture summary (3-6 sentences).
2. Component inventory — table: `Component | Purpose | Entrypoint | Inputs | Outputs | Dependencies | Evidence (file:line) | Risks`.
3. Entrypoints & execution flows (each long-running process, job, CLI, DAG).
4. Key dependencies & integration points (external services, APIs, queues).
5. Configuration & environment assumptions (config surfaces, env keys — names only).
6. Error handling & retry strategy (where errors are caught / retried / swallowed).
7. Observability & logging (what is logged, what is measured, what alerts).
8. Deployment & runtime assumptions (how it ships; what the code assumes about prod).
9. Critical-path walkthroughs (2-3 most important flows, end to end).
10. Known unknowns (what you could not determine and why).

Include a Mermaid `flowchart` only if it reflects real code evidence.

### Lane 2 — Code map → `system/code-map.md`

Brief: Map the code structure and the critical execution paths. Cover:

- Modules/packages and the boundaries between layers.
- Important classes, functions, handlers, jobs, tasks, models, interfaces.
- Shared utilities and cross-cutting concerns.
- Where validation happens; where state is read/written; where errors are caught, retried, swallowed, transformed, logged.
- Where behavior depends on env vars, config, feature flags, or runtime state.

For each critical flow, use this block:

```
Flow: <name>
Purpose: <what it does>
Trigger: <how it starts>
Path:
  1. <file:function> → <what happens>
  2. <file:function> → <what happens>
State touched: <DB tables, files, queues, caches, APIs>
Failure modes: <what can go wrong>
Evidence: <file:line refs>
```

### Lane 3 — Data model & data flow → `system/data-model-map.md` *(conditional)*

Run **only** if a data surface exists (DB, ORM, migrations, dbt, pipelines, event streams, request/response schemas). Cover:

- Source systems; raw → staging → intermediate → final models (if a pipeline).
- ORM entities & relationships; tables, views, materializations, migrations, indexes.
- Primary/foreign keys, unique constraints, nullability, defaults.
- Incremental logic, deduplication logic, timezone/timestamp semantics, SCD/snapshot logic.
- Data-freshness assumptions, data-quality checks/tests.
- API request/response schemas; ownership and downstream consumers.

Discovery starters (adapt to the stack): grep for `declarative_base|mapped_column|ForeignKey|primary_key|nullable|CREATE TABLE|ALTER TABLE`; for dbt, `materialized|unique_key|is_incremental|ref\(|source\(|not_null|unique|freshness`.

---

## Part B — Concern lanes (Phase 4)

Each concern subagent writes `system/findings-<lane>.md` using this finding format, and returns a 2-4 line count-by-severity summary:

```
### [CRITICAL|HIGH|MEDIUM|LOW] <short title>
Status: Confirmed | Likely | Hypothesis
Area: <component/module/file>
Evidence:
  - <file:line> — <what the code does>
  - <command output / failing test, if any>
What is happening: <plain English>
Why it matters: <impact — correctness/reliability/data/perf/security/maintainability>
How to fix: <high-level remediation>
```

**Do not force findings.** If a lane is clean, write "No material findings" and say what you checked. Severity guide (matches output-guide §4.4, so the orchestrator maps it straight to `priority:*`): CRITICAL = data loss / security exposure / outage risk / broken critical path; HIGH = high-impact bug, major data-quality issue, serious reliability problem; MEDIUM = medium correctness/maintainability/observability/test gap; LOW = cleanup/docs/naming. The `Status` label (Confirmed/Likely/Hypothesis) is the one axis carried downstream — a Hypothesis states what would confirm or falsify it.

### Lane 1 — Correctness at rest *(primary)*

Logic that contradicts documented behavior; unhandled edge cases; wrong assumptions about nulls / empty collections / missing fields / absent config / pagination / retries / ordering / timezones / idempotency; incorrect type assumptions; dead/unreachable paths; inconsistent validation across layers; exceptions swallowed without action; error messages that hide root cause; incorrect async/concurrency; race conditions; unexpected state mutation; incomplete migrations or backfills.

### Lane 2 — Reliability & operations *(primary)*

Non-idempotent jobs; missing or unsafe retries; missing timeouts; missing circuit breakers; incomplete failure recovery; poor logging; missing metrics; no alerting for critical failures; no health checks; incomplete cleanup after partial failure; deployment assumptions not reflected in code; local↔production behavior divergence.

### Lane 3 — Backend performance & scalability *(primary)*

N+1 queries; full table scans where an index/partition filter belongs; inefficient loops; unbounded memory; loading whole datasets unnecessarily; poor server-side pagination; missing/invalid server-side caching; hot paths doing unnecessary serialization; over- or under-materialized data jobs; inefficient joins. (Anything client-side — rendering, scroll/layout, fetch waterfalls, state/memoization, bundle & loading — belongs to `/claudna:audit frontend-perf`; do not cover it here.)

### Lane 4 — Data-quality correctness *(primary; only if a data surface exists)*

Wrong grain; metric-definition ambiguity; join fanout; duplicate rows; incorrect date boundaries; leaky/overbroad source filters; missing data-quality tests; broken referential assumptions; unvalidated incremental loads; business logic hidden in SQL/code; missing source-freshness checks; inconsistent semantic definitions.

### Lane 5 — Security & secrets *(breadth — defer depth)*

Secrets committed or likely to leak; unsafe logging of credentials/user data; overbroad permissions; missing input validation at a boundary; insecure defaults; sensitive data in errors/logs/telemetry; auth/authz checks missing at a system boundary; obvious dependency risk from lockfiles. Report at remediation level only — no exploitation, no attack tooling. This is a breadth pass; for the full 8-category scan, the finding should note "deep-scan candidate for `/claudna:audit security`."

### Lane 6 — Maintainability *(breadth — defer depth)*

Overly coupled modules; unclear boundaries; duplicate logic; unused or premature abstractions; missing domain concepts; config scattered through code; business logic in scripts/notebooks without tests; tests asserting implementation details instead of behavior. Breadth pass; for the full quality-axis scan (DRY, naming, SRP, dead code, magic literals), note "deep-scan candidate for `/claudna:audit tech-debt`." For *stale or inaccurate project documentation* specifically, the right deep lens is `/claudna:audit docs`, not tech-debt — route doc-quality findings there.
