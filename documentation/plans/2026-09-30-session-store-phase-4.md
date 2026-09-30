# Session store, phase 4: activity — design notes

**Status:** prep, 2026-09-30. Written locally after phase 3 (#383) merged. It lands as its own PR.
**Spec:** `documentation/specs/2026-09-28-session-store-design.md` §4.2 (hook → store action), §6.2 (activity kinds), §6.5 (`segment.json` counts), P4 (metadata by default), §11 item 2 (prompt text, decided), §12 item 4.

Phase 4 records what happens *inside* a segment:
- `prompt.submitted`, one per prompt;
- `skill.invoked`, one per Skill call;
- `tool.failed`, one per failing tool call;
- `segment.json` counts over all three.

The event kinds, their caps and redaction have existed since phase 1 (`events.py`), and the store already appends activity (`store.py`, `seg=None` resolves the current segment under the lock). So phase 4 is mostly the adapter, hook wiring and the migration of `telemetry-emit.sh`.

## Canaries run 2026-09-30

A scratch plugin logged every payload for UserPromptSubmit, PostToolUse, PostToolUseFailure, SessionStart and SessionEnd. Claude Code 2.1.286 drove it headless (`claude -p`, Haiku): one failing Bash call, then one Skill call.

| Question | Observed | Consequence |
|---|---|---|
| What does UserPromptSubmit carry? | `prompt` (full text), `prompt_id` (a UUID), `permission_mode`. | `prompt.submitted.prompt_id` is real, and `chars` is `len(prompt)`. The text is stored only with `CLAUDNA_CAPTURE_PROMPTS=1` (decided, §11 item 2). |
| Does `prompt_id` tie things together? | The same `prompt_id` is on the prompt, the tool failure and the Skill call that followed. | Activity can be grouped by prompt without timestamps. It isn't in the tool kinds' registry yet (see §3). |
| What does PostToolUseFailure carry? | `tool_name`, `tool_input` (Bash: `command`, `description`), `error` (`"Exit code 2\nls: cannot access …"`), `is_interrupt`, `duration_ms`, `tool_use_id`. | `exit_code` parses from the first line (`Exit code N`). The signature comes from the first *real* error line. `is_interrupt: true` is the user pressing Esc, not a failure (§3). |
| What does PostToolUse(Skill) carry? | `tool_input: {skill, args}`, **`tool_response: {success, commandName}`**, **`duration_ms`**. | The real success and duration are both there. `telemetry-emit.sh` guesses success by grepping the output for "error", and always writes `duration_ms: null`. |
| Is `CLAUDE_PID` on these hooks? | Yes, on every one. | The nested-child guard (#373) covers activity unchanged. |
| Do command hooks support `async`? | Yes. The schema has `async` ("hook runs in background without blocking") and `asyncTimeout`. An async UserPromptSubmit hook that slept 5 s didn't delay the turn (13 s against a 14 s baseline), still received its stdin payload, and logged mid-turn. | Activity hooks run async, so no prompt waits on the store (§2). |
| What happens to an async hook when the process ends? | In a `claude -p` that exited before a 5 s async hook finished, the hook never logged. | A short headless run can lose its last activity append. Activity isn't fsynced anyway (§11 item 11: "at most a few tallies"), so this is acceptable and documented. |

## 1. What gets recorded

| Hook | Kind | `data` |
|---|---|---|
| UserPromptSubmit | `prompt.submitted` | `prompt_id`, `chars`; `text` only with `CLAUDNA_CAPTURE_PROMPTS=1` (redacted and capped at 500 by `make_event`) |
| PostToolUse, matcher `Skill` | `skill.invoked` | `skill` (as called: `claudna:recall`, `canary:hello`, a bare user skill), `args_chars`. **Proposed additions:** `ok` (from `tool_response.success`) and `duration_ms`, both optional (§3). |
| PostToolUseFailure | `tool.failed` | `tool`, `signature`, `exit_code`. `command` and `error` are free text: see §4 for whether they're stored. |

- Every skill is recorded, not just `claudna:*`. The store is the user's own record; the `claudna:` filter belongs to the telemetry projection (§5).
- A `tool.failed` with `is_interrupt: true` isn't recorded: pressing Esc isn't a failure, and counting it would pollute `session failures` (phase 6). Open question 3 asks whether to count interrupts separately.
- **The signature** is `tool` plus the first error line that isn't `Exit code N`, normalized. Paths become `<path>`, numbers `<n>`, hex runs and UUIDs `<id>`, quoted strings `<str>`, whitespace is collapsed, and the result is redacted and capped at 200 (the registry cap). The canary's error gives `Bash: ls: cannot access <str>: No such file or directory`. It's a grouping key, stable across paths and ids, and it is computed once at write time (§6.2).

## 2. The hot path

UserPromptSubmit runs before the model sees every prompt. The store's hook costs about 75 ms, most of it interpreter start, which is too much to add to every turn.
- **All three activity hooks are `"async": true`** in `hooks.json`. The boundary hooks stay synchronous: their seals fix the byte ranges, and SessionEnd already has its 5 s timeout.
- Async means ordering against the boundaries isn't guaranteed:
  - An activity append that lands after SessionEnd hits a closed session. The store refuses it (§6.3), and the adapter records nothing, silently, since this is expected and not an error.
  - An append that lands after a PreCompact seal goes to the sealed-but-current segment. §6.3 already allows that.
  - One that lands after SessionStart(`compact`) goes to the new segment. That's a prompt counted one segment late, which is acceptable for tallies.
- **Older Claude Code:** a build without `async` would run these hooks synchronously, if it ignores the unknown key, or reject `hooks.json`. That needs one canary on an older build before merge (§6). If it rejects the file, the async hooks move into their own hooks file or stay out.
- **Cost:** only UserPromptSubmit fires every turn. PostToolUseFailure fires only on failures, and PostToolUse is matched to `Skill` only. The existing guards apply unchanged: `CLAUDNA_SESSION_CHILD`, `CLAUDNA_SESSION_STORE=0`, the `CLAUDE_PID` nested-child check, and no open session means nothing is recorded.

## 3. Registry and schema changes

- `skill.invoked`: add optional `ok: bool|null` and `duration_ms: int|null`. That's additive; readers fold extra keys (§6.2).
- `tool.failed`: add optional `duration_ms`.
- `prompt_id` on the tool kinds: add optional `prompt_id` to `skill.invoked` and `tool.failed`, so a timeline can group by prompt. Cheap and additive. Open question 4.
- `segment.json.counts` (`prompts`, `skills`, `failures`, `checkpoints`) is already in the schema. Its projection folds from `events.jsonl`, and phase 4 is its first real input. Tests pin it.

## 4. Privacy: free text in `tool.failed`

P4 says free text (prompts, stderr) is off unless opted in. `tool.failed.command` is a command line, and `error` is stderr. Both are redacted and capped at write time, but that redaction is pattern-based (the #373 review showed how many shapes it can miss).
- **Proposal:** off by default, like prompt text. By default `tool.failed` carries `tool`, `signature` (normalized and redacted), `exit_code`, `duration_ms` and `prompt_id`. `CLAUDNA_CAPTURE_TOOL_ERRORS=1` adds `command` and `error`.
- The signature is what `session failures --group` needs, and it keeps working by default.
- Open question 1.

## 5. Migrating `telemetry-emit.sh`

`telemetry-emit.sh` (PostToolUse, `Skill`) appends one line per `claudna:*` skill call to `${CLAUDNA_TELEMETRY_PATH:-~/.claude/telemetry/skill-events.jsonl}`. It only does so with `CLAUDNA_TELEMETRY=1`, which Claudlobby sets for fleet bots. That file is a **Claudosseum ingestion contract**: `{ts, bot, type: "skill_invocation", source: "vitals", data: {skill_slug, duration_ms, success, session_id}}`. Changing that contract needs the owner's approval (CLAUDE.md, "Requires approval").

**Proposal:** the store's `skill.invoked` path writes that line itself, and `telemetry-emit.sh` retires.
- The same opt-in, path, `claudna:` filter, bare slug and field names apply. It's a projection of `skill.invoked`, written in the same hook call, so there's one PostToolUse(Skill) hook instead of two.
- **Byte-compatible by default:** `success` and `duration_ms` keep their current meaning (the heuristic, and `null`) unless the owner approves switching to the real values from the payload (open question 2). The real values are strictly better, but they are a contract change.
- `session_id` becomes the real session id. Today it is `${CLAUDE_SESSION_ID:-$$}`, and Claude Code doesn't export `CLAUDE_SESSION_ID`, so it's a shell pid. That's a behavior change on a field the contract names, so it's part of question 2.
- Pruning (30 days, every ~100th write) moves from the shell to the sweep worker (phase 3), off the hook path.
- `telemetry-emit.sh` stays one release as a no-op shim that exits 0, then is removed. That covers a user who wired it by hand.
- If the owner would rather not touch the contract in phase 4, the fallback is to leave `telemetry-emit.sh` exactly as it is and record `skill.invoked` alongside it. The spec's "migrate" then moves to a later phase.

## 6. Tests and canaries phase 4 adds

- **Adapter tests:**
  - each hook produces its kind with the payload fields mapped;
  - `chars` without text by default, text with the opt-in, redacted;
  - no event from an interrupt;
  - signature normalization: paths, numbers, ids, quoted strings, redaction and the cap;
  - an activity hook with no open session, or after SessionEnd, records nothing and isn't logged as an error;
  - a nested child's activity is ignored.
- `segment.json.counts` after a mix of events, including a rebuild.
- **The telemetry projection:** golden lines byte-compatible with today's script for the same input, the filter and opt-in, the `bot` default, and pruning in the sweep.
- **`hooks.json`:** the three activity hooks are `async: true` and wired with the right matchers. The Cursor manifest still has no hooks (`make check-manifest`).
- **Canaries still needed:**
  - an **older Claude Code** build with `async` in `hooks.json` (ignored or rejected?);
  - **interactive** timing on a plain machine, to confirm an async UserPromptSubmit adds nothing a person can feel;
  - `PostToolUseFailure` for a **Skill** that fails, and for an MCP tool, to see what their `error` looks like.

## Open questions for the owner

1. **Is `tool.failed` free text off by default?** Proposed: yes. `command` and `error` only with `CLAUDNA_CAPTURE_TOOL_ERRORS=1`, and signatures always on.
2. **Is the telemetry contract migrated, and fixed?** Proposed: the store writes the Claudosseum line and `telemetry-emit.sh` retires after a one-release shim. Within that, choose:
   - keep `success`, `duration_ms` and `session_id` byte-compatible (the heuristic, `null` and a pid);
   - or switch them to the payload's real values, which Claudosseum would need to know about.
3. **Interrupts:** don't record them (proposed), or count them as their own `tool.interrupted` kind?
4. **`prompt_id` on tool events:** add it (proposed; additive), or leave the registry as the spec has it?
