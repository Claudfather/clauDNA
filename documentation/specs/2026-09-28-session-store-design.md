---
title: Session Store — Session-Segmented Capture Design
date: 2026-09-28
status: draft
authors: [chrisrogers37]
repos: [claudna, claudron, claudlobby]
---

# Session Store — Session-Segmented Capture Design

## 1. Problem

clauDNA captures nothing locally about what a session did. `telemetry-emit.sh` writes an unbounded, opt-in JSONL of skill calls; `/claudna:capture` distills knowledge straight into the vault; failures, boundaries, and "what happened in this task" are lost when the session closes. Two workloads need the same substrate:

- **Interactive work** — one session per task, then close out. Wants a per-session record with readers, and an end-of-session summary.
- **Claudlobby workers** — long-running interactive `claude` in tmux, never resumed. Workers `/compact` themselves after every task and `/clear` themselves when switching repos; the manager can only *request* a compact; a restart relaunches the process (new session, no clear). Wants the same record, cut into bounded pieces — for a bot, a segment is ≈ one task.

**Goal:** a local, append-only, session-id-keyed store that clauDNA writes and organizes, with readers, a per-segment `claude -p` summary, and an export door that Claudron and Claudlobby *optionally* pull from.

**Non-goals:** fleet metrics (tokens / cost / latency — Claude Code's OpenTelemetry export, Claudlobby's to configure; a design-stage pilot there today); pushing to any hosted service; vault writes (Claudron owns ingestion, dedup, ranking); anything the Claudlobby plane already records (§1.1).

### 1.1 Boundary with Claudlobby and Claudron

| Layer | Owner | Scope | Answers |
|---|---|---|---|
| Inter-agent / fleet | **Claudlobby plane** (`state/plane/plane.db`, SQLite) | host, all bots | who asked whom to do what, did it land, is the bot healthy |
| Intra-session | **clauDNA session store** (this spec) | one session, cut into segments | what happened inside this session/segment, what broke, what it learned |
| Durable knowledge | **Claudron** vault | fleet / user | what's worth keeping |

Rules:

1. **A fact is recorded once, by whoever observes it first-hand.** The plane's `bot-vitals.sh` already records every tool call (`tool_call`), so the store records **no generic tool-call event**. It records only what the plane lacks: `tool.failed` (vitals hooks PostToolUse, not failures — a gap today), `skill.invoked`, prompt metadata, and segment boundaries. Interactive sessions have no plane, which is why the store stands alone.
2. **Neither side writes the other's storage.** clauDNA never touches `plane.db`; the plane never parses the store's files. Claudlobby consumes `session export` like Claudron does (a `consumers.json` entry) and joins on `sess_<sha256(sid)[:32]>`.
3. **Claudlobby owns per-bot config; clauDNA reads it.** `CLAUDNA_STATE_DIR` (per bot, e.g. `$BOT_DIR/data/claudna`), `CLAUDNA_SESSION_SUMMARY`, and identity env (`FLEET_NAME`, `BOT_ID`).
4. **Run siloed, then consolidate.** Claudlobby's `transcript-digest.sh` (a SessionEnd `claude -p` digest using capture's rubric) overlaps this spec's summarizer. For an observation period both run, siloed, on a small set of bots; one owner is then chosen on evidence (quality, cost, coverage including the skipped rows the plane's monitor needs). The comparison is **pre-registered before the observation period starts** — the session battery, the version pins of both paths, the metrics and their thresholds, and the stopping rule are written down first — so the result can't be read either way after the fact. Pre-registration is a phase 2 exit criterion. Tracked in [Claudlobby#1961](https://github.com/Claudfather/Claudlobby/issues/1961), which also covers the digest child's missing isolation.

**Prior art, used as concept reference only:** other session-capture and "AI brain" projects — per-session dirs, failure logs, a detached `claude -p` summarizer, raw-inbox → wiki promotion. This design takes the *concepts* and rebuilds from first principles; nothing is ported. Their observed failure modes shape §7.2 and §12 (see §1.2).

### 1.2 Lessons from prior knowledge-loop attempts

Observed in earlier raw-inbox → wiki systems, each with the design answer here:

| Failure | Answer |
|---|---|
| Capture was built first; the distill/promote step never shipped, so captures influenced nothing | §12 builds a thin **end-to-end slice** (seal → summary → harvest → draft → recall) before broadening anything |
| Most captured sections were empty or placeholder ("nothing yet") | blocks are emitted only when non-empty; an empty `done` beside observed commits fails validation (§6.6) |
| Fields that were always null (PR, ticket, engineer, a stuck "active" status) | deterministic fields come from events, never the LLM; status is derived from the log; every field carries an explicit absence state |
| A human gate before the write became a rubber-stamp or a graveyard | auto-drain to `draft`; the human gate is promotion, capped and ranked (§7.2) |
| A scheduled promoter died silently for weeks | liveness is shown every SessionStart ("last harvest N days ago · last error"); stdlib only, pinned deps |
| The same session was captured repeatedly | idempotent on `<sid>:<seg>` + content hash |
| Knowledge scattered across per-session pages | harvest re-keys facts by **subject** (§7.2) |
| The knowledge base filled with docs about its own tooling | tooling docs stay out of the memory homes |

## 2. Observed harness behavior (canary, 2026-09-28)

Verified with hook-payload logging against Claude Code 2.1.284, headless `--input-format stream-json` (prompt → `/clear` → prompt → `/compact` → prompt):

| Hook | session_id | source / reason / trigger |
|---|---|---|
| SessionStart | A | `startup` |
| SessionEnd | A | `clear` |
| SessionStart | **B** (new; new transcript file) | `clear` |
| PreCompact | B | `manual` |
| SessionStart | B (same; same transcript file) | `compact` |
| SessionEnd | B | `other` |

Consequences this design is built on:

1. `/clear` mints a new session id and transcript → **a session is self-bounding at clears.**
2. Compaction keeps the id and transcript; both sides are observable → **compaction is a clean segment boundary.**
3. SessionEnd(clear) and SessionStart(clear) arrive back-to-back from one `claude` process → **clear lineage is linkable** (§4.3).
4. A nested `claude -p` launched from inside a session adopted the *parent's* session id, even with `CLAUDE_CODE_SESSION_ID` unset (observed in a cloud container; on a plain macOS machine the child gets a fresh id, §11.5) → **every child we spawn gets an explicit `--session-id`** (§7).

The two open questions this left (the compact offset, the pid across `/clear`) are confirmed, headless and on a plain machine (§11.3–11.4).

## 3. Principles

- **P1 — Logs are truth; JSON files are projections.** Every `.json` in the store is rebuildable from the `.jsonl` logs beside it (`session rebuild <sid>`). A torn or deleted projection is a cache miss, never data loss. **One exception:** `consumers.json` (§6.8). No log records an ack, so `rebuild` can't regenerate it; `SessionHandle.ack` writes it fsynced (file and directory) instead, since a lost ack re-harvests or re-exports work.
- **P2 — One writer per file.** Hooks append events. The projector (same process, right after the append) rewrites projections via temp + `os.replace`. The summarizer writes only its own artifact, then appends an event announcing it.
- **P3 — Reference, don't copy.** The transcript is never copied into the store. Segments point at it by path + byte range.
- **P4 — Metadata by default.** Free text (prompts, stderr) is off unless opted in, and when on is scrubbed (`scripts/redact.py` rules) and capped. Capping happens in `make_event`, so no caller can forget it; redaction joins it there — one choke point — when free-text capture ships (phase 2 moves `redact.py` into `lib/claudna/`).
- **P5 — Boundaries are observed, never inferred.** Only harness hook events open or close sessions and segments. Counters are derived from what exists on disk, never stored.
- **P6 — Fail open, bounded.** A store hook never blocks, never fails a session, and returns in well under a second. Heavy work detaches.
- **P7 — Everything is versioned.** Every event carries `v`; every projection and artifact carries `schema: "claudna.<name>/<major>"`.

## 4. Identity and boundaries

### 4.1 Units

| Unit | Identity | Opened by | Closed by |
|---|---|---|---|
| **Session** | Claude Code `session_id` | SessionStart `startup` \| `clear` \| `resume` \| `fork` | SessionEnd (any reason) |
| **Segment** | `(session_id, index)`, index 1-based | session open; SessionStart `compact` | next compact; session close |

A segment is a contiguous byte range of the session's transcript. A session with no compactions has exactly one segment. **The segment is the unit** — summaries, harvest cursors, export items, and vault evidence all address it by its canonical ref `<sid>:<seg>` (e.g. `3fbb…:2`).

Identity hierarchy, each level stable across a different boundary:

| Level | ID | Stable across | Source |
|---|---|---|---|
| bot | `(actor.fleet, actor.bot_id)` | restarts | Claudlobby env; null for interactive |
| chain | `chain_id` — the root session of a clear lineage | `/clear` | copied from the parent at `session.opened`; a session with no parent is its own root |
| session | `sid` | compaction, resume | Claude Code |
| segment | `seg`, int ≥ 1 | — (the unit) | derived: max existing + 1 |

### 4.2 Hook → store action

| Hook event | Store action |
|---|---|
| SessionStart `startup` / `resume` | `session.opened` (resume: reopen existing dir, open a new segment); `segment.opened`. If the previous segment is unsealed (a lost SessionEnd), `open_segment` seals it first, `sealed_by: "resume"`: at the new segment's start when the transcript is the same file, at the old transcript's size when the resume moved to a new one. That seal is then summarized like any other (§7.1). |
| SessionStart `clear` | `session.opened` with `parent_sid` from the clear link (§4.3); `segment.opened` |
| SessionStart `fork` | `session.opened` for the new session id (`--fork-session`, `/fork`, `/branch`; Claude Code before v2.1.214 reported these as `resume`); `segment.opened`. Lineage to the source session is a phase 3 canary. |
| UserPromptSubmit | `prompt.submitted` (segment events) |
| PostToolUse (Skill) | `skill.invoked` |
| PostToolUseFailure | `tool.failed` (failing calls fire this event, not PostToolUse, and only it carries the error field); `tool.interrupted` when `is_interrupt` (the user pressed Esc). The three activity hooks run `async` (phase 4). |
| PreCompact | `segment.sealed` — record end offset; start summarizer on that range. Idempotent: a second PreCompact (first was blocked) re-seals with the later offset. |
| SessionStart `compact` | `segment.opened` for index N+1, start = last seal offset. If no seal exists (missed PreCompact), `open_segment` seals first at the new start, `sealed_by: "compact"`. |
| SessionEnd | `segment.sealed` (final); `session.closed`; start summarizer; on `reason=clear` write the clear link. |

**Why cut at SessionStart(compact), not PreCompact:** PreCompact can fire without a compaction following (clauDNA's own `precompact-reflect.sh` blocks the first attempt by design). Sealing is safe to repeat; opening a segment is not.

**The directory is the holder.** There is no stored counter. Under an exclusive `flock` on the session dir, `next = max(existing seg-NNN) + 1`, and the new segment exists the instant its `mkdir` succeeds (atomic). Only the highest-index segment can be open, so "which segment do I append to" is the same lookup: `current = max(existing seg-NNN)`. A crash between `mkdir` and the `segment.opened` event leaves an empty dir that is still the correct current segment; `rebuild` projects it as `opened_by: "unknown"` (logs are never rewritten). A stored counter could disagree with the directories after a crash; a derived one cannot. `session.json.segments.open` caches the answer for readers but is never consulted by writers.

### 4.3 Clear lineage

SessionEnd(`reason=clear`) writes `links/<claude-pid>.json` naming the ending session. The pid is `$CLAUDE_PID`, which Claude Code exports to its hooks; an ancestor walk to the first process whose name contains `claude` is the fallback where it's missing. The next SessionStart(`source=clear`) from the same pid consumes it (reads, then deletes) and records `parent_sid`. The parent's `session.json` learns its child through a `session.child_linked` event appended to the parent's log. A link older than 60 s is ignored (stale). If no link is found, `parent_sid` is `null` — lineage is best-effort, never guessed.

Worker identity across a chain of sessions is `(actor.fleet, actor.bot_id)`. Clear links order sessions within a repo switch; restarts (process relaunch, SessionEnd without `reason=clear`) produce unlinked sessions, ordered by `opened_at` within the same bot. The store never guesses a `parent_sid` for a restart.

### 4.4 Hook stacking — a new role, not a contested one

#203 ruled that SessionEnd is Claudron's (`R-sync`) and "clauDNA adds no SessionEnd hook". The rule's purpose was that no role is duplicated. Claude Code fires every registered hook for an event, so co-registration is mechanically fine; what matters is roles. This spec adds a clauDNA-local role rather than contesting one of Claudron's. `R-record` is **not** a row in Claudron's session-loop table (`docs/CLI_CONTRACT.md`, "The four roles", held by a doc-parity gate): that table lists the roles that touch the knowledge layer, and `R-record` never does (invariant 1). So the table, its heading and its parity test stay as they are; what changes is clauDNA's own #203 rule (§11.7).

| Role | Content class | Owner | Events |
|---|---|---|---|
| `R-record` — the session store: boundaries, activity, segment summaries | behavior | **The front-end (clauDNA).** | SessionStart, PreCompact, UserPromptSubmit, PostToolUse (Skill), PostToolUseFailure, SessionEnd |

SessionStart (every source), PreCompact and SessionEnd (with a 5 s `timeout`) run synchronously. The three activity hooks — UserPromptSubmit, PostToolUse (matcher `Skill`) and PostToolUseFailure — run `async`. Skill telemetry (`telemetry-emit.sh`) is a separate async entry on PostToolUse and PostToolUseFailure, both matcher `Skill`.

`R-record` holds four invariants, so it can never collide with `R-sync` or `R-capture-prompt`:

1. **Never touches the vault or git itself.** No store hook runs `claudron`, sync or capture, so there is no race with Claudron's bounded `sync --push` at SessionEnd. The one path to the vault is the harvest a SessionStart hook may start, detached (§7.2). It writes only through `claudron capture`, which Claudron serializes with its own `sync`: every vault mutator holds Claudron's cross-process flock (`docs/CLI_CONTRACT.md`, concurrency). Claudron reads the store only by pulling through `session export`, on its own schedule.
2. **Never prompts, never blocks, emits no stdout.** The store's PreCompact handler is separate from `precompact-reflect.sh` (which holds `R-capture-prompt`) and only records a seal.
3. **Returns in < 100 ms.** Anything heavier (the summarizer) detaches. Claude Code does not reliably wait for SessionEnd hooks, so a slow hook is a lost one.
4. **Silent in children.** Exits 0 immediately under `CLAUDNA_SESSION_CHILD=1` (and Claudlobby's child marker once one ships — `CLAUDLOBBY_HOOK_CHILD` is proposed in [Claudlobby#1961](https://github.com/Claudfather/Claudlobby/issues/1961); none exists today), so no `claude -p` child records into — or summarizes — its parent. A nested `claude` that *inherits* its parent's session id (canary §11.5) can't touch the parent's session either. The open session records the `claude` process that opened it (`CLAUDE_PID`, which Claude Code exports to its hooks), and a hook from any other process is ignored, except a `resume`. A `startup`, `clear` or `fork` SessionStart that names a session the store already has, open or closed, is a child's and never reopens it; a `resume` always reopens, from any process. An entrypoint that differs from the recorded one still marks a child when no pid was recorded. A real child marker would still be the stronger signal where it exists.

## 5. Layout

```
${CLAUDNA_STATE_DIR:-~/.claudna}/
  sessions/
    <sid>/
      lifecycle.jsonl        # session-scope events (§6.2)          — truth
      session.json           # projection of lifecycle.jsonl (§6.4)
      summary.json           # deterministic rollup of segment summaries (§6.7)
      consumers.json         # export cursors per consumer (§6.8)
      seg-001/
        events.jsonl         # in-segment activity (§6.3)          — truth
        segment.json         # projection (§6.5)
        summary.json         # claude -p artifact (§6.6)
      seg-002/ …
  links/
    <pid>.json               # clear handoff, ephemeral (§6.9)
  harvest/
    lock                     # single-flight flock (§7.2)
    last_run.json            # the last run's report; its time is the debounce
    liveness.txt             # one line the SessionStart briefing shows
    held.jsonl               # blocks held back for the human digest (person facts)
  hooks/
    errors.log               # one JSON line per hook failure (no payloads)
    *.stderr                 # what a wrapper or worker couldn't log itself
    reflected-<sid>          # the pre-compact capture prompt's marker
```

`~/.claude/notes/` and Claude Code's own directories are out of bounds (CLAUDE.md). Directory mode `0700`, files `0600`.

**One activity stream, not a `failures.jsonl`.** Failures are `tool.failed` events in the segment's `events.jsonl`; `session failures` is a reader view. One stream keeps ordering intact (a failure is readable next to the prompt and skill call around it) and adds one file kind instead of N.

## 6. Data models

Schemas ship as JSON Schema (draft 2020-12) beside the code in `lib/claudna/session_store/schemas/`, one file per model below, with a golden fixture (logs + expected projections) in `tests/fixtures/session-store/`. The field tables here are the human-readable spec; the schema files are normative.

### 6.1 Shared types

| Type | Shape |
|---|---|
| `Timestamp` | RFC 3339 UTC, millisecond precision, `Z` suffix — `2026-09-28T17:04:05.123Z` |
| `SessionId` | string, as issued by Claude Code (UUID today; treat as opaque) |
| `SegIndex` | integer ≥ 1; directory name `seg-%03d` (widens past 999 without breaking sort for readers that parse the int) |
| `ByteRange` | `{ "start": int ≥ 0, "end": int ≥ start \| null }` — `end: null` means open |
| `TranscriptRef` | `{ "path": string, "range": ByteRange }` |
| `Actor` | `{ "kind": "interactive" \| "headless" \| "bot", "fleet": string \| null, "bot_id": string \| null, "bot_name": string \| null, "model": string \| null, "entrypoint": string \| null }` — `fleet`/`bot_id` from `FLEET_NAME`/`BOT_ID`, matching the plane's `bot:<fleet>/<BOT_ID>` alias |
| `Origin` | `{ "cwd": string, "repo": string \| null, "branch": string \| null, "head": string \| null }` — repo = `owner/name` from the git remote |
| `Text` | scrubbed string, capped per field (caps listed where used); `null` when capture is off |

### 6.2 Event envelope (`lifecycle.jsonl`, `events.jsonl`)

Every line in every log:

```json
{"v": 1, "ts": "2026-09-28T17:04:05.123Z", "kind": "segment.sealed", "sid": "3fbb…", "seg": 2, "data": { … }}
```

| Field | Type | Notes |
|---|---|---|
| `v` | int | envelope version; readers skip lines with an unknown major |
| `ts` | Timestamp | stamped by the writer, not the caller |
| `kind` | string | `<noun>.<verb-past>`; the registry below is closed — unknown kinds are skipped, not errors |
| `sid` | SessionId | |
| `seg` | SegIndex \| null | null for session-scope events that aren't tied to a segment |
| `data` | object | per-kind payload. Writers reject a key the registry doesn't name (so text caps, and later redaction, can't be bypassed); readers fold an extra key, so an older reader still reads a newer writer's log |

**Lifecycle kinds** (`lifecycle.jsonl`):

| kind | data |
|---|---|
| `session.opened` | `{ source: "startup"\|"clear"\|"resume"\|"fork", parent_sid: SessionId\|null, chain_id: SessionId, actor: Actor, origin: Origin, transcript_path: string\|null, claude_pid?: int ≥ 1\|null, harvest?: { enabled: bool, vault: string\|null } }`. `claude_pid` is the owning Claude Code process (§4.4 invariant 4); `harvest` is the session's own opt-in and vault, recorded at open (§7.2) |
| `session.child_linked` | `{ child_sid: SessionId }` |
| `session.privacy_set` | `{ private: bool, by: "user"\|"policy" }` |
| `segment.opened` | `{ opened_by: "session_open"\|"compact", start: int }` |
| `segment.sealed` | `{ end: int ≥ start, sealed_by: "precompact"\|"compact"\|"session_end"\|"resume"\|"abandoned", trigger: "manual"\|"auto"\|null }` |
| `segment.retired` | `{ reason: "acked"\|"age" }` — appended by retention (§9) before the segment's directory is removed |
| `summary.requested` | `{ job_id: string }` |
| `summary.completed` | `{ job_id: string, artifact: "seg-NNN/summary.json", input_sha256: string, duration_ms: int }` |
| `summary.screened` | `{ job_id: string, blocks_dropped: int, strings_withheld: int, patterns: string (≤200), fingerprints: string (≤400) }` — what the instruction screen (`lib/claudna/screen.py`) took out before the summary was written: counts, comma-joined pattern ids, 12-hex fingerprints, never the text |
| `summary.failed` | `{ job_id: string, error: string (≤200), retryable: bool }` |
| `summary.skipped` | `{ reason: "private"\|"disabled"\|"trivial"\|"headless"\|"no_transcript" }` |
| `session.closed` | `{ reason: "clear"\|"resume"\|"logout"\|"prompt_input_exit"\|"other"\|"abandoned" }`. `abandoned` is the store's own (`seal`, the sweep: a session whose SessionEnd never ran); a SessionEnd payload can't claim it |

**Activity kinds** (`seg-NNN/events.jsonl`):

| kind | data |
|---|---|
| `prompt.submitted` | `{ prompt_id: string\|null, chars: int, text?: Text (≤500, off by default) }` |
| `skill.invoked` | `{ skill: string, args_chars: int, ok?: bool\|null, duration_ms?: int\|null, prompt_id?, tool_use_id? }` |
| `tool.failed` | `{ tool: string, signature: string (≤200), exit_code: int\|null, duration_ms?, prompt_id?, tool_use_id? }`. `signature` is a stable grouping key (tool + the first real error line, normalized and redacted), computed at write time so readers group without re-parsing. **No copy of the command or its stderr** (phase 4 decision): `tool_use_id` points at the call in the transcript, which holds both. |
| `tool.interrupted` | `{ tool: string, duration_ms?, prompt_id?, tool_use_id? }`. The user stopped the call: counted as `interrupts`, never as a failure. |

### 6.3 Why two logs

`lifecycle.jsonl` is low-volume and session-scope (dozens of lines); it is what `session.json` projects from and what the export cursor reads. `events.jsonl` is per-segment and higher-volume. A segment's activity log is frozen once it is superseded (a later segment opened) or its session is closed; the store refuses activity anywhere but the current segment of an open session. A *sealed but current* segment still accepts activity — a blocked compaction seals at PreCompact, work continues, and the next PreCompact re-seals with a later end. Adapters pass `seg=None` so the current segment is resolved under the session lock. Readers that only need structure never touch activity.

### 6.4 `session.json` — projection of `lifecycle.jsonl`

```json
{
  "schema": "claudna.session/2",
  "sid": "3fbb…",
  "parent_sid": "533c…",
  "chain_id": "533c…",
  "children": [],
  "status": "open",
  "private": false,
  "agent_cli": "claude",
  "actor":  { "kind": "interactive", "bot_name": null, "model": "…", "entrypoint": "cli" },
  "origin": { "cwd": "/…/clauDNA", "repo": "Claudfather/clauDNA", "branch": "main", "head": "abc123" },
  "transcript_path": "/…/3fbb….jsonl",
  "opened_at": "…", "opened_by": "clear",
  "closed_at": null, "close_reason": null,
  "segments": { "count": 2, "open": 2, "retired": 0 },
  "summary": { "segments_done": 1, "segments_pending": 1, "segments_failed": 0, "segments_skipped": 0 },
  "projected_from": { "lines": 7, "bytes": 1432, "skipped": 0 }
}
```

`status`: `open` → `closed`. `segments.open` is the open segment's index or `null`; `segments.retired` counts segments retention has removed (§9). `projected_from` is a watermark: `session.json` carries the lifecycle log's (lines, bytes, skipped), each `segment.json` its activity log's. Before re-folding, a write compares the watermark with the log's size before its append; a mismatch means an earlier refresh never ran (a killed hook), and the store rebuilds. Every write checks `session.json` against the lifecycle log — activity appends included — so a lost lifecycle refresh is healed by the next write to either log; a lost activity refresh is healed by the next activity append. Until a write comes, `check` reports each projection whose watermark lags its log as a warning.

`agent_cli` is the first `session.opened`'s (`claude` for a log written before 0.27). `claudna.session/1` is an older tag: readers fold it from the log, `check` warns, the sweep rewrites it once (as for `claudna.segment/1`).

### 6.5 `segment.json` — projection

```json
{
  "schema": "claudna.segment/2",
  "sid": "3fbb…",
  "index": 2,
  "status": "sealed",
  "opened_at": "…", "opened_by": "compact",
  "sealed_at": "…", "sealed_by": "session_end",
  "transcript": { "path": "/…/3fbb….jsonl", "range": { "start": 48211, "end": 90377 } },
  "counts": { "prompts": 4, "skills": 2, "failures": 1, "interrupts": 0 },
  "summary": { "status": "done", "job_id": "…" }
}
```

`status`: `open` → `sealed`. A sealed segment whose `range.end` changes (re-seal after a blocked compaction) is still `sealed`; `sealed_at` moves. `summary.status`: `none` | `pending` | `done` | `failed` | `skipped` (private, or summaries disabled).

### 6.6 `seg-NNN/summary.json` — summarizer artifact

The one LLM-authored file. Written atomically by the summarizer; the matching `summary.completed` event makes it visible to readers and export. Two parts: the **journey** (the segment's own story — stays local, used by readers and resume) and **blocks** (typed facts — what harvest consumes).

**Shipped in phase 2 as `claudna.segment-summary/1`** (`schemas/segment-summary.schema.json`), a subset of the target below. `journey`, `blocks` and `procedures` sit at the top level, as shown. `input` carries `transcript_path`, `range`, `sha256` and `turns`, and `producer` adds `cost_usd`. Blocks have no `id`, `evidence`, `about`, `observed_at` or `open` yet, and there is no `artifacts` object and no `prior_rollup_sha256`. Those arrive with the rollup (§6.7) and activity events (phase 4). The model's part of the file, `$defs.model_output`, is passed as is to `claude --json-schema`.

```json
{
  "schema": "claudna.segment-summary/2",
  "sid": "3fbb…", "index": 2,
  "input":    { "range": { "start": 48211, "end": 90377 }, "sha256": "…", "prior_rollup_sha256": "…" },
  "producer": { "model": "claude-haiku-…", "prompt_version": "segment-summary/2", "duration_ms": 8123 },
  "journey": {
    "title":   "Wire PreCompact seal into session store",
    "intent":  "…",
    "outcome": "shipped | partial | blocked | abandoned",
    "arc":     [{ "step": "tried X", "result": "failed: …" }, { "step": "switched to Y", "result": "worked" }],
    "done":        [{ "text": "…", "evidence": ["commit:abc123"] }],
    "in_progress": [{ "text": "…" }],
    "next":        [{ "text": "…", "due": null }]
  },
  "blocks": [
    {
      "id": "3fbb…:2:1",
      "home": "entity | concept | person | project | decision | practice",
      "subject_hint": { "name": "Acme block explorer API", "aliases": ["…"], "kind": "api", "context": "…" },
      "claim": "Serves stale data for old heights; verify by sampling heights at UTC midnight.",
      "section_hint": "Behavior & gotchas",
      "asserted_by": "user | agent | tool",
      "observed_at": "…",
      "evidence": [{ "range": { "start": 51002, "end": 51990 } }],
      "about": ["…other subject names…"],
      "tags": ["tech:…"],
      "open": { "due": null }
    }
  ],
  "procedures": [{ "text": "…", "why": "…" }],
  "artifacts": { "prs": { "state": "value|none_observed|unknown", "items": [] }, "commits": { "state": "…", "items": [] }, "files": { "state": "…", "items": [] } }
}
```

- **No durability flag.** Extraction classifies, it never filters; whether a fact matters is decided at harvest with the vault in view. Because segments persist until acked and summaries carry `prompt_version`, extraction is **replayable** — an improved prompt can be re-run over history, for as long as the transcript exists. Claude Code deletes transcripts after `cleanupPeriodDays` (30 by default, the same as §9's cap), so replay and summarizer retries are bounded by the transcript's life; `summary.skipped` gains a reason for a missing transcript when the summarizer ships.
- **`asserted_by` weights, it doesn't gate.** A user-stated fact is trusted more than an agent's inference; neither is dropped.
- **`open`** marks open threads (follow-ups with an optional `due`) that a later segment can resolve.
- **`procedures`** are agent-executable how-tos. They are not vault material — they route back to clauDNA as skill-improvement proposals.
- **Empty must be earned:** a list is omitted when empty, never filled with a placeholder; an empty `journey.done` with commits observed in the segment fails validation. Deterministic fields (`artifacts`) come from observed events, never the model, and carry an explicit `state`.
- Resume state (`in_progress`, `next`) stays in the local store; harvest ignores it.
- `input.sha256` makes the summarizer idempotent; `prior_rollup_sha256` makes it reproducible.

### 6.7 `sessions/<sid>/summary.json` — deterministic rollup

No LLM. Recomputed from the `done` segment summaries on every `summary.completed`. Merge rules are declared once, as data:

| Field | Rule |
|---|---|
| `journey.title`, `journey.intent`, `journey.outcome` | latest segment's |
| `journey.arc`, `journey.done`, `blocks`, `procedures` | union across segments, dedup on normalized text (blocks: on `home` + subject + claim), keep `from_seg` |
| `journey.in_progress`, `journey.next` | latest segment's only |

```json
{ "schema": "claudna.session-summary/2", "sid": "…", "through_seg": 2, "fields": { … }, "segments": [1, 2], "screened": true }
```

**As built (phase 6):** it's also recomputed on every retirement (a retired segment's summary is archived in `sessions/<sid>/summaries/` and still counts) and by `session_store rebuild <sid>`. With nothing left to roll up, the file is removed rather than left stale. `session show` computes a missing rollup in memory; `session list` reads the file only.

### 6.8 `consumers.json` — export cursors

```json
{
  "schema": "claudna.consumers/1",
  "sid": "…",
  "consumers": {
    "claudron": { "through_seg": 1, "acked_at": "…" }
  }
}
```

Written only through the store's `SessionHandle.ack(consumer, through)`, under the session lock; a cursor never moves back. Two callers: harvest (consumer `harvest`, §7.2) and, later, `session export --ack <consumer> --through <seg>`. The store never deletes a segment that any registered consumer hasn't acked, unless it exceeds the hard age cap (§9).

### 6.9 `links/<pid>.json` — clear handoff (ephemeral)

```json
{ "schema": "claudna.clear-link/1", "pid": 4242, "sid": "533c…", "chain_id": "533c…", "ts": 1790615045.123 }
```

`ts` is a float epoch (`time.time()`), not a `Timestamp`: the link only needs an age check. Consumed and deleted by the next SessionStart(clear) from that pid; ignored after 60 s; stale links are deleted by the detached unclosed-session sweep.

## 7. Summarizer and harvest

### 7.1 Summarizer

A pure function of `(segment range, prior rollup) → segment summary`, run out of band.

- **When:** once per seal, from the hook that knows the seal is final. SessionEnd spawns for its own seal. A PreCompact seal is spawned from the SessionStart(`compact`) that follows, because the capture hook blocks the first PreCompact attempt of each compaction and both attempts seal: spawning at PreCompact paid twice. A seal the store made itself (a resume after a crash, a missed PreCompact) is also spawned from SessionStart. An `abandoned` seal is spawned by whoever closed the session: the sweep, or `session_store seal <sid>`, which applies the gates below with the environment of the shell that ran it (its `CLAUDNA_SESSION_SUMMARY` counts; the harvest opt-in is still the one the session recorded at open). In each case, only a sealed segment whose summary status is still `none` is spawned.
- **How it runs:** the hook applies the gates below. If one is closed, it records `summary.skipped` itself and starts nothing. Otherwise it spawns a detached worker (`session_store summarize <sid> <seg>`) in its own session (Python's `start_new_session`, which works on macOS; the `setsid` binary does not ship there), so a group kill of the hook tree doesn't reap it. The hook returns immediately. The worker, not the hook, appends `summary.requested` when it starts the model call, so a skip never passes through `pending`.
- **Child isolation:** the worker runs `claude -p` with an explicit fresh `--session-id` and `--no-session-persistence`. It passes `--setting-sources ""`, so no settings-registered hook fires in the child, clauDNA's or any other plugin's (Claudron's SessionEnd sync included). It also passes `--tools ""` and `--strict-mcp-config`, and sets `CLAUDNA_SESSION_CHILD=1`. The instructions go in `--system-prompt` and the transcript on stdin as untrusted data. `--json-schema` holds the output to `$defs.model_output`, the result is validated again before the write, and a hard timeout applies. `--bare` would isolate further but refuses OAuth, which breaks subscription users.
- **Input:** the segment's transcript range, streamed and reduced to user/assistant prose (tool I/O, thinking and sidechains dropped), with injected context blocks stripped (including `<bash-input>`/`<bash-stdout>`/`<bash-stderr>`, which is how Claude Code records `!cmd` I/O as user text), redacted with `claudna.redact` turn by turn before the input cut, and framed as untrusted data. Phase 2 sends no prior rollup; it arrives with §6.7.
- **Idempotent:** skips, before reading anything, when a `done` summary already covers the same transcript range with the same prompt version (the transcript is append-only). One worker per segment: a second finds the segment's lock taken.
- **Gates:** skipped (`summary.status: skipped`) if the session is private, if `CLAUDNA_SESSION_SUMMARY=0`, if it is headless or a bot, if it didn't opt into harvest at open (`disabled`: in phase 2 a summary has no other reader), if the transcript is gone (`no_transcript`), or if the slice holds no user turn (`trivial`). `CLAUDNA_SESSION_SUMMARY=1` overrides both the headless/bot gate and the harvest opt-in; only privacy, a missing transcript and a trivial slice still skip.
- **Default:** off until a reader exists: on only for interactive sessions (`cli`, `claude-vscode`, `claude-desktop`; an allowlist, so any new automation entrypoint is headless) that opened with `CLAUDNA_HARVEST=1`. **Off for headless sessions** either way — every script, CI job, and other tool's `claude -p` would otherwise spawn a Haiku call at exit. Claudlobby sets `CLAUDNA_SESSION_SUMMARY` per bot (bots compact after every task, so they pay per task).
- **Output:** the model's part is validated against `$defs.model_output` on its own, every string in it is redacted (the model can echo a secret the input redaction missed), and provenance (`sid`, `index`, `input`, `producer`) is merged last, so no key the model returns can stand in for it. Any worker exception is recorded as `summary.failed` (retryable), so harvest can retry it.

### 7.2 Harvest — from session store to vault

Harvest is the librarian: it turns segment **blocks** into vault notes organized by **subject**. It is judgment (a `claude -p` pass), so it is clauDNA's; Claudron supplies mechanical pipes and never reads transcripts or store files ([Claudron#200](https://github.com/Claudfather/Claudron/issues/200)). **The pipes ship in Claudron 0.7.0** (`subjects`, `resolve`, `amend`, `--run-id` and `revert-run`, and trust-aware reads, which withhold session- and web-sourced drafts by default instead of an `--include-drafts` flag). Harvest uses them through its deterministic filing slice (below); the plan model and the risk tiers are still to come.

**Pipeline, per unharvested sealed segment:**

1. `claudron subjects` / `claudron resolve` return candidate subjects (home, aliases, sections, maturity) for each block's `subject_hint`.
2. The harvest model emits a **plan** of edits: attach to subject X section S · add evidence to an existing fact · create a subject · supersede · already-known · park as ambiguous · inbox.
3. The plan is applied through Claudron's section-targeted writes with the run id in every commit's trailer; `revert-run` undoes the whole run as **one revert commit**. Every write lands `maturity: draft`.
4. The segment is acked (`consumers.json`) only after apply succeeds, so a crash re-harvests rather than skips.

**Risk tiers:**

| Tier | Actions | Handling |
|---|---|---|
| Low (additive) | fact → existing subject section; evidence on an existing fact; tag reuse; close an explicitly resolved open thread | auto |
| Medium (structure) | new subject; split a section into a `part_of` child; alias add; tag `proposed → active` | auto once an evidence threshold holds |
| High (destructive / sensitive) | supersede or contradict a trusted fact; merge subjects; any other-person fact bound for `_shared/`; new kinds; tag deprecation | human digest |

- **New subject threshold:** user-asserted, **or** recurring across ≥ 2 distinct sessions, **or** a proper name plus one corroboration. Otherwise the block waits in its home's inbox; inbox items unreinforced for ~90 days are archived (searchable, not ranked, never deleted).
- **Ambiguous:** parked and retried on later runs; to the human digest after 3 unresolved attempts.
- **User-asserted contradictions** supersede automatically (the old fact moves to History). A draft never supersedes a trusted fact.
- **Drafts are untrusted:** Claudron's `lookup` returns trusted notes only by default; the recall brief shows drafts in a separate, capped "Unverified" block with provenance. Direct filesystem reads can't be blocked; clauDNA guidance routes vault reads through `claudron`, drafts carry a banner line, and Claudlobby read-denies draft paths for bots.
- **Promotion** (`draft → verified → canonical`) stays human: a digest capped at ~5 items, most-reinforced first, surfaced as one SessionStart line, never blocking.

**Phase 2 ships a thin slice** (`harvest.py`). It has no subject resolution, plan model or risk tiers: each block of a summarized segment is one `claudron capture --stdin --json`, scoped to the session's repo, landing as a draft tagged `origin:session-harvest`, with its session and segment named after the claim. `person` blocks are held in `harvest/held.jsonl` for the digest, and private sessions are never harvested. Only **final** segments are taken: ones with a later segment, or in a closed session. The current segment can still be re-sealed and re-summarized, and an index cursor would miss that. A segment is taken whole or not at all (at most 10 captures a run, but a first segment always fits). The cursor passes skipped segments and stops at one still pending or unreadable. A summary left `pending` 15 minutes past its request, or failed with a retryable error, is re-run in the harvest process, up to 3 attempts per segment and 2 per run. After that, harvest gives up on the segment, reports it, and moves on. Attempts are counted since the segment's last seal. A final segment still at `none` 15 minutes after its seal (the spawn failed, or the hook or worker died first) is stranded too, and a `done` summary whose range ends before the last seal is treated as pending, so a re-sealed tail is never skipped.

**Filing slice** (`filing.py`, needs Claudron ≥ 0.7.1's `subject-filing` with `subjects`, `amend`, `runs` and `trust-aware-reads`). Still no model. Each block's `subject_hint` is resolved within the session's project (its name, aliases and the bannered `(unverified) <name>`). The claim goes in as `amend append_fact` (section from `section_hint`, else `Facts`; evidence `session:<sid>:<seg>`; `expect_trust: external`) only when every exact match is a subject note harvest wrote (a session draft tagged `harvest:subject`). With no exact match, harvest creates a subject draft and appends the fact to it. Any other exact match gets a per-claim draft, so harvest never edits a reviewed or authored note. Whatever Claudron declines falls back to a per-claim draft. This covers the low-risk tier for harvest's own subjects: a fact into its subject draft, and evidence on an existing fact. Filing into reviewed subjects, supersede, merge, the new-subject threshold and ambiguity parking wait for the plan model. Every write in a run carries one run id, so the run is undone with `revert-run`. That is one commit per write, not per run: Claudron commits each write at once (durability, Claudron#157) and reverts a run as one commit. It refuses the revert when a later edit conflicts, and the clauDNA ledger keeps its lines either way. The digest lists every claim in a note and promotes a note only at the revision the person saw. On an engine with `memory-homes` (Claudron#200 §2) a block is filed under its home's own type and `kind`, and its fact goes only under one of that home's sections.

Since the #373 review, harvest is also **per session**: it runs only for sessions that opened with `CLAUDNA_HARVEST=1`, captures each into the vault that session recorded (`--vault`, with `$CLAUDRON_VAULT_PATH` removed from the child), skips sessions outside a git repo (Claudron would file them in `vault.shared`), and prefixes each draft's title with `(unverified)`, since Claudron's own SessionStart brief shows drafts with only a `(knowledge, draft)` label. A run that found nothing debounces for 1 hour, not the full interval, and every run writes `last_run.json` even when a session raises.

**Scheduling:** SessionStart, detached, after Claudron's `sync --pull` (fresh vault; outside SessionEnd's push window). Guards: a non-blocking `flock` on `~/.claudna/harvest/lock` (single-flight per host), a debounce in `~/.claudna/harvest/last_run.json` (run only if ≥ `CLAUDNA_HARVEST_INTERVAL_H` hours, default 6, since the last run started; 1 hour when that run found nothing to take), and a cursor per segment. The SessionStart also needs `CLAUDNA_HARVEST=1` in its own environment and `claudron` on `PATH`. It doesn't check for unharvested segments first; the detached run finds out, and an empty run is what earns the short debounce. There is no harvest skill verb: the run is the detached `session_store harvest` worker the SessionStart starts when one is due, and `session_store harvest --force` runs it by hand, past the debounce. `/claudna:capture --review` is the person's step after it, over the digest. Liveness — last run, last error — is shown on every SessionStart.

## 8. Readers and the export door

Readers are verbs on the existing `/claudna:session` skill (no new skill), backed by one stdlib script:

| Verb | Shows |
|---|---|
| `session list [--since] [--repo] [--bot]` | sessions, newest first, with status and segment counts |
| `session show <sid>` | session.json + rollup, lineage (parent/children) |
| `session timeline <sid>` | merged lifecycle + activity, ordered |
| `session failures [<sid>] [--group]` | `tool.failed` events, grouped by `signature` |
| `session rebuild <sid>` | regenerate every projection from logs |
| `session export …` | the Claudron door (below) |

**Export contract** (the only surface Claudron pins; drift-gated on their side per Claudron register rule R3):

```
session export --consumer claudron [--since-seg N] --json
session export --consumer claudron --ack --sid <sid> --through <seg>
```

Returns an envelope: `{ schema: "claudna.export/1", items: [{ sid, seg, session: <session.json subset>, summary: <segment summary> }], next: <cursor> }`. Claudron reads through this command and never parses the store's files — the storage layout stays clauDNA's to change; only the export envelope is contract.

## 9. Retention

- A segment is deletable once every registered consumer has acked it, or once it passes the hard cap (default 30 days), whichever comes first. **As built (phase 6), owner-approved 2026-09-30:** an acked segment also waits a 7-day floor (`CLAUDNA_RETAIN_ACKED_DAYS`), because harvest acks at once and would otherwise erase recent history. The rollup keeps what a retired segment summarized. A consumer is registered for a session by its first ack, so one that never ran holds nothing back. The exception, owner-decided 2026-10-01: a session opened with harvest enabled registers harvest from its first segment, so its segments wait for harvest even before harvest's first ack.
- **An index is never reused.** `open_segment` numbers one past every index the session has ever named (directories *and* `segment.opened` events), so a new segment can't inherit a deleted one's lifecycle events, and export watermarks (`through_seg`) stay monotonic. When retention ships (phase 6) it records each deletion as a `segment.retired` lifecycle event before removing the directory, so a deletion is visible in the log rather than inferred from a missing directory.
- Sessions with no registered consumers use the age cap alone.
- Sweeping is started by SessionStart (one marker `stat`), and runs detached and debounced (at most every 6 hours) in the unclosed-session sweep. Never at SessionEnd.
- Private sessions are swept on the same rules; they are never exported.

## 10. Implementation shape

- **Language and location:** stdlib Python ≥ 3.9 (stock macOS `/usr/bin/python3`; CI runs 3.12 — a 3.9 CI leg lands with the first hook, see §11), the package `lib/claudna/session_store/`, called by thin `plugin-hooks/*.sh` wrappers in the directory form, `python3 "${CLAUDE_PLUGIN_ROOT}/lib/claudna/session_store" <verb>`. Not `python3 -m`: hooks run in the user's project, and `-m` puts the current directory first on `sys.path`, so a project's `json.py` would shadow the stdlib (`-P` fixes that only from 3.11, above the floor). The store is POSIX-only (`fcntl`). `lib/` is runtime only — stdlib-only imports, strictly downward layering inside a package, and a single `sys.path` shim at the entry point, each gated by `tests/test_runtime_layout.py` (rules: `lib/CLAUDE.md`). No third-party runtime deps.
- **Hosts:** the core (`paths`, `fsio`, `events`, `project`, `store`) is host-agnostic; only the hook adapter that maps a host's events onto store events is Claude Code-specific. The Cursor manifest ships no hooks, so on Cursor nothing is recorded — readers and harvest report "no session store on this host" rather than failing. A Cursor adapter can land later without touching the core.
- **Modules:** `paths` (layout, id validation) · `fsio` (private dirs, atomic JSON, JSONL append/read, locks) · `transcript` (a transcript range as prose) · `schema` (stdlib JSON Schema subset) · `events` (kind registry) · `project` (log → projections, `rebuild`, `refresh`, session facts and the summary gate) · `store` (the write API) · `summarize` (the worker, phase 2) · `harvest` (the thin slice, phase 2) · `boundaries` (hook → action table in §4.2, phase 2) · `cli`. The redactor is `lib/claudna/redact.py`, shared with `scripts/redact.py`. Later phases add `readers` and `export`. Each module owns one concern; the hook table is data, not branching.
- **Validation:** JSON Schemas in `lib/claudna/session_store/schemas/`, checked by `schema.py` — a stdlib JSON Schema subset that raises on any keyword it doesn't implement, so a schema can't silently ask for an unchecked rule. Tests pin a golden fixture byte-for-byte, a rebuild round trip, and incremental-equals-full refresh; drift gates keep the schemas and the registry in step (every kind fits the envelope's kind pattern, projection vocabularies match registry choices, one timestamp pattern everywhere, only supported keywords at every schema node). `check <sid>` runs the same validation on a live store, including placement (each event in the right session, log, and segment).
- **`telemetry-emit.sh`:** stays as the telemetry gate. It checks `CLAUDNA_TELEMETRY=1` and calls the store's `telemetry` verb (`telemetry.py`), which decodes the Skill payload with the same code as `skill.invoked` and prunes its own file. It has its own hook entry so it works with the store off (phase 4 plan, decision 2).

## 11. Open questions and decisions

1. **State dir default — decided 2026-09-30: `~/.claudna/`.** It must be absolute: a relative `CLAUDNA_STATE_DIR` is rejected, so the store can't land inside a repo. It is visible to Claudron and Claudlobby outside Claude Code, and it survives plugin updates and uninstall (SETUP_GUIDE documents manual cleanup). `${CLAUDE_PLUGIN_DATA}` was rejected because uninstall deletes it and it can only be resolved inside Claude Code. `$CLAUDNA_STATE_DIR` still overrides the default.
2. **Prompt text capture — decided 2026-09-30: off by default for everyone, opt-in with `CLAUDNA_CAPTURE_PROMPTS=1`.** By default `prompt.submitted` carries the time and `chars` only. The summarizer reads the transcript, so summaries and harvest come out the same either way; stored text would only make timelines nicer, at the cost of a second copy of what was typed. When capture is opted in, the text is redacted at `make_event` (P4) and capped at 500 chars. Bots gain nothing from it, because the plane already holds their prompts.
3. **Compact offset canary** — confirm PreCompact's transcript size equals the offset where post-compact content begins. **Confirmed** headless and on a plain macOS machine (the phase 3 plan's canary table; `scripts/session_canary.py`).
4. **Pid stability across `/clear`** — the clear link (§4.3) assumes the same `claude` pid; confirm with a hook that records the `claude` pid, not the hook shell's. **Confirmed** the same way, `$CLAUDE_PID` and the `ps` walk both.
5. **Nested session-id inheritance** — **container-only.** In a cloud container a nested `claude -p` takes its parent's id; on a plain macOS machine it gets a fresh one (same table). The guard stays, because containers and bots are where it happens; `scripts/session_canary.py` re-checks it, asking the guard about every child event. Bot workers are unaffected (Claudlobby never resumes; every launch is fresh), but every `claude -p` *child* — ours and Claudlobby's digest — gets an explicit `--session-id` and a hook-suppression marker ([Claudlobby#1961](https://github.com/Claudfather/Claudlobby/issues/1961)).
6. **Claudron pull verb** — Claudron-side work; this spec defines only the door it calls.
7. **#203 — decided 2026-09-30: reversed.** `R-record` is ratified as a clauDNA-local SessionEnd role (§4.4). #203's only stated reason was the role split, and `R-record` duplicates no role: it never touches the vault or git, never blocks, and returns fast. The phase 2 hooks PR updates `SETUP_GUIDE.md` §7.4. Claudron's session-loop table needs no amendment, because `R-record` owes the knowledge layer nothing.
8. **Memory homes and tag registry** — Claudron schema work ([Claudron#200](https://github.com/Claudfather/Claudron/issues/200)); block `home` values track it.
9. **Python floor for hooks — shipped with phase 2.** The store runs unchanged on 3.9 (stock macOS), and `lib/CLAUDE.md` names the floor. The `runtime-floor` CI leg runs `make test-runtime` (the store, hook, summarizer, harvest, redact, layout and hook-script suites) on 3.9 with pytest 8.4.2, the last release that supports it. The layout gate falls back to a stdlib list read from the interpreter's own stdlib directory when `sys.stdlib_module_names` (3.10+) is missing, so on the floor leg it judges imports against the floor.
11. **Hook cost on slow storage — decided 2026-09-30: fsync lifecycle events only.** On an SD card the fsync dominates: a reviewer measured a median of 32 ms, p95 of 154 ms and a worst case of 3.5 s per append on a loaded Raspberry Pi, where interpreter start plus import alone takes ~100 ms. Lifecycle events (opens, seals, close, summary jobs) are a handful per session and fix the byte ranges, so each is fsynced. Activity appends are not fsynced; a crash can lose at most a few tallies, which are derived counters. The SessionEnd hook entry sets an explicit `timeout` of 5 s, since SessionEnd hooks otherwise share a 1.5 s budget. `fsio.append_jsonl` gains a `durable` flag in phase 2, when the first hook is wired.
10. **Skill contract and `lib/`** — `SKILL_CONTRACT.md` §1.1 and its validator know bundled scripts only as `scripts/<name>`. The first skill text that calls `lib/` (the `/claudna:session` readers, or `redact.py`'s move) extends the contract and the validator together.

## 12. Phasing

The loop closes first; everything else broadens a loop that already works.

1. **Store core** — `store`, `events`, `project`, schemas + fixtures, `rebuild`. No hooks wired.
2. **Thin vertical slice** (shipped 2026-09-30) — the minimum that proves the loop end to end: SessionStart / PreCompact / SessionEnd boundaries → segment summary with `journey` + `blocks` → harvest (one capture per block; the plan model waits on Claudron#200) → one draft note written through Claudron (today's `claudron capture` until [Claudron#200](https://github.com/Claudfather/Claudron/issues/200)'s pipes land) → visible in the recall brief's Unverified block. Ugly is fine; closed is required. Includes the liveness line.
3. **Boundaries, complete** — clear lineage, `chain_id`, child isolation (done early, in #373), unclosed sessions closed as `abandoned` by `session seal <sid>` and a detached `session sweep`. Canaries for §11.3–11.4. Plan: `documentation/plans/2026-09-30-session-store-phase-3.md`.
4. **Activity** — `prompt.submitted`, `skill.invoked`, `tool.failed`, `tool.interrupted`; `telemetry-emit.sh` migrated into the store (`telemetry.py`). Plan: `documentation/plans/2026-09-30-session-store-phase-4.md`.
5. **Harvest, complete** — risk tiers, inbox + ambiguous queues, evidence counting, `revert-run`, the promotion digest (`/claudna:capture --review`). **Built, the clauDNA side:** the harvest ledger, evidence counting and the promotion digest. Built on Claudron 0.7's pipes: subject filing, section writes and `revert-run` (the filing slice, §7.2). Still to come: the plan model, risk tiers and the queues. Plan: `documentation/plans/2026-09-30-session-store-phases-5-7.md`.
6. **Readers + export** — `list`, `show`, `timeline`, `failures`; the export envelope and acks; retention sweep. **Built**, with the §6.7 rollup.
7. **Ops log** — `~/.claudna/runs/` and per-session ops records, mirroring `.claudron/`. **Built:** `runs/runs.jsonl`, one record per background run. Per-session history is the lifecycle log.
