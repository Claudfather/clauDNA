# Migration Playbook

Reference material for the `/claudna:audit data-model-redesign` lens — the staging discipline behind the protocol's Part 7. Plan agents read this alongside `skills/_shared/planning-standard.md` when authoring the migration stage docs; each stage (or coherent stage group) is one phase doc = one PR.

The shape is invariant whatever the stores involved: **never break the readers; make every step independently shippable and reversible; move the source of truth last.** The old model remains authoritative until cutover — every stage before it can be abandoned by flipping a switch.

---

## The six stages

| # | Stage | One line | Reversible by |
|---|---|---|---|
| 1 | **Expand** | New structures exist alongside the old; nothing uses them yet | Dropping them |
| 2 | **Backfill** | Historical data copied/derived into the new structures | Stop + truncate |
| 3 | **Dual-write** | Every writer writes both models; old stays the truth | Disable the new-side write |
| 4 | **Shadow-read** | Reads computed from both, old served, divergence measured | Disable the shadow |
| 5 | **Cutover** | Consumers flip to the new model, one at a time, behind a switch | Flip back (old still dual-written) |
| 6 | **Contract** | Old structures and scaffolding removed | **Not reversible — the point of no return is here, not at cutover** |

### 1. Expand

Add the new tables/columns/indexes/topics/collections alongside the old. Strictly additive — no writes, no reads, no constraint that can reject existing traffic (new NOT NULLs arrive with defaults or wait for contract). Never combine expand and contract in one deploy: the deploy that adds the new must not be the deploy that can break the old.

### 2. Backfill

Copy or derive historical data into the new structures. Requirements, all four:

- **Idempotent** — safe to re-run from the top after any failure.
- **Resumable** — chunked, with a durable progress marker; a crash resumes, never restarts blind.
- **Rate-limited** — never starves production traffic; the throttle is a knob, not a constant.
- **Verified** — row/record counts plus a checksum or sampled field-by-field comparison against the source, recorded in the stage doc.

The backfill/dual-write overlap must be reconciled explicitly: once stage 3 starts, the backfill may not clobber rows the dual-write already wrote newer versions of — state the rule (compare-and-set, timestamp guard, or backfill-only-below-a-watermark) in the plan.

### 3. Dual-write

Every writer (the full writer list comes from the consumer inventory) writes both models. Define in the stage doc, not in the implementer's head:

- **Write ordering** — old model first; it remains the source of truth until cutover.
- **Failure semantics** — a new-side failure must not fail the user-facing write; it logs, increments a metric, and lands in a repair queue.
- **The repair job** — how missed or failed new-side writes are detected and healed, and how its backlog is monitored.

### 4. Shadow-read

Read paths compute from both models, serve the old, compare, and emit divergence metrics. Define up front: the divergence metric, the acceptable threshold, and the soak window. **Cutover is gated on divergence sitting at or under the threshold for the full window** — a stage-5 date is a hope, not a plan, until the shadow numbers earn it. Where full shadow-reads are too expensive, a sampled shadow is acceptable if the sampling rule is stated.

### 5. Cutover

Flip the read source (then the write-authority) to the new model, **consumer by consumer, behind a switch that flips back**. Order consumers by blast radius, lowest first; state the order and the bake time between flips. The old model is still receiving dual-writes throughout, so flipping any consumer back is safe and lossless. Cutover completes when every consumer in the coverage matrix reads the new model.

### 6. Contract

Remove the old structures, the dual-write path, the shadow, and the switches. Gated on: every consumer cut over, the post-cutover soak passed, and a stated retention window elapsed (backups/exports of the old structures per the constraints). This is the only irreversible stage — the plan says so explicitly and names who signs off.

---

## Per-consumer coverage

The consumer inventory (protocol Part 1) is the coverage spine. The plan carries a **consumer × stage matrix**: every reader and writer — services, endpoints, background jobs, reports/analytics, ad-hoc scripts, external integrations — gets an explicit disposition at every stage (`migrates in stage N` / `dual-written from stage 3` / `flips in cutover wave 2` / `unaffected — reads a surface that doesn't change`). "Unaffected" is a recorded disposition, never an omission. A consumer discovered after planning is a plan defect: add the row, re-run the verification checklist, and re-check the cutover ordering.

---

## Rollback

Every stage defines, **before it ships**:

- **Trigger** — the metric or observation that mandates rolling back (divergence above threshold, repair-queue growth, error-rate delta), not "if something feels wrong".
- **Mechanism** — the concrete action: flag flip, deploy revert, truncate-and-restart, consumer flip-back.
- **Blast radius** — what is lost or degraded during the rollback, and for whom.

Stages 1–5 must be reversible without data loss. Stage 6 is not; its "rollback" is the retention window, and the plan states the restore procedure and its cost.

---

## Adapting the playbook

- **Incremental repair** uses the same discipline: any repair step that changes schema or moves a concept's source of truth is the six stages in miniature (a column rename is expand → backfill → dual-write → cutover → contract). Code-only repairs skip stages **explicitly** — the doc names which stages don't apply and why.
- **Collapsing stages** is legitimate when justified in writing: a new nullable column feeding one internal consumer may not need a shadow-read; an append-only event stream may have no backfill. The plan names each collapsed or skipped stage and the reason — silent absence is what the verification checklist exists to catch.
- **Multiple concepts moving** — stage per concept or per cluster, never one monolithic six-stage plan for the whole redesign; the matrix keeps the interleaving honest.
