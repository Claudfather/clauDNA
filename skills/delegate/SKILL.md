---
name: delegate
user-invocable: true
hosts: [claude-code, codex]
description: "Use when delegating a bounded task between Claude Code and native Codex. For same-provider work or isolation, use /claudna:worktree."
argument-hint: "[run|status] [task]"
requires:
  - cli: python3
    reason: "Stdlib launcher; native codex CLI must also be installed and authenticated"
---

# Delegate

Hand one authorized task to the other provider's native CLI; retain judgment and acceptance in the parent. Preserve native permissions and settings. Do not relax controls or retry until a model happens to comply.

> **Codex:** Read `../_shared/codex-tools.md` first. Same-host subagents do not cross providers.

## Procedure

1. Resolve the actual plugin root per `../_shared/claudna-root.md` and read `native-clis.md`. Honor the user's provider, model, native account and billing mode; reuse standing authorization. No automatic account/model substitution, API billing, permission widening or provider retry.
2. Identify the current parent's actual recorded `(agent_cli, session_id)` from its host receipt; confirm with `/claudna:session show`. Never choose the latest session or infer identity from cwd. Missing identity/history blocks delegation; continue locally if authorized. For `status`, run `scripts/delegate.py status --parent <sid>` through the bundled entry point below; no provider call.
3. Assign one objective, workspace-relative owned paths and a meaningful existing check. Hand off an absolute task-owned workspace and pause parent writes until observed exit. Edits require a clean baseline. Dirty prerequisites and concurrent work remain with the caller; `/claudna:worktree` can prepare isolation before delegation. Delegate never creates/removes a workspace.
4. Feed one JSON request through the host's stdin-capable process API to `python3 -S <claudna-root>/scripts/delegate.py run --request -`: `parent_sid`, `parent_provider`, `provider`, `cwd`, `owned_paths` (list), `task`, `model` (explicit name or null for native default), `deadline_seconds` (1–3600), `workspace_owned: true`, `read_only` (boolean). Do not interpolate task text into shell code. State provider/model, owned paths and check before launch. Preserve required controls; a denial is a blocker.
5. Keep the actual process handle and wait. A tool yield/timeout does not prove exit; do not start a replacement. `completed` means native completion only. Inspect **all** changes, including untracked files, and verify scope and behavior. Inspect returned `permission_denials`: an optional diagnostic denial can coexist with completed work; a denied required action with no independently verified permitted result means rejection. Include the disposition of denials in acceptance evidence. Do not classify command text or accept worker prose as proof. Reuse fresh worker check evidence only when it matches the tested source. Do not add tests merely to pin implementation text.
6. Automatically record the parent decision using `scripts/delegate.py settle --parent <sid> --job <job-id> --decision accepted|rejected --evidence-stdin`, passing concrete check evidence via stdin. Worker prose is not approval. Failed/partial edits stay in the same workspace; rejection never resets/deletes them.
7. Report worker outcome, parent decision and cleanup separately. Launcher bookkeeping is cleaned automatically, with retry on workflow entry/session start. An unresolved worker remains protected and blocks another launch until ownership is resolved. Build then continues its existing review/verify/ship once; delegate never opens a PR or repeats that pipeline.

## Limits

One foreground worker per state root. No native resume, recursive delegation, worktree factory, patch integration, recovery archives or heuristic reaper. Path ownership is an assignment, not a sandbox. Provider history is neither copied nor deleted; no direct vault writes. Useful lessons use `/claudna:capture` or existing opt-in harvest with privacy and human promotion unchanged.
