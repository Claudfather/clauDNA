# Scale Audit Report Template

The output contract for the `/claudna:audit scale` lens. The report is **stable**: sections appear in exactly this order with these headings, so downstream consumers (issue filing per `skills/_shared/output-guide.md`, re-audits, diffs between audits) can rely on the structure. Sections with nothing to report state that explicitly ("No open decisions.") — never omit a section.

Severity and confidence vocabulary are defined at the bottom; findings carry the canonical concern areas from `skills/_shared/contracts/lens-result-contract.md`.

---

## 1. Executive verdict

Exactly one of:

- **approve** — the system survives its declared envelope: the isolation boundary holds and capacity behavior is bounded across the audited surfaces; remaining findings are P2/P3.
- **approve with required changes** — the direction is sound, but named P0/P1 findings must land before (further) growth: more replicas, more tenants, or higher admitted throughput.
- **reject** — the boundary or the capacity model does not hold and no bounded set of changes identified by this audit closes it; a design change is required.

Follow the verdict with the minimum rationale (2–5 sentences) and the boxed summary (lens, scope, verdict, finding counts by severity).

## 2. Scorecard

Score each dimension 0–5 against **repository-proven** evidence only (documentation-only and external-assumption claims never raise a score). One row per dimension, with a one-line reason:

| Dimension | Score | Reason |
|---|---:|---|
| Identity and authorization | /5 | |
| Data isolation | /5 | |
| Distributed coordination | /5 | |
| Provider isolation | /5 | |
| Fairness and capacity | /5 | |
| Observability | /5 | |
| Migration safety | /5 | |
| Testability | /5 | |

Anchors: 0 = boundary absent; 2 = present but fail-open or single-process-only; 4 = enforced with independent layers and tested; 5 = enforced, tested hostile + cross-process, and operator-observable. When Phase 0 records no isolation unit, the isolation-specific dimensions grade `N/A` with that reason — an absent boundary is never scored as a safe one, and `N/A` rows are excluded from any aggregate.

## 3. Boundary and capacity map

The Phase 0 output, finalized: the isolation unit ("tenant" — org/workspace/account, or the individual user account in a consumer product; or its recorded absence), where tenant identity is derived server-side (and every place it is instead client-supplied), and the enumerated surfaces the boundary must span — processes, replicas, queues, databases, caches, provider credentials, operational workflows. Include a short table of tenant-owned data stores/tables with their ownership column and nullability.

Close the map with the **capacity envelope** the audit graded against: provisioned vs. concurrently active tenants, peak admission rate, replica plan, shared budgets (DB pool, provider concurrency, limiter scope), and each latency/availability SLO with its unambiguous measurement point. State whether the envelope was declared by the repository or derived by the audit — an underived, undeclared envelope is a finding, not a blank.

## 4. Evidence audit

One row per significant claim examined, with its evidence class from the lens's evidence discipline:

| Claim | Class | Evidence (file/symbol) | Consequence |
|---|---|---|---|
| | `repository-proven` \| `documentation-only` \| `external-assumption` \| `proposed` \| `unverified` | | |

Cite paths and symbols; add line ranges only when stable. Contradicted claims are `unverified` with the contradicting evidence named.

## 5. Failure sequences

The Phase 2 traces: for each open failure window (per `failure-windows.md`), a concrete ordered sequence instantiated against this codebase's actual symbols, followed by the required invariant. Windows verified closed are listed with the closing evidence. Never a generic warning — a sequence a reader could reproduce.

## 6. Findings (P0–P3)

Findings grouped by severity, P0 first. Every finding uses this block:

```markdown
### [P0-1] <title>
- **Severity:** P0 | P1 | P2 | P3
- **Confidence:** high | medium | low
- **Concern area:** <canonical value from lens-result-contract.md>
- **Evidence:** <file/symbol citations; file:line where stable>
- **Consequence:** <what a tenant, operator, or peer tenant experiences>
- **Exploit / failure sequence:** <ordered steps, where applicable; reference §5 traces>
- **Remediation direction:** <concrete direction — the invariant or mechanism to introduce, not a vague "improve">
```

## 7. Required invariants

The deduplicated list of invariants that must hold for the verdict's conditions to be met — each stated as a testable property ("finalization requires the lease's fencing token", "every tenant-scoped interface raises on missing tenant context"), cross-referenced to the findings it discharges.

## 8. Acceptance-test matrix

Concrete tests that would prove the invariants — positive, hostile, missing-context, and cross-process. All external providers faked/sandboxed; a production effect is never a test oracle.

| Scenario | Injection | Expected state/effect | Proof signal |
|---|---|---|---|
| hostile cross-tenant read | tenant A requests tenant B's id | denial, no existence leak | denial audit + unchanged B rows |
| missing tenant context | call scoped interface without context, as the runtime DB role | fail closed (raise/deny) | integration assertion under runtime role |
| concurrent claim | two processes claim the same job | one live lease token | conditional-update row count |
| flood fairness | tenant A contributes 90% of enqueued work | peers start within the declared lag bound | per-tenant lag quantiles |
| provider rate-limit storm | fake limit responses with reset headers | bounded jittered retry, reduced concurrency, no herd | active/retry timeline |
| DB pool saturation | hold DB-active tasks at the pool bound | fast reject/defer with bounded admission latency — no full-timeout hangs | pool-wait metric + admission status |
| coordination-store outage | stop the limiter/wake-up store under load | the declared degraded policy holds (fail-closed, or bounded fail-open) and degrades loudly | admission decisions + degradation alert during outage |
| post-recovery herd | restore a failed shared dependency with a retry backlog | gradual ramp, no synchronized burst re-tripping the dependency | dependency call-rate timeline after recovery |
| … | | | |

Include at minimum: one positive-isolation row, one hostile cross-tenant row, one missing-context row, one row per open failure window from §5, and **one saturation row per shared budget** (DB pool, provider budget, coordination/limiter store). Saturation rows must prove fast reject/defer at the admission edge — bounded latency, never unbounded queue growth or full-timeout hangs — under load at the Phase 0 envelope's declared peak.

## 9. Open decisions

Only choices that materially alter correctness, schema, or the tenant boundary (e.g. the physical tenant key, the fairness algorithm and its starvation bound, database role design). Implementation details and naming do not belong here. "No open decisions." when empty.

## 10. Unverified claims

The explicit list of every claim classified `unverified` (including contradicted ones) and every `external-assumption` not re-verified during the audit, each with what it would take to verify it. This section is the honesty ledger — it may not be empty unless §4 contains no such rows.

---

## Severity ladder

| Severity | Definition | `--output github` label |
|---|---|---|
| **P0** | Cross-tenant exposure, data corruption, or duplicate/lost external effect reachable now (or on the first added replica) — correctness blocker before any multi-tenant/multi-replica operation | `priority:critical` |
| **P1** | Boundary holds only by convention (fail-open interface, missing fencing, unproven recovery) — required before scale-out or the next tenant cohort | `priority:high` |
| **P2** | Hardening gap: fairness bound, observability, capacity math, test coverage | `priority:medium` |
| **P3** | Hygiene and follow-ups with no near-term exposure | `priority:low` |

Do not inflate ordinary implementation tasks into P0. Confidence (`high`/`medium`/`low`) reflects the evidence class behind the finding: `repository-proven` evidence supports high; inference from partial evidence is medium; pattern-only leads are low and say so.
