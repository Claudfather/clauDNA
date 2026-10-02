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

## 1. Clear lineage (§4.3) — built

- **SessionEnd(`reason: clear`)** writes `links/<claude-pid>.json` = `{schema: "claudna.clear-link/1", pid, sid, chain_id, ts}`, atomically, `0600`.
- **SessionStart(`source: clear`)** reads `links/<claude-pid>.json`. The link is used only when it names a *different* session and is under 60 s old. It is consumed (deleted), and the new session opens with `parent_sid` set to the link's `sid` and `chain_id` set to the link's `chain_id`, so a chain keeps one root across any number of clears. A `session.child_linked` event goes to the **parent's** lifecycle log (a write to another session, under that session's lock). A parent whose directory is gone is never recreated.
- **No link, a stale link, or one for the same session:** `parent_sid: null`. Never guessed.
- **Sweep:** the detached unclosed-session sweep (§3) deletes links older than 60 s, so no hook pays for it. `take_link` enforces the TTL anyway.
- **Finding the pid:** `$CLAUDE_PID`, which Claude Code exports to its hooks. It is the same value `session.opened` records for the nested-child guard (#373). Only when it is missing (an older Claude Code) does the adapter walk ancestors to the first process whose name contains `claude`, at most 6 hops (`/proc` on Linux, one `ps -o ppid=,comm=` per hop on macOS). No pid means no link.

## 2. Child isolation — done in #373

The #373 review replaced the entrypoint stopgap before phase 3 started. Each session records its owning `claude` process (`CLAUDE_PID`) at open, and a hook from another process is ignored, except a `resume`. A `startup`, `clear` or `fork` SessionStart never reopens an open session, and the entrypoint check remains as a fallback for sessions with no recorded pid. That covers the nested interactive `claude` this section set out to catch, so the transcript-path key proposed here was dropped. `CLAUDLOBBY_HOOK_CHILD` ([Claudlobby#1961](https://github.com/Claudfather/Claudlobby/issues/1961)) is still worth honoring once it ships.

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
- A **plain-machine canary** (macOS and Linux, not this container) for §11.5: does a bare nested `claude -p` inherit the parent's id? It decides whether the entrypoint signal can go. Run it with `scripts/session_canary.py setup`.
- An **interactive `/clear` canary** on a plain machine, confirming the `claude` pid is also stable there. This container's canary was headless. The same script covers it.

## Owner decisions

The owner kept the defaults as built on 2026-09-30: a 24 h idle threshold and a sweep at most every 6 h, 5 sessions per run.

1. **The `abandoned` close reason and the 24 h threshold.** Built: 24 h, configurable with `CLAUDNA_UNCLOSED_AFTER_H`.
2. **Should an abandoned session be summarized?** Built: yes, under the usual gate. The alternative loses the segment, and harvest's drafts are untrusted anyway.
