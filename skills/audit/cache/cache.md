Invoked by /claudna:audit in cache mode — the prompt-cache efficiency of a project's Claude Code config: what silently invalidates the cached prefix or bloats every API call.

Prompt caching is a prefix match — static content at the front is cached and reused; anything that varies between turns, or any byte change earlier in the prefix, invalidates the cache from that point on, and every token ships on every call regardless. This lens reads `CLAUDE.md` and the `.claude/` config and runs six read-only checks, each targeting one user-controllable invalidation or bloat factor. Diagnostic, not a rewrite. For a deep single-codebase debt scan, use `/claudna:audit tech-debt`.

**Reference:** `cache-checks.md` (same directory) — the six checks with PASS/WARN/FAIL criteria.

## Lens arguments (beyond contract §2)

Shared argument semantics live in `../../_shared/audit-lens-contract.md` §2. Lens-specific:

- `[focus]` — a directory to scope the scan (default: the repo root's `CLAUDE.md` + `.claude/`).
- **auto: yes** — deterministic and read-only; runs non-interactively under `--auto` (contract §4).

## Procedure

Follow these steps in order.

### Step 1: Locate the config

Find `CLAUDE.md` at the repo root (and any nested `CLAUDE.md`), plus `.claude/rules/` and any hooks/settings that load files into context. If no `CLAUDE.md` exists, report that and stop — there is nothing to score.

### Step 2: Run the six checks

Run every check in `cache-checks.md`, scoring each PASS / WARN / FAIL against its criteria. All reads only — never edit the config.

### Step 3: Present

Lead with a boxed summary: lens, scope (files scanned), and counts by score. Then a severity-ordered findings table — FAIL before WARN, PASS summarized in the box — each row: check, score, the offending location (`file:line` where it applies), and a one-line fix naming the caching impact. Findings carry the **performance** concern area (contract §3). Close with the single highest-leverage fix.

## Output Targets

This lens defaults to retaining a sanitized `00_CACHE_AUDIT.md` report with `/claudna:publish <artifacts>/00_CACHE_AUDIT.md --to artifacts`; resolve the actual SID/provider and exact paths through orchestration guide §1. Explicit `session` presents the summary and findings in chat only, with no report file. Explicit `github` writes selected issue docs under `<artifacts>/cache/` and exports them with `/claudna:publish <artifact-file> --to github-issue --repo <repo>`; retain the sources. Publish validates, dedups, and applies labels (`auto-audit` + `cache`).

Under `--auto` (auto: yes): preserve the selected output target. With artifact-backed output, retain the canonical report; explicit `session` keeps findings in context without files. Then emit the single fenced structured-result JSON per `../../_shared/orchestration-guide.md` §10.C (skill: `audit`, `"lens": "cache"` inside `artifacts`, including `report_path` only when a canonical report was actually written) — no chat prose.

## Notes

- **Read-only.** The lens reports; it never edits config.
- **Diagnostic, not prescriptive.** Some cache-unfriendly patterns are deliberate (a small always-loaded checklist may be worth its cost) — note the trade-off, don't flag blindly.
- **No `CLAUDE.md` → skip.** Report and stop; every check keys off it.
- **Concern area = performance.** Cache findings are a token/latency-cost concern; the lens does not mint a `cache` concern (contract §3, `lens-result-contract.md`).
