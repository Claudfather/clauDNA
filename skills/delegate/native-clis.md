# Native execution and cleanup

## Route independently of the lens

Both Claude→Codex and Codex→Claude support consult, execute and generic simplify assignments. Choose the lens for the desired result, then choose an authorized destination and model for the work. Neither provider has a permanent coordinator or worker role.

Explicit provider, model, native account and billing choices take precedence. Within authorized unpinned choices, use currently available model names from the destination's exposed model selection/help or account information, then choose the least costly capable option supported by that evidence:

| Task complexity | Capability to select |
|---|---|
| Clear mechanical work, such as literal replacements with a decisive existing check | A smaller/economy worker that can follow the bounded brief reliably. Batch related replacements into one assignment. |
| Bounded implementation or a focused opinion with familiar evidence | A suitable general worker; the native default is valid when no supported explicit selection is established. |
| Difficult design, ambiguous tradeoffs or evidence that needs substantial reasoning | A stronger reasoning worker when the task warrants it and access permits. An opinion can need this tier even though it makes no edits. |

These are capability tiers, not CLI model aliases or price claims. Use verified available names for explicit selection; `model: null` means native default, not cheapest. Current quota/access evidence can narrow the authorized choices. Missing quota, served-model or comparative cost information remains unknown; a model label alone establishes no saving. Report measured savings only with attributable usage/billing evidence and a stated comparison.

Keep outcomes distinct: **unavailable/unknown model or quota** is a routing/access limitation; **native failure** is an incomplete execution; **a denied required task action** prevents acceptance without an independently verified permitted result. Honor a pinned unavailable model by reporting the blocker, not substituting. A completed opinion with a real evidence gap can receive one bounded clarification/correction when authorized; a disagreement or refusal is not grounds to shop models. Preserve existing authorization and native controls throughout.

## Simplification capability

Name the requested procedure and actual execution shape: **native Claude `/simplify`**, **clauDNA's equivalent generic cleanup procedure**, or an ordinary bounded cleanup assignment. Equivalent describes the cleanup goal, not proof of native command execution or independent review.

The current helper accepts a generic task prompt and prefixes it with `No subagents`; it has no qualified native-command route. Putting `/simplify` in that prompt does not prove command expansion. Therefore actual native Claude `/simplify` is unavailable through this helper, and an explicit request for it remains unsatisfied. An authorized generic cleanup assignment is still useful when labeled as such. It cannot replace a separately required independent review. The caller retains its existing diff threshold, isolation and review/verify/ship pipeline once.

## Native compatibility evidence

V1 supports Claude-to-Codex and Codex-to-Claude. The launcher uses `codex exec --sandbox workspace-write --json -` or `claude --print --output-format json --permission-prompts none`, adding `--model` only when supplied. Native authentication, configured permission mode, settings and project/user policy remain loaded. Read-only Codex work uses its local read-only sandbox; read-only Claude work restricts built-in tools to Read, Glob and Grep. MCP servers, connectors and hooks remain subject to native policy, outside that local restriction. This flag supplies no external read-only guarantee; stronger isolation must already be supplied by native policy or the task is unsupported. Tests/builds are not inherently read-only. No settings/rules/hook-trust bypass.

Compatibility measured 2026-10-20: Claude Code 2.1.304 with an existing Max login and Codex CLI 0.162.1 with an existing ChatGPT login each supplied a native ID, completion envelope and exit 0 for no-edit and bounded-edit probes. The supplied normalization test failed before and passed after; only normalize.py changed. No account override or policy bypass. This proves native compatibility, not deterministic model correctness or every configuration/version.

The end-to-end helper probe passed for Codex: native completion, existing unittest passed, only normalize.py changed, parent accepted, and only the empty lock remained. The first Claude helper probe was rejected because our completion gate treated every tool denial as a run failure. Its exact denied operation was `echo "exit=$?"` in a compound test/status command. Claude subsequently ran the test and status separately in the same session and completed the task. That blanket gate confused native completion with task acceptance.

The corrected Claude helper passed under the user's configured Auto mode and, separately, under the original stricter Manual mode. The Manual probe deliberately attempted that diagnostic once: it remained denied, no permission was changed, and independently permitted commands completed the task. Parent checks verified test failure before / success after, only normalize.py changed, and the test file unchanged. Both runs recorded acceptance and left only the empty lock. No launcher retries or permission broker.

`--permission-prompts none` is native noninteractive behavior, not an allow rule: unanswered prompts are denied and Claude is told nobody can approve or retry them. Existing rules, hooks and mode still decide permissions. The launcher does not force Auto mode. See [native headless permission behavior](https://code.claude.com/docs/en/headless#turn-off-permission-prompts-in-unattended-runs).

Codex supplies `thread.started.thread_id`, final agent-message records and `turn.completed`. Claude supplies a `result` with `session_id`, `subtype: success` and `is_error: false`. Native errors/turn failure, nonzero exit or missing identity/completion are incomplete. Claude's bounded, redacted `permission_denials` return separately for parent review; history retains their count. A denied required action without an independently verified permitted result means rejection. An optional diagnostic denial is not automatically a failed task. The parent's review decides task correctness and prose-only refusals; no keyword classifier or model self-certification. Unknown served model/quota remains unknown.

## Lifecycle

`<state>/delegation/` holds one stable empty `.lock` and, while unresolved, private `active.json` (at most 32 KiB). Prompt and bounded output pass through pipes; no per-job directories, dependency copies, raw transcript copies or generated launchers. The internal-child marker prevents clauDNA hooks from attributing child activity to the parent; other required policies remain enabled.

Actual exit, parent acceptance and cleanup are separate observations in the existing lifecycle log. Provider-qualified delegation child links do not alter `/clear` chains or invent native-only child transcript directories. Late lifecycle results do not reopen a closed parent. Normal cleanup and reconciliation use one finalizer/lock, independent of harvest settings. No worker state is inferred from PID absence, file age or elapsed time.

The CLI routes Ctrl-C, SIGTERM and SIGHUP through owned-worker cancellation: kill, reap, record cancellation, and terminal cleanup. An ordinary observation error after reaping records failure and cleans up too. SIGKILL and other abrupt death without observed exit retain the protected slot. The host's process timeout must exceed the worker deadline. Parent settlement waits on the existing session lock like other lifecycle writers; its decision and evidence remain visible independently of cleanup and identical replay is safe. Retired parent history is never recreated: a known-terminal record is removed with a warning instead.

Deletion and history append are not a distributed transaction. Cleanup is recorded **after** deletion. Abrupt death between them may leave history pending although bookkeeping is gone; never invent a success event. A known logging failure restores the small retry record. This harmless reporting gap does not justify a second journal/database. User code remains in the borrowed workspace throughout.

SessionStart cannot run while the host is absent. Unknown execution needs an operator decision: preserve the workspace, verify termination of the owned worker, then remove only its exact `active.json`, retaining `.lock`. Routine automatic cleanup never discards unknown work. Provider-native history is managed by its provider, not clauDNA.
