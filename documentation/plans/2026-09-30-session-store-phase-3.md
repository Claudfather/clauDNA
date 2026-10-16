# Session store, phase 3: boundaries, complete — design notes

**Status:** built, 2026-09-30, on top of phase 2 (#373, merged). §1 and §3 are built, and §2 was done in #373.
**Spec:** `documentation/specs/2026-09-28-session-store-design.md` §4.3 (clear lineage), §11.3–11.5 (canaries), §12 item 3.

Phase 3 makes the boundary layer trustworthy before activity (phase 4) is recorded on top of it. That means four things:
- **clear lineage:** which session a `/clear` came from;
- **real child isolation**, replacing phase 2's entrypoint stopgap;
- **unclosed sessions:** noticed, and sealable by hand;
- **canaries** for the facts all three rest on.

## Canaries run 2026-09-30

A plugin-dir hook logged every payload, plus the `claude` process's pid and the transcript's size at hook time. It drove Claude Code 2.1.285 headless with stream-json input (the interactive tmux route stops at an OAuth prompt in this container): prompt → `/compact` → prompt → `/clear` → prompt. A `--resume … --fork-session` run followed.

| Question | Observed | Consequence |
|---|---|---|
| **§11.4:** is the `claude` pid stable across `/clear`? | **Yes.** Every hook in the run, before and after `/clear`, had the same `claude` ancestor. The hook's parent is a per-hook `sh`; `claude` is its parent. | The clear link keyed on the `claude` pid (§4.3) works. Find the pid by walking ancestors to the first process whose name contains `claude`. |
| What does `/clear` look like? | `SessionEnd{reason: clear}` on the old id, then `SessionStart{source: clear}` on a **new** id and a new transcript file. The new file doesn't exist yet at SessionStart (size 0). No payload names the other session. | Lineage has to come from our own link; nothing in the payload carries it. |
| **§11.3:** does PreCompact's size mark where post-compact content begins? | PreCompact at 155177; SessionStart(compact) at 155741. The 564 bytes between are bookkeeping only (`queue-operation`, `last-prompt`, `atis-latch`), and the `compact_boundary` record comes right after. | Starting the next segment at the seal's end is right. The boundary and compact-summary records land in the new segment, and the transcript reader already drops them (`isCompactSummary`). |
| Does a fork name its source? | `SessionStart{source: fork}` carries no source id. The forked transcript rewrites every `sessionId` to the new id, with no `forkedFrom`. | A fork's parent is unobservable from hooks. `parent_sid` stays null; lineage is never guessed. |
| What else is in the payloads? | SessionStart(compact) carries `model`. A fork's SessionStart carries `seconds_since_last_response`, `context_tokens` and cache estimates. | `actor.model` can be filled from SessionStart(compact) later. It isn't needed for phase 3. |
| **§11.5:** do nested sessions inherit the id? | In this cloud container, yes: a bare `claude -p` and a fork both took the parent's id even with `CLAUDE_CODE_SESSION_ID` unset. Passing `--session-id` gives a fresh one. **Not yet tested on a plain machine.** | The guard below is needed wherever this happens; the plain-machine canary decides how often that is. |
| **Re-run 2026-10-02** (2.1.287, headless, `scripts/session_canary.py`) | §11.3 held (only `queue-operation`, `last-prompt`, `atis-latch` before the boundary); §11.4 held (`$CLAUDE_PID` and the walk the same across `/clear`); §11.5: the nested child took its parent's id with its own `$CLAUDE_PID`, and `boundaries.inherited` ignores all 3 of its events. | Unchanged. The plain-machine run is the same script, interactively. |
| **Plain machine, 2026-10-02** (macOS 25.1, 2.1.287, interactive, `scripts/session_canary.py`) | §11.3 held (only `last-prompt`, `mode`, `permission-mode`, `atis-latch` before the boundary); §11.4 held (`$CLAUDE_PID` 10628 before and after `/clear`, and the `ps` walk found the same process); §11.5: the nested `claude -p` got a **fresh** session id. | Inheriting the id is a container behaviour, not Claude Code's. The child guard stays for containers and bots, where it happens; on a plain machine a nested child is simply its own session. |
| **C10, 2026-10-05** (2.1.289, headless and interactive tmux, `harness/runtime-neutral-canary.py`) | A tmux server started from a Claude Bash tool passed `CLAUDE_CODE_CHILD_SESSION=1`, `CLAUDECODE=1` and the caller's `CLAUDE_CODE_SESSION_ID` to its pane. Claude started with those markers took a fresh id and set its own markers on hooks and tools. The interactive macOS leg booted but reported that transcript saving was off because of the inherited child marker. | The launcher scrubs all three markers before exec to preserve transcript saving. This does not make the marker a nested-session signal: Claude sets it again on its own children. The store's pid/entrypoint guard remains. |
| **C11, 2026-10-05** (2.1.289, headless and interactive macOS tmux, `harness/runtime-neutral-canary.py`) | Main-thread Bash, an Agent subagent's Bash and every hook carried the SessionStart `session_id` and `CLAUDE_CODE_CHILD_SESSION=1`, including the subagent's `PostToolUse`. The interactive leg confirmed the headless readings. Only hook payload `agent_id`/`agent_type` distinguished the subagent's hooks. | Never suppress store hooks by `CLAUDE_CODE_CHILD_SESSION`: that would suppress every session's events. Keep the inherited-session pid/entrypoint checks, including for activity events. |

| **C1/C2, Codex P0, 2026-10-16** (native 0.162.0-alpha.17.2, private interactive root) | Actual stdin carries session_id, transcript_path, cwd and hook_event_name; sources startup/resume/compact, manual PreCompact, SessionEnd other. Tool name Bash; command is a string, successful response empty string. Hooks have no CODEX_SESSION_ID/THREAD_ID env; tools have both, equal to the hook UUID. The owner is a stable own Codex ancestor. | Explicit adapter selection and a bounded own-ancestry owner walk; no inferred PID env or PostToolUseFailure support. Native permission_mode bypassPermissions describes its enum; actual interactive sandbox was workspace-write. |
| **C3, Codex and Claude, 2026-10-16** | Codex SessionStart stdout and compact-specific stdout reached the next real model reply; manual PreCompact continue:false blocked compact. Claude fixed-localhost-provider requests received successful manual SessionStart(compact) stdout. A synthetic-usage native automatic Claude trigger continued to a main request without the blocking reason or a compact SessionStart; fixed responses prove request delivery only. | Engine capture-prompt correction is Claudron's owner contract, not store behavior. No real Claude inference or semantic uptake was claimed. |
| **C4, Codex, 2026-10-16** | Exact-ID resume and a tool turn grew the rollout 162197→181134 bytes with the entire old prefix unchanged. Actual response_item messages carry input_text/output_text; event_msg duplicates conversation information; context/tool records are separate. | Byte ranges hold for this measured version. Read only response_item user/assistant prose; exclude duplicates, tools, reasoning and context. Keep actual redacted golden records/provenance. |
| **C8/C9, Codex, 2026-10-16** | A local native marketplace/plugin installed and its trusted SessionStart hook ran. PLUGIN_ROOT/PLUGIN_DATA and Claude-compatible aliases were set and equal. Named public v0.28.1 marketplace fetch succeeded but plugin install reported claudna absent. A second SessionStart command populated its own selected log; private hook trust persisted across restart. | Add Codex marketplace/manifest and explicit host commands. Install and hook trust are separate; no cause is inferred from the old install failure. No global state changed. |

The C10/C11 rows are from Claudlobby's `documentation/plans/2026-10-04-runtime-neutral-observability-run-log.md`, the 2026-10-05 C10/C11 entries and operator leg 1 (interactive tmux). The earlier rows remain the measurements made on their dates; `scripts/session_canary.py` was the 2026-10-02 harness, not the C10/C11 instrument.

## 1. Clear lineage (§4.3) — built

- **SessionEnd(`reason: clear`)** writes `links/<claude-pid>.json` = `{schema: "claudna.clear-link/1", pid, sid, chain_id, ts}`, atomically, `0600`.
- **SessionStart(`source: clear`)** reads `links/<claude-pid>.json`. The link is used only when it names a *different* session and is under 60 s old. It is consumed (deleted), and the new session opens with `parent_sid` set to the link's `sid` and `chain_id` set to the link's `chain_id`, so a chain keeps one root across any number of clears. A `session.child_linked` event goes to the **parent's** lifecycle log (a write to another session, under that session's lock). A parent whose directory is gone is never recreated.
- **No link, a stale link, or one for the same session:** `parent_sid: null`. Never guessed.
- **Sweep:** the detached unclosed-session sweep (§3) deletes links older than 60 s, so no hook pays for it. `take_link` enforces the TTL anyway.
- **Finding the pid:** `$CLAUDE_PID`, which Claude Code exports to its hooks. It is the same value `session.opened` records for the nested-child guard (#373). Only when it is missing (an older Claude Code) does the adapter walk ancestors to the first process whose name contains `claude`, at most 6 hops (`/proc` on Linux, one `ps -o ppid=,comm=` per hop on macOS). No pid means no link.

## 2. Child isolation — done in #373

The #373 review replaced the entrypoint stopgap before phase 3 started. Each session records its owning `claude` process (`CLAUDE_PID`) at open, and a hook from another process is ignored, except a `resume`. A `startup`, `clear` or `fork` SessionStart never reopens an open session, and the entrypoint check remains as a fallback for sessions with no recorded pid. That covers the nested interactive `claude` this section set out to catch, so the transcript-path key proposed here was dropped. The proposed `CLAUDLOBBY_HOOK_CHILD` ([Claudlobby#1961](https://github.com/Claudfather/Claudlobby/issues/1961)) never shipped. C11 above confirmed that Claude Code's own `CLAUDE_CODE_CHILD_SESSION=1` is universal on hooks and tools, so the guard does not read it (spec §4.4).

## 3. Unclosed sessions and `session seal` — built

A SessionEnd that never ran (a crash, a kill, a laptop lid) leaves a session `open`. A later resume seals the old segment (phase 2); a session that is never resumed stays open for good. `unclosed.py` closes those.
- **Unclosed** means: `open`; its lifecycle log unchanged for 24 h (`CLAUDNA_UNCLOSED_AFTER_H`, never under 1 h), read from the log's mtime since appends are its only writes, and its transcript unchanged as long (only boundaries touch the log; a working session writes its transcript every turn); and the `claude` pid recorded at open (`session.opened.data.claude_pid`, shipped in #373) is no longer running.
  - A session with **no recorded pid is never swept automatically.** An idle live session and a dead one look the same without it, and closing a live one would drop its real SessionEnd.
  - A reused pid reads as alive. That only delays a sweep.
- **`session_store seal <sid>`** closes one session by hand. It seals the open segment at the transcript's size (`sealed_by: "abandoned"`, a new seal reason, so it never reads as a real SessionEnd) and closes with a new reason, `abandoned`, added to the registry and `session.schema.json` together. A SessionEnd payload can't claim `abandoned`. The sealed segment is summarized under the usual gate, so an abandoned session is still summarized and harvested when it opted in. A later `resume` reopens it as usual.
- **`session_store sweep [--dry-run]`** does the same for at most 5 sessions per run, oldest first, single-flight.
  - The close is one locked step (`SessionHandle.close_abandoned`). It re-checks that the session is still open and still owned by the dead pid the sweep judged, so a `resume` in between leaves it open.
  - The sweep acts for every session, so it drops the spawning session's `CLAUDNA_SESSION_SUMMARY`. Each abandoned session is summarized only by its own recorded opt-in, the per-session rule from #373.
- **Not in the hook itself** (a change from the first draft of this plan): a walk over every session costs a `stat` each, and the store only grows. So SessionStart checks one marker (`hooks/unclosed-sweep.last`) and spawns the sweep detached at most every 6 hours.
- **Not built:** showing the flag on the SessionStart liveness line. `sweep --dry-run` lists the candidates in the meantime.

## 4. Tests and canaries phase 3 adds

- Adapter tests for each lineage case: a link, no link, a stale link, a same-session link, and a chain across 3 clears keeping one `chain_id`.
- The nested-child transcript guard, including a nested interactive child.
- `seal` and the sweep: its bound, and that it never touches a live pid's session.
- A **plain-machine canary** (macOS and Linux, not this container) for §11.5: does a bare nested `claude -p` inherit the parent's id? Run 2026-10-02 on macOS: a fresh id, so inheritance is container-only and the entrypoint signal stays for containers.
- An **interactive `/clear` canary** on a plain machine, confirming the `claude` pid is also stable there. Done 2026-10-02 on macOS: stable.

## Owner decisions

The owner kept the defaults as built on 2026-09-30: a 24 h idle threshold and a sweep at most every 6 h, 5 sessions per run.

1. **The `abandoned` close reason and the 24 h threshold.** Built: 24 h, configurable with `CLAUDNA_UNCLOSED_AFTER_H`.
2. **Should an abandoned session be summarized?** Built: yes, under the usual gate. The alternative loses the segment, and harvest's drafts are untrusted anyway.


The 2026-10-16 P0 report SHA256 is `4d13c914c1227807d736293573b24e10ac9f055a504f298c6955288369bc9cb7`; the hook fixture manifest is `8ca604533fe6d6f509d75a832938f422fac3aa8c2512db95592f97b07eae8c2a`, and the actual-rollout golden excerpt is `85dc581b6c525be0412dff6713f3cc8e9b45e7ec09cdc7108fa07a08b245164c`. Claudlobby's canonical runtime-neutral run log records the full evidence and limitations before the [P4 plan](2026-10-16-codex-session-store-adapter.md). These are fixture/owner boundaries, not fleet activation or long-duration acceptance.
