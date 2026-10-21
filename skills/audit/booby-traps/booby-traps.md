Invoked by /claudna:audit in booby-traps mode — examine safeguards that silently stop protecting their intended boundary, or shift their cost onto an unrelated person.

Follow `../../_shared/audit-lens-contract.md` for arguments, concern vocabulary, output routing and autonomous results. Read `trap-classes.md` before scanning. This is a read-only diagnostic: recommendations do not authorize changing gates, credentials, owners, production state or retention.

**Focus:** a subsystem, gate, exemption, output or operational symptom; default to the current repository. A focused symptom uses the spot check below. An explicit audit uses the sweep. Both support `--auto` without questions or plan-mode entry. In interactive sweeps, follow the shared contract's plan-mode discipline; exit deliberation before writing finding docs or cleaning owned scratch. Where mode controls are unavailable, preserve that read/write boundary without claiming a mode switch.

## Routing

- General duplication, naming and code quality → `/claudna:audit tech-debt`.
- Vulnerabilities, exposed credentials and authorization flaws → `/claudna:audit security`. Person-dependent production access belongs here for continuity risk; exposure belongs to security.
- An active outage → `/claudna:investigate-app`.
- An ordinary diff → `/claudna:review-work`; use this lens's spot check only when a safeguard symptom appears.

## Spot check during another task

1. Name the intended protection and trace its actual readers, enforcement point and notification recipient. A CI-only gate can be valid: establish what it gates before calling it decorative.
2. Measure the claim behind the exception or failure. Check the exit condition, relevant history, workflow event/mode and current state within the authorized scope. Comments, tickets and previous reports are hypotheses, not measurements.
3. Recommend the smallest fix that restores the intended protection. Do not bump a date, suppress a check or remove half of paired config merely to make CI green. If a temporary exception is necessary, state its measured reason, owner and compensating control for the caller's decision.
4. Return the evidence, affected boundary, who discovers failure, proposed verification and the fix's deployment effects to the caller. Resume the original task; unrelated candidates use its existing follow-up/publish route only when authorized. Do not start a second full audit or create scratch for this short check.

Finish through the finalization and result rules in sweep Step 5, including under `--auto`.

## Procedure: sweep

### 1. Bound the surface

State the repository, revision and focus. Inspect the relevant gates, exemptions, owner/routing maps, writers/readers and deploy workflows. Use existing authorized operational history where available; do not expand into other repositories or accounts without authorization. Missing history limits confidence, not permission.

### 2. Trace the five trap classes

Work through `trap-classes.md` sequentially. Keep a compact inventory in context; create `<scratch>` per `../../_shared/orchestration-guide.md` §1 only if file output is needed. There is no mandatory subagent fan-out or per-class directory.

For each candidate, establish:

- What protection is promised, and what actually changes when it lapses, its owner leaves, or the output is retired?
- Who learns about the failure, through which path, and what happens when that path itself fails?
- Which source paths and observations support the claim? Which compensating controls or counterexamples refute it?

Existing checks, static tracing or a cheap isolated reproduction may suffice. Never trigger a production failure to test a hypothesis. Missing matching test files, dates, manual controls or broad deploys are not findings by themselves.

### 3. Assess and recommend

Label confidence **Confirmed**, **Likely**, or **Hypothesis** and state the observed evidence and its limits. For unmeasured operational claims, name the exact check that would settle them. Rank impact using CRITICAL/HIGH/MEDIUM/LOW and the shared concern vocabulary; do not mint a `booby-traps` concern area.

Each finding names the broken protection, file:line evidence, affected party, lapse behavior, smallest remediation and proportionate verification. Check the remediation's own failure behavior and deployment path: a monitor fix that never deploys restores nothing. Preserve working controls; an enrollment defect does not justify deleting the coverage check.

### 4. Deliver through the existing output route

For `session` (default), present a compact scope/count summary, severity-ordered findings and cleared candidates. A clean scope is a valid result; do not manufacture findings.

**Automatic GitHub filing (`--auto` with explicit `--output github`):** select only **Confirmed** or **Likely** findings for issue docs. Retain every **Hypothesis** in the final findings/result at its assessed severity, with the missing evidence and exact confirming check. Confidence limits automatic filing, not impact severity. This gate applies only to this lens's automatic GitHub output; session output retains all findings. With no eligible findings, return `completed` with no issues only after Step 5 succeeds.

For explicit `--output github`, prepare the selected finding-cluster docs in `<scratch>` with the output-guide's §4.1 skeleton and route through `/claudna:publish` for validation, deduplication, labels and redaction. Follow `../../_shared/output-guide.md`; never call `gh` directly from this lens. Audit selection alone does not authorize filing, remediation or another logging stack.

### 5. Finalize before returning

On completion, no findings, all-duplicate results, blocked publication or handled cancellation, run the owning workflow's finalizer in `../../_shared/orchestration-guide.md` §1.1 **before** the terminal result. Present or publish sanitized findings first; if publication fails, preserve them in the session result and report the requested target as blocked. Delete only this run's owned scratch after all its writers have stopped. A caller-owned scratch root remains the caller's responsibility and is reported as such.

Under `--auto`, emit one final structured result per orchestration-guide §10.C: `skill: audit`, `artifacts.lens: booby-traps`, the findings/output references and `artifacts.cleanup` (`not-needed`, `complete`, `caller-owned` or `blocked`). Publication or cleanup failure prevents a `completed` outcome; include the failure and exact remaining owned path in `errors`. No separate job directory, transcript copy, cleanup command for the user or retention heuristic is needed.
