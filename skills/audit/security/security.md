Invoked by /claudna:audit in security mode — scan the codebase for security vulnerabilities (injection, authentication and authorization flaws, secrets exposure, unsafe dependencies), present findings by severity, and generate phased remediation plans.

**Persona:** Application security engineer — thorough, methodical, and pragmatic. Prioritize exploitable vulnerabilities over theoretical risks. Never print secret values.

**Focus interpretation** (flag semantics live in the lens contract §2): the focus text is a security area or path (e.g., `auth`, `api/`, `dependencies`). If provided, scope the scan to that area; otherwise scan the full codebase.

## When NOT to use

- For general code quality/tech debt → use `/claudna:audit tech-debt`
- For frontend performance → use `/claudna:audit frontend-perf`
- For production outages → use `/claudna:investigate-app`

## Procedure

Follow these steps exactly in order.

**Enter Plan Mode.** Call `EnterPlanMode` per `skills/_shared/audit-lens-contract.md` §6 — the discovery, analysis, and proposal steps below are read-only.

---

## Phase 1: Scan

Scan the codebase across 8 categories (A-H). Follow `scan-categories.md` for the full checklist of each category's checks, tools, and grep patterns.

Present findings using the severity system and table format defined in `severity-definitions.md`.

---

## User Gate

Present the findings table and ask:

**"Here are the security findings. Would you like me to generate remediation plans? I'll group related fixes into PRs."**

Do NOT proceed to Phase 2 without explicit confirmation.

**Exit Plan Mode.** Call `ExitPlanMode` per `skills/_shared/audit-lens-contract.md` §6 — doc generation past this point requires the Write tool.

---

## Phase 2: Remediation Plans

**Output lands in:**
```
documentation/planning/security/<session_name>_<YYYY-MM-DD>/
├── 00_SECURITY_AUDIT.md
├── 01_<remediation-slug>.md
├── 02_<remediation-slug>.md
└── ...
```

Plan agents write the family to the session's scratch docs directory (`/tmp/security-audit-<YYYY-MM-DD_HHMMSS>/docs/`); the orchestrator publishes it with `/claudna:publish <scratch-docs-dir> --to docs --dir documentation/planning/security/<session_name>_<YYYY-MM-DD>/` (family mode; orchestration guide, Section 3).

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

Follow Section 9 of the orchestration guide (`skills/_shared/orchestration-guide.md`). Plan agents must also read `skills/_shared/planning-standard.md` for quality standards and phase doc structure. Scratch directory: `/tmp/security-audit-<YYYY-MM-DD_HHMMSS>/research/`.

**Security-specific rule:** Never surface a raw secret value. Prose masking is not the mechanism — "show `sk-****`" leaked live tokens twice (a Telegram bot token, then a neon API key) because it relied on the model remembering to mask and only illustrated the `sk-` shape. Each subagent MUST scrub its research/findings file **in place** with the bundled redactor before handoff — `python3 scripts/redact.py <file>` (resolve the path per `skills/_shared/orchestration-guide.md` §7 "Redacting credentials in CLI output"). It masks the known token shapes and `SECRET=value` assignments to `[REDACTED]` while sparing `file:line`, so keep reporting file:line + the variable name for readability; the redactor is the deterministic backstop, not a substitute for it.

---

## Phase 2.5: Adversarial Review Pass

Follow `skills/_shared/pre-handoff-checklist.md` for the full procedure. The adversarial-review `--dispatch` output is markdown with YAML frontmatter per `skills/_shared/contracts/lens-result-contract.md` — parse `status` from frontmatter and findings from body sections. Run on each remediation doc (`<NN>_*.md`) and the master `00_SECURITY_AUDIT.md` in the session's scratch docs directory, before the family is published to `documentation/planning/security/<session>/`. Apply in all output modes and `--auto`.

### Security-specific rules

- The adversarial-review subagent inherits the secret-masking rule: critics MUST NOT reproduce secret values in their findings. And before the family is published, the orchestrator scrubs every doc in the session's scratch directory through the redactor (`python3 scripts/redact.py <scratch-dir>/*.md`; redactor path per orchestration-guide §7) — the mechanical gate that catches any raw value a scan or critic subagent quoted, independent of per-subagent memory.
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

  Audit docs: documentation/planning/security/<session>/
═══════════════════════════════════════════════════════════════════════════
```

Then tell the user:

**"Plans are ready. Run `/claudna:build documentation/planning/security/<session>/` to start building — it will handle challenge review, branching, implementation, and PRs for each phase doc."**

**This lens produces plans, not code** — see the shared reminder in `skills/_shared/orchestration-guide.md` §11: build, branch, and PR steps are always `/claudna:build`'s job.

---

## Notes

- **Never print secret values.** Report file:line and the variable name; the redactor (orchestration-guide §7) is the deterministic backstop that scrubs any raw value to `[REDACTED]` before findings leave the subagent.
- **Severity is explicit.** Use the definitions in `severity-definitions.md` — don't inflate or deflate.
- **Group related fixes.** One finding per PR creates review fatigue. Group logically.
- **Skip missing tools gracefully.** If `pip-audit` isn't installed, note it and move on. Don't block the audit.
- **User gates at every phase transition.** Scan → confirm → plan.
- **Subagent strategy.** Phase 1 can use Explore agents for deep code analysis (disk-write pattern). Phase 2 uses Plan agents for remediation docs (disk-write pattern). Both patterns defined in `skills/_shared/orchestration-guide.md`. Context never flows through the orchestrator.
- See orchestration guide, Section 10 for shared reminders (one PR per doc, testing, plans-not-code).

---

## Output Targets

`--output` flag semantics are owned by the lens contract (§2). This lens supports `github` and `session` in addition to the `docs` deliverable produced by the full interactive procedure above.

Follow the output guide at `skills/_shared/output-guide.md`:
- For `github`: write each finding as a doc (frontmatter + the Section 4 body skeleton) and delegate to `/claudna:publish <file> --to github-issue --repo <repo>` — publish validates, dedups, and applies labels from `tags:`. Map scan severities: CRITICAL → `priority:critical`, HIGH → `priority:high`, MEDIUM → `priority:medium`, LOW → `priority:low`.
- For `session` (engine default): produce the doc, then `/claudna:publish <file> --to session` prints it to chat (Section 5)
- For `docs`: follow the subagent workflow in the orchestration guide (publish step: `--dir documentation/planning/security/<session_name>_<YYYY-MM-DD>/`)

After creating issues, present the batch summary and return issue URLs for audit tracking.

---

## Autonomous Mode (--auto)

When `--auto` is set (implies `--output github`; see the lens contract §4 and orchestration guide Section 10):
1. Skip Plan Mode — go straight to Phase 1 scan
2. Skip the user confirmation gate between Phase 1 and Phase 2
3. Use the focus area from the dispatched arguments as scope. If none provided, scan full codebase.
4. Create GitHub Issues for all findings (CRITICAL and HIGH immediately, MEDIUM batched)
5. Skip LOW/INFO findings unless particularly noteworthy
6. Return structured summary for audit tracking
7. **Security-specific:** Never include a raw secret value in issue bodies — scrub the doc with the redactor (`python3 scripts/redact.py <file>`; path per orchestration-guide §7) before publishing, and report file:line + variable name only.
8. **Emit the structured-result shape** per `skills/_shared/orchestration-guide.md` §10.C as the FINAL output of the run — a fenced ```json block with no text after:

```json
{
  "skill": "audit",
  "outcome": "completed",
  "artifacts": {
    "lens": "security",
    "issues_created": ["https://github.com/org/repo/issues/123", "..."],
    "findings_by_severity": {"critical": 0, "high": 2, "medium": 5, "low": 3},
    "session_dir": "documentation/planning/security/<session>/"
  },
  "summary": "<2-3 line digest>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

- `outcome` is `completed` on success, `partial` if some issue creates failed, `blocked` if the scan couldn't run.
- Secret values MUST remain masked in `summary` and all artifact fields — run each published doc through the redactor (orchestration-guide §7) so structured-result fields carry `[REDACTED]`, never a raw value.
