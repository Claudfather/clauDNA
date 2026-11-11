---
name: session
user-invocable: true
description: "Use at session boundaries — resume at the start of a new session (resolve a scoped handoff and brief on where to pick up), handoff at the end of a session (write it), checkpoint for a mid-session save without the full ceremony, or name to label the session. Also use to look back at recorded sessions — list, show, timeline, or recurring tool failures. Replaces /session-handoff, /session-resume, /name-session."
argument-hint: "[handoff|resume|name|checkpoint|list|show|timeline|failures] [--auto]"
allowed-tools: Bash(git status *), Bash(git branch *), Bash(git log *), Bash(git rev-parse *), Bash(git stash *), Bash(git worktree *), Bash(git check-ignore *), Bash(gh pr view *), Bash(gh pr list *), Bash(ls *), Bash(wc *), Bash(date *), Bash(grep *), Bash(stat *), Bash(mv *), Bash(mkdir *), Read, Write, Edit, Glob
---

# Session

> **Codex:** Read `../_shared/codex-tools.md` before following this skill. Apply its tool, root and dispatch mappings throughout.

One engine for session continuity — `handoff`, `resume`, `name`, and `checkpoint` as verb modes. Continuity is owned by the native session at `R/sessions/<native-sid>/handoff.md`; scoped pointers in `R/continuity/` discover prior handoffs and separately published artifacts. Session continuity only — durable knowledge capture is `/claudna:capture` territory.

## Mode dispatch

Arguments to dispatch (first token = verb, the rest belong to the verb): $ARGUMENTS

| Verb | When | Auto | Depth |
|------|------|------|-------|
| `resume` | Start of a new session — read the handoff, reap, scan live state, brief | yes | `resume.md` |
| `handoff` | End of a session — capture, reap, write the handoff | yes | `handoff.md` |
| `checkpoint` | Mid-session save — append new items, no reaping, no ceremony | yes | `checkpoint.md` |
| `name` | Label the session for `/resume` discovery | no | `name.md` |
| `list`, `show`, `timeline`, `failures` | Look back at what the session store recorded: past sessions, one session's events, recurring tool failures | yes | `history.md` |

For the selected verb, read ONLY its depth file in this skill directory and follow it exactly — never load another verb's depth.

[`templates.md`](./templates.md) is the one exception, because it is not a verb depth: it holds the v2 content format, reaper rules, migration notes, and narrow source-level stable surface. Load it alongside the verb's depth file whenever a verb reads or writes continuity.

**No verb token → deterministic inference only (F2, epic #165), rules checked in order — first match wins:**
- Fresh session (little prior conversation) and a unique scoped handoff resolves → `resume` (checked first: the read-only mode wins any tie).
- The request contains an explicit wrap-up cue — one of: "wrap up", "wrapping up", "done for the day", "end of session", "handoff", "sign off", "calling it" → `handoff`.
- Anything else → print the table above and stop. Never infer `checkpoint` or `name`, and never ask a blocking question — the table is the answer.
- **Headless / `--auto`: the verb is required** — never inferred. `--auto` on the `name` verb emits the structured result with `"outcome": "blocked"` and a `blocker_description` naming it interactive-only (it hands the user a `/rename` command).

## Shared conventions

- **Identity:** use the actual native SID and host from a qualified host surface. Never derive one from cwd, time, or an operation ID. Missing or conflicting identity means no continuity write.
- **Ownership:** write only `R/sessions/<current-native-sid>/handoff.md`; predecessors remain immutable. Resolve scoped pointers without selecting “latest”.
- **CLI:** `session-store` below is shorthand for `python3 -B "<loaded-package>/lib/claudna/session_store"`; append the documented verb and arguments to that executable. Follow `documentation/guides/STORAGE_OWNERSHIP.md` for the effective root and ownership contract.
- **Permissions:** use the host's ordinary command and destination permission controls for that exact loaded helper. The frontmatter grants no generic Python pre-approval. If permission is denied or unavailable, report partial persistence with `handoff_path: null`; retain existing content and never change global grants or substitute another writer. Native interactive and `--auto` permission acceptance remain separate qualification gates.
- **Atomic writes:** submit the complete v2 content to `session-store handoff-write`; do not create shell temp files or use `mv`.
- **Capture-off:** `CLAUDNA_SESSION_STORE=0` disables background checkpointing. An explicit user-requested manual handoff may still persist with verified native identity; it does not initialize lifecycle state. Artifact-only cross-session discovery requires explicit public-context opt-in.
- **No compound commands:** separate parallel tool calls; `allowed-tools` patterns match simple commands only.
- **`--auto` is silent:** no questions, reaper as the only pruning mechanism, and a §10.C structured result (per `../_shared/orchestration-guide.md`) as the final output — `"skill": "session"` with `"mode"` inside `artifacts`.
- **Speed over thoroughness:** resume under 30 seconds; handoff under 60 with `--auto`; checkpoint faster than both.
