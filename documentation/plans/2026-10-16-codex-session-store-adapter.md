---
title: Codex session-store adapter
type: plan
status: active
owner: clauDNA
created: 2026-10-16
---

# Codex session-store adapter

## Summary

Record Codex hook lifecycle events through the existing session store and read its append-only rollout prose in detached summarization. Preserve Claude behavior, the activity policy, the Python 3.9 floor and the existing Claude summarizer runner. Ship a Codex manifest and native marketplace entry carrying only session-store hooks. Composition, fleet execution and skills remain the execution companion's work.

## Evidence

Claudlobby#2145's canonical run log recorded the native canary answers before this plan. Native Codex 0.162.0-alpha.17.2 emitted common `session_id`, `transcript_path`, `cwd` and `hook_event_name` keys; Bash input has `command`, while successful PostToolUse carried an empty string response. Lifecycle sources observed were startup, resume and compact, with manual PreCompact and SessionEnd reason other. No PostToolUseFailure was observed.

Hooks expose no CODEX_SESSION_ID or CODEX_THREAD_ID environment variable. The native Codex process was a stable own ancestor, one level above the recording hook; a bounded own-ancestry walk supplies the owner PID used by child guards, clear links and abandoned sweeps. The literal Claude child-session marker remains unusable as a guard.

The native rollout retained its entire old prefix after resume (162197 to 181134 bytes). Captured response_item messages contain input_text/output_text; event_msg duplicates conversation information, while tool calls/results and context records must be excluded. The original P0 17-record golden excerpt had SHA256 `85dc581b6c525be0412dff6713f3cc8e9b45e7ec09cdc7108fa07a08b245164c`; independent source review identified missing noncontent classification enums. The refined 20-record excerpt, independently reproduced from the same actual source, has SHA256 `589998008aad8966709fa19914c93a3b649789695025679b9a5ee9260811e31d` and preserves both injected-environment and genuine-user shapes. Native hook fixtures and their manifest (`8ca604533fe6d6f509d75a832938f422fac3aa8c2512db95592f97b07eae8c2a`) were transformed from actual stdin before export, never synthesized from producer code.

Native plugin installation and trusted packaged hooks worked. PLUGIN_ROOT/PLUGIN_DATA and CLAUDE_PLUGIN_ROOT/CLAUDE_PLUGIN_DATA aliases were present and equal within the private installation. Public v0.28.1 marketplace fetch succeeded, but plugin installation reported that claudna was not found; that result alone establishes no cause. Hook trust is separate from install. The second SessionStart command selected its own log, proving explicit command selection.

## Implementation Plan

### Dependencies

The measured C1, C2, C4, C8 and C9 answers above. Source baseline is published v0.28.1, `5025af58273b2150bf479c745729bb62dab4228b`. The engine's capture-prompt correction belongs to its separately reviewed contract change; no engine protocol is reimplemented here.

### Blocks

Publication waits for independent native-evidence and implementation review. This change does not satisfy the live fleet week or authorize global plugin trust/settings writes. Release must precede companion composition.

### Steps

1. Introduce immutable shared host types below adapters, at rank 5; keep flat host_claude/host_codex modules at rank 6 and neutral orchestration at rank 7. Retain compatibility exports from boundaries. Strict imports remain downward.
2. Normalize lifecycle/activity inputs in each adapter. Select the adapter explicitly through `hook --host codex EVENT` and `session-store.sh --host codex EVENT`; default Claude commands remain unchanged. Derive Codex actor and owner PID without unrelated process searches or invented environment signals.
3. Put runtime-specific transcript decoding and dispatch in the existing rank-1 transcript module. Detached summarize selects by the session's recorded agent_cli, covering harvest resummarize and abandoned-session summaries without importing rank-6 adapters. Preserve byte ranges and exclude duplicate events, tool output, system/developer/context content.
4. Add captured fixtures/provenance, lifecycle/guard/reader regressions and a private no-inference fixture protocol canary. Freeze activity.py byte-for-byte.
5. Add `.agents/plugins/marketplace.json`, selecting its own plugin root with the measured local-source grammar, and `.codex-plugin/plugin.json` and a separate store-only hook configuration, with explicit commands and bounded SessionEnd timeout. Extend manifest validation and release version sync to three manifests. Cursor remains hook-free; Codex skill/agent discovery is explicitly scoped to an inert directory.
6. Mirror canary findings into the phase-3 table, document host selection and install/trust boundaries, update the runtime module order and changelog, and record verification.

## Test Plan

Run RED/GREEN regressions for new host selection, lifecycle/guard handling, captured rollout parsing and manifest invariants. Run existing runtime suites, layout/lint/manifest gates and the complete `make check` in separate prepared exports with private HOME/TMPDIR, retaining counts, failed names and exit codes. Compare baseline failures rather than claiming an already failing suite green. Tests and protocol canary never call real Claude inference.

## Verification Checklist

- [ ] Captured fixture hashes and provenance retained; no personal identifiers or credential content committed.
- [ ] Claude existing tests and compatibility exports hold; activity.py remains identical.
- [ ] Codex owner PID, resume/compact/close, child guard and unknown-host fail-open tested.
- [ ] Rollout prose is read once and excludes tools, reasoning and injected context; detached reader uses recorded agent_cli.
- [ ] Three manifest versions agree; store-only Codex hooks validate and Cursor remains hook-free.
- [ ] Runtime floor/layout, affected tests and complete gate recorded with exact scope.
- [ ] Independent simplify/spec/evidence findings folded before publication.

## What NOT to Do

No new summarizer provider, activity behavior, Codex skill/agent port, fleet execution adapter, live activation, global settings/cache edit, real Anthropic inference, or unobserved event support claim. Do not relax the strict layer gate to fit the earlier interface sketch.

## Context

This is P4 of Claudlobby#2145. The earlier interface sketch placed shared types in a peer adapter and selected rank-6 adapters from rank-5 detached consumers; that violates the shipped strict-layer contract. Shared types at rank 5 plus transcript dispatch at rank 1 keep the intended flat adapters and avoid that cycle. Host.read_range remains a binding for adapters, while detached consumers call the lower reader selector directly.


### Native packaging refinement

The first source manifest used empty `skills`/`agents` arrays. Actual native `skills/list` still exposed the default root skills, so a static-only pass was insufficient. Explicit paths to the tracked inert `.codex-plugin/store-only/` directory produced `plugin/read.skills: []`, zero plugin skills in `skills/list`, and exactly five store hooks in `hooks/list`, all still untrusted; SessionEnd was parsed as 3 seconds. The private native app-server submitted no turns and required no authentication. This is a packaging/discovery observation, separate from captured-envelope execution tests. The installed protocol has no plugin agents field/list method; that API cannot establish an observed agent count. The manifest selects the same inert directory for agents and the static gate forbids content there. Official [packaging guidance](https://developers.openai.com/plugins/build/plugins) documents compatibility manifests and explicit paths; the installed native result governs the empty-array correction.


### Reader review correction

Independent review of the actual private native rollout (`97a96d73d5898942359bd517632f9642270bcac81098f1b8fa1f285e6b71254f`, 181134 bytes) found seven user-role messages: six classify their content as `user.text`, while one is injected `environments.environment_context`. There are no event_msg.user_message records in this capture. The old golden had redacted those classification enums and retained the injected user record in place of a genuine prompt. The revised actual-source transformation includes nested kinds in selection and retains only those two safe classification enums; source content remains redacted. An independent in-memory reproduction matched all 20 selected lines and the final bytes/hash.

The reader now requires aligned nested `internal_chat_message_metadata_passthrough.content_item_kinds` metadata and admits only `user.text` input items. Missing/mismatched/unrecognized metadata fails closed. Assistant output is limited to the measured commentary/final_answer phases; unmeasured phases are ignored. The observed source has six commentary and five final_answer records, with one final_answer empty. Tests first reproduced the actual golden leak and nine classification mutations, then passed with the correction. Direct, host-bound and detached summarize readers all use this same decoder; harvest/resummarize and abandoned-session summaries reach it through summarize's recorded agent_cli selection.


### Measured test-matrix adaptation

The earlier epic sketch proposed parametrizing every Claude hook assertion across both hosts. This phase parametrizes the shared lifecycle/runtime/PID/compact/resume contract and adds actual Codex-envelope, Codex actor/child-guard, explicit-command, direct/host/detached reader and native packaging regressions. Claude-specific entrypoint, fork and other vendor-only assertions remain Claude tests, because their predicates were not observed for Codex. Passing the existing Claude suites plus these measured shared/Codex cases is the claimed coverage; this is not a claim that every Claude-specific assertion ran against Codex.
