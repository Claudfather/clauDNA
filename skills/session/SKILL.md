---
name: session
user-invocable: true
description: "Use at session boundaries — resume at the start of a new session (read the per-cwd handoff and brief on where to pick up), handoff at the end of a session (write it), checkpoint for a mid-session save without the full ceremony, or name to label the session. Replaces /session-handoff, /session-resume, /name-session."
argument-hint: "[handoff|resume|name|checkpoint] [--auto]"
allowed-tools: Bash(git *), Bash(gh *), Bash(ls *), Bash(wc *), Bash(date *), Bash(grep *), Bash(stat *), Bash(mv *), Bash(mkdir *), Read, Write, Edit, Glob
---

# Session

One engine for session continuity — `handoff`, `resume`, `name`, and `checkpoint` as verb modes over the per-cwd substrate: `<cwd>/.claude/session.md`, reaped by `skills/_shared/reaper-rules.md`. Session continuity only — durable knowledge capture is `/claudna:reflect` and `/claudna:capture` territory.

## Mode dispatch

Arguments to dispatch (first token = verb, the rest belong to the verb): $ARGUMENTS

| Verb | When | Auto | Depth |
|------|------|------|-------|
| `resume` | Start of a new session — read the handoff, reap, scan live state, brief | yes | `resume.md` |
| `handoff` | End of a session — capture, reap, write the handoff | yes | `handoff.md` |
| `checkpoint` | Mid-session save — append new items, no reaping, no ceremony | yes | `checkpoint.md` |
| `name` | Label the session for `/resume` discovery | no | `name.md` |

For the selected verb, read ONLY its depth file in this skill directory and follow it exactly — never load another verb's depth.

**No verb token → deterministic inference only (F2, epic #165), rules checked in order — first match wins:**
- Fresh session (little prior conversation) and `<cwd>/.claude/session.md` exists → `resume` (checked first: the read-only mode wins any tie).
- The request contains an explicit wrap-up cue — one of: "wrap up", "wrapping up", "done for the day", "end of session", "handoff", "sign off", "calling it" → `handoff`.
- Anything else → print the table above and stop. Never infer `checkpoint` or `name`, and never ask a blocking question — the table is the answer.
- **Headless / `--auto`: the verb is required** — never inferred. `--auto` on the `name` verb emits the structured result with `"outcome": "blocked"` and a `blocker_description` naming it interactive-only (it hands the user a `/rename` command).

## Shared conventions

- **Identity:** keyed by cwd. The handoff lives at `<cwd>/.claude/session.md`. No global slug, no cross-project state, and **no writes to `~/.claude/`** — this engine stays out of the user-config tree entirely.
- **Atomic writes:** always `session.md.tmp` then `mv` — a concurrent reader never sees a half-written file.
- **No compound commands:** separate parallel tool calls; `allowed-tools` patterns match simple commands only.
- **`--auto` is silent:** no questions, reaper as the only pruning mechanism, and a §10.C structured result (per `skills/_shared/orchestration-guide.md`) as the final output — `"skill": "session"` with `"mode"` inside `artifacts`.
- **Speed over thoroughness:** resume under 30 seconds; handoff under 60 with `--auto`; checkpoint faster than both.
