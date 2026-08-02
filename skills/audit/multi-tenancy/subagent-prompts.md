# Subagent Prompt Templates

Reference material for the `/claudna:audit multi-tenancy` lens. Detailed instructions for the subagents launched during Phases 1–2. All subagents follow the disk-write pattern (`skills/_shared/orchestration-guide.md` Sections 2 & 6): write findings to the scratch dir, return a 2-4 line summary, never stream research through the orchestrator. Every research file that captured command output or configuration is scrubbed in place with the redactor (`python3 scripts/redact.py <file>`; path per orchestration-guide §7) before handoff.

Every prompt receives: the Phase 0 tenant-boundary map, the focus area (if any), and the scratch path `/tmp/multi-tenancy-audit-<YYYY-MM-DD_HHMMSS>/research/`.

Common rules for all subagents:

- The audited target is **read-only** — read, grep, and trace; never modify it or execute effects against it.
- Classify every claim per the lens's evidence discipline (`repository-proven` / `documentation-only` / `external-assumption` / `proposed` / `unverified`) and record the class next to the claim.
- Cite file and symbol for everything; line ranges only when stable.
- Report absences explicitly ("no outbox model exists") — an absence is evidence, not a gap in the research.

---

## Subagent A: Identity & data isolation

**Prompt:** "Audit tenant identity and data isolation per categories A and B of `<skill-dir>/scan-categories.md`. The tenant-boundary map is: <paste>. Write findings to `<scratch>/research/identity-data.md` using the Write tool. Return a 2-4 line summary."

The subagent should:

1. Trace the admission chain per category A: authentication → membership → role resolution → server-side tenant derivation, for every entry surface (API, CLI, webhooks, workers, admin).
2. Inventory fail-open interfaces per category B: optional tenant arguments, conditional scoping, nullable ownership columns, unscoped helpers, global prefix lookups, maintenance paths through `tenant=None`.
3. Inventory tenant-aware keys: FKs, uniqueness, indexes, aggregates, cache keys, memoization.
4. Assess RLS posture where applicable: policies, `FORCE ROW LEVEL SECURITY`, owner/`BYPASSRLS` attributes of the runtime role, transaction-local context under the actual pooling mode.

**Research file format:**
```markdown
# Identity & Data Isolation
## Admission chain (per entry surface)
### <surface>: derivation point (file:symbol), membership check, role resolution, client-supplied tenant inputs
## Fail-open inventory
| Interface (file:symbol) | Fail-open shape | Evidence class | Notes |
## Tenant-aware keys
| Store/table | Ownership column (nullable?) | Uniqueness/index scope | Aggregates/caches touching it |
## RLS posture
[policies, roles, context mechanism, pooling mode — each with evidence class]
```

---

## Subagent B: Coordination & providers

**Prompt:** "Audit distributed coordination and provider-effect safety per categories C and D of `<skill-dir>/scan-categories.md`. The tenant-boundary map is: <paste>. Write findings to `<scratch>/research/coordination-providers.md` using the Write tool. Return a 2-4 line summary."

The subagent should:

1. Inventory every queue, job model, lease/claim mechanism, outbox, scheduler, and idempotency key — recording durability (authoritative store vs. memory vs. broker), key scope (tenant? namespace? fingerprint?), and fencing (token-checked finalization or id-only).
2. Inventory in-memory state that guards cross-process invariants (locks, in-flight sets, dedup caches, cancellation flags).
3. For each externally visible provider operation: the operation key scope, the handling of ambiguous outcomes (timeout after send), retry policy, and where tenant credentials travel (payloads? logs?).
4. Record the recovery story: what re-emits lost wake-ups, what promotes due delayed work, what quiesces poison work.

**Research file format:**
```markdown
# Coordination & Providers
## Work inventory
| Unit (file:symbol) | Durability | Claim/lease shape | Fencing | Idempotency scope |
## In-memory invariant state
| State (file:symbol) | Invariant it guards | Breaks with replicas? |
## Provider operations
| Operation | Key scope | Ambiguity handling | Retry policy | Credential path |
## Recovery story
[wake-up recovery, delayed-work promotion, poison quiescence — each with evidence class]
```

---

## Subagent C: Fairness & observability

**Prompt:** "Audit fairness/capacity and observability per categories E and F of `<skill-dir>/scan-categories.md`. The tenant-boundary map is: <paste>. Write findings to `<scratch>/research/fairness-observability.md` using the Write tool. Return a 2-4 line summary."

The subagent should:

1. For every rate limiter and concurrency bound: the *enforced* scope (storage backend, key) vs. the *claimed* scope; what multiplies with replica count; what shared budgets (provider, DB pool) lack deployment-wide enforcement; whether multi-bucket admission is atomic (all-or-none) and what the declared degraded-mode policy is when the limiter store is unavailable.
2. Trace the one-tenant-flood path: dispatch order, prefetch, scheduler iteration — can one tenant delay peers, and is there an observable fairness bound?
3. Trace saturation behavior: at each shared-budget bound, does admission fail fast (reject/defer, bounded latency) or hang/grow unbounded queues? Are retries and recovery polls bounded and jittered, or do replicas herd after a shared outage? Is autoscaling keyed on queue age/saturation rather than CPU? Challenge every number against the Phase 0 capacity envelope.
4. Assess telemetry: metric cardinality strategy for tenant labels, tenant context in traces/logs, cross-tenant leakage through error messages or shared dashboards, operator visibility of queue age / lease recoveries / ambiguous operations / poison counts.
5. For each SLO in the Phase 0 envelope: name its unambiguous measurement point in shipped telemetry, or record that none exists.

**Research file format:**
```markdown
# Fairness & Observability
## Limiter inventory
| Limiter (file:symbol) | Enforced scope | Claimed scope | Multiplies with replicas? | Degraded-mode policy |
## Flood path
[dispatch order, prefetch, the concrete delay mechanism — evidence class per claim]
## Saturation & recovery behavior
[per shared budget: fail-fast vs. hang, retry jitter, herd risk, autoscaling signal — evidence class per claim]
## Telemetry
[cardinality, tenant context, leakage risks, operator visibility — each with evidence class]
## SLO measurement points
| SLO (claimed) | Measurement point (or MISSING) |
```

---

## Subagent D: Migrations & tests

**Prompt:** "Audit migration safety and isolation-test coverage per categories G and H of `<skill-dir>/scan-categories.md`. The tenant-boundary map is: <paste>. Write findings to `<scratch>/research/migrations-tests.md` using the Write tool. Return a 2-4 line summary."

The subagent should:

1. Build the ownership inventory: every tenant-owned table with nullable ownership, every global read/write path that would break under mandatory scoping.
2. Assess migration machinery: backfill ambiguity handling, constraint sequencing, non-transactional phases and their postconditions, shadow mode, cohort cutover, rollback posture, legacy NULL semantics.
3. Inventory existing tests against category H: positive isolation, hostile cross-tenant, missing-context (under the real runtime DB role), and cross-process (separate connections, worker kills, broker loss, deterministic time, provider fakes). Record which acceptance-matrix scenarios are covered vs. absent.

**Research file format:**
```markdown
# Migrations & Tests
## Ownership inventory
| Table/store | Ownership column | Nullable? | Backfill derivable? |
## Migration machinery
[sequencing, shadow mode, rollback, NULL semantics — each with evidence class]
## Test coverage vs. acceptance matrix
| Scenario | Covered? | Test (file:symbol) or gap |
```

---

## Convergence subagent: Failure-window tracing (Phase 2)

**Prompt:** "Read the four research files in `<scratch>/research/` and trace every window in `<skill-dir>/failure-windows.md` against the actual code paths they document. For each applicable window produce a concrete ordered failure sequence using this codebase's real symbols, plus the required invariant; for each closed window cite the closing evidence. Also flag contradictions between research files. Write to `<scratch>/research/failure-traces.md` using the Write tool. Return a 2-4 line summary."

Rules:

- A trace must be reproducible: numbered steps naming the actual functions/queries/states involved.
- "Does not apply" requires a reason (e.g. "no delayed work exists — window 3 vacuous").
- Where evidence is insufficient to decide, classify the window `unverified` — it feeds the report's §10, not a guessed verdict.

**Research file format:**
```markdown
# Failure Traces
## Window <n>: <name> — OPEN | CLOSED | N/A | UNVERIFIED
[ordered sequence with real symbols, or closing evidence, or reason]
**Required invariant:** ...
```
