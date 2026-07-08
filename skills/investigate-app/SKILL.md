---
name: investigate-app
user-invocable: true
description: "Use when something is broken in production and you need to investigate -- errors, outages, degraded performance, or unexpected behavior."
---

# Investigate App

Production debugging workflow: detect platform, gather evidence, root-cause analysis, generate fix plans.

**Persona:** Senior SRE -- methodical, evidence-driven, never guesses. Every finding cites evidence. Every recommendation includes confidence and rationale.

## The Iron Law

**ALWAYS find root cause before attempting fixes.** Random fixes waste time and create new bugs. Symptom fixes are failure.

<HARD-GATE>
Do NOT propose any fix until evidence gathering (Steps 1-5) is complete.
Violating the letter of this rule is violating the spirit of debugging.
</HARD-GATE>

## Procedure

Follow steps in order. **Enter Plan Mode** (`EnterPlanMode`). All steps through Step 6 are read-only. If user declines, proceed normally -- still read-only by convention.

---

### Step 1: Understand the Problem

Ask the user: (1) What's broken? (2) When did it start? (3) What changed recently? (4) What's the impact? Capture answers as structured context for the investigation.

---

### Step 2: Detect Platform

Run detection checks in parallel, bootstrap missing CLIs, present detection summary. See `platform-detection-reference.md` for detection matrix, bootstrap sequences, and summary format.

---

### Steps 3-4: Gather Evidence & Trace Code

Scratch directory: `/tmp/investigate-app-<YYYY-MM-DD_HHMMSS>/research/`.

Launch **parallel Explore subagents** per orchestration guide, Section 2 (Explore Agent Disk Pattern). Each writes research to the scratch directory, returns a 2-4 line summary. Do NOT read CLAUDE.md or MEMORY.md in the orchestrator.

Follow `evidence-gathering-checklist.md` in this skill's directory for signals to gather and codebase tracing targets.

---

### Step 5: Root Cause Analysis

Present findings as a table: `#`, `Category`, `Finding`, `Confidence`, `Evidence`. Confidence: **High** (direct evidence), **Medium** (correlation), **Low** (needs more investigation).

---

### Step 6: Fix Proposals

For each root cause, propose a fix scored by **Impact**, **Effort**, **Risk** (each H/M/L). Present as a table: `#`, `Fix`, `Impact`, `Effort`, `Risk`.

Ask the user: **"Which fixes would you like me to plan? Pick by number, or tell me to adjust."** Do NOT proceed until the user selects fixes.

**Exit Plan Mode.** Call `ExitPlanMode` -- doc generation requires the Write tool.

---

### Escalation: 3+ Failed Fixes

**If 3+ fix attempts failed: STOP.** Signs: new coupling, massive refactoring, new symptoms each time. Discuss with user -- wrong architecture, not failed hypothesis.

---

### Step 7: Generate Fix Plans

Generate implementation plans for approved fixes. Ask user for a session name (e.g., `api-500s`).

**Output** lands in `documentation/planning/investigations/<session_name>_<YYYY-MM-DD>/` -- `00_INVESTIGATION.md` (full record) plus numbered fix docs. Plan agents write the family to the session's scratch docs directory and the orchestrator publishes it with `/claudna:publish <scratch-docs-dir> --to docs --dir documentation/planning/investigations/<session_name>_<YYYY-MM-DD>/` (family mode; orchestration guide, Section 3). Archive convention: orchestration guide, Section 8.

**Subagent workflow:** Orchestration guide, Section 9. Plan agents read from the scratch directory. Keep fix docs proportional to complexity.

---

### Step 8: Postmortem Summary & Handoff

Present summary: session, date, problem, platform, root causes, fix list, prevention recommendations, docs path. Direct user to run `/claudna:implement-plan` on the investigation directory.

**This skill produces plans, not code.** Do NOT build, branch, or create PRs.

---

## Red Flags — STOP

If you think "quick fix for now," "just try X," "it's probably X," or "one more attempt" (after 2+ failures) -- STOP and return to evidence. Systematic is faster than guess-and-check. 3+ failures = architectural problem.

---

## Notes

- **User gates at every major step.** Never auto-proceed between investigation, planning, and implementation.
- **Evidence over intuition.** Every diagnosis must cite specific log lines, metrics, or code.
- **Platform-agnostic core.** Platform-specific commands used when available, never required.
- **Subagents.** Steps 3-4: Explore (disk-write). Step 7: Plan (disk-write). See orchestration guide. Context never flows through the orchestrator.
- **Never display secrets.** Env var names only. Mask secrets in logs.
- **Supporting files:** `platform-detection-reference.md`, `evidence-gathering-checklist.md`, `root-cause-tracing.md`, `defense-in-depth.md`.
- Orchestration guide, Section 10: one PR per doc, testing, plans-not-code.
