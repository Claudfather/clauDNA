# Multi-Tenancy Scan Categories

Reference material for the `/claudna:audit multi-tenancy` lens. Eight categories (A–H), one per scorecard dimension in `report-template.md`. Subagents run the categories assigned to them (see `subagent-prompts.md`), adapting the grep heuristics to the detected stack. A pattern hit is a *lead to trace*, never an automatic finding; a clean grep is never proof of absence.

Do NOT read CLAUDE.md or MEMORY.md — already in the system prompt.

## A. Identity & authorization

The chain that must hold before any tenant-scoped work is admitted: authentication → membership → role resolution → **server-side tenant derivation**.

- Where is the caller authenticated, and what principal object results?
- Is tenant identity derived server-side from the principal's memberships — or accepted from client input (header, body field, URL segment, JWT claim the client can mint)? Client-supplied tenant identity without a membership check is a P0 lead.
- Is membership checked *active* (not just historical)? What happens on removal, suspension, or account switching?
- Are roles resolved per-tenant (a user can be admin in one tenant, viewer in another) or globally?
- Do internal/service-to-service calls carry tenant context, or do they run as an implicit superuser?
- Grep leads: `X-Tenant`, `tenant_id` in request-body/query-param parsing, `current_tenant`, `get_current_user`, JWT decode sites, `role`, `membership`, `is_admin`.

## B. Data isolation

Every read/write interface, key, and cache the tenant boundary must pass through.

- **Fail-open interfaces:** optional tenant arguments (`tenant=None` defaults), conditional scoping (`if tenant is not None: filter`), nullable ownership columns, unscoped query helpers, global prefix/key lookups, maintenance access hidden behind a missing tenant. The safe shape is fail-closed: missing tenant context *raises*; global access goes through a separate, named, audited privileged interface.
- **Tenant-aware keys:** foreign keys, uniqueness constraints, and indexes should be composite with the tenant column where the invariant is per-tenant (`UNIQUE (tenant_id, slug)`, not `UNIQUE (slug)`). Aggregates (`COUNT`, `SUM`, dashboards) must group or filter by tenant. Cache keys, idempotency keys, and memoization keys must embed the tenant (and, where applicable, the provider account) — a bare `cache[slug]` is cross-tenant by construction.
- **RLS (where the database supports it):** policies on every tenant-owned table; `FORCE ROW LEVEL SECURITY` where the runtime role could be the table owner; runtime role is non-owner and has no `BYPASSRLS`; tenant context is set **transaction-locally** (e.g. `SET LOCAL`) inside every transaction — session-scoped context does not survive transaction-mode connection pooling; privileged maintenance uses a separate role, not a policy hole. Integrity-constraint errors (FK/unique violations) bypass RLS and can act as cross-tenant existence oracles.
- Grep leads: `nullable=True` on ownership columns, `Optional[` tenant params, `.filter(` helpers with conditional tenant clauses, `ENABLE ROW LEVEL SECURITY`, `BYPASSRLS`, `SET LOCAL`, `session.execute` without scoping helpers.

### Machine-checked fail-open patterns

These heuristics are exercised by this repo's CI against the golden fixtures in `tests/fixtures/multi-tenancy/` (fail-open fixture must trip every pattern; the fail-closed fixture must trip none). One pattern per line; `#` starts a comment.

<!-- test-anchor: fail-open-patterns -->
```regex
# optional tenant parameter or tenant default of None/null/undefined
tenant\w*(?:\s*:\s*[^=,)\n]*)?\s*=\s*(?:None|null|undefined)\b
# scoping applied only when the tenant argument happens to be provided
if\s+tenant\w*\s+is\s+not\s+None
# nullable tenant-ownership column
tenant\w*[^\n]{0,60}nullable\s*=\s*True
# global prefix lookup over an unscoped keyspace
\.startswith\(\s*prefix
# maintenance/global access smuggled through an explicit tenant=None call
\(\s*tenant\w*\s*=\s*None\s*\)
```

## C. Distributed coordination

Everything that stops being true when a second process exists.

- **Durable admission:** is accepted work committed to an authoritative store before success is reported, or does it live only in process memory / a non-durable broker?
- **Claims and leases:** can a committed-but-in-progress row be re-claimed by a second worker? Do leases carry a fencing token/ownership generation that finalization and heartbeats must present, or does expiry alone "transfer" ownership while the stale holder keeps running?
- **Idempotency:** are keys scoped to tenant + operation namespace, and fingerprint-checked so key reuse with different payload semantics conflicts rather than silently deduplicates?
- **Outboxes and wake-ups:** if a broker message is lost *after* the outbox row is marked published, does an independent scan of authoritative ready/due work recover it? Delayed/scheduled work included?
- **Queue messages and jobs:** do payloads carry tenant context (and exclude credentials)? Are schedulers tenant-fair or sequential-by-tenant?
- **In-memory state inventory:** locks, in-flight registries, dedup sets, cancellation flags — each is a finding lead when it guards an invariant that must hold across replicas.
- Grep leads: `threading.Lock`, `asyncio.Lock`, module-level dicts/sets guarding work, `SKIP LOCKED`, `claimed_at`, `lease`, `visibility`, `outbox`, `published_at`, `celery`/`sidekiq`/`bull`/consumer-group configs.

### Machine-checked distributed queue/worker patterns

Exercised by CI against the queue/worker fixture (must trip every pattern; the fail-closed fixture must trip none).

<!-- test-anchor: queue-worker-patterns -->
```regex
# idempotency key not scoped by tenant (no tenant component on the line)
idempotency_key\s*=\s*(?!.*tenant)[^\n]+
# claim query that re-admits rows already claimed as processing (no lease fencing)
status\s+IN\s*\(\s*'ready'\s*,\s*'processing'\s*\)
# finalization keyed on id alone — a stale worker that lost its lease can still finalize
SET\s+status\s*=\s*'done'\s+WHERE\s+id\s*=\s*%s
# blind retry of an externally visible call after an ambiguous outcome
except\s+(?:TimeoutError|ConnectionError)\b[^\n]*:\n[^\n]*(?:publish|send|retry)
# process-local rate limiter guarding a shared budget — multiplies with replicas
InMemoryRateLimiter|memory://
```

## D. Provider isolation

Externally visible effects performed with tenant-owned credentials against third-party providers.

- Are provider operations keyed per provider-account and command namespace, so two tenants (or two operations for one tenant) cannot collide or dedupe against each other?
- Is there an explicit **ambiguous** state for a provider call whose response was lost after the request may have been sent? Blind retry of an externally visible effect is a P0 lead; the safe shape is reconcile-or-hold-for-review.
- Are tenant credentials isolated — never in shared queue payloads, logs, traces, or error strings? Is egress (webhooks, user-supplied URLs) validated per-tenant against SSRF?
- Can one tenant's provider failure (rate-limit storm, revoked credential) exhaust a shared client, connection pool, or retry budget and starve peers?
- Grep leads: provider client construction sites, `retry`, `backoff`, webhook handlers, credential loading, `httpx`/`requests`/SDK call sites inside workers.

## E. Fairness & capacity

Challenge every rate-limit and fairness claim **at its actual shared scope**.

- For each limiter: what is the enforced scope (process, replica, deployment, tenant, provider account) versus the *claimed* scope? A process-local limiter multiplies with replica count; a global limiter keyed by tenant does not protect a genuinely shared provider budget, and tenant-keying a shared budget does not create per-tenant capacity.
- Can one tenant's burst delay every other tenant (FIFO queue, sequential scheduler loop, unbounded prefetch)? Consumer groups distribute work — they do not by themselves implement weighted fairness, priority, or a starvation bound. Demand the dispatch-time mechanism and its observable maximum peer lag.
- Capacity math: process concurrency × replicas vs. database pool budget, provider concurrency, thread offload, temporary storage. "Scale the workers" must not silently multiply provider or DB pressure.
- Grep leads: rate-limiter construction (storage backend = the enforced scope), semaphores, pool sizes, prefetch counts, `for tenant in tenants:` loops in schedulers.

## F. Observability

Whether an operator can see the boundary holding — without the telemetry itself leaking.

- Metric cardinality is bounded: per-tenant labels on unbounded tenant populations blow up the metrics store; the pattern is bounded cohorts/top-N plus per-tenant logs, not a label per tenant.
- Traces and logs carry tenant context on every tenant-scoped operation, so a cross-tenant incident is diagnosable.
- No cross-tenant leakage *through* telemetry: tenant A's identifiers, payload contents, or credentials must not appear in tenant B's error messages, shared dashboards, or support tooling.
- Operator visibility for the coordination machinery: queue age per tenant, lease recoveries, ambiguous provider operations awaiting review, poison/dead-letter counts, fairness lag. An invariant nobody can observe will be violated silently.

## G. Migration safety

Getting *to* mandatory tenant scoping without corrupting or exposing data on the way.

- **Ownership inventory first:** every nullable tenant-owned table and every global read/write path enumerated before any constraint lands.
- **Backfill ambiguity:** rows whose owner cannot be derived mechanically go to explicit review — never a guessed default tenant.
- **Sequencing:** backfill → verify → `NOT NULL` / composite-unique / RLS enable, each gated; constraint validation staged (e.g. validate separately from add) to bound locks. Non-transactional phases (concurrent index builds) need explicit postconditions — do not assume every migration atomically updates its version record.
- **Shadow mode and cohorts:** new enforcement runs in shadow (log-only) before deny; cutover proceeds by tenant cohort, not big-bang. Shadow work must be immutably non-executable — a later global flag must never activate historical shadow rows whose legacy effect already occurred.
- **Rollback:** stops new routing without deleting durable evidence, blindly resuming ambiguous provider operations, or "temporarily" running as the RLS-bypassing owner role.
- **Legacy NULL behavior:** while NULLs remain, which queries treat NULL as "global", which as "orphaned"? Divergence is a finding.

## H. Testability

Whether the isolation claims are (or can be) *proven*.

- **Positive tests:** tenant A sees exactly tenant A's data through every interface (API, workers, caches, aggregates).
- **Hostile tests:** tenant A requests tenant B's IDs — direct, via nested/related objects, via aggregates, via idempotency-key collision, via queue payload tampering. Expect denial with no existence leak.
- **Missing-context tests:** every tenant-scoped interface called without tenant context fails closed (raises/denies), including under the real runtime database role (not the owner role that skips RLS).
- **Cross-process tests:** separate processes/connections for claim contention; worker kill at state boundaries; broker restart/loss; lease expiry with a paused-then-resumed stale worker; deterministic time; provider fakes (a production provider call is never a test oracle).
- The report's acceptance-test matrix (`report-template.md` §8) lists the concrete scenarios; grade this dimension by how many are already covered vs. absent.
