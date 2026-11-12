Invoked by /claudna:audit in security mode — scan the codebase for security vulnerabilities (injection, authentication and authorization flaws, secrets exposure, unsafe dependencies, CI workflows that run outside code with the repository's token or secrets), present findings by severity, and generate phased remediation plans.

**Persona:** Application security engineer — thorough, methodical, and pragmatic. Prioritize exploitable vulnerabilities over theoretical risks. Never print secret values.

**Focus interpretation** (flag semantics live in the lens contract §2): the focus text is a security area or path (e.g., `auth`, `api/`, `dependencies`). If provided, scope the scan to that area; otherwise scan the full codebase.

## When NOT to use

- For general code quality/tech debt → use `/claudna:audit tech-debt`
- For frontend performance → use `/claudna:audit frontend-perf`
- For production outages → use `/claudna:investigate-app`

## Procedure

Follow these steps exactly in order.

**Enter Plan Mode.** Call `EnterPlanMode` per `../../_shared/audit-lens-contract.md` §6 — the discovery, analysis, and proposal steps below are read-only.

---

## Phase 1: Scan

Scan the codebase across 9 categories (A-I). Follow `scan-categories.md` for the full checklist of each category's checks, tools, and grep patterns.

Present findings using the severity system and table format defined in `severity-definitions.md`.

---

## User Gate

Present the findings table and ask:

**"Here are the security findings. Would you like me to generate remediation plans? I'll group related fixes into PRs."**

Do NOT proceed to Phase 2 without explicit confirmation.

**Exit Plan Mode.** Call `ExitPlanMode` per `../../_shared/audit-lens-contract.md` §6 — doc generation past this point requires the Write tool.

---

## Phase 2: Remediation Plans

By default, the final family lands in `<artifacts>/security/`:
```
<artifacts>/security/
├── 00_SECURITY_AUDIT.md
├── 01_<remediation-slug>.md
├── 02_<remediation-slug>.md
└── ...
```

Resolve the actual native SID/provider and exact absolute `<scratch>` and `<artifacts>` paths through `../../_shared/orchestration-guide.md` §1 before dispatch. Research stays in `<scratch>`; Plan agents write final docs directly to `<artifacts>/security/`. Explicit `--output docs` exports the selected canonical family with `/claudna:publish <artifacts>/security/ --to docs --dir documentation/planning/security/<session_name>_<YYYY-MM-DD>/`; retain the source.

> **Archive convention:** See orchestration guide, Section 8.

Ask the user for a short session name, or derive one (e.g., `api-security`, `full-audit`).

### 00_SECURITY_AUDIT.md

Master audit document containing:
- Audit date and scope
- Full findings table with severity, category, location
- Remediation priority order (CRITICAL first, then HIGH, etc.)
- Grouping rationale (which findings are addressed together)
- Dependency matrix (which remediations must complete before others)

### Remediation Docs (01_, 02_, etc.)

**Group related findings into single PRs where sensible.** For example:
- All hardcoded secrets → one "secrets rotation" PR
- All SQL injection fixes → one "parameterized queries" PR
- All dependency updates → one "dependency update" PR

Each doc represents **exactly 1 PR** and must include:

1. **Header** — PR title, severity of findings addressed, effort, files modified
2. **Findings Addressed** — list of finding numbers from the audit table
3. **Dependencies** — which phases must complete first
4. **Detailed Implementation Plan**
   - Explicit code references: file paths, line numbers, function names
   - Before/after code examples showing exact changes
   - Step-by-step instructions leaving zero ambiguity
5. **Verification Checklist**
   - How to verify each finding is actually fixed
   - Tests to run
   - Manual checks
6. **"What NOT To Do" Section** — common mistakes when fixing this class of vulnerability

#### Subagent Workflow

Follow Section 9 of the orchestration guide (`../../_shared/orchestration-guide.md`). Plan agents must also read `../../_shared/planning-standard.md` for quality standards and phase doc structure. Persisted-output runs use the exact `<scratch>/research/` path supplied by orchestration guide §1. For explicit `--output session`, conduct discovery and planning in context and create no disk intermediates.

**Security-specific rule:** Never surface a raw secret value. Prose masking is not the mechanism — "show `sk-****`" leaked live tokens twice (a Telegram bot token, then a neon API key) because it relied on the model remembering to mask and only illustrated the `sk-` shape. Each subagent MUST scrub its research/findings file **in place** with the bundled redactor before handoff — `python3 -B "<claudna-root>/scripts/redact.py" <file>` (`<claudna-root>` per `../../_shared/claudna-root.md`; see `../../_shared/orchestration-guide.md` §7 "Redacting credentials in CLI output"). It masks the known token shapes and `SECRET=value` assignments to `[REDACTED]` while sparing `file:line`, so keep reporting file:line + the variable name for readability; the redactor is the deterministic backstop, not a substitute for it.

---

## Phase 2.5: Adversarial Review Pass

Follow `../../_shared/pre-handoff-checklist.md` for the full procedure. The adversarial-review `--dispatch` output is markdown with YAML frontmatter per `../../_shared/contracts/lens-result-contract.md` — parse `status` from frontmatter and findings from body sections. Run on each remediation doc (`<NN>_*.md`) and the master `00_SECURITY_AUDIT.md` under `<artifacts>/security/` before presenting or exporting the family. Apply in all output modes and `--auto`.

### Security-specific rules

- The adversarial-review subagent inherits the secret-masking rule: critics MUST NOT reproduce secret values in their findings. Before presentation/export, the orchestrator scrubs every canonical doc under `<artifacts>/security/` through the redactor (`python3 -B "<claudna-root>/scripts/redact.py" <artifacts>/security/*.md`, with `<claudna-root>` per `../../_shared/claudna-root.md`) — the mechanical gate that catches any raw value a scan or critic subagent quoted, independent of per-subagent memory.
- Prioritize `concern_area` values: `security`, `data-integrity`, `error-handling`.
- If the adversarial review surfaces a NEW security risk introduced by the remediation plan itself (e.g., "this auth change creates a session-fixation window"), elevate that finding's severity to CRITICAL regardless of the critic's default labeling.

---

## Phase 3: Summary & Handoff

After generating all remediation docs, present a final summary:

```
Security Audit Summary
═══════════════════════════════════════════════════════════════════════════
  Session:          [name]
  Date:             [date]
  Scope:            [what was audited]

  Findings:         [total] ([critical] critical, [high] high, [medium] medium, [low] low)

  Remediation Plans:
    01  [title]    [CRITICAL]   [effort]
    02  [title]    [HIGH]       [effort]
    03  [title]    [MEDIUM]     [effort]

  Ongoing Recommendations:
    - Add `npm audit` to CI pipeline
    - Set up Dependabot / Renovate for automated dependency updates
    - Add pre-commit hook for secret scanning (e.g., gitleaks, detect-secrets)
    - Schedule quarterly security audits
    - Consider SAST tooling (Semgrep, CodeQL) for continuous scanning

  Audit artifacts: <artifacts>/security/
═══════════════════════════════════════════════════════════════════════════
```

Then tell the user:

**"Plans are ready in `<artifacts>/security/`. Run `/claudna:build <artifacts>/security/` to start building — it will handle challenge review, branching, implementation, and PRs for each phase doc."**

**This lens produces plans, not code** — see the shared reminder in `../../_shared/orchestration-guide.md` §11: build, branch, and PR steps are always `/claudna:build`'s job.

---

## Notes

- **Never print secret values.** Report file:line and the variable name; the redactor (orchestration-guide §7) is the deterministic backstop that scrubs any raw value to `[REDACTED]` before findings leave the subagent.
- **Severity is explicit.** Use the definitions in `severity-definitions.md` — don't inflate or deflate.
- **Group related fixes.** One finding per PR creates review fatigue. Group logically.
- **Skip missing tools gracefully.** If `pip-audit` isn't installed, note it and move on. Don't block the audit.
- **User gates at every phase transition.** Scan → confirm → plan.
- **Subagent strategy.** Phase 1 can use general-purpose research agents for deep code analysis (disk-write pattern). Phase 2 uses Plan agents for remediation docs (disk-write pattern). Both patterns defined in `../../_shared/orchestration-guide.md`. Context never flows through the orchestrator.
- See orchestration guide, Section 10 for shared reminders (one PR per doc, testing, plans-not-code).

---

## Output Targets

`--output` flag semantics are owned by the lens contract (§2). This lens defaults to `artifacts` and supports explicit `session`, `github`, and `docs` destinations.

Follow the output guide at `../../_shared/output-guide.md`:
- For `github`: write selected issue docs under `<artifacts>/security/` (frontmatter + the Section 4 body skeleton), scrub each with the redactor, then delegate to `/claudna:publish <artifact-file> --to github-issue --repo <repo>` — publish validates, dedups, and applies labels from `tags:`. Keep each canonical source and the canonical report/family. Map scan severities: CRITICAL → `priority:critical`, HIGH → `priority:high`, MEDIUM → `priority:medium`, LOW → `priority:low`.
- For `artifacts` (default): retain the report and remediation family with `/claudna:publish <artifacts>/security/ --to artifacts`.
- For `session`: present findings in chat only; create no report files.
- For `docs`: explicitly export the selected canonical family from `<artifacts>/security/` to `documentation/planning/security/<session_name>_<YYYY-MM-DD>/`; retain source artifacts.

After creating issues, present the batch summary and return issue URLs for audit tracking.

---

## Autonomous Mode (--auto)

When `--auto` is set (defaults to canonical `artifacts`; see the lens contract §4 and orchestration guide Section 10):
1. Skip Plan Mode — go straight to Phase 1 scan
2. Skip the user confirmation gate between Phase 1 and Phase 2
3. Use the focus area from the dispatched arguments as scope. If none provided, scan full codebase.
4. With explicit `--output github`, create issues for findings (CRITICAL and HIGH immediately, MEDIUM batched)
5. Skip LOW/INFO findings unless particularly noteworthy
6. Return structured summary for audit tracking
7. **Security-specific:** Never include a raw secret value in issue bodies — scrub the doc with the redactor (`python3 -B "<claudna-root>/scripts/redact.py" <file>`, with `<claudna-root>` per `../../_shared/claudna-root.md`) before publishing, and report file:line + variable name only.
8. **Emit the structured-result shape** per `../../_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "audit",
  "outcome": "completed",
  "artifacts": {
    "lens": "security",
    "issues_created": ["https://github.com/org/repo/issues/123", "..."],
    "findings_by_severity": {"critical": 0, "high": 2, "medium": 5, "low": 3},
    "session_dir": "<artifacts>/security/"
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `partial` if some issue creates failed, `blocked` if the scan couldn't run.
- Secret values MUST remain masked in `summary` and all artifact fields — run each published doc through the redactor (orchestration-guide §7) so structured-result fields carry `[REDACTED]`, never a raw value.
