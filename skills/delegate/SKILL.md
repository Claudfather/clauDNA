---
name: delegate
user-invocable: true
hosts: [claude-code, codex]
description: "Use when delegating a bounded task between Claude Code and native Codex. For same-provider work or isolation, use /claudna:worktree."
argument-hint: "[run|status] [task]"
requires:
  - cli: python3
    reason: "Stdlib launcher; the destination's native Claude or Codex CLI must also be installed and authenticated"
---

# Delegate

Hand one authorized task to the other provider's native CLI; retain judgment and acceptance in the parent. Preserve native permissions and settings. Do not relax controls or retry until a model happens to comply.

> **Codex:** Read `../_shared/codex-tools.md` first. Same-host subagents do not cross providers.

## Procedure

1. Resolve the actual plugin root per `../_shared/claudna-root.md` and read `native-clis.md`. Honor the user's provider, model, native account and billing mode; reuse standing authorization. No automatic account/model substitution, API billing, permission widening or provider retry.
2. Identify the current parent's actual recorded `(agent_cli, session_id)` from its host receipt; confirm with `/claudna:session show`. Never choose the latest session or infer identity from cwd. Missing identity/history blocks delegation; continue locally if authorized. For `status`, run `scripts/delegate.py status --parent <sid>` through the bundled entry point below; no provider call.
3. Assign one objective, workspace-relative owned paths and a meaningful existing check. Hand off an absolute task-owned workspace and pause parent writes until observed exit. Edits require a clean baseline. Dirty prerequisites and concurrent work remain with the caller; `/claudna:worktree` can prepare isolation before delegation. Delegate never creates/removes a workspace.
4. Feed one JSON request to `python3 -S <claudna-root>/scripts/delegate.py run --request -`: `parent_sid`, `parent_provider`, `provider`, `cwd`, `owned_paths` (list), `task`, `model` (explicit name or null for native default), `deadline_seconds` (1–3600), `workspace_owned: true`, `read_only` (boolean). Use the host transport below; serialize task data as JSON, never interpolate it into an executable shell command. State provider/model, owned paths and check before launch. The host's actual process timeout must exceed `deadline_seconds`; a tool yield must retain the process handle. Preserve required controls; denied required actions block acceptance.
5. Keep the actual process handle and wait. A tool yield/timeout does not prove exit; do not start a replacement. `completed` means native completion only. Inspect **all** changes, including untracked files, and verify scope and behavior. Inspect returned `permission_denials`: an optional diagnostic denial can coexist with completed work; a denied required action with no independently verified permitted result means rejection. Include the disposition of denials in acceptance evidence. Do not classify command text or accept worker prose as proof. Reuse fresh worker check evidence only when it matches the tested source. Do not add tests merely to pin implementation text.
6. Automatically record the parent decision using `scripts/delegate.py settle --parent <sid> --job <job-id> --decision accepted|rejected --evidence-stdin`, passing concrete check evidence via stdin. Worker prose is not approval. Failed/partial edits stay in the same workspace; rejection never resets/deletes them.
7. Report worker outcome, parent decision and cleanup separately. Launcher bookkeeping is cleaned automatically, with retry on workflow entry/session start. An unresolved worker remains protected and blocks another launch until ownership is resolved. Build then continues its existing review/verify/ship once; delegate never opens a PR or repeats that pipeline.

## Host input transport

On Codex, use the exposed process API's stdin input or write-to-process control and retain the returned handle. Claude Code's Bash tool has no stdin argument: use a **single-quoted here-document** containing the serialized request on **one physical JSON line**. Encode embedded newlines and other control characters inside JSON strings; never paste an unserialized prompt. The JSON object line begins with `{`, so it cannot equal the delimiter. Quoting the delimiter disables shell expansion, including dollar signs, backticks and command substitution.

```bash
python3 -S "<claudna-root>/scripts/delegate.py" run --request - <<'CLAUDNA_DELEGATE_JSON'
{"parent_sid":"<actual-parent>","parent_provider":"claude","provider":"codex","cwd":"/absolute/task-workspace","owned_paths":["file.py"],"task":"Bounded objective; encode embedded newlines as \n.","model":null,"deadline_seconds":300,"workspace_owned":true,"read_only":false}
CLAUDNA_DELEGATE_JSON
```

For Claude Code settlement, use the same single-line JSON transport. Existing permission checks still apply to these Bash calls; an unanswered approval blocks the call, without policy changes or retries.

```bash
python3 -S "<claudna-root>/scripts/delegate.py" settle --request - <<'CLAUDNA_DELEGATE_EVIDENCE'
{"parent_sid":"<actual-parent>","job_id":"<actual-job>","decision":"accepted","evidence":"<commands, actual results, changed scope and denial disposition>"}
CLAUDNA_DELEGATE_EVIDENCE
```

## Limits

One foreground worker per state root. No native resume, recursive delegation, worktree factory, patch integration, recovery archives or heuristic reaper. Path ownership is an assignment, not a sandbox. `read_only` restricts local built-in tools or the local filesystem sandbox; native MCP/connectors and hooks retain their existing permissions. It does not guarantee external read-only access. Tasks requiring stronger external isolation are unsupported unless native policy already supplies it. Provider history is neither copied nor deleted; no direct vault writes. Useful lessons use `/claudna:capture` or existing opt-in harvest with privacy and human promotion unchanged.

If an abrupt death leaves unknown execution, keep parent writes paused. Only after the operator verifies the owned worker has terminated and preserves its edits may they remove that exact `<state>/delegation/active.json`; never delete the stable lock. Routine terminal cleanup is automatic, including when parent history was removed by retention.
