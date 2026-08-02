# Cross-Process Failure Windows

Reference material for the `/claudna:audit multi-tenancy` lens, consumed by the Phase 2 convergence subagent. Each window is a *shape* of distributed failure; the subagent instantiates it against the actual code paths found in Phase 1, producing a concrete ordered sequence (who does what, in what order, what breaks) — or records the repository evidence that closes the window. A generic warning is not an acceptable trace.

Format per window: **Sequence** (the generic shape) · **Required invariant** (what closes it) · **Where to look** (evidence leads).

## 1. Duplicate delivery / replay of an accepted command

**Sequence:** a client, webhook, or broker redelivers an already-accepted command (retry, at-least-once delivery, double-click); a second unit of work is admitted; the external effect happens twice.
**Required invariant:** admission is idempotent on a tenant- and namespace-scoped unique key with a payload fingerprint — same key + same fingerprint returns the original result; same key + different fingerprint conflicts loudly.
**Where to look:** webhook/inbox handlers, unique constraints on admission tables, idempotency-key derivation, dedup caches (process-local dedup is not dedup).

## 2. Broker loss after durable commit (outbox marked published)

**Sequence:** work is committed to the authoritative store; the relay publishes a wake-up to the broker and marks the outbox row published; the broker loses/trims the message before any worker consumes it; a relay that only scans unpublished rows never republishes; the work is stranded forever despite being durably accepted.
**Required invariant:** an independent periodic scan of authoritative ready/unleased work re-emits wake-ups regardless of the outbox delivery flag (bounded by a cooldown/generation counter).
**Where to look:** outbox relay queries (`published_at IS NULL`-style predicates), broker persistence configuration, any recovery/reconciliation loop.

## 3. Delayed-work wake-up loss

**Sequence:** a job is deferred until a future time; its delayed wake-up message is published and then lost; a recovery scan that looks only at currently-ready work never sees the waiting job; it never runs.
**Required invariant:** due waiting work is promoted to ready by an authoritative-store scan (same recovery path as window 2), not solely by broker-delivered timers.
**Where to look:** scheduled/retry queues, `available_at`/`run_at` columns, whether the recovery scan's predicate includes due-but-waiting states.

## 4. Lease expiry vs. stale worker (fencing)

**Sequence:** worker A leases a job and stalls (GC pause, network partition, slow provider call); the lease expires; worker B legitimately claims the job; worker A resumes and finalizes — or performs the external effect a second time.
**Required invariant:** every lease carries a fencing token/ownership generation; heartbeats and finalization must present the matching token; a stale holder's writes are rejected. For externally visible effects, a one-shot effect permit is persisted and re-checked immediately before send, so successors reconcile rather than re-issue.
**Where to look:** claim/heartbeat/finalize queries (does the WHERE clause include the token, or only the job id?), lease-duration vs. provider-timeout configuration.

## 5. Cancellation racing an in-flight external effect

**Sequence:** a user cancels a command; the worker has already begun the provider request; the system marks the command cancelled immediately; the provider call succeeds anyway; the effect exists but the record says cancelled.
**Required invariant:** cancellation is cooperative once an effect may be in flight — persist `cancel_requested`, transition through a reconciling state, and mark `cancelled` only when no-effect is proven.
**Where to look:** cancellation endpoints/handlers, state machines for in-flight work, whether cancellation checks happen before or after the point of no return.

## 6. Ambiguous provider response

**Sequence:** the provider request is sent; the connection drops before the response arrives; the effect may or may not have occurred; a blind retry publishes twice; blind failure hides a real success from the tenant.
**Required invariant:** an explicit ambiguous state per provider operation, keyed to the provider account and operation namespace, resolved by reconciliation (query the provider) or held for operator review — never blind retry, never silent discard.
**Where to look:** provider-client exception handling, retry decorators/wrappers around externally visible calls, whether any provider-side anchor (container/operation id) is persisted before the irreversible step.

## 7. Rolling restart / stale-code worker

**Sequence:** a deploy replaces replicas while work is leased; an old-code worker holds a lease across the cutover and finalizes under superseded assumptions (old schema, old state machine, old provider contract); or the restart drops in-memory state (locks, dedup sets, cancellation flags) that guarded an invariant.
**Required invariant:** every invariant that must survive a restart lives in the authoritative store, not process memory; leases drain or fence across deploys; schema/behavior changes are compatible with one version of in-flight work.
**Where to look:** the in-memory state inventory from scan category C, deploy/drain hooks, lease durations vs. deploy cadence.

## 8. Poison-work regeneration

**Sequence:** a job fails deterministically (bad payload, revoked credential); retry/recovery returns it to ready; it fails again — forever; the recovery machinery from windows 2–3 faithfully regenerates the poison, burning the tenant's (or everyone's) capacity.
**Required invariant:** bounded attempts move the job *and its parent command* atomically to a quiescent review state that every recovery scan and lease query excludes; an operator path exists to resolve or discard it.
**Where to look:** attempt counters, dead-letter handling, whether recovery-scan predicates exclude review/terminal states.

## 9. Missing tenant context on a pooled connection (RLS window)

**Sequence:** a code path opens a transaction but skips setting tenant context; under transaction-mode pooling the connection carries no session state from any previous request (or worse, stale state under session pooling); a permissive policy, owner role, or `BYPASSRLS` attribute lets the unscoped query read every tenant's rows.
**Required invariant:** the runtime role is non-owner with no `BYPASSRLS`; enabled tables default-deny (`FORCE ROW LEVEL SECURITY` where the owner executes); the unit-of-work entry point sets transaction-local tenant context unconditionally, and tests connect as the real runtime role.
**Where to look:** unit-of-work/session factories, `SET LOCAL` call sites, role definitions in migrations, pooler mode configuration.

## 10. One-tenant flood vs. peer latency (fairness window)

**Sequence:** tenant A enqueues a large burst ahead of tenant B; FIFO ordering, a sequential per-tenant scheduler loop, or a large prefetch keeps serving A; B's first job waits behind A's ten-thousandth; per-tenant concurrency caps bound A's *active* work but not B's queue-position wait.
**Required invariant:** fairness is enforced at or before dispatch (weighted quantum, per-tenant interleaving, age promotion) with bounded prefetch, and produces an observable maximum peer lag — queue topology alone is not a fairness proof.
**Where to look:** dispatch/relay selection queries, scheduler iteration order, prefetch/batch sizes, any fairness metric or its absence (ties to scan category F).

## 11. Shared limiter/coordination-store outage (degraded admission)

**Sequence:** the store backing shared rate limits or admission coordination becomes unavailable; each replica silently falls back to admitting at its full local capacity (or to no limit at all); aggregate admission multiplies by replica count precisely while a dependency is already down; downstream budgets (DB pool, provider limits) are breached and the outage cascades. The inverse failure is equally real: an undeclared fail-closed fallback turns a coordination blip into a total admission outage nobody planned for.
**Required invariant:** the degraded-mode admission policy is *declared* and bounded — fail-closed, or fail-open within a conservative per-replica budget sized so that replicas × local budget stays inside every shared downstream budget — and the degradation is loud (metric + alert), not silent.
**Where to look:** limiter-client exception handling (what happens on connection error?), fallback branches around the coordination store, whether any test exercises admission during a store outage.

## 12. Post-recovery retry herd (thundering herd)

**Sequence:** a shared dependency (provider, broker, database) recovers after an outage; every replica's fixed, unjittered poll/backoff interval fires on the same tick; all queued and retry-eligible work re-attempts simultaneously; the synchronized burst re-trips the provider's rate limit or re-saturates the pool; the dependency "fails" again — a self-inflicted oscillation.
**Required invariant:** retries and recovery polls are bounded and jittered; provider reset/retry-after signals are respected with per-key spreading; concurrency ramps back gradually (e.g. additive increase) instead of releasing the full backlog at once.
**Where to look:** retry/backoff decorators and their jitter parameters, fixed `sleep(CONSTANT)` worker loops, backlog release behavior after health checks flip green (ties to scan category E).
