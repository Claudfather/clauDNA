# Extract a Complete, Anonymized System Specification

Copy the prompt below into a coding-agent session opened at the root of the system to be analyzed. The agent may use subagents. Replace the optional variables if needed; otherwise let the stated defaults apply.

---

## Prompt

You are the lead system archaeologist and specification editor for this task.

Your job is to inspect the entire supplied project and produce a single, standalone Markdown specification from which a capable engineering team, working in a fresh session without access to the original project, could recreate the same functional system. The recreated system may use a cleaner or better architecture, but it must preserve the original system's meaningful capabilities, behavior, data semantics, interfaces, boundaries, workflows, and operational requirements.

### Inputs and deliverable

- Project root: `{{PROJECT_ROOT}}` (default: current working directory)
- Final output: `{{OUTPUT_PATH}}` (default: `FULL_SYSTEM_SPEC.md` in the project root)
- Optional scope notes: `{{SCOPE_NOTES}}` (default: none; inspect the full project)
- Scratch workspace: create a temporary or ignored directory outside the final deliverable for inventories, evidence, agent reports, and alias mappings.

Produce exactly one authoritative final specification at the requested output path. Intermediate research may be split across many files, but it is not part of the deliverable.

Treat inspection as read-only. Do not alter application source, configuration, schemas, infrastructure, dependencies, or project data. Do not invoke commands that can mutate databases, queues, cloud resources, deployments, external services, or user accounts. Run tests or probes only when they are local, bounded, and non-mutating. The only authorized writes are scratch research artifacts and the requested final Markdown file.

### Non-negotiable outcome

The final specification must be:

1. **Functionally complete.** It covers every meaningful wing of the system, not merely the largest, newest, best-documented, or easiest-to-understand areas.
2. **Evidence-derived.** Load-bearing claims come from inspected source, configuration, schemas, tests, infrastructure, or executable behavior. Documentation is a lead, not unquestioned truth.
3. **Reconstruction-ready.** It contains enough precise behavior, data semantics, contracts, edge cases, and acceptance criteria to guide an independent implementation.
4. **Architecture-flexible.** It distinguishes required behavior and constraints from replaceable implementation choices. Do not turn accidental code organization into a requirement.
5. **Anonymized.** It contains no PII, secrets, organization or project identity, proprietary names, source paths, code symbols, repository metadata, or other details that reveal the originating project.
6. **Honest.** Uncertain or contradictory behavior is labeled explicitly. Never fill gaps with plausible invention.

Do not optimize for a short document. Optimize for the shortest document that loses no unique, reconstruction-relevant information. Consolidate duplication, not substance.

Anonymization must not become semantic flattening. Preserve meaningful rules, calculations, roles, cardinalities, state transitions, validation, ordering, failure behavior, and externally observable distinctions. Replace identifying nouns and identifiers with precise functional language; do not replace distinct domain concepts with vague labels such as “item,” “record,” or “process.”

---

## Operating rules

### Completion is coverage-based, not length-based

You are not finished because you have written a long document, described the main path, reached a convenient token boundary, or covered “representative” modules. You are finished only when every completion gate in this prompt passes.

Proceed autonomously through all phases. Do not pause after inventory, planning, a research wave, or a draft to ask whether you should continue. Do not return a progress report in place of the deliverable. Ask the user only when missing access or a genuinely consequential scope decision makes further evidence-based progress impossible. Otherwise record reasonable assumptions and continue. If agent concurrency is limited, run successive waves until coverage is complete.

Prohibited shortcuts include:

- Describing only representative examples when a complete inventory is required.
- Stopping after the primary application while omitting workers, scripts, migrations, admin tools, scheduled jobs, infrastructure, or operational paths.
- Treating tests, schemas, configuration, CI/CD, or deployment files as secondary and therefore optional.
- Inferring a whole subsystem from its README or directory name.
- Repeating source structure without explaining behavior and intent.
- Compressing later research phases because earlier phases consumed substantial context.
- Declaring an area “standard,” “conventional,” “straightforward,” or “similar” instead of documenting its actual semantics.
- Silently excluding confusing, obsolete-looking, duplicated, or apparently unused code.

If context becomes tight, save progress, update the coverage ledger, and continue in another research wave. Context pressure is a reason to subdivide work, never a reason to omit it.

Before any context compaction or handoff, write the current phase, completed scopes, open scopes, unresolved contradictions, and exact next actions to the scratch control artifacts. On continuation, read those artifacts and resume from the first incomplete gate rather than restarting or summarizing prematurely.

### Use subagents as bounded investigators

Act as an orchestrator. Delegate bounded evidence-gathering tasks to subagents and keep central responsibility for scope, reconciliation, privacy, and the final specification.

Each subagent assignment must state:

- Its exact functional or cross-cutting scope.
- The inventory entries, directories, entry points, entities, or flows it owns.
- Questions it must answer.
- The required report structure and scratch output path.
- The evidence standard.
- Its completion checklist.
- The instruction to return only a brief status summary after writing the full report to disk.

Do not give several agents the vague task “explore the codebase.” Assign non-overlapping primary ownership, then use separate cross-cutting reviewers to examine seams.

Recursively subdivide an assignment when its agent cannot exhaustively enumerate and explain its scope within a coherent report. As a starting heuristic, split scopes larger than roughly 25 substantive hand-authored files, 8,000 lines of relevant code, 20 entry points, or 20 persisted entities; adjust for complexity. The orchestrator, not the subagent, retains responsibility for proving that the combined child scopes cover the parent scope.

Subagents must cite source paths, symbols, and line ranges in scratch research. They must never copy secret values, credentials, tokens, private keys, personal records, or production payloads. Evidence references are for internal verification only and must not appear in the final specification.

The orchestrator must read every completed subagent report, reconcile it with the inventory, and either accept it, send a focused follow-up, or subdivide the remaining scope. A subagent's “complete” status is not itself evidence that its assignment is complete.

### Maintain resumable control artifacts

Create and continuously update these scratch artifacts:

1. **Repository inventory:** every relevant tracked file or artifact, its type, approximate size, assigned wing, inspection owner, inspection depth, and disposition.
2. **Wing registry:** every functional wing and recursive sub-wing, its purpose, boundaries, owned entry points, owned state, dependencies, and research status.
3. **Coverage ledger:** completion state for files, entry points, flows, entities, interfaces, integrations, runtime processes, and final-spec sections.
4. **Evidence reports:** subagent findings with source references.
5. **Alias ledger:** source-specific term to anonymized semantic alias. This file is private scratch material and must not be included or referenced in the deliverable.
6. **Contradiction and unknowns log:** disagreements among code, tests, schemas, configuration, and documentation, including how each was resolved or why it remains unknown.

Distinguish these inspection depths in the inventory:

- `full`: the hand-authored file was read and its role understood.
- `targeted`: the relevant regions were inspected and the uninspected regions were mechanically shown to be irrelevant to system behavior.
- `generated`: generated content was classified; its generator, contract, and consumption were inspected instead of restating every generated line.
- `vendor`: third-party code was classified; local modifications and integration boundaries were inspected.
- `binary/data`: the artifact's format, producer, consumer, and role were determined without exposing its contents.
- `excluded`: exclusion is justified explicitly and has no hidden runtime, data, build, test, or operational role.

Do not equate “listed” with “inspected.” Report both inventory coverage and inspection coverage.

---

## Phase 1: Establish scope and build the complete inventory

Before deep interpretation:

1. Read all repository-level agent instructions and applicable nested instructions.
2. Inspect repository metadata, manifests, dependency declarations, lockfiles, workspaces, build definitions, startup commands, container files, infrastructure definitions, CI/CD, environment templates, migrations, schemas, seeds, fixtures, test configuration, scripts, documentation indexes, and generated-code configuration.
3. Enumerate the complete tree using repository-aware and filesystem-aware methods. Account for tracked files, meaningful untracked project files, symlinks, submodules, nested packages, and ignored runtime/build inputs when accessible.
4. Identify languages, frameworks, deployable units, runtime processes, databases, caches, queues, object stores, external providers, and developer/operations tooling.
5. Classify every artifact into a functional wing, shared infrastructure, evidence/support, generated/vendor, binary/data, or justified exclusion.
6. Identify every executable entry point: web/API handlers, UI routes, CLIs, workers, consumers, schedulers, jobs, hooks, event handlers, migrations, administrative scripts, notebooks with production logic, and deployment/bootstrap commands.

Derive functional wings from responsibility, call paths, state ownership, and runtime connectivity—not directory structure alone. A wing is a cohesive capability or operational responsibility with a describable boundary. Shared libraries are not automatically wings; determine which behaviors they enable and which consumers depend on them.

Record anything ambiguous for deliberate investigation. Never allow `unknown` to become a silent exclusion.

Distinguish active behavior, configuration- or flag-gated behavior, migration/compatibility behavior, operational tooling, experimental behavior, and demonstrably unreachable/dead code. The first four remain in scope. Experimental behavior must be documented with its status. Dead code may be excluded only after reachability and absence of operational use are established; record the rationale in the coverage attestation rather than turning dead implementation into a reconstruction requirement.

### Phase 1 gate

Do not proceed until:

- Every discovered artifact has a disposition.
- Every deployable or executable unit has an owner in the wing registry.
- Every entry point has been assigned for tracing.
- Generated, vendored, binary, and excluded areas have explicit handling rationale.
- Oversized wings have been recursively subdivided.

---

## Phase 2: Investigate every wing deeply

Assign one primary investigator to each appropriately sized wing or sub-wing. Require the following dossier, even when the answer is “none.” Omitting a heading requires an explicit reason.

### Wing dossier template

1. **Purpose and responsibility**
   - User, business, system, or operational outcome it owns.
   - Responsibilities inside its boundary and responsibilities explicitly outside it.
   - Actors and upstream/downstream consumers.

2. **Entrypoints and triggers**
   - Every route, command, event, schedule, hook, job, or programmatic interface.
   - Preconditions, authentication/authorization category, validation, and dispatch behavior.

3. **Components and services**
   - Each meaningful component's responsibility.
   - Public and internal contracts.
   - Dependencies and permitted direction of dependency.
   - Lifecycle and statefulness.

4. **Behavior and business rules**
   - Decision rules, calculations, filtering, ordering, precedence, defaults, quotas, thresholds, and invariants.
   - State machines and allowed/forbidden transitions.
   - Idempotency, deduplication, reconciliation, and conflict behavior.
   - Edge cases, fallback behavior, and negative paths.

5. **Data ownership and access**
   - State owned, read, written, cached, emitted, or derived.
   - Transaction boundaries and consistency expectations.
   - Retention, deletion, archival, and recovery behavior.

6. **Interfaces and connectivity**
   - Calls to other wings and external systems.
   - Request, response, event, file, and message semantics.
   - Sync/async behavior, versioning, compatibility, and failure handling.

7. **Reliability and errors**
   - Error taxonomy and propagation.
   - Retries, backoff, timeouts, circuit breaking, compensation, dead-letter behavior, and partial-failure recovery.
   - What can fail silently or report false success.

8. **Security and trust**
   - Trust boundary crossings.
   - Identity, authentication, authorization, tenancy, permissions, secret categories, input validation, and sensitive-data handling.
   - Describe categories and controls without recording real identities or values.

9. **Concurrency and performance**
   - Parallelism, scheduling, locks, races, ordering, rate limits, batching, pagination, resource bounds, caching, and scale assumptions.

10. **Configuration and runtime**
    - Configuration categories, feature flags, environment assumptions, startup/shutdown, health behavior, and dependency readiness.

11. **Observability and operations**
    - Logs, metrics, traces, audit records, health checks, alerts, dashboards, runbooks, manual interventions, and diagnostic gaps.

12. **Verification**
    - Tests and fixtures that prove behavior.
    - Untested behavior and observable acceptance criteria.

13. **Unknowns and contradictions**
    - Anything not provable from the available project.
    - Conflicting sources and the investigator's evidence-based interpretation.

14. **Reconstruction requirements**
    - Behavior and constraints a new implementation must preserve.
    - Replaceable design choices.
    - Safe opportunities to improve the design without changing functional intent.

Before completing a dossier, the investigator must reconcile it against every inventory item assigned to the wing and confirm that every owned entry point, entity, interface, and flow appears in the report.

---

## Phase 3: Run cross-cutting investigations

Wing dossiers are necessary but insufficient because important behavior lives at seams. Run dedicated cross-cutting investigations in parallel where possible.

### A. End-to-end execution flows

Identify and trace every materially distinct user, data, administrative, and operational flow. At minimum include all critical paths and every flow that crosses a wing or system boundary.

For each flow record:

- Trigger and actor.
- Preconditions and authorization.
- Ordered steps and branches.
- Validation and transformations.
- State read and mutated at each step.
- Transactions and consistency boundaries.
- Internal and external calls.
- Events/messages emitted or consumed.
- Success postconditions.
- Failure, retry, rollback, compensation, and recovery behavior.
- Idempotency and duplicate-delivery behavior.
- Observability and relevant tests.

Do not collapse distinct create/update/delete, sync/async, interactive/background, success/failure, or privileged/unprivileged branches when their behavior differs.

### B. Complete logical data model and lineage

Catalog every persisted or contractually significant entity, aggregate, event, document, cache record, file/blob, configuration record, and externally visible schema.

For each, determine:

- Semantic purpose and source of truth.
- Grain: what one record represents.
- Fields and their meanings, logical types, requiredness, defaults, valid ranges/enums, validation, and sensitivity category.
- Primary, natural, foreign, external, idempotency, and partition keys.
- Relationships, cardinality, optionality, ownership, and cascade behavior.
- Uniqueness, checks, indexes, and where each constraint is enforced.
- Creation, mutation, state transitions, soft/hard deletion, retention, archival, and restore lifecycle.
- Derived/computed values and recalculation rules.
- Readers, writers, and permission boundaries.
- Transactional and eventual-consistency expectations.
- Serialization, versioning, and backward-compatibility rules.
- Migration, bootstrap, seed, import/export, and backfill behavior.

Reconcile models against migrations, raw queries, schemas, API/event contracts, tests, and fixtures. Surface drift rather than choosing one source silently. Trace source-to-destination lineage for derived data. Include caches and denormalized/search representations, not only the primary database.

The final specification may state that the system handles categories of personal or sensitive data when functionally relevant, but it must never contain actual personal data or copied production examples.

### C. Services and rule catalog

Build a catalog of domain services, application services, workers, jobs, policy/validation modules, and meaningful utilities. Map each rule to its inputs, outputs, callers, state effects, failure semantics, and tests. Identify duplicated or inconsistent rules across layers.

### D. Interface and connectivity matrix

Catalog every inbound, outbound, and internal connection. For each connection record:

- Semantic source and destination.
- Purpose and direction.
- Protocol/transport category.
- Synchronous or asynchronous behavior.
- Contract/schema and versioning.
- Authentication and authorization category.
- Trust boundary and data sensitivity.
- Timeout, retry, backoff, circuit, rate-limit, and idempotency behavior.
- Ordering and delivery guarantees.
- Failure, fallback, reconciliation, and operator recovery.
- Observability and ownership.

Include databases, caches, queues, object stores, identity providers, third-party APIs, webhooks, file exchange, telemetry, CI/CD, deployment control planes, and local inter-process boundaries where present.

### E. Runtime, deployment, and operations

Reconstruct build and release flow, deployable topology, environments, startup/shutdown, migrations, dependency readiness, scaling, scheduling, networking, storage, secret categories, feature rollout, rollback, backup/restore, disaster recovery, health checks, monitoring, alerting, and routine/manual operations.

### F. Security and privacy boundary review

Trace identity and authorization decisions end to end. Document trust zones, tenant boundaries, privilege levels, sensitive-data categories, validation/sanitization, encryption expectations, auditability, retention/deletion, and failure behavior. Do not expose exploit instructions, real credentials, real identities, or sensitive payloads.

### G. Test and behavioral-contract review

Map tests to capabilities, flows, entities, rules, interfaces, and failure modes. Extract behavioral contracts from assertions and fixtures while checking them against implementation. Identify behavior that is load-bearing but untested, and express it as acceptance criteria in the final spec.

### H. User interface and interaction review (when applicable)

Catalog every user-facing surface, route/view, navigation path, role-dependent state, action, form, validation rule, and interaction. For each surface document information shown, available operations, client/server state ownership, loading/empty/success/error/partial states, optimistic behavior, refresh/reconciliation, real-time updates, accessibility semantics, keyboard behavior, responsiveness, localization/timezone handling, and relevant analytics. Trace each user action through services and state changes. Visual styling details are replaceable unless they carry functional, accessibility, or brand-independent information-hierarchy requirements.

### I. Specialized domain surfaces (when applicable)

Detect and investigate specialized behavior rather than forcing it into generic headings. Examples include:

- Analytics and reporting: exact metric semantics, grain, filters, joins, attribution, time windows, timezone behavior, freshness, late data, and correction rules.
- Data pipelines: source-to-output lineage, scheduling, incremental behavior, deduplication, backfills, quality gates, and replay/recovery.
- AI/ML, search, ranking, or recommendations: inputs, prompt/feature construction, model/provider contract, nondeterminism, thresholds, guardrails, evaluation, feedback, fallback, and reproducibility.
- Monetary or entitlement behavior: units/currency, precision, rounding, authorization, ledger/idempotency semantics, reconciliation, refunds/reversals, and audit requirements.
- Real-time or collaborative behavior: connection lifecycle, presence, ordering, conflict resolution, reconnection, fanout, and consistency.
- Offline or synchronization behavior: local state, merge policy, tombstones, retry, duplicate handling, and eventual convergence.
- Multi-tenant behavior: tenant resolution, isolation, tenancy-scoped keys, authorization, quotas, administration, migration, and observability.
- Extension/plugin systems: discovery, registration, capability boundaries, lifecycle, compatibility, failure isolation, and trust.

This list is illustrative, not exhaustive. Add a dedicated investigation for any system-defining surface that the standard lanes do not fully explain.

---

## Phase 4: Reconcile the system as a whole

The orchestrator must now read the scratch reports and resolve the seams.

1. Compare every wing's claimed inputs, outputs, dependencies, and state with the corresponding claims from connected wings.
2. Reconcile code, schema, migrations, tests, configuration, infrastructure, and documentation.
3. Detect orphan entry points, entities without readers/writers, interfaces without both sides, jobs without triggers, configuration without consumers, and flows that terminate without a defined outcome.
4. Verify load-bearing claims against at least two independent evidence locations when possible. If only one source exists, record the lower confidence internally.
5. Re-open source for contradictions and surprising claims. Run focused tests or read-only probes where safe and useful.
6. Convert unresolved ambiguity into a clearly scoped known unknown with implementation consequences; never smooth it over.
7. Update all coverage ledgers before drafting the final specification.

---

## Phase 5: Write the standalone specification

Write the final specification as a clean, original system design—not as a repository tour, reverse-engineering report, audit, or commentary about existing code.

Use declarative language such as “The system must…” and “The service returns…”. Do not say “the repository,” “the codebase,” “the existing project,” “the original implementation,” or “the source files.” Do not include evidence citations, filenames, paths, line numbers, class/function names, commit history, or research-process narration.

Use the neutral name **System** unless a more descriptive, non-identifying semantic name improves clarity. Give wings, entities, services, and integrations consistent descriptive aliases based on function. Maintain the same alias everywhere.

### Required final structure

1. **Specification contract**
   - Purpose, intended audience, scope, normative terms, semantic glossary, and how to interpret unknowns and replaceable choices.

2. **System intent and outcomes**
   - Problem addressed, actors, desired outcomes, core promise, non-goals, and system-wide invariants.

3. **Capability map**
   - Complete hierarchy of capabilities and sub-capabilities, with actors and observable outcomes.

4. **Architecture and boundaries**
   - Logical architecture, responsibility boundaries, dependency rules, trust zones, state ownership, and a technology-neutral context/component diagram when useful.

5. **Functional-wing specifications**
   - One full subsection per wing and sub-wing, derived from the wing dossier. Preserve unique detail; do not replace multiple wings with a generic pattern unless their behavior is truly identical.

6. **End-to-end workflows**
   - Complete critical and cross-boundary flows, including alternate and failure branches.

7. **Data architecture and logical data model**
   - Entity catalog, field semantics, relationships, constraints, lifecycle, ownership, lineage, consistency, migrations, retention, and sensitive-data classifications. Include diagrams or tables where they improve precision.

8. **Services and business-rule catalog**
   - Responsibilities, inputs/outputs, rules, invariants, state effects, errors, and consumers.

9. **Interfaces and contracts**
   - User-facing, programmatic, message/event, file, and internal contracts; schemas; validation; compatibility; pagination; errors; and versioning.

10. **Connectivity and integration requirements**
    - Complete anonymized connection matrix and integration behavior.

11. **Identity, security, privacy, and trust**
    - Authn/authz model, permissions, trust boundaries, validation, sensitive-data handling, audit, retention/deletion, and required controls.

12. **Configuration and feature control**
    - Configuration categories, precedence, defaults, validation, secret categories, flags, dynamic/static behavior, and failure on invalid configuration.

13. **Runtime and deployment model**
    - Logical deployables, processes, dependencies, startup/shutdown, topology, environments, releases, migrations, scaling, backup/restore, and rollback requirements.

14. **Reliability and failure semantics**
    - Error taxonomy, timeouts, retries, idempotency, consistency, partial failure, compensation, recovery objectives, and degraded modes.

15. **Observability and operations**
    - Logs, metrics, traces, audit events, health, alerts, dashboards, runbooks, operator actions, and support diagnostics.

16. **Performance, capacity, and concurrency**
    - Workload shape, latency/throughput expectations when inferable, resource bounds, caching, batching, pagination, rate limits, ordering, races, locks, and scaling assumptions.

17. **Testing and acceptance strategy**
    - Test layers, fixtures, contract/integration/end-to-end coverage, failure injection, migration testing, security checks, and capability-level acceptance criteria.

18. **Reconstruction blueprint**
    - Recommended implementation sequence, dependency order, minimum viable vertical slices, data migration/bootstrap needs, and validation milestones.

19. **Required constraints vs. replaceable choices**
    - Separate externally observable or data-integrity requirements from incidental architecture, framework, naming, packaging, and hosting choices.

20. **Improvement opportunities**
    - Safe ways a new implementation could improve cohesion, boundaries, reliability, security, operability, performance, or testability without changing functional intent. Tie each opportunity to a preserved requirement.

21. **Known unknowns and decisions required**
    - Precise unresolved questions, why they could not be answered, affected requirements, risk, and the decision or experiment needed to resolve them.

22. **Coverage attestation**
    - Anonymized counts and percentages for artifact classification, meaningful-file inspection, wings, entry points, entities, interfaces, integrations, runtime processes, and critical flows.
    - Justified exclusion categories.
    - Confirmation that all completion gates passed, or an explicit declaration that the specification remains incomplete.

For each major requirement, make clear whether it is:

- **Required behavior:** externally observable functionality or workflow semantics.
- **Required constraint:** necessary for compatibility, integrity, security, reliability, or operations.
- **Replaceable design choice:** one valid implementation pattern that may be changed.
- **Improvement opportunity:** a recommended change that preserves intent.

Avoid framework and vendor names unless compatibility truly requires them. Prefer capability descriptions such as “relational transactional store,” “asynchronous message transport,” or “external identity provider.” When a particular external contract is mandatory, specify the required protocol and semantics under an anonymized functional alias.

---

## Phase 6: Adversarial review before completion

Do not let the drafting agents grade their own completeness. Dispatch fresh reviewers with access to the inventory and research artifacts.

### Coverage reviewer

Attempt to disprove that the spec is complete. Look specifically for:

- Unassigned or shallowly inspected files.
- Missing small wings, scripts, jobs, hooks, migrations, tools, admin paths, or fallback paths.
- Entry points absent from workflows.
- Entities absent from the data model.
- Readers without writers, writers without readers, and undocumented state transitions.
- One-sided interfaces and integrations.
- Configuration, flags, permissions, error paths, or tests missing from the spec.
- Generic prose that could apply to any system but does not capture this system's actual semantics.

Every gap must be investigated and either added to the spec or explicitly resolved in the coverage ledger.

### Reconstruction reviewer

Assume you must implement the system with no project access and only the draft specification. Identify every point where you would have to guess about behavior, data, boundaries, contracts, failure handling, operations, or acceptance. Require the orchestrator to close answerable gaps. Remaining unanswerable gaps belong in Known Unknowns with concrete consequences.

### Architecture-flexibility reviewer

Find places where the draft overfits filenames, frameworks, libraries, directory structure, hosting, or accidental coupling. Preserve the underlying behavior or constraint while rewriting replaceable choices as such. Also find underfit areas where useful detail was removed in the name of generality.

### Privacy and identity reviewer

Review the final deliverable semantically and mechanically. Remove or replace:

- Names, emails, usernames, handles, author metadata, and personal filesystem paths.
- Organization, repository, product, customer, tenant, team, and proprietary feature names.
- Internal domains, hostnames, URLs, remotes, account/project IDs, ticket IDs, commit hashes, dataset/bucket/schema names, and environment-specific identifiers.
- Secrets, tokens, keys, credential material, connection strings, and real configuration values.
- Exact source paths, filenames, module/package names, class/function symbols, and distinctive internal terminology.
- Production records, payloads, examples, logs, or fixtures containing personal or identifying content.
- Phrases revealing that the document was extracted from a particular pre-existing project.

Preserve functional meaning with stable semantic aliases. Do not erase the fact that the system processes a category of sensitive information when that fact is relevant to requirements; describe the category, lifecycle, and controls without including real values.

Build a prohibited-term list from repository metadata, manifests, remotes, documentation headings, namespaces, distinctive domain vocabulary, configuration, and the private alias ledger. Scan the final Markdown case-insensitively. Treat a clean string scan as necessary but not sufficient; also perform semantic review for indirect identification.

Review prohibited terms before applying replacements. Do not corrupt generic technical language merely because a short project identifier happens to be a substring of a common word. Re-scan the rendered Markdown after all replacements.

### Consistency reviewer

Check that actors, names, aliases, entities, cardinalities, state transitions, flows, error semantics, and cross-references agree throughout the document. Resolve contradictions rather than leaving multiple incompatible descriptions.

---

## Final completion gates

You may report completion only when all applicable gates pass:

- [ ] 100% of discovered artifacts have a recorded disposition.
- [ ] 100% of meaningful hand-authored files have `full` or justified `targeted` inspection.
- [ ] 100% of generated, vendor, binary/data, and excluded artifacts have justified handling.
- [ ] Every wing and recursively defined sub-wing has a complete dossier and final-spec section.
- [ ] Every entry point is documented and participates in at least one execution trace or is explicitly classified as non-runtime.
- [ ] Every critical and cross-boundary flow is traced through success, alternate, and failure behavior.
- [ ] Every persisted or contractually significant entity has semantics, keys, relationships, constraints, lifecycle, readers, writers, and ownership documented.
- [ ] Every interface and integration has both sides, contract semantics, trust/auth category, and failure behavior documented.
- [ ] Every runtime process, job, scheduler, worker, hook, migration path, and administrative operation is covered.
- [ ] Configuration, deployment, security, reliability, observability, performance, concurrency, and testing have been reconciled across wings.
- [ ] Documentation claims have been checked against executable evidence.
- [ ] Contradictions are resolved or recorded as consequential known unknowns.
- [ ] The coverage reviewer found no unresolved omissions.
- [ ] The reconstruction reviewer found no answerable gaps.
- [ ] The architecture-flexibility reviewer found neither implementation overfit nor semantic underfit.
- [ ] The consistency reviewer found no unresolved internal contradictions.
- [ ] The privacy reviewer and prohibited-reference scan found no PII, secrets, identifying references, source paths, or project-specific identifiers in the final Markdown.
- [ ] The final file exists at the requested path and contains all required sections.

If a gate cannot pass because the project is incomplete, inaccessible, non-executable, or internally contradictory, do not pretend otherwise. Finish the research that is possible, mark the deliverable **Incomplete Specification**, and state the exact blocked gates and consequences in Known Unknowns and Coverage Attestation.

### Final response

After the file and all reviews are complete, respond briefly with:

- The final output path.
- Whether every completion gate passed.
- Anonymized coverage totals.
- The count of unresolved known unknowns.
- No project-identifying details and no substitute summary of the specification.
