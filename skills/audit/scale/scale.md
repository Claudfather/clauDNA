Invoked by /claudna:audit in scale mode — evaluates whether the system will survive growth: high throughput, high user counts, and multiple tenants across processes, replicas, queues, databases, caches, external providers, and operational workflows. Answers one question: what breaks first under growth — and does the isolation boundary hold while it breaks? Multi-tenancy is one dimension of scale survival, not a separate concern: the seams that leak between tenants and the seams that collapse under load are audited together because they fail together.

**Persona:** Principal distributed-systems reviewer with a hostile-caller mindset. Evidence-driven — every finding cites file/symbol. Treats process memory, brokers, and network responses as fallible. Does not validate a design merely because it is detailed; prefers a smaller enforceable contract over broad aspirational language. If the evidence does not support a claim, says so.

**Focus interpretation** (flag semantics live in the lens contract §2): the focus text is a subsystem or path (e.g., `auth`, `workers/`, `migrations`, a specific queue). If provided, scope the audit to that area but always complete Phase 0 (the boundary definition) for the whole system — isolation cannot be judged inside a scope that omits the boundary.

## Routing

Direct invocation: `/claudna:audit scale [focus]`. Automatic routing is the engine's job — the engine (`skills/audit/SKILL.md`) selects this lens from its table when the request wording unambiguously matches the triggers below; otherwise it prints the lens table and stops (engine dispatch rules). This lens never claims the ambiguous case.

### Positive triggers

Evidence in the request or repository that warrants this lens:

- growth questions — "will this survive 10x users or traffic?", launch-spike readiness, capacity planning;
- sustained or bursty high throughput — ingestion, fan-out, worker fleets under load;
- horizontal scaling or multiple replicas of any process;
- multi-tenancy — multiple tenants, organizations, workspaces, accounts, or customer isolation;
- tenant-owned database rows;
- queues, workers, jobs, leases, outboxes, or schedulers;
- tenant or provider rate limits and fairness between tenants;
- Row-Level Security (RLS);
- tenant-aware migrations or backfills;
- externally visible effects performed with tenant-owned credentials.

"Tenant" names the isolation unit, not the billing shape: in a consumer product the unit is the individual user account — a tenant of size one — and every trigger and check in this lens applies unchanged to per-user isolation at high user counts.

### Negative triggers (when NOT to use)

- A `tenant_id` column existing somewhere is NOT a trigger by itself — an ordinary code-quality request against a codebase that happens to have tenants routes to `/claudna:audit tech-debt`.
- Injection, secrets exposure, OWASP patterns → `/claudna:audit security` (cross-tenant *authorization* stays here; generic vulnerability scanning does not).
- Whether interfaces enforce cross-cutting concerns consistently → `/claudna:audit access-path`.
- Schema-to-intent fit and awkward code-to-DB paths → `/claudna:audit data-model`.
- Making one endpoint or page faster (profiling, query tuning, micro-optimization) is performance engineering, not scale survival → `/claudna:audit frontend-perf` for UI symptoms, `/claudna:audit system` for whole-system triage that includes backend performance.
- A live production outage → `/claudna:investigate-app` (this lens examines systems at rest).

## The Key Insight

A codebase that works single-process at today's load usually fails growth through three seam classes, and none is visible from healthy-path reading:

1. **Fail-open interfaces** — the tenant scope is *optional* somewhere: a `tenant=None` default, a nullable ownership column, an unscoped query helper, a global prefix lookup, or a maintenance path that smuggles global access through a missing tenant. Every optional scope is an isolation bug waiting for one forgotten argument.
2. **Cross-process windows** — invariants enforced by process memory (locks, in-flight sets, local rate limiters) silently stop holding when a second replica, worker, or scheduler exists. The failure is a *sequence*, not a line of code: replay, lease expiry, stale workers, cancellation racing an external effect, broker loss.
3. **Capacity cliffs** — budgets enforced per process silently multiply with replica count; admission has no backpressure, so overload becomes cascading failure instead of bounded rejection; unjittered retries herd after every recovery; fairness is assumed from queue topology. The system does not degrade under growth — it falls off a cliff, and nobody stated the envelope it was supposed to hold.

The audit therefore hunts for optionality, for sequences, and for unstated envelopes — never for the mere presence of tenant vocabulary or a big queue.

## Evidence discipline

Classify every claim encountered (in code, docs, or the request) into exactly one class, and carry the class through to the report:

| Class | Meaning |
|---|---|
| `repository-proven` | Behavior demonstrated by code, tests, migrations, or configuration in the audited repository — cite file and symbol |
| `documentation-only` | Asserted by README/docs/comments but not backed by code the audit located |
| `external-assumption` | Provider or platform behavior (broker delivery, pooler mode, rate-limit scope) that must be re-verified against first-party sources |
| `proposed` | Target behavior from a design document, not yet implemented |
| `unverified` | Could not be verified in the time available, or repository evidence *contradicts* it (say which) |

A `documentation-only` or `external-assumption` claim never upgrades a scorecard dimension. Every `unverified` claim is listed in the report's final section — never silently dropped.

## Read-only iron law

<HARD-GATE>
The audited target is read-only. Never modify the audited repository, run its migrations, mutate its databases/queues/caches, or trigger externally visible operations against its providers. Read, grep, and static tracing only. Writes are permitted solely to the audit's own scratch directory and to the published audit documents. When the audited target is this plugin's own skill tree, the same rule applies to the *subject* of the audit — only clauDNA's own skill implementation, tests, and documentation may change, and only via a normal reviewed change, never as an audit side effect.
</HARD-GATE>

## Quick Reference

| Phase | What happens | User gate? |
|-------|-------------|------------|
| **0: Boundary** | Define the intended tenant boundary and authoritative tenant identity | No |
| **1: Scan** | Parallel discovery across the eight scan categories (`scan-categories.md`) | No |
| **2: Trace** | Walk the cross-process failure windows (`failure-windows.md`) against actual code | No |
| **3: Report** | Assemble the stable report (`report-template.md`), present summary | **Yes** |
| **4: Remediation** | Generate per-PR planning docs on confirmation | No |

## Procedure

Follow these steps exactly in order.

**Enter Plan Mode.** Call `EnterPlanMode` per `skills/_shared/audit-lens-contract.md` §6 — discovery, tracing, and report assembly below are read-only.

Do NOT read CLAUDE.md or MEMORY.md — already in system prompt.

### Phase 0: Boundary definition

Before scanning anything, answer in writing (this becomes the report's boundary and capacity map):

1. **What is the isolation unit ("tenant") here?** The organization/workspace/account/customer unit the system claims to isolate — in a consumer product, the individual user account (a tenant of size one). Name the model/table/type that anchors it. If the system genuinely has none (a single-customer internal tool with no user accounts), record that: the isolation-specific checks grade `N/A` with that reason, and the audit proceeds on the throughput and coordination dimensions.
2. **What is the authoritative tenant identity?** Where is the tenant derived *server-side* from the authenticated principal — and where is it instead accepted from client input (a header, a body field, a URL segment)? Client-supplied tenant identity is a finding, not a boundary.
3. **Which surfaces are inside the boundary?** Processes, replicas, queues, databases, caches, provider credentials, scheduled/operational workflows — enumerate what the boundary must span.
4. **What does the system claim?** Collect isolation/fairness/scaling claims from docs and comments and pre-classify each per the evidence discipline.
5. **What is the declared capacity envelope?** Provisioned vs. concurrently active tenants, peak admission rate, replica plan per process, shared budgets (DB pool, provider concurrency), and every latency/availability SLO the system claims — each SLO with its measurement point. All pressure claims in Phases 1–2 are challenged against these declared numbers. **No declared envelope is itself a finding** — a system cannot be pressure-tested against an unstated target; derive a conservative envelope from observed configuration, say so, and grade against that.

If the system has neither an isolation unit nor any scale-out surface (no replicas, no workers or queues, no shared budgets), report that and stop — this lens has nothing to audit (under `--auto`, emit the structured result with `"outcome": "blocked"`).

### Phase 1: Parallel discovery

**Scratch directory:** `/tmp/scale-audit-<YYYY-MM-DD_HHMMSS>/research/`

Launch four `general-purpose` subagents in parallel (disk-write pattern per `skills/_shared/orchestration-guide.md` — subagents write findings to the scratch dir and return 2-4 line summaries; the orchestrator never reads full research files):

- **Subagent A: Identity & data isolation** — scan categories A–B: authentication, membership, role resolution, server-side tenant derivation; fail-open interfaces; tenant-aware keys, uniqueness, indexes, aggregates, caches. Writes `research/identity-data.md`.
- **Subagent B: Coordination & providers** — scan categories C–D: queues, jobs, leases, outboxes, idempotency keys, provider-operation keys, ambiguous external effects. Writes `research/coordination-providers.md`.
- **Subagent C: Fairness & observability** — scan categories E–F: rate limits at their actual shared scope, per-tenant budgets, metric cardinality, tenant context in traces/logs, cross-tenant leakage. Writes `research/fairness-observability.md`.
- **Subagent D: Migrations & tests** — scan categories G–H: ownership inventory, backfill ambiguity, constraint sequencing, shadow mode, rollback, legacy NULLs; existing positive and hostile cross-tenant tests. Writes `research/migrations-tests.md`.

Pass the Phase 0 boundary map and the focus area into every subagent prompt. **Full prompts and research file formats:** `subagent-prompts.md` in this lens directory. Scan checklists: `scan-categories.md`.

### Phase 2: Failure-window tracing

Launch one convergence subagent that reads all four research files and traces each window in `failure-windows.md` against the *actual* code paths found in Phase 1. For each window that applies, it produces a concrete, ordered failure sequence (steps a hostile caller or an unlucky deployment would actually take) plus the invariant that would close it — never a generic warning. Windows that provably cannot occur are recorded with the evidence that closes them. Writes `research/failure-traces.md`.

### Phase 3: Report assembly

Assemble the report **exactly** per `report-template.md` in this lens directory — stable section order, scorecard dimensions, finding fields, and severity ladder are all defined there. Grade findings P0–P3 per the template's ladder; carry each finding's concern area from the canonical vocabulary (`skills/_shared/contracts/lens-result-contract.md` — contract §3; this lens mints no new concern). Present the report summary: boxed header (lens, scope, verdict, counts by severity), then the report body.

---

## User Gate

Present the report and ask:

**"Here is the scale audit. Would you like me to generate remediation plans? I'll group related fixes into PRs."**

Do NOT proceed to Phase 4 without explicit confirmation.

**Exit Plan Mode.** Call `ExitPlanMode` per `skills/_shared/audit-lens-contract.md` §6 — doc generation past this point requires the Write tool.

---

## Phase 4: Remediation Plans

**Output lands in:**
```
documentation/planning/scale/<session_name>_<YYYY-MM-DD>/
├── 00_SCALE_AUDIT.md
├── 01_<remediation-slug>.md
└── ...
```

Plan agents write the family to the session's scratch docs directory (`/tmp/scale-audit-<YYYY-MM-DD_HHMMSS>/docs/`); the orchestrator publishes it with `/claudna:publish <scratch-docs-dir> --to docs --dir documentation/planning/scale/<session_name>_<YYYY-MM-DD>/` (family mode; orchestration guide, Section 3).

`00_SCALE_AUDIT.md` is the full Phase 3 report. Each numbered doc is exactly one PR, grouping related findings (e.g., all mandatory-tenant-context changes → one PR; all lease-fencing changes → one PR), ordered P0 first, and must include the required invariants it discharges plus the acceptance-test rows that prove it. Plan agents follow Section 9 of the orchestration guide and `skills/_shared/planning-standard.md`.

**Adversarial review pass:** follow `skills/_shared/pre-handoff-checklist.md` on every doc before publishing. Prioritize `concern_area` values `security`, `data-integrity`, `error-handling`. If a critic finds that a proposed remediation *itself* opens a cross-tenant window (e.g., a backfill that guesses ownership), elevate to CRITICAL.

Then hand off: **"Plans are ready. Run `/claudna:build documentation/planning/scale/<session>/` to start building."** This lens produces plans, not code — see `skills/_shared/orchestration-guide.md` §11.

---

## Output Targets

This lens supports `--output github`, `--output session` (the engine default, contract §2), and the `docs` deliverable above.

Follow the output guide at `skills/_shared/output-guide.md`:
- For `github`: write each finding-cluster as a doc (frontmatter + the Section 4 body skeleton) and delegate to `/claudna:publish <file> --to github-issue --repo <repo>`. Map severities per `report-template.md`: P0 → `priority:critical`, P1 → `priority:high`, P2 → `priority:medium`, P3 → `priority:low`.
- For `session` (engine default): produce the report doc, then `/claudna:publish <file> --to session` prints it to chat (Section 5).
- For `docs`: the Phase 4 subagent workflow above.

**Credential rule:** tenant credentials and connection strings surface in exactly this kind of audit. Never reproduce a secret value — file:line and variable name only, and scrub every research/findings file in place with the redactor (`python3 scripts/redact.py <file>`; resolve the path per `skills/_shared/orchestration-guide.md` §7) before it leaves a subagent or is published.

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Flagging every table without a tenant column | Some data is legitimately global (reference data, system config). The finding is *ambiguous* ownership, not global data per se — check the boundary map first. |
| Treating `tenant_id` presence as isolation | Presence proves nothing. Audit whether the scope is *mandatory* at every interface and enforced by an independent layer (constraints, RLS) beneath application code. |
| Accepting "exactly once" language | Require the uniqueness key, conditional transition, provider anchor, ambiguity policy, and crash window that make replay harmless — or classify the claim `unverified`. |
| Trusting a lease to fence an in-flight network call | A lease check before send cannot fence the send itself. Look for a one-shot effect permit / fencing token; successors must reconcile, not re-issue. |
| Adding tenant IDs to genuinely shared budgets | Rate limits must be challenged at their *actual* shared scope — a provider-account budget is shared across tenants no matter how the limiter is keyed. The inverse error (tenant-keying a global budget) is also a finding. |
| Scoring fairness from queue topology | FIFO streams and consumer groups distribute work; they do not implement weighted fairness or starvation bounds. Demand the dispatch-time mechanism and its observable bound. |
| Pressure-testing an unstated target | Without a declared capacity envelope (Phase 0), "handles scale" is unfalsifiable. Derive a conservative envelope from configuration, flag the absence, and grade against the derived numbers. |
| Accepting CPU-based autoscaling as saturation coverage | Provider slots, DB pools, limiter budgets, and ambiguity backlogs exhaust while CPU idles. Saturation signals are queue age, budget exhaustion, and admission latency (scan category E). |
| Assuming session state survives pooled connections | Under transaction-mode pooling, session GUCs, advisory locks, and LISTEN/NOTIFY do not behave session-locally. RLS context must be transaction-local and set inside every transaction. |
| Declaring RLS "on" sufficient | Table owners and `BYPASSRLS` roles skip policies unless `FORCE ROW LEVEL SECURITY` is set; integrity-constraint errors can leak cross-tenant existence. Verify the runtime role's attributes. |
| Reporting a generic warning for a distributed race | Every cross-process finding needs a concrete ordered failure sequence (who does what, in what order, and what breaks) — `failure-windows.md` defines the required form. |
| Quoting credentials in findings | file:line + variable name only; redactor scrub per orchestration-guide §7 before handoff. |

## Notes

- **Subagent pattern.** Four parallel discovery subagents + one convergence subagent (disk-write pattern, orchestration guide Sections 2 & 6). Phase 4 uses Plan agents per Section 9. The orchestrator coordinates only.
- **Technology-agnostic.** The scan categories and failure windows are written to the *shapes* of multi-tenant systems (optional scopes, leases, outboxes, pooled connections), not to any specific framework, broker, database vendor, or hosting platform. Adapt grep patterns to the detected stack.
- **Compatibility.** Shared arguments, output routing, autonomous mode, and plan-mode discipline are owned by `skills/_shared/audit-lens-contract.md`; this lens adds no divergent behavior.

---

## Autonomous Mode (--auto)

When `--auto` is set (implies `--output github`; lens contract §4, orchestration guide Section 10):

1. Skip Plan Mode — run Phases 0–3 directly.
2. Skip the user confirmation gate; do not generate Phase 4 remediation plans.
3. Use the engine's `[focus]` argument as scope; if none, audit the full system.
4. Create GitHub Issues for all P0 and P1 findings (immediately), P2 batched; skip P3 unless particularly noteworthy. **Confidence floor:** a `low`-confidence (pattern-only) lead never files as P0/P1 — batch it with the P2s, naming the evidence that would confirm or dismiss it.
5. Scrub every published doc through the redactor (orchestration-guide §7) — no raw credential values in issue bodies or artifacts.
6. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "audit",
  "outcome": "completed",
  "artifacts": {
    "lens": "scale",
    "verdict": "approve with required changes",
    "issues_created": ["..."],
    "findings_by_severity": {"P0": 1, "P1": 2, "P2": 4, "P3": 3},
    "scorecard": {"identity-authorization": 3, "data-isolation": 2, "distributed-coordination": 2, "provider-isolation": 3, "fairness-capacity": 1, "observability": 2, "migration-safety": 3, "testability": 2},
    "unverified_claims": 2,
    "session_dir": "documentation/planning/scale/<session>/"
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `partial` if some issue creates failed, `blocked` if the system has neither an isolation unit nor a scale-out surface (per Phase 0).
