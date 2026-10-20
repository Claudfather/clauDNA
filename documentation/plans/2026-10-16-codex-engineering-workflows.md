---
title: Codex engineering workflows through the clauDNA marketplace
type: plan
status: active
owner: clauDNA maintainers
created: 2026-10-16
---

# Codex engineering workflows through the clauDNA marketplace

## Summary

Extend the released P4 store adapter with an explicitly curated Codex catalog of **36 existing skills**, host-qualified use of **eight existing agent prompts**, and one startup continuity handler. Keep the canonical Claude catalog of 39 skills and Cursor's declared 35 unchanged. Catalog discovery does not prove every workflow can execute on every Codex host; delegation-dependent routes require proof on the execution host. This implements source-reachable clauDNA#404; closure of that issue still requires the agreed workflows running through the marketplace in #2149's mixed-runtime fleet canary.

No new canonical skill, native agent registration, summarizer provider, cloud service or global configuration writer is introduced. Source work and isolated Codex verification may proceed now under the user's delegated implementation/review authority. The mixed-fleet week and concrete live-host authority remain separate gates.

## Evidence

Frozen inventory source: released base `3c56fb6c6b3e01546ee264e684a383d741a0a497`, tree `33244925ae8a541eb0520612880506d48c99115f`. The inventory reads one explicit Git-object export; all 425 exported files match their Git blob identities and separately match the retained pre-implementation baseline's bytes and Git modes. The original 194-entry audit was independently verified against its original P4 merge `82d9ceae0f9602f792e6005f3c2b397cbfa0a2cf`, tree `729f63879e61f50b09cfbddf6931fcc662623205`, with zero mismatches. This is a baseline refresh: 193 audited files remain byte-identical; only two docstring lines in `scripts/validate-manifest.py` differ. Catalog, hook, agent, cross-reference and dependency counts are unchanged. Release PR #416 merged at this base, with [clauDNA v0.29.0](https://github.com/Claudfather/clauDNA/releases/tag/v0.29.0) published; the engine owner separately verified Claudron v0.10.0; preserve #416's three-manifest contributor/release/template corrections. Implementation starts from this verified actual main or a verified later main. The planning audit changed no source; implementation runs in a separate checkout from this verified release.

- `CLAUDE.md:1-27,69-102` declares marketplace-only distribution, the existing store-only Codex scope and three-manifest release discipline. `PROJECT_MISSION.md` places skills/agents on Codex in #404, outside #2145 F12's store-only slice.
- `SKILL_CONTRACT.md:22-48,64-76,92-97,126-150` owns plugin-root resolution, tool metadata, inter-skill references and host/context scoping. `scripts/skill_checks.py:40` currently recognizes only `claude-code`/`cursor`; `:292` owns Cursor's existing exclusion predicate.
- `scripts/check_cursor_scope.py:33-110` parses actual component directories and checks the explicit list in both directions. Reuse that path-classification mechanism for Codex without changing Cursor's exclusion policy.
- Frozen inventory covers **39 skill directories, eight agent files and 12 files under plugin-hooks/**. All tracked files in every skill directory were scanned; `_shared` was scanned separately. Matching-line counts are lexical dependency evidence, not unique defects or a claim every occurrence needs rewriting. The [promoted audit receipt](2026-10-16-codex-engineering-workflows-audit.json) records relative source paths, hashes and counted scope; full private lexical-hit evidence remains separately retained.
- Existing `scripts/routing_eval.py:1-15,105-119,146-175` invokes `claude -p` with a `Skill`-only tool surface and judges its first native Skill call. That surface is not a Codex API. The shared matrix has **41 rows, two controls, ten live-marked rows**, no known-failure markers and expectations for ten skill names; it does not yet cover the complete proposed Codex catalog.
- P0 C1/C3/C8/C9 observed native Codex 0.162.0-alpha.17.2 SessionStart sources startup/resume/compact, packaged hook execution, context delivery and explicit command arguments. Hook root/data aliases were set; ordinary skill shell environments were not established by that observation. PermissionRequest/SubagentStart/SubagentStop were wired but unobserved; none is added to this hook configuration. Notification, file-edit tool payloads and a native plugin-agent registration API were not observed.
- P4's actual native discovery corrected `skills: []`, which unexpectedly exposed 39 default-discovered skills. Explicit inert paths produced zero plugin skills and five untrusted store hooks. A nonempty explicit catalog must therefore be measured through native discovery, not assumed from static JSON validity.
- The installed `codex exec --help`, inspected without a model turn, supports `--sandbox read-only`, `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, `--output-schema`, `--json` and stdin prompts. It exposes no Claude `Skill`-only or `--max-budget-usd` equivalent. That help command warned it could not create PATH aliases; no model/server/auth operation was run by this planning audit.

The release-base refresh leaves all skill/shared dependency counts and classifications unchanged. The separate routing-summary correction counts two rows that omit mode; its previous zero was an audit-summary error, and the routing fixture bytes remain unchanged.

The original private P0 final report has SHA256 `4d13c914c1227807d736293573b24e10ac9f055a504f298c6955288369bc9cb7`; its conclusions are bounded by the canonical epic/run-log corrections, including the refined C4 classification in the merged P4 plan. The private audit retains its input locator. Public promotion retains hashes and sanitized conclusions, never local absolute paths, raw rollout/prompt/tool content, authentication or personal identifiers.

## Architecture

Keep one canonical skill tree. `.codex-plugin/plugin.json` declares the selected existing skill directories explicitly; its `agents` component remains the tracked inert directory. Agent prompt files remain ordinary bundled reference content, read and filled by a workflow before it dispatches a Codex subagent.

Add `skills/_shared/codex-tools.md` as clauDNA-owned procedure for mapping host tools. Selected skill bodies point to this mapping before host-specific actions. Native names are translated into available Codex controls; absent controls cause a documented inline/read-only fallback or an explicit capability limitation. Tool grants, background mode, agent memory and Claude model aliases are never invented.

Codex continues to use P4's store hooks. A separately named SessionStart `startup` entry runs the existing continuity briefing through a quoted `PLUGIN_ROOT` command with an explicit five-second native timeout. It neither claims the knowledge-recall role nor runs at compact. The complete Claudron owner pack supplies recall/capture instructions when composed by #2149; no second frontend compact prompt is added here.

## Agreed catalog and counted dependency evidence

P = procedure portable with shared host mapping/root resolution; A = explicit adaptation before Codex publication; X = excluded only from Codex marketplace discovery. Counts below are matching lines within that skill's whole directory. Generic examples of another project's `.claude` files are not automatically host dependencies.

| Existing skill | Class | Evidence / concrete action |
|---|---|---|
| adversarial-review | A | Four plan/question lines; map controls and preserve already-authorized user decisions. |
| audit | A | Six delegation, 20 plan/question, ten root, two Claude-state lines; map dispatch and give Codex repo-list storage its own clauDNA state path. |
| build-all | A | Three native `/simplify` references; route through the shared Codex simplify procedure. |
| build | A | Two delegation, one plan, four root and 12 `/simplify` lines; map dispatch/simplify and preserve owned-change boundaries. |
| capture | A | Five root/eight Claudron lines are portable; one selected-to-excluded reference at `SKILL.md:79` needs Codex source-checkout guidance for skill-scaffold. |
| claudron | P | 20 CLI lines; preserve capability probes and current optional-dependency semantics. |
| cleanup-legacy-install | X | `hosts:[claude-code]`, 39 Claude-state lines and destructive legacy-overlay cleanup; not a Codex installation procedure. |
| dbt | P | Declared dbt CLI; one root line resolves through the shared loader. No warehouse operations are exercised by the port tests. |
| development-retro | P | Generic git/read procedure; allowed-tools is not a Codex grant. |
| extract-system-spec | P | Read/extract procedure with existing prompt files; common dispatch mapping applies where requested. |
| file-github-issue | P | Declared gh CLI and screenshot input; preserve explicit outbound-write authority. |
| find-skills | A | Two Skill-tool references; use native skill loading and preserve the pinned external CLI. Do not infer a new installer flag or auto-install to a global host. |
| forge | A | One plan-mode line; map to actual collaboration mode or read-only planning convention. |
| github-activity-report | P | Declared gh CLI, two bundled-root lines; no host-specific execution dependency. |
| heist | A | Six delegation/one Skill line; map scouts. `.claude` artifacts being researched remain legitimate target examples. |
| index | P | Two Claudron lines; keep engine-managed-root refusal and raw-tree fallback contract. |
| init-project | A | Claude-focused template/rules paths; offer Codex AGENTS.md output from the approved project instructions without writing user-global config or pretending `.claude` grants apply to Codex. |
| investigate-app | A | Named-agent dispatch plus two plan/question lines; fill existing role prompts and use available Codex subagents. |
| ironclad | A | Six plan/question and six root lines; map panel/author dispatch, modes and result contracts. |
| kindle | P | Deliberation/user-approval procedure; no unavailable native tool is required. Existing explicit authorization persists. |
| modal | P | Declared Modal CLI; unchanged read/write approval boundaries. |
| neon | P | Declared psql/Neon CLIs and five bundled-root references; no service calls during port tests. |
| product-enhance | A | Four plan/question lines; use mapped controls and the same output contract. |
| product-vision | A | Two plan-mode lines; same discovery method through supported controls. |
| promotion-intake | X | `requires-context:repo-clone`; integration changes this repository, not the user's arbitrary marketplace project. Canonical skill remains available in its proper context. |
| publish | P | Existing document destinations and capability-probed Claudron path; no new hosted destination. |
| qa | A | Three delegation/four plan lines; use the browser control actually exposed to the task. Missing browser capability is a named prerequisite, not invented native browser tooling. |
| railway | P | Declared Railway CLI; unchanged authorization/dependency checks. |
| recall | A | Two root lines plus Claude auto-memory lookup at `SKILL.md:87-106`; on Codex use the declared vault/repo knowledge paths and skip the Claude-only memory facet explicitly. Do not read or write Codex internal memory stores. |
| review-work | A | Root resolution and Explore dispatch; preserve exact scope, provenance gate and CI/run-evidence distinction. |
| session | P | Shared per-cwd `.claude/session.md` is an existing cross-runtime handoff artifact, not a user-global Claude setting. Retain this compatibility path and read-only legacy lookup; history uses the runtime-neutral store. |
| ship | P | Git/gh workflow; preserve task authority, explicit staging and app-managed worktree branch checks. |
| skill-scaffold | X | `requires-context:repo-clone`, repository validator invocation and `claude --plugin-dir` development instruction; not an installed arbitrary-project capability. |
| sync-branches | P | Git-only workflow; preserve conflict reporting and no force/reset policy. |
| using-claudna | A | Claude cache/health paths, eight-hook table and unavailable skill-scaffold route; add Codex catalog/hook/trust diagnostics and host metadata. |
| vercel | P | Declared Vercel CLI; preserve provider prerequisites without live service operations. |
| verify-completion | A | Named-agent reporting language; map evidence collection without interpreting a subagent's success as verification. |
| weigh-development-paths | A | Two plan/question lines; map the controls, preserve selected forks. |
| worktree | A | Four delegation/two TaskOutput lines; map wait/cleanup and app-managed checkout ownership. |

Totals: **16 P, 20 A, three X; 36 selected**. These are distribution decisions for Codex, not removals from the canonical 39 or changes to Cursor's 35.

Cross-reference sweep found exactly two selected-to-excluded references: `capture/SKILL.md:79` and `using-claudna/SKILL.md:22`, both to skill-scaffold. Their Codex branches direct the user to a clauDNA source checkout/contribution workflow and do not attempt an unavailable catalog invocation. Shared native `/simplify` and TaskOutput references are handled centrally; a scan for uppercase tool names alone would have missed them.

## Agent prompt decisions

All eight files use `model: opus`; six specify project memory, five background mode, and dbt-engineer requests worktree isolation. These metadata fields are not native Codex registration or enforcement promises.

| Prompt | Codex dispatch | External prerequisite / adaptation |
|---|---|---|
| code-reviewer | Read/fill body, spawn focused reviewer | Preserve read-only review scope and concrete file/line findings. |
| spec-reviewer | Read/fill body, spawn focused spec reviewer | Preserve untrusted-input/no-branch-execution rules. |
| dbt-engineer | Read/fill body, spawn owned worker | dbt/Snowflake prerequisites; supply an actual owned checkout before worktree isolation is claimed. |
| snowflake-analyst | Read/fill body, spawn scoped analyst | snowsql/auth prerequisite; no warehouse calls in this port's tests. |
| neon-analyst | Read/fill body, spawn scoped analyst | psql/Neon prerequisite; replace its Claude-cache-only root paragraph with the shared resolver/passed absolute root. Keep resource cleanup scoped to resources actually created. |
| modal-ops | Read/fill body, spawn scoped investigator | Modal CLI/auth; no new background supervisor or persistent memory writer. |
| railway-ops | Read/fill body, spawn scoped investigator | Railway CLI/auth; retain explicit mutation authority. |
| vercel-ops | Read/fill body, spawn scoped investigator | Vercel CLI/auth; retain secret-safe commands and explicit mutation authority. |

Use the task's configured Codex model by default; never translate opus into an invented Codex model name. Pin the execution host for every supported dispatch route: desktop/app collaboration and native CLI are distinct surfaces. Establish actual subagent availability on that same surface before advertising a delegated workflow there; a desktop spawn/wait proves only the desktop route. Do not infer native CLI tools from desktop tools, schema registration or a prompt saying to delegate. If subagents are unavailable, run the role inline only when its procedure allows that; otherwise report the route as unsupported on that host. A required independent review cannot be replaced by an inline self-review or counted as passing. Prompt read-only restrictions are instructions, not proof of a host-enforced tool sandbox. No installer writes `.codex/agents/` or `~/.codex/agents/`.

The mandatory dispatch acceptance fixture is a tiny disposable project with a written contract that expiry includes equality and `expiry.py:2` incorrectly returning `now > deadline`. Keep the known-defect oracle separate: neither the dispatched task nor the plain native-routing utterance discloses the defect, expected line or correction. Read the complete installed code-reviewer prompt, fill every placeholder including the task and absolute project root, and record the installed prompt hash plus the private filled-prompt hash. From each claimed execution host, use its actually available subagent controls and capture genuine spawn and completed-wait receipts linked to that task. The reviewer must independently identify `expiry.py:2`, the equality trigger and the `>=` correction. A host-availability check, correct file read, self-reported delegation or a successful desktop run alone does not establish native CLI dispatch. Missing native CLI capability remains an explicit limitation of that route; neither registration nor a supported workflow claim may be fabricated to clear the gate.

## Hooks and helpers: all 12 inventoried files

| File | Codex decision | Reason |
|---|---|---|
| codex-hooks.json | Extend from five to six handlers | Preserve the five P4 store definitions and SessionEnd timeout 3; add only startup briefing below. |
| hooks.json | Preserve Claude-only wiring | Do not import its Notification, Write/Edit or failure-hook contracts into Codex. |
| session-store.sh | Carry unchanged | P4 already selects `--host codex` explicitly; activity policy remains frozen. |
| lib/state-dir.sh | Carry as existing helper | Canonical clauDNA state resolution; no host-global configuration mutation. |
| session-start.sh | Add Codex startup wiring | Actual captured startup envelope + C3 stdout delivery ground this path. Quoted `${PLUGIN_ROOT}` command, matcher startup, native timeout 5, existing briefing opt-out; no compact/resume/clear assumption. |
| precompact-reflect.sh | Exclude from Codex wiring | Claudron's complete pack owns compact-start capture when installed. Standalone Codex users invoke capture explicitly; no duplicate or unreliable block-reason prompt. |
| pretooluse-permissions.sh | Exclude | Claude permission-decision JSON/allowlist semantics are not a Codex security policy. Codex sandbox/execpolicy and fleet composition retain authority. |
| gh-guard-decide.py | Do not wire separately | Helper of the excluded Claude permission hook; no false claim that Codex receives its guard. |
| auto-format.sh | Exclude | Requires observed Write/Edit file_path payloads; P0 captured Bash command and empty response. Builds still run their normal formatting checks explicitly. |
| notify.sh | Exclude | Notification event/payload and AppleScript UI contract not measured on Codex. No automatic notification settings. |
| statusline.sh | Exclude | Opt-in Claude statusLine stdin/UI protocol; no Codex equivalent is asserted. |
| telemetry-emit.sh | Exclude | Claude Skill/failure/usage payloads; Codex Skill invocation and failure payloads were not observed. P2 owns telemetry normalization. |

Adding startup continuity is not installation of Claudron's knowledge hooks. `using-claudna health` must report installed versus trusted versus observed separately. A native timeout can suppress a degraded briefing; no promise that optional gh sections finish within five seconds is made. The source's GNU-timeout fallback is not promoted into a universal hard-bound claim.

## Decision Forks

These are locked engineering choices under the user's delegated source/metadata authority. The independent root review may identify a concrete defect and revise them before publication; no new human design permission is needed.

| ID | Context / mutually exclusive options | Selected choice and rationale | Ratifier / status |
|---|---|---|---|
| F404-1 | Discover all 39 / explicit curated set / expose no skills | Explicit 36; respects actual host/context restrictions and prevents empty-array fallback. | Delegated Codex workstream; locked. |
| F404-2 | Native agent registration / read-and-dispatch prompts / omit specialist roles | Read-and-dispatch all eight existing prompts only on execution hosts with observed subagent controls; require same-host fixture proof and label unsupported CLI routes. | Delegated Codex workstream; locked. |
| F404-3 | Port all Claude hooks / startup plus existing store / store only | Startup plus store; measured source/channel, preserves continuity while excluding unmeasured policy/edit/notification contracts. | Delegated Codex workstream; locked. |
| F404-4 | Reuse Claude paid routing eval / static-only claim / Codex selection check plus actual skill probes | Codex selection substitute + actual native load/action probes, including an unhinted plain-utterance automatic-routing arm; separate outcomes, no Claude inference or static-as-E2E claim. | Delegated Codex workstream; locked. |
| F404-5 | Move handoff to .codex / retain existing per-cwd artifact / duplicate two writers | Retain `.claude/session.md`; existing consumers already own this shared handoff contract. | Delegated Codex workstream; locked. |
| F404-6 | Native /simplify assumption / new canonical simplify skill / shared Codex procedure | Shared clauDNA-owned four-lens prompt; no nonexistent builtin or unnecessary catalog addition. | Delegated Codex workstream; locked. |

## Implementation Plan

### Dependencies

1. The root reports merged release PR #416 at `3c56fb6c6b3e01546ee264e684a383d741a0a497` and marketplace clauDNA v0.29.0. Use the existing release/tag/tree readback as the prerequisite; implementation begins from fresh verified actual main including that merge.
2. The root reports Claudron v0.10.0 released with `codex-session-loop`. Verify that released capability before the #2149 composer renders its owned pack. #404 does not render or fork that snippet.
3. Private Codex authentication reuse is already explicitly authorized. New bounded Codex routing/native probes use isolated homes, with auth-only reuse as needed; no Claude inference or global trust/config writes.
4. #2149 owns runtime launch/supervision/composition. Its actual mixed-fleet week needs declared live root/fleet/channel authority and elapsed observation; it is blocked, not waived.

### Blocks

Unlocks Codex workflow composition and marketplace acceptance in #2149. Does not unblock telemetry's seven-day floor-host gate or satisfy Half B/Task 9 windows.

### Steps

1. **Land audit/host scope first.** Promote a sanitized counted catalog/hook/agent matrix and this plan under `documentation/plans/`; retain source/report hashes but replace private absolute locators with logical evidence labels and remove identifiers and raw evidence from every public asset, including published receipts. Keep the full private audit separate and check the staged public diff for these leaks before publication. Snapshot actual current main/release, including #416's corrections. After sanitization and actual release-prerequisite updates, regenerate the promoted-document receipt over the exact document bytes; use logical labels and hashes, never copy the path-bearing private receipt. Any subsequent public edit invalidates that document hash and requires a fresh receipt. Extend `SKILL_CONTRACT.md` and `scripts/skill_checks.py` with `codex` as a recognized host. Adapt using-claudna's hosts to `[claude-code,codex]`; keep the three excluded skills' actual restrictions. Extract only the shared component-path parser from `check_cursor_scope.py` if useful; add a Codex scope gate that rejects missing selected skills, included restricted skills, default-discovery fallback and unknown paths. Cursor's existing predicate/output remains behaviorally identical.
2. **Ship the portable host mapping.** Add `skills/_shared/codex-tools.md`, referenced from selected skill entrypoints and relevant shared dispatch chains. Map Read/Write/Edit/search/Bash to available native tools; Skill to complete file reading/invocation; Task/Agent to read-and-fill role prompt + focused subagent; TaskOutput/TaskStop to actual wait/interrupt controls. Map plan/question tools only when available, otherwise preserve read-only planning and already-authorized choices. State that allowed-tools grants, opus/background/memory, native slash registration and hooks cannot be inferred from skill text.
3. **Adapt actual host edges.** Update root resolver contract plus byte-for-byte shared copy/parity: validate a candidate contains the needed bundled file; use the selected skill's actual absolute path; no unresolved shell variable and no Codex fallback to a Claude cache glob. Update using-claudna health to inspect the Codex manifest's selected set, six expected handlers and separate trust state. Adapt audit repo-list state, recall's Claude-only auto-memory facet, init-project's AGENTS target, worktree ownership/wait mapping and the two skill-scaffold routes. Preserve per-cwd session.md compatibility. Changes to init-project descriptions/templates update catalog budgets only to measured values.
4. **Make build/review/simplify executable on Codex.** Add a shared clauDNA-owned four-lens simplify prompt (reuse/simplification/efficiency/altitude) and a Codex branch in the existing simplify chain. Dispatch through available Codex agents, deduplicate findings, preserve behavior and reverify. Stage only owned files. Revert only an identified owned simplification commit/patch when safe; never apply the legacy blanket reset to another worker's edits. Keep existing review/spec roles separate and preserve exact-scope and provenance restrictions. Update selected skills' host-specific dispatch instructions, not every mention of another project's Claude artifacts.
5. **Extend the manifest and continuity wiring.** Declare the explicit nonempty list of 36 existing skill directories, leave agents inert, retain marketplace identity/local-source grammar. Preserve all five P4 store handlers byte-for-byte; append the startup-only briefing entry with quoted PLUGIN_ROOT and timeout 5. Revise `validate_codex_store_hooks` into a precise Codex behavior-scope validator: allowed hook set/commands/matchers/timeouts, inert agent directory and curated skills. No Cursor hooks; no native agent registration/config writer. Native discovery must return exactly the selected names; unsupported array semantics fail this phase rather than silently shipping 39.
6. **Add a Codex routing substitute.** Keep existing `make routing-eval` unchanged and do not run it in Codex-only verification. Add `routing-eval-codex` with explicit result method `catalog_selection`, using the same utterances plus Codex coverage additions. Deterministic floor checks discovery, names/descriptions/invocation hints, required mode tokens, positive coverage for all 36 and confusable/negative controls. The one promotion-intake expectation is explicitly unsupported on Codex, with a source-checkout reason; it is not silently relabeled a pass or deleted from Claude's matrix. Add deterministic mocked-runner tests for invalid JSON, wrong skill/mode, excluded skill, timeout/auth/setup errors and exhausted attempt budget.
7. **Measure real Codex selection and loading separately.** A bounded isolated `codex exec` run receives only public fixture utterance plus installed catalog names, descriptions and actual `argument-hint` values and produces schema-constrained `{skill,mode}`. Use supported read-only/ephemeral/config-isolation flags, subprocess timeout and an attempt-count ceiling; no invented dollar or turn-limit flag. Persist IDs/enums/counts/timing and actual model/version; do not export prompt/tool/auth content. Default live set: the ten existing live-marked rows + two controls, plus six paired build/build-all, capture/recall and worktree/sync cases, one attempt each. Stop on three consecutive setup errors and report incomplete evidence. These are model-based catalog choices, not native automatic skill invocation accuracy. Then run separate actual native marketplace skill-load/action probes: explicit using-claudna health, a read-only review/verification workflow, the mandatory same-host reviewer fixture above, and session handoff/resume in a disposable project. Pin host identity/surface and actual tools for each result; desktop dispatch is not native CLI proof. Use fake gh/service outputs where necessary and no real outbound changes. Record actual loaded SKILL.md paths/normalized IDs, real spawn/wait receipts and observable artifacts; final answer self-report alone is not load evidence. A plain-prompt native routing miss remains a finding even if the choice substitute passed. Actual harmless packaged startup-hook execution and stdout context delivery on the target native CLI are also mandatory: record startup source, packaged command identity/exit, and evidence that its unique synthetic Boolean marker reached the model context. Zero-turn discovery, replay alone and a final-answer claim without linked execution/context evidence are insufficient. If this proof is absent or fails, startup continuity cannot be marked accepted or released as supported.

   **Mandatory native automatic-routing arm:** in the disposable bug fixture, launch the target native CLI with its normal installed curated catalog and the plain public utterance, "Check the current change for bugs and report any exact file and line." Do not mention any skill, role prompt or file to load, supply a catalog-selection prompt, or require a `{skill,mode}` schema. The normal catalog metadata may be supplied only by the runtime's usual plugin discovery. Retain actual skill-read/action metadata showing whether the expected review-work route loaded its installed SKILL.md and performed the requested review. Record normalized skill ID, installed file hash, host/version, read/action receipts and the resulting fixture finding, without publishing raw prompt/tool content or private paths. An explicit skill invocation or successful structured-choice result cannot substitute for this arm. Missing reads, wrong routes and action failures remain native routing findings, separately reported from `catalog_selection` results; do not claim automatic routing passed from discovery or self-report.
8. **Integrate and release only converged source.** Fresh baseline/after exports with private HOME/TMPDIR; full make check, actual Python 3.9 runtime floor, manifest/layout/catalog/host-portability tests, deterministic routing tests and fresh native discovery/skill probes. Preserve any baseline failing names rather than declaring an already failing suite green. Independent Codex simplify + source/spec/evidence reviews fold findings. Open/attach a draft-first PR, run exact-head CI, integrate eligible source and release the next actual minor version after P4 using the three-manifest release flow. Read back the tag/tree/release, then supply that release to #2149. Keep #404 open until its mixed-fleet done criterion has actual evidence.

## Complexity and Sequencing

| Phase / PR | Size | Depends on | Parallel with |
|---|---|---|---|
| 404-A host adapter, audit and shared workflow edges | M | P4 source; release before consumer use | Routing runner implementation |
| 404-B catalog/agent-dispatch/continuity distribution | M | 404-A and P4 marketplace release | Deterministic tests |
| 404-C Codex routing substitute, native proof and release | M | 404-B | Unrelated telemetry observation |
| 404-D mixed-fleet acceptance | External elapsed gate | 404-C release + #2149 runtime + explicit host/channel authority | None assumed |

Critical path: P4 release → A → B → C release → #2149 composition → actual mixed-fleet week. Source phases may be one reviewable PR if their combined diff stays coherent; phase boundaries still govern evidence and release order.

## Test Plan

- **Scope gates:** fixtures include missing/empty skills fields, empty arrays defaulting to 39, extra/omitted/excluded names, malformed paths, unintended agent content, extra hooks and altered matchers/timeouts. Positive fixture has exactly the 36 names and six handlers. Existing Cursor 35 and Claude 39 are separately pinned.
- **Workflow mapping:** fixture-driven reads of Task/Agent/Skill/wait/plan mappings; complete installed role prompts are fully filled with task/absolute root and hashed; no Claude model alias or unsupported background/memory claim survives the Codex dispatch path. The mandatory disposable expiry fixture requires actual same-host spawn/completed-wait receipts and the correct `expiry.py:2` equality finding. Record desktop and native CLI separately; desktop success cannot clear the CLI gate. Capture/using-claudna do not invoke excluded skill-scaffold. Missing browser/subagent capability yields an explicit unsupported result and limits the affected host route; a required independent review stays unsatisfied.
- **Root and project state:** installed paths with spaces, no plugin env in ordinary shells, poisoned cwd helper names, absent bundled file, unsupported host cache fallback, existing AGENTS.md, Claude-only memory, and cross-runtime handoff readback. No global auth/config/notes/cache mutation.
- **Startup continuity:** replay the actual captured Codex startup envelope into the packaged command; verify bounded untrusted-data framing and health pointer, opt-out, no repo, absent/slow fake gh and no global state. Native discovery verifies matcher/timeout separately. An actual harmless read-only Codex turn is mandatory to verify the target native CLI executes the installed packaged startup hook and delivers its stdout synthetic Boolean marker into context. Capture linked source/command/exit and context-delivery evidence; discovery, replay and an uncorroborated final-answer claim do not substitute. Missing or failed execution/delivery blocks startup support acceptance. No compact hook or capture-owner duplication.
- **Routing:** preserve the complete 41-row/two-control source matrix and explicit host filtering; static coverage for all 36; fake-runner RED/GREEN parser/failure cells; bounded real Codex choice check; actual skill-load/action proofs kept separate. At least one actual native CLI arm uses the normal installed catalog and an unhinted public fixture utterance with no skill mention or schema-selection prompt; actual skill-read/action receipts decide its outcome. Preserve native misses separately even if structured choices pass. No Claude inference or live Modal/Railway/Vercel/warehouse operation; no model-based claim from static checks.
- **Integration:** compare source bytes/Git modes/dependencies/interpreter before/after each isolated run; full gate, actual runtime floor, native zero-turn discovery and subsequent read-only action canary. Versioned release tree and cache contents must match reviewed/tested source.

## Verification Checklist

- [ ] Audit is pinned to source SHA/tree, includes all 39 skills/eight agent prompts/12 hook files, and each lexical count is reproducible.
- [ ] Claude 39 and Cursor 35 remain unchanged; Codex discovers precisely the selected 36, never default 39.
- [ ] Both selected-to-excluded references have a functioning Codex context explanation; no missing registered-skill invocation.
- [ ] Agent dispatch support is qualified by execution host. Each claimed route has a fully filled installed reviewer prompt, real same-host spawn/completed-wait receipts and correct `expiry.py:2` finding; desktop proof does not clear native CLI. Unsupported CLI routes and unsatisfied independent-review requirements remain explicit.
- [ ] Shared simplify/wait/root mappings are real procedures, with owned-change and evidence boundaries preserved.
- [ ] Six intended handlers are discoverable; five store handlers retain P4 behavior; mandatory actual packaged startup execution and stdout context delivery are observed separately from discovery/replay; trust remains explicit.
- [ ] Deterministic routing floor, bounded real Codex selection, explicit skill loading/action probes and the unhinted native automatic-routing arm are separately reported; actual read/action metadata supports native outcomes, and misses are not masked by `catalog_selection` passes.
- [ ] Fresh full/floor/CI evidence, independent reviews and release/tag/tree/cache readbacks converge.
- [ ] Public plan/audit promotion replaces private locators with logical evidence labels, preserves input hashes and contains no raw rollout/prompt/tool/auth content or personal identifiers. The promoted-document receipt was regenerated over the exact sanitized bytes after actual release-prerequisite updates; no path-bearing private receipt is published.
- [ ] #2149 mixed-fleet week completed on a specifically authorized live host/root/fleet/channel before #404 is closed — **currently blocked and unperformed**.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Manifest discovery falls back despite declared paths | Unusable or unsafe catalog scope | Actual native names/count comparison and negative empty-array fixture; fail closed. |
| Host mapping is read too late or only at top level | Nested workflows call nonexistent tools | Entrypoint and shared-chain pointers, filled prompt tests and actual reviewer dispatch probe. |
| Desktop subagent proof is transferred to native CLI | Delegation-dependent workflows fail on their target host | Pin the execution surface, require the known-bug fixture with real same-host spawn/wait receipts, and label unsupported routes. |
| Structured choice passes while native routing still fails | False behavior-parity claim | Distinct method labels, a mandatory unhinted native arm and actual skill-read/action receipts; preserve misses as findings. |
| Existing Claude paths are rewritten indiscriminately | Breaks valid artifact searches/handoff consumers | Counted classification, surgical branches and unchanged Claude/Cursor regressions. |
| Startup optional network work stalls | Slow or missing continuity context | Native five-second cap, fake slow-gh control, no universal completion promise. |
| Startup registration is mistaken for context delivery | Continuity is advertised without working injection | Mandatory actual packaged native execution and linked stdout marker delivery; discovery and replay remain separate floors. |
| Source success is mistaken for live fleet acceptance | Premature issue closure | Separate blocked acceptance phase and owner release/composition order. |
| Private audit is copied into a public plan/receipt | Personal paths or raw evidence leak | Logical evidence labels, staged-diff privacy gate and a newly generated exact-byte receipt after sanitization. |

## Companion Plans

- Claudfather/Claudlobby#2145 canonical runtime-neutral plan/run log: measured prerequisites and owner boundaries.
- clauDNA P4 `documentation/plans/2026-10-16-codex-session-store-adapter.md`: released store substrate; F10/F8 remain intact.
- Claudron P4 runtime-neutral owner plan: complete owned session-loop pack and capability/release gate.
- Claudfather/Claudlobby#2149: execution, composition, policy, supervision and the actual mixed-runtime week. This draft does not seize that ownership.

## What NOT To Do

Do not remove any canonical skill, copy 39 skills blindly, invent native Codex agent registration, invoke Claude inference, change the summarizer, weaken permissions or review rigor, trust hooks automatically, mutate global user configuration, port unobserved permission/notification/edit/failure payloads, fork Claudron's protocol, claim static routing is E2E, or waive elapsed/live gates. Do not change the root's release checkout while preparing this private plan.

## Context

Area: behavioral portability and marketplace scope. Overall effort: L across three source slices. Priority: critical path to #2149 mixed-runtime acceptance. The user explicitly delegated Codex source reviews/implementation and planned marketplace scope; the remaining user input is operational, not an owner code-review request: a concrete live host/root/fleet/channel must be authorized for the final canary. Exact runtime/API limitations discovered during implementation are evidence gates, not reasons to guess an API or stop independent source work.

## Implementation measurement correction

The first complete 18-case `catalog_selection` epoch exposed an evaluator input
gap: names and descriptions selected the correct skill in all cases, but two
required modes live in installed `argument-hint` metadata. The original routing
matrix explicitly separates description selection from body mode dispatch. The
corrected catalog exports each installed skill's actual `argument-hint`, without
fixture-derived answers or case-specific hints, and labels that input accurately.
One fresh bounded complete epoch follows the correction; the original 16/18
normalized result remains evidence. Original nonmatching mode strings were not
retained, so those exact strings are unavailable rather than inferred from nulls.
The corrected runner retains exact schema responses privately, while public
reports contain only case IDs, known enums, counts, timing and observed metadata.
This correction does not replace the separate unhinted native routing gate.

The second complete epoch retained 17/18: the actual `first-principles` lens
value differed from the required `--lens` invocation token. Independent contract
review identified ambiguity in the generic word mode. Prompt and schema now
share one rule for the routing invocation suffix: preserve installed verbs or
selector flags and supplied values; omit unavailable positional placeholders and
never invent arguments. This rule applies to every skill. Expectations, judging
and both historical epochs remain unchanged. One fresh complete epoch measures
this correction, without case-specific answers or normalization into a pass.

The third complete epoch remains 17/18: the same ironclad utterance returned
`mode: null`. The real result and exact private schema responses are retained; no
further inference or acceptance normalization follows. The selection mode gate
is unresolved pending independent review of the residual. Source checks and
other native observations proceed independently; this phase is not releasable
from that result alone.

Independent spec review classified the retained 17/18 as a bounded exact-mode
selection limitation: the utterance does not uniquely require the single-lens
route. The original expectation and failed result remain unchanged, with no
rescore, waiver or assumed reason for null. No 18/18 threshold was specified as
a separate acceptance hard gate; release eligibility still requires every actual
hard gate and independent source/evidence review.

The first frozen full run exposed stale resolver/scoping assertions and a real
explicit-override precedence concern. The correction preserves Claude's expanded
SKILL-body candidate first, then validated operator roots before the loaded-path
default; Codex skips Claude-only expansion/cache candidates. Existing runnable
script cases remain, with added Codex/no-cache, paths-with-spaces, poisoned-cwd
and unknown-instruction refusal coverage. Orientation proves Codex inclusion and
Cursor exclusion. The ironclad availability claim now follows actual tool
detection, with required independent review left unsatisfied on an inline path.
