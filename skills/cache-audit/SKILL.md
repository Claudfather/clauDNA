---
name: cache-audit
description: "Use when you want to check whether your CLAUDE.md and project configuration are hurting prompt cache efficiency."
---

# Cache Audit

Diagnostic scan of a project's Claude Code configuration for patterns that hurt prompt cache efficiency. Run this occasionally — like `/tech-debt` or `/security-audit` — to check your project's cache hygiene.

This is a **read-only** skill. It reads files and presents findings. It does not modify anything.

## Background

Claude Code's prompt caching works by prefix matching: static content at the start of the system prompt is cached and reused across turns. Anything that changes between turns or sessions invalidates the cache from that point forward. The main user-controlled factors are:

1. **CLAUDE.md section ordering** — static content first, dynamic content last
2. **CLAUDE.md size** — larger files mean more tokens in every API call
3. **Lessons file loading** — auto-loading `.claude/lessons.md` adds variable content to every request
4. **Tool set stability** — adding/removing tools mid-session invalidates the entire cache
5. **Model stability** — switching models mid-session rebuilds the cache from scratch
6. **Mid-session CLAUDE.md edits** — editing CLAUDE.md during a session invalidates the cached prefix

## Procedure

Run all six checks, then present the combined findings table. Do not ask questions or pause between checks — run them all and present results.

**Checks** (see `cache-checks.md` for detailed guidance and scoring):

1. **Section ordering** — static sections before dynamic sections in CLAUDE.md
2. **CLAUDE.md size** — line count thresholds (200 / 350)
3. **Lessons isolation** — `.claude/lessons.md` on-demand only, not auto-loaded
4. **Tool & model stability** — no mid-session tool/model switching patterns
5. **Mid-session edits** — no instructions to edit CLAUDE.md during a session
6. **Rules file configuration** — `.claude/rules/` files have correct `paths:` frontmatter

Each check scores PASS / WARN / FAIL per the criteria in `cache-checks.md`.

## Presenting Results

After running all checks, present a single findings table:

```
Cache Audit Results
═══════════════════════════════════════════════════════════════════════════

  Check                        Status    Notes
  ─────────────────────────    ──────    ─────────────────────────────
  Section ordering             PASS      Static-first layout detected
  CLAUDE.md size               WARN      247 lines (threshold: 200)
  Lessons isolation            PASS      On-demand only
  Tool & model stability       PASS      No mid-session changes
  Mid-session edits            WARN      "Update continuously" language
  Rules file config            PASS      All rules have paths: frontmatter

═══════════════════════════════════════════════════════════════════════════
  6 checks: 4 passed, 2 warnings, 0 failures
```

Then, for each WARN or FAIL item, provide a brief recommendation explaining the caching impact and a concrete suggestion.

## Tone & Framing

- **Diagnostic, not prescriptive.** Present findings as "here is what we found" not "you must fix this."
- **Explain the why.** For each finding, briefly explain the caching impact so the user can make an informed decision.
- **Acknowledge trade-offs.** Some cache-unfriendly patterns exist for good reasons (e.g., keeping lessons in CLAUDE.md for projects where context is critical). Note these rather than blindly flagging them.
- **No false alarms.** If CLAUDE.md does not exist, report that and skip all checks. If a check has nothing to flag, mark it PASS and move on. Do not invent findings.

## Notes

- **Works on any project.** Does not assume clauDNA is installed. Checks whatever CLAUDE.md and .claude/ configuration exists in the current project root.
- **No CLAUDE.md = short report.** If the project has no CLAUDE.md, report "No CLAUDE.md found — nothing to audit" and exit. Do not create one.
- **Read-only.** Never modify any files. This is a diagnostic tool.
- **No subagents.** Read files directly and present findings in a single response. Do not use the Task tool.
- **Run occasionally.** Not embedded in every workflow. Users run it when they want to check cache hygiene.
