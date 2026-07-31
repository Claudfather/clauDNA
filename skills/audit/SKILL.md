---
name: audit
user-invocable: true
description: "Use for codebase audits across ten concerns — security vulnerabilities, technical debt, stale documentation, visual and UX design, frontend performance (janky scroll, slow loads), cross-cutting consistency of interfaces, data model fit, a birds-eye view across repositories, whole-system comprehension reviews, and prompt-cache efficiency. Replaces /security-audit, /tech-debt, /docs-review, /design-review, /access-path-audit, /data-model-audit, /frontend-performance-audit, /repo-health."
argument-hint: "[security|tech-debt|docs|design|access-path|data-model|frontend-perf|repo-health|system|cache] [--auto] [--output github|session] [focus]"
requires:
  - cli: gh
    reason: "GitHub CLI for --output github issue filing (via publish) and the repo-health lens's PR/CI listing"
---

# Audit

One engine for codebase audits — ten concern lenses as verb modes. Shared behavior (arguments, output routing, autonomous mode, orchestration) lives in `skills/_shared/audit-lens-contract.md`; this file supplies only the lens table and dispatch rules.

## Lens dispatch (contract §2, §4)

Arguments to dispatch (first token = lens, the rest belong to the lens): $ARGUMENTS

No lens token → infer only when the request wording is unambiguous (e.g. "check for security vulnerabilities" → `security`); otherwise print this table and stop — never ask a blocking question when the table answers it. Headless contexts require the lens token.

| Lens | When | Auto | Depth |
|------|------|------|-------|
| `security` | Security vulnerabilities — injection, auth/authz flaws, secrets exposure, unsafe dependencies | yes | `security/security.md` |
| `tech-debt` | Technical debt — duplication, dead code, fragile modules, outdated patterns | yes | `tech-debt/tech-debt.md` |
| `docs` | Project documentation stale, inaccurate, or incomplete vs the codebase | yes | `docs/docs.md` |
| `design` | Visual and UX audit of a deployed app — spacing, typography, flows, accessibility | no | `design/design.md` |
| `access-path` | Interfaces (API, CLI, Slack, MCP, SDK, workers) enforcing cross-cutting concerns consistently, at the right layer | yes | `access-path/access-path.md` |
| `data-model` | How well the data model serves the application — schema-to-intent mismatches, awkward code-to-DB paths | no | `data-model/data-model.md` |
| `frontend-perf` | Frontend performance symptoms — flickering, slow loads, janky scroll, re-renders, layout shifts | yes | `frontend-perf/frontend-perf.md` |
| `repo-health` | Birds-eye view across multiple repositories — activity, staleness, CI health, open work | no | `repo-health/repo-health.md` |
| `system` | An unfamiliar whole system (or subsystem) to understand and triage at rest — comprehension maps plus cross-concern correctness/reliability/performance/data-quality risk, filed as junior-executable, tracker-deduplicated issues | no | `system/system.md` |
| `cache` | Prompt-cache efficiency of project config (`CLAUDE.md`, `.claude/`) — section ordering, file size, auto-loaded files, tool/model stability, mid-session edits, rules-file scoping | yes | `cache/cache.md` |

For the selected lens, read ONLY its depth file in this skill directory and follow it exactly — never load another lens's depth (contract §1).

## Surfaces (contract §2–§4)

- `--output github` files findings as issues per `skills/_shared/output-guide.md` (all filing routes through `/claudna:publish`); `--output session` (default) presents in chat.
- `--auto` runs non-interactively for lenses marked **Auto: yes** and emits the structured-result JSON per `skills/_shared/orchestration-guide.md` §10.C as the final output. For an **Auto: no** lens, emit the structured result with `"outcome": "blocked"` naming the lens as interactive-only — never improvise a non-interactive variant.

## Related

For production outages and live debugging, use /claudna:investigate-app — audits examine systems at rest. For reviewing an uncommitted diff or a specific PR (a change, not a system at rest), use /claudna:review-work; for hardening a plan Issue with the lens panel, use /claudna:ironclad.
