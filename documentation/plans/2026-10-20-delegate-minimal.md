---
title: Minimal cross-provider delegation with existing session history
type: plan
status: proposed
owner: clauDNA
created: 2026-10-20
tags: [delegation, session-store, cleanup]
---

# Minimal Delegate Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task when execution is authorized. Native implementation is recommended; do not introduce a reviewer or worker per checklist item. Checkboxes track deliverables, not a requirement to add a test for every step.

**Goal:** Run one explicitly authorized cross-provider task in an existing workspace, connect it to the parent's session history, and automatically release disposable bookkeeping without risking user work.

**Architecture:** A small stdlib launcher owns one foreground process and bounded output. It records history through the existing session store, reuses its parent/child event, and keeps one temporary operational record. The parent owns code review and acceptance; delegate never creates, integrates, or removes a worktree.

**Tech stack:** Existing Python 3.9+ stdlib runtime, session-store APIs, native Claude/Codex CLIs, existing Git workspace, pytest and `make check`. No new runtime dependency or hosted service.

**Spec:** The October 11 delegate design and simulation in this chat, revised by the constraints below. This document is self-contained and supersedes that draft's broader worktree, resume and recovery-management proposals for v1.

## Summary

Ship a narrow, synchronous delegation skill. A successful invocation leaves code in the same caller-owned workspace, a provider-qualified child reference and result in the existing session history, and no retained brief, transcript copy, turn-log directory, or checkout. Cleanup happens in the launcher before it returns, with a small retry on subsequent workflow entry/session start for interrupted cleanup.

The model's answer and vendor availability cannot be made 100% deterministic. The implementation must make its own state transitions deterministic, test them without a model, and stop on unsupported or ambiguous observations. If the native CLI cannot supply the necessary identity/completion evidence without bypassing controls, do not enable that adapter. Do not build inference or retries to conceal the gap.

## Evidence and baseline

Plan baseline: current upstream main `bfeee6a2f8bbbfe62c5496d8524267425a30d001`, 2026-10-19, plugin v0.30.0. This working checkout is older (`686b407`, v0.19.0). Execution must start from fresh main; do not transplant this implementation into the old checkout.

- `session_store/events.py`: `session.opened.agent_cli` accepts Claude/Codex; the external identity is `(agent_cli, session_id)`. `session.child_linked` currently carries only `child_sid`.
- `lineage.py` / `boundaries.py`: automatic parent/child links currently describe `/clear` continuations. Preserve their meaning and chain IDs.
- `host_claude.py` / `host_codex.py`: both host adapters now exist. Do not reimplement host discovery or invent a Codex identity environment variable; the native hooks' October 16 measurements found none.
- `store.py`: lifecycle appends are locked and durable. Session-level lifecycle events can be appended after close; activity events cannot. A late delegation result can therefore be recorded without reopening the parent or inventing another log.
- `readers.py`: existing `show` and `timeline` are the history surfaces. `fsio.py` supplies private files, durable atomic JSON writes and advisory locks.
- `harvest.py`: Claudron is reached through the existing opt-in knowledge flow. Delegation history is not a vault note or a second transcript store.
- Installed CLI help inspected without model calls: Claude Code 2.1.304; Codex CLI 0.162.1. Both expose noninteractive structured output and stdin prompts. This proves parser surfaces only, not authentication, policy preservation, or runtime success.

## Global constraints

- One foreground delegation at a time per clauDNA state root. A fixed local slot is intentional v1 scope, not a queue.
- Reuse an explicitly caller-owned workspace. For edits, require a clean Git index/tracked/untracked baseline and exclusive handoff while the worker runs. Dirty prerequisites, concurrent work and worktree creation remain with the caller's existing workflow.
- Read-only tasks use actual provider read-only controls. A label in the brief does not sandbox commands; tests/builds can write files.
- Preserve project/user policy, authentication and billing choice. No account switching, global configuration changes, broad auto-allows, hook-trust bypass, or invented permission translation. Unsupported policy combinations block delegation; the parent may continue the task locally.
- No automatic model escalation, model routing for trivial skills, recursive delegation, provider retry, native resume manager, PID-based reaper, dependency copying or recovery archive system. ADR 001's objection to cheap-model overhead for tiny tasks still applies.
- The native CLI's own history may remain. clauDNA neither duplicates nor deletes it. Do not use ephemeral native sessions until their effect on the required session identity is actually established.
- No user-work deletion, Git reset/stash, worktree deletion, automatic patch application, or age-based removal of partial code. Worker changes, including failed attempts, remain in the borrowed workspace for parent inspection.
- No new history file/database. Operational state never becomes a second transcript or receipt log. No direct Claudron writes, harvest opt-in changes or duplicate child summaries.
- Running a configured project test is execution of that project's code. Support trusted tasks only; tool scope in the brief is not an isolation guarantee.

## Review focus

Each boundary below has one behavior check in the owning task; do not expand it into combinatorial boilerplate:

1. Native session identity arrives late, is missing, or collides by bare SID across providers: preserve explicit provider identity; never invent a child or attach it to the wrong parent.
2. Runner dies between launch and recording completion: keep the small unresolved slot; never assume the worker stopped or start a second writer.
3. Worker exits with edits but fails its task: preserve those edits; do not claim accepted or remove the workspace.
4. Parent closes or logging fails before terminal cleanup: lifecycle history stays honest; cleanup has a deterministic pending state and never reopens the parent.
5. Native output is huge/malformed or the child tries to inherit parent logging: bound capture, return incomplete honestly, and avoid duplicate/misattributed session writes.

## File map

| Files | Responsibility |
|---|---|
| New `lib/claudna/delegation.py` | Foreground runner, two small native adapters, one operational slot and finalizer; keep together until actual size warrants splitting |
| New `scripts/delegate.py` | Thin safe entry point resolving this plugin's `lib`; no project-cwd imports or shell interpolation |
| Existing `lib/claudna/session_store/events.py`, `store.py` | Typed delegation lifecycle data, additive parent/child metadata and idempotent writes under existing session lock |
| Existing `lib/claudna/session_store/project.py`, `readers.py` | Derive delegation view from lifecycle; preserve `/clear` projection |
| New `skills/delegate/SKILL.md`, `skills/delegate/native-clis.md` | Thin run/status routing and verified provider-specific instructions |
| Existing `skills/build/SKILL.md`, `skills/_shared/orchestration-guide.md`, `skills/session/history.md` | Call-site settlement, workspace ownership and existing history visibility |
| Existing `plugin-hooks/session-start.sh` | Bounded retry of already-proven terminal bookkeeping cleanup; independent of harvest/capture |
| Existing session-store tests; new `tests/test_delegation.py` | Reuse identity/history coverage; add focused process and cleanup boundary checks |
| `SETUP_GUIDE.md`, `SKILLS.md` if present, `README.md`, `CHANGELOG.md`, `Makefile` | Document actual supported scope and include new runtime tests in the existing check structure |

## Implementation Plan

### Dependencies

Existing session store and Codex adapter on the baseline above. Session recording must be available for v1; if explicitly disabled or the parent cannot be identified from a real receipt/host contract, stop before launching rather than inventing a parallel logging fallback. Cleanup reconciliation itself remains independent of capture/harvest settings.

### Blocks

The public skill and workflow call-sites must not be enabled until the native compatibility gate in Tasks 0 and 3 pass. This is one cohesive PR; the tasks below are not six separate releases. No deployment or external message is authorized by this planning document.

### Steps

### Task 0: Cheap native compatibility gate — before runtime implementation

**Files:** No product code. A private scratch capture during this probe only; retain just the sanitized minimal native observation needed by Task 3, and remove the scratch capture automatically when the probe exits.

- [ ] Before Tasks 1–2, use installed CLI help and current project policy to prepare one exact noninteractive invocation per intended provider. Confirm existing authorization covers the native account/model/billing mode. This plan authorizes preparation, not a paid call during planning.
- [ ] Under execution authorization, run a bounded no-edit task in a caller-owned disposable workspace. Observe the native session ID, process exit, completion/error representation and retained policy. Then use one tiny existing behavior check for the provider intended to edit code; a prose answer alone does not prove file-edit permissions work.
- [ ] If neither provider exposes an unambiguous, policy-preserving interface, stop here. If only one passes, scope the implementation to that direction. Do not implement a large runner first and discover that the intended vendor boundary cannot be supported afterward. No repeated attempts to obtain particular model wording.

### Task 1: Extend the existing history contract

**Files:** `events.py`, `store.py`, `project.py`, `readers.py`, `tests/test_session_store_lineage.py`, `tests/test_session_store_readers.py`.

**Interfaces:** Add `record_delegation(parent: SessionHandle, job_id: str, phase: str, data: dict) -> dict` and extend `SessionHandle.link_child(child_sid: str, *, relation: str = "continuation", child_agent_cli: str | None = None, job_id: str | None = None) -> dict`. Implement within existing store conventions, not a new journal class.

- [ ] Add one session-scoped lifecycle kind, `delegation.updated`, with phases `started`, `finished`, `accepted`, `rejected`, `cleanup_pending`, `cleaned`. Validate exact allowed fields: job/provider identity, nullable native child SID, nullable exit code, outcome, cleanup state, and bounded redacted summary/evidence. Never store the full prompt, argv containing secrets, or raw output. `started` means the launch operation began, not proof the native process started.
- [ ] Add optional `relation`, `child_agent_cli`, `job_id` to `session.child_linked`; absent relation retains legacy continuation semantics. Delegation edges require provider and job identity. Leave the child's native ID opaque and retain the provider qualifier.
- [ ] Under the existing session lock, make `(job_id, phase)` replay idempotent: identical repeats reuse the record, conflicting repeats fail. Apply the same rule to the delegation edge. No new event-envelope version is needed unless implementation discovers an actual incompatibility.
- [ ] Preserve `parent_sid`, `chain_id` and legacy `children` as `/clear` continuity. Derive `delegations` in `show` from lifecycle edges/events; include provider, native SID, result, acceptance and cleanup. Do not create a duplicate child session directory merely to represent a native-only child. Label it `native_only` unless an existing local session with the matching provider is actually present. Bare-SID equality is insufficient.
- [ ] Add focused assertions to the existing suites: unchanged `/clear` chain; same native SID on two providers remains distinct; replay produces one edge; late result after parent close leaves the parent closed and is visible in timeline. No transcript or Claudron change.

**Check:** `python3 -m pytest tests/test_session_store_lineage.py tests/test_session_store_readers.py tests/test_session_store.py`.

### Task 2: Build the minimal deterministic runner and finalizer

**Files:** new `lib/claudna/delegation.py`, `scripts/delegate.py`, `tests/test_delegation.py`.

**CLI contract:** `python3 -S <claudna-root>/scripts/delegate.py run --request -` consumes one bounded JSON request from stdin; `settle --parent <sid> --job <id> --decision accepted|rejected --evidence-stdin` consumes check evidence from stdin; `status --parent <sid>` and `reconcile` launch no provider. Each prints one JSON result, without raw stream or credentials. File-based request copies are not required.

**Interfaces:** `run_job(request: Request, store: SessionStore) -> Result`, `settle(store: SessionStore, parent_sid: str, job_id: str, decision: str, evidence: str) -> dict`, `reconcile(store: SessionStore) -> dict`. `Request` pins parent SID/provider, worker provider, absolute cwd, owned paths, task text, requested model and an invocation deadline. `Result` separates observed process outcome, native session ID, bounded response and cleanup outcome. Define these local dataclasses in the same module; no public framework.

- [ ] Use exactly one fixed private root `<state>/delegation/`, with `active.json` and a stable `.lock`. Reuse state-root validation, private permissions, atomic writes and `flock`. Do not unlink/recreate a held lock inode. The empty lock file is intentionally retained. No per-job directory, launcher, copied transcript, dependency installation or persistent output file.
- [ ] Acquire the slot before launch. If busy, return busy. If the lock is free but an unresolved active record remains, return needs-attention; do not infer safety from PID absence, mtime or elapsed time. Store only the job ID, parent reference, cwd/base, provider/native SID when known, current phase and terminal outcome needed for recovery. Cap this record at 32 KiB, excluding prompt and raw streams.
- [ ] Verify the parent record/provider and writable durable state before launching; require explicit owned-workspace handoff and, for edits, a clean Git baseline. Reject unsupported requests before any provider call. Use resolved executable argv with `shell=False`, explicit cwd and stdin. Do not treat caller-supplied shell text as an executable launcher.
- [ ] Drain stdout/stderr concurrently and incrementally. Bound individual protocol records at 1 MiB; retain at most 64 KiB final response and 16 KiB diagnostic tail, in memory. On excess/malformed data, drain safely, report protocol failure and do not silently call truncated text a valid result. Redact before surfacing or logging.
- [ ] Own the actual `Popen` handle until it is reaped. An outer tool poll/yield is not an exit. At the declared deadline/cancellation, use only the runner-owned process/group and wait for termination; if termination cannot be established, keep the unresolved record. Do not promise that arbitrary subprocesses a repository deliberately detached are gone. No automatic relaunch or orphan killing on startup.
- [ ] After known spawn failure or observed exit, durably write `finished` and run the finalizer before returning. Remove only the runner's operational record/atomic-write leftovers after durable `cleaned` history, then release the lock. If history or unlink fails, preserve `cleanup_pending` in the operational record and return that status honestly. Replay by job ID avoids duplicate terminal events.
- [ ] `settle` records the parent's verified acceptance/rejection after worker exit; it neither applies a patch nor deletes code. Cleanup of launcher bookkeeping does not wait for acceptance because user code already lives in the persistent borrowed workspace. A parent crash after worker exit therefore leaves code plus recorded worker outcome, not a second checkout awaiting integration.
- [ ] `reconcile` acquires the same lock and retries only cleanup with a durable known-terminal result. An unresolved launch without observed exit stays protected. Never clear an unknown active slot automatically. A real ambiguous crash may require resolving worker ownership; that is exceptional recovery, not routine cleanup homework.

**Behavior checks:** Use a small controlled Python subprocess through the same runner I/O path; synchronize with pipes/events, not sleeps. Cover normal completion plus bounded output; nonzero exit preserving a changed and untracked workspace file; malformed/oversized protocol; live worker holding the slot; interrupted terminal append/unlink followed by idempotent reconciliation. Inject clock/deadline decisions rather than asserting wall-clock timings. Tests must not launch a model or inspect real user state.

**Check:** `python3 -m pytest tests/test_delegation.py`.

### Task 3: Prove the native boundary before enabling it

**Files:** adapter functions in `delegation.py`, `skills/delegate/native-clis.md`, minimal sanitized fixtures in `tests/fixtures/delegation/`, `tests/test_delegation.py`.

**Interfaces:** `native_command(request: Request) -> list[str]`; `parse_native_record(provider: str, record: dict) -> NativeObservation`. Observations carry only native identity, final result, explicit error/refusal, and completion evidence; no model self-certification.

- [ ] Implement only the installed, inspected noninteractive interfaces: Claude print structured output and Codex exec JSONL, prompts through stdin. Confirm record shapes through an explicitly authorized live compatibility run before fixing parser expectations. Do not guess flag semantics from a successful help command or synthetic fixture.
- [ ] Keep native authentication and required project/user policy. Set the existing clauDNA internal-child marker in the child so the launcher owns delegation logging, without disabling unrelated required controls. Do not strip settings/rules/hooks wholesale. Test that the child cannot write into the parent's session record through inherited IDs. Missing safe permissions means blocked, not broader grants.
- [ ] Require actual native ID, successful process exit, valid completion envelope and no explicit error/refusal for observed worker completion. Task correctness still requires the parent's check. Preserve requested versus actually observed model separately; unknown served identity/quota remains unknown.
- [ ] Exercise one authorized, bounded handoff per supported provider using an existing trivial task/check in a disposable caller-owned fixture workspace. Verify identity, policy preservation, terminal evidence, parent edge and absent operational leftovers. Capture only a sanitized protocol excerpt with CLI version, command shape and source provenance; no tokens/full transcript/new per-run report stack.
- [ ] Add parser assertions against those actual captured shapes and one controlled refusal/error. Exact model wording is never an assertion. Native live runs are a release compatibility check outside `make check`, not repeated CI inference.
- [ ] **Stop condition:** if a provider cannot reliably supply these observations under the intended policy, leave it unsupported. If neither provider can, stop the feature and record the finding; do not add a daemon, retry fleet, transcript scraper, guessed session lookup or permission translator to make it appear complete. One passing live canary demonstrates compatibility, not 100% model reliability.

### Task 4: Wire the skill into task execution and automatic cleanup

**Files:** `skills/delegate/SKILL.md`, `native-clis.md`, `skills/build/SKILL.md`, `_shared/orchestration-guide.md`, `skills/session/history.md`, `plugin-hooks/session-start.sh`, existing `tests/test_session_start_hook.py`.

- [ ] Expose only `run` and `status`. `run` resolves actual parent identity, states provider/model/scope/check, reuses existing authorization, invokes the helper, inspects diff and meaningful check, and automatically invokes `settle`. Native resume, concurrent editing and automatic worktrees are explicitly unsupported in v1. A new continuation is another bounded task against current source, not a silent rerun.
- [ ] Build calls delegate only for an explicitly authorized cross-provider bounded task in its clean owned workspace. Pause parent writes until observed exit. Reuse the worker's valid check evidence where it still matches the source; rerun only when acceptance is unresolved or source changed. Build continues its existing review/verify/ship steps once; delegate never creates another PR or repeats the pipeline.
- [ ] At delegate entry, invoke `reconcile`. At SessionStart, add a bounded, noninteractive invocation of the same function through the safe bundled entry point; do not put it behind harvest/capture opt-in or a paid summarization call. One slot means no scanning cursor, queue or age sweeper is necessary. If the slot is busy, return immediately. Existing hook checks must confirm no model call and no write to the project/vault.
- [ ] Status/history use the existing session readers. A recovery warning identifies the job/provider/cwd and pending condition without claiming the worker died. A disabled/missing session store blocks a new delegated launch; it must not disable cleanup of an already-known terminal record.
- [ ] Describe Claudron's unchanged role: the parent may retain useful verified lessons through normal capture/opt-in harvest and human promotion. No automatic brief/log ingestion or separate child harvest; private parents remain private. Logging acceptance does not promote knowledge.

**Check:** `python3 -m pytest tests/test_delegation.py tests/test_session_start_hook.py tests/test_session_store_hook.py tests/test_session_store_codex.py`.

### Task 5: Validate the complete workflow and document the actual limits

**Files:** `SETUP_GUIDE.md`, appropriate skill catalog/README, `CHANGELOG.md`, `Makefile` and runtime-layout checks only where the new module requires registration.

- [ ] Add the new deterministic suite to `RUNTIME_TESTS` in `Makefile`; keep the Python 3.9 runtime floor and existing pinned dependencies. All automated checks stay in the Makefile, not bespoke workflow steps. Avoid unrelated architecture refactors.
- [ ] Walk through: clean owned workspace → delegated worker → parent/child edge → actual diff/check → acceptance → no active record → normal build shipping. Record native compatibility versions and whether each provider passed; do not present the fake-process suite as live provider proof.
- [ ] Exercise one controlled interruption. Expected state is a protected small record and unchanged/preserved user workspace, not a heuristic automatic restart. Exercise terminal cleanup retry separately: the next invocation/startup removes stale bookkeeping without user cleanup commands or another worker run.
- [ ] Run focused suites after relevant edits, then `make check` and `make test-runtime`. Record exact outcomes. New tests cover the distinct boundaries above; no prose-string checks, one-test-per-field, fabricated timing thresholds, or repeated full-suite runs after a passing unchanged tree.
- [ ] Document automatic cleanup, one-slot scope, clean-workspace requirement, unsupported resume/concurrency, provider-native storage, exceptional unresolved-worker handling, and the fact that nothing runs when clauDNA is absent. Update CHANGELOG; follow the current repo's release convention when publishing, not as part of this planning-only change.

## Test Plan

Deterministic CI: existing session/lineage readers plus a single new fake-process suite using real pipes, temporary Git workspaces, injected clocks and injected filesystem failures. The fakes control process/protocol behavior; they do not purport to prove vendor semantics. Existing tests remain the authority for `/clear`, host adapters, privacy, harvest and runtime floor.

Native compatibility: one opt-in real handoff for each enabled adapter, checking observable identity/completion and artifact cleanup; no exact-answer, latency or probabilistic model-success assertion. If a regression cannot be reproduced deterministically, do not add a flaky test/retry loop. State the limitation and narrow/disable the feature that depends on it.

## Verification Checklist

- [ ] Existing history shows provider-qualified delegation edges without changing `/clear` continuity.
- [ ] Success removes transient bookkeeping before returning; failed work remains in the user workspace.
- [ ] Interrupted terminal cleanup is retried automatically; unknown execution is never treated as stopped.
- [ ] No new checkout, per-turn directory, dependency copy, transcript copy, history log or Claudron API path.
- [ ] Every enabled provider has actual compatibility evidence; unsupported providers block clearly.
- [ ] Required checks pass on current main plus the implementation; no claim of 100% deterministic model behavior.

## What NOT To Do

Do not restore the broader October 11 design by stealth: no automatic worktree factory, Git integration engine, lossless archive system, general resume manager, PID/heartbeat reaper, account/permission rewriting or retry orchestration. Those would need separate demonstrated demand and a separately reviewed plan. If v1 is not useful without them, stop and discuss the premise rather than building them speculatively.

## Context

Planning only: no provider task, live compatibility canary, implementation or tests were run while writing this document. Current upstream code, installed CLI versions/help, and the prior design were inspected. The changes proposed here reduce scope expressly to honor automatic cleanup, minimal disk usage and deterministic behavior at the boundaries clauDNA controls.

## Execution record

- Task 0 passed: Claude 2.1.304 (existing Max login) and Codex 0.162.1 (existing ChatGPT login) returned native IDs and successful terminal records. Each fixed only normalize.py in a disposable Git workspace; supplied unittest failed before and passed after. No account/config/policy bypass. Probe workspaces were automatically removed.
- Ruling: use the app-managed worktree on fresh main; preserve the original old checkout and its untracked draft. Use one execution record here rather than another handoff directory.
- Tasks 1–5 implemented with a deliberate scope reduction: **Claude → Codex only**. The real helper canary completed, passed the supplied unittest, changed only normalize.py, logged parent acceptance and left only the empty lock. Claude's helper canary encountered native policy denials despite a correct edit; that direction remains disabled. No permission rewriting or provider retries.
- Reused the existing lifecycle store, typed child links and readers. One foreground worker borrows the caller's clean workspace. No new checkout, per-job folder, transcript copy, database or Claudron ingestion path. The temporary record disappears on known terminal completion; reconciliation runs on entry and SessionStart independently of harvest settings.
- Final independent review reproduced settlement/display and handled-cancellation gaps. Fixed them within the existing lock/event system: decisions are atomic and idempotent, evidence survives cleanup, and a reaped Ctrl-C cancellation receives terminal cleanup. Unknown execution still blocks rather than guessing.
- Focused post-review validation: 50 delegation, lineage and startup-hook tests passed. Deterministic regressions cover opposite concurrent decisions, acceptance before cleanup/replay, and actual subprocess interruption/reaping. Full validation results follow below.
- The task checkboxes above retain the original proposed scope as planning history; this execution record is authoritative for the narrowed implementation. No support for the rejected direction, native resume, detached-process policing or 100% model correctness is claimed.
- Final isolated `make check`: lint, catalog, routing, skill/integration, agent, manifest and changelog checks passed; pytest reported **2,216 passed, 9 skipped, 1 failed**. The sole failure is `TestWriteRedirectionKeepsThePrompt::test_dev_null_still_approves`, independently reproduced on unchanged upstream main. It is preserved as a baseline failure, not changed in this work.
- `make test-runtime`: **963 passed** on Python 3.14.5 / pytest 9.0.3 and **963 passed** on the supported Python 3.9.6 floor / pinned pytest 8.4.2. Both used disposable source exports and private HOME/TMP; no provider calls. Additional Ruff coverage of the new runtime module and session-store package passed, as did `git diff --check`.
