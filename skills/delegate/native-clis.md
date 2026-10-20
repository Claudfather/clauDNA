# Native execution and cleanup

V1 supports only Claude-to-Codex. The launcher uses `codex exec --sandbox workspace-write --json -`, adding `--model` only when supplied. Native authentication, settings and project/user policy remain loaded. Read-only work uses the read-only sandbox; tests/builds are not inherently read-only. Unsupported permission requirements block: no settings/rules/hook-trust bypass.

Compatibility measured 2026-10-20: Claude Code 2.1.304 with an existing Max login and Codex CLI 0.162.1 with an existing ChatGPT login each supplied a native ID, completion envelope and exit 0 for no-edit and bounded-edit probes. The supplied normalization test failed before and passed after; only normalize.py changed. No account override or policy bypass. This proves native compatibility, not deterministic model correctness or every configuration/version.

The end-to-end helper probe passed for Codex: native completion, existing unittest passed, only normalize.py changed, parent accepted, and only the empty lock remained. The Claude helper probe made the correct edit but encountered policy denials for compound Bash commands; it was rejected. That direction is disabled rather than adding permission rewriting, retries or prompt-based guarantees.

Codex supplies `thread.started.thread_id`, final agent-message records and `turn.completed`; explicit errors/turn failure, nonzero exit or missing identity/completion are incomplete. The parent's review decides task correctness and prose-only refusals; no keyword classifier or model self-certification. Unknown served model/quota remains unknown.

## Lifecycle

`<state>/delegation/` holds one stable empty `.lock` and, while unresolved, private `active.json` (at most 32 KiB). Prompt and bounded output pass through pipes; no per-job directories, dependency copies, raw transcript copies or generated launchers. The internal-child marker prevents clauDNA hooks from attributing child activity to the parent; other required policies remain enabled.

Actual exit, parent acceptance and cleanup are separate observations in the existing lifecycle log. Provider-qualified delegation child links do not alter `/clear` chains or invent native-only child transcript directories. Late lifecycle results do not reopen a closed parent. Normal cleanup and reconciliation use one finalizer/lock, independent of harvest settings. No worker state is inferred from PID absence, file age or elapsed time.

Handled Ctrl-C kills and reaps the owned worker, records cancellation, and runs terminal cleanup. An abrupt death with no observed exit retains the protected slot. Parent settlement is atomic under the existing session lock; its decision and check evidence remain visible independently of cleanup and identical settlement replay is safe.

Deletion and history append are not a distributed transaction. Cleanup is recorded **after** deletion. Abrupt death between them may leave history pending although bookkeeping is gone; never invent a success event. A known logging failure restores the small retry record. This harmless reporting gap does not justify a second journal/database. User code remains in the borrowed workspace throughout.

SessionStart cannot run while the host is absent. Unknown execution may need an ownership decision; routine automatic cleanup does not authorize discarding unknown work. Provider-native history is managed by its provider, not clauDNA.
