---
title: "[plan] EPIC: Claudron integration — the vault becomes the knowledge engine"
type: plan
status: draft
owner: chris
created: 2026-07-07
updated: 2026-07-07
tags: [planning, epic, claudron, knowledge-lifecycle]
repos: clauDNA
links:
---

# EPIC: Claudron integration — the vault becomes the knowledge engine

The companion epic to Claudron's v0.2→v0.6 roadmap (Claudfather/Claudron#14, docs under
`documentation/plans/2026-07-07-claudron-roadmap/`). Claudron ships the engine; this epic
rewires clauDNA's knowledge-lifecycle skills to prefer it, provisions the vault seam that
today has a consumer but no producer, and settles the two-doc-planes question that
`output-guide.md:19` has deferred since the substrate shipped. Hardened by an ironclad
cycle-1 panel before filing (`08_ironclad-cycle1.md` — 6 lenses, 4 blockers found and
folded).

## Summary

clauDNA's knowledge loop (`/remember → work → /learn → /reflect → /index`) has two
independent problems. First, its substrate is provisioned by nothing: `/remember`
resolves `SHARED_DOCS_PATH` or a "Shared Documentation" CLAUDE.md section that no clauDNA
skill ever creates — the consumer has no producer, so the loop is dead on arrival in
fresh repos. Second, its retrieval is an INDEX.md line-scan, which Claudron's field
research (F3) puts at a ~100–200-page viability ceiling (distinct from the 5-doc
*presentation* budget, which is a context-cost rule this epic deliberately keeps).

**Track A (P1–P3) fixes the first problem and needs no Claudron code** — it is
independently ratifiable and carries standalone value even if Claudron never ships:
publish becomes the single router over both doc planes, the vocabulary gets one SSOT,
and `/init-project` finally provisions the seam. **Track B (P4–P7) fixes the second** by
preferring Claudron's engine (schema-validated, dedup-gated, search-backed) wherever a
vault is detected, with today's behavior preserved as the frozen fallback. Six decision
forks are presented open with leans; the epic Issue is the ratification surface.

## Evidence

Verified against this repo at `fc04d4f` and Claudron `main` post-#13 (2026-07-07); every
anchor below was independently re-verified by the ironclad panel (adversarial-review +
precedent-check both report all citations accurate):

- **The producer-less consumer:** `skills/remember/SKILL.md:26` (root resolution:
  `SHARED_DOCS_PATH` env or CLAUDE.md "Shared Documentation" section);
  `skills/init-project/SKILL.md` provisions neither. Repo-wide grep: only `remember` and
  `index` consume the shared-docs root; nothing produces it (unchanged since the
  substrate landed in PR #4, 2026-05-11).
- **The retrieval ceiling:** `skills/remember/SKILL.md:51` + `:98-99` (hard 5-doc cap;
  INDEX-scan-only rule). Claudron field evidence F3: flat-index scanning stops being
  viable as primary retrieval at ~100–200 pages. The cap is a presentation budget and
  stays; the scan is the ceiling and gets an engine underneath it.
- **The deferred split:** `skills/_shared/output-guide.md:5` (self-declared "canonical
  house-style spec") and `:19` — publish's disk adapter targets the shared vault while
  planning skills' default `docs` target writes per-project `documentation/planning/`
  directly; "Reconciling the two is its own change." Known contradiction the panel
  sharpened: `skills/forge/SKILL.md:22,:206` already *describes* `--output docs` as
  routing through publish while publish's disk adapter targets `shared/planning/active/`
  (`skills/publish/SKILL.md:69-76`) — and audit skills write multi-file session
  directories whose `00_` masters would fail publish's Step 1b skeleton hard gate
  (`skills/publish/SKILL.md:56-58`). P1 fixes the mechanism, not just the prose.
- **The deferred bridge:** `documentation/archive/2026-05-15-session-handoff-resume-redesign-design.md:199-205`
  — "`/claudron-write` (or equivalent)" out of scope "when Claudron's MCP server lands"
  (ratified in PR #88); `CHANGELOG.md:138` — "until the Claudron-write skill ships."
- **The stacking hazard:** `plugin-hooks/precompact-reflect.sh` blocks first compaction
  and instructs `/claudna:reflect`; clauDNA registers **no SessionEnd hook**
  (`plugin-hooks/hooks.json`). Claudron E2 PR3 plans capture prompts on **PreCompact and
  SessionEnd** and commits to detecting claudna and deferring — so the contract must be
  per-event, and the detection surface must be purpose-built (the reflect marker is
  transient; the opt-out env var is unset in the default case).
- **The engine contract:** Claudron `03-mcp-server.md` — `claudron_write` returns
  `{action: created|updated|suggest_update|suggest_supersede, path, reason}` and
  **routes near-duplicates, never hard-rejects**. `02-session-loop.md` — the same
  validate/dedup/slug `engine.py` ships one epic earlier as CLI `recall`/`capture`
  (E2 PR2, release 0.2.0, **before Gate G1**) — but 0.2.0 is explicitly single-writer
  (the `flock` write-lock arrives in E3), which Track B's concurrency posture must
  absorb. `01-schema.md` — SCHEMA.md as SSOT: `status` activity union includes clauDNA's
  values with documented mappings; `maturity` is a second axis; the type enum excludes
  `skill` **by design**; clauDNA's `output-guide.md` is named as the reconciliation
  target (their E1 PR4 lands the pointer; this epic owns the behavior).
- **Companion-repo reality check (panel):** Claudron has zero releases and no SCHEMA.md
  on `main` today (its E1 issue state notwithstanding) — hence every gate below is an
  **artifact gate** (a file, a tag), never an issue state.
- **Backlog staked out:** #110, #112, #106, #107, #50, #36, #104 — plus panel-found
  overlaps #116/#159 (publish single-sink completion), #114 (deprecation lifecycle),
  #192 (removed-names gate hardening), #111, #41, #176. Dispositions in Reconciliation.

## Architecture

Target end state — **one engine, two planes, one router**:

```
                       ┌──────────────────────────────────────────────┐
                       │ Claudron vault (private git repo)            │
  /remember ──recall──▶│  _shared/{knowledge,decisions,runbooks,      │
  /learn ────capture──▶│           planning/{active,completed}}       │
  /reflect ──capture──▶│  projects/<repo>/                            │
  /claudron ──────────▶│  SCHEMA.md = field-vocabulary SSOT           │
   write|read|status   │  engine: validate + dedup + rank (E2/E3)     │
                       └──────────────▲───────────────────────────────┘
                                      │ CLI door (floor, 0.2.0): claudron recall/capture/read/status --json
                                      │ MCP door (optional, 0.3.x): mcp__claudron__* — same engine
                                      │ fallback (no claudron): raw shared/ tree + INDEX.md scan (frozen)
       ┌──────────────────────────────┴──────────────┐
       │ /claudna:publish — the single output router │
       │   --to vault  (knowledge/runbook/decision;  │
       │    engine-backed when claudron present)     │
       │   --to docs   (per-project documentation/ — │
       │    plans/audits/reviews; single doc OR      │
       │    00_+NN_ family)                          │
       │   --to github-issue | github-pr | session   │
       └─────────────────────────────────────────────┘
```

- **Plane doctrine (F3):** per-project `documentation/` holds work-in-flight and
  repo-coupled records (plans, audits, reviews, ADRs, specs) — versioned with the code,
  PR-reviewed, public if the repo is. The vault holds cross-project referential
  knowledge — private, lifecycle-managed, search-backed. Both planes stay; `publish` is
  the one router that knows the difference, and the doctrine section ships a
  **"which door" table** partitioning the four vault-writing surfaces
  (`/claudron write` = deliberate save · `/learn` = external ingestion · `/reflect` =
  session distillation · `publish --to vault` = finished-doc routing).
- **Engine preference with a frozen fallback:** every vault touch goes through the
  Claudron engine when a vault is detected (detection ladder + JSON-envelope validation
  + bounded-retry-then-degrade posture specified once in `skills/_shared/claudron-engine.md`,
  born in P4). When claudron is absent, skills run today's raw-tree + INDEX.md behavior
  — **frozen by policy**: no new features land on the fallback path; it is the
  compatibility floor, not a parallel product. clauDNA ships **zero MCP servers** and
  never writes user settings — the CLI is the contract floor; the MCP tools are an
  equivalent door users may configure.
- **Boundary, both directions:** procedural content never enters the vault (SCHEMA.md
  excludes `type: skill`; Claudron `validate` warns on skill-shaped notes; clauDNA's
  write doors refuse and point at `/claudna:skill-scaffold`). Referential content stops
  accumulating in clauDNA surfaces: `/notes` + `/lessons` are dispositioned in P7 under
  fork F4 — with the capability trade-off stated honestly there.

## Implementation Plan

### Dependencies

Artifact gates only (never issue states): SCHEMA.md file on Claudron `main` gates P2;
the Claudron **0.2.0 release tag** (+ the E1 CLI-contract one-pager it includes) gates
P4–P7. Track A's P1/P3 are ungated. Nothing waits on Gate G1 or E3 under the F1 lean —
this deliberately revises the "blocked on E3" framing the roadmap's socket row assumed.
**0.2.0 re-confirmation checkpoint:** before P4 starts, re-verify the shipped CLI
(envelope keys, flags, `init` verb names) against the specs written here from roadmap
bullets; fold deltas as amendments, not surprises.

### Blocks

#106/#107 (P7), #36 (superseded at P5), #112's clauDNA half (P6), #116/#159's remaining
work (P1), the #50 loop's retrieval half, and Claudron E3 PR4's clauDNA-handoff
deliverable (which becomes "confirm parity," not "build the integration").

### Steps

Phase-by-phase; each phase is one PR, detailed in its own doc:

1. **P1 — publish two-plane router** (`01_doc-planes-router.md`, **L**, ungated):
   `--to docs` adapter with **single-doc and family modes** (00_ master + NN_ phases;
   per-doc loop mirroring forge's F7 family-publish; masters validated for presence,
   phases for the full §4.1 skeleton — the implement-plan-readiness gate applies to
   phases, not inventories); `disk`→`vault` rename with a one-release alias (F4-doctrine
   scoping recorded: no-stub applies to picker entries, not adapter flag values — the
   0.2.0→0.5.0 stranding incident argues for the grace window); the plane-doctrine +
   which-door table in documentation-standard; the author-skill sweep (grep-derived
   list, ~8 skills, incl. fixing forge's stale `--output docs` prose).
2. **P2 — vocabulary SSOT** (`02_vocabulary-ssot.md`, **M**, gated on SCHEMA.md
   existing): output-guide §3 becomes a rendered copy of SCHEMA.md's vocabulary,
   **stamped with the source commit** and diffed by a CI drift check; publish/index enum
   tables deduplicate to it; `maturity` + `schema_version` accepted-and-passed-through;
   namespaced `x-*` fields as the local escape hatch; gap channel = comments on the
   relevant open Claudron epic issue.
3. **P3 — init-project provisions the vault seam** (`03_init-project-vault-seam.md`,
   **M**, after P1's doctrine section): the "Shared Documentation" CLAUDE.md section
   (parseable format spec + `(claudron vault)` annotation for engine-managed roots),
   detection ladder incl. the CLI-present-no-vault branch, raw-tree scaffold defaulting
   to a stable absolute `~/shared`, `claudron init --personal` guidance, retirement of
   the deprecated `repo-documentation-standard.md` stub, and the consolidated
   "Claudron integration" SETUP_GUIDE section later phases append to.
4. **P4 — `/claudron` engine skill + the engine contract** (`04_claudron-engine-skill.md`,
   **L**, gated on 0.2.0 + ratification): verbs `write` | `read` | `status` per
   `infra-cli-contract.md` (thin body, per-verb depth files); drafts by default on the
   maturity axis; routes-never-rejects surfaced; `skills/_shared/claudron-engine.md`
   born here (detection ladder, envelope validation on every call, bounded-retry-then-
   degrade, fallback-freeze policy); `publish --to vault` upgraded to prefer the engine.
   The `read` verb is the read-door answer P7's disposition depends on.
5. **P5 — `/remember` + `/learn` prefer the engine** (`05_remember-learn-engine.md`,
   **M**, after P4): recall replaces the INDEX scan when a vault is detected (door
   reported either way); learn writes through capture with engine title-dedup interim
   (source_url key requested cross-repo); fallback prose unchanged and frozen; the
   retrieval-delta fixture makes "materially smarter" measurable.
6. **P6 — `/reflect` vault-write + the per-event stacking contract**
   (`06_reflect-precompact-stacking.md`, **M**, after P4): reflect routes through the
   engine with retry-then-fallback (nothing is ever lost at compaction); the stacking
   contract becomes **per-event** (PreCompact: clauDNA prompts, Claudron defers;
   SessionEnd: Claudron prompts, clauDNA is silent — it has no such hook; cross-event
   double-capture is dedup-absorbed); a purpose-built presence marker
   (`claudna-active-<session_id>`, written by session-start.sh) replaces the
   unobservable reflect-marker/env surface; contract cross-posted to Claudron#16 with
   the write-lock pull-forward ask.
7. **P7 — `/notes` + `/lessons` disposition** (`07_notes-lessons-disposition.md`, **M**,
   gated on F4 locked + P4–P6 released + #192's gate hardening merged + adoption
   evidence): executes whichever F4 option is ratified; if (a), ships with the read
   door live, gate-derived sweep (incl. SKILL_CONTRACT's own `/notes` example and the
   CLAUDE.md template's `/claudna:lessons` line), field-remediation guidance for
   already-initialized repos, an idempotent-by-dedup migration guide, the semver
   statement, and a named breakage-report channel for the bake.

## Decision Forks

### Fork F1: Engine door — CLI-first or MCP-first
- **Context:** Claudron exposes the same engine twice: CLI (`recall`/`capture`, E2,
  0.2.0, pre-gate) and MCP tools (E3, 0.3.x, behind Gate G1). The roadmap's socket row
  assumed skills call the MCP tools.
- **Options:** **(a) CLI-first** — skills shell `claudron … --json` via Bash; MCP
  documented as an equivalent optional door · **(b) MCP-first** — skills call
  `mcp__claudron__*`; CLI unused · **(c) dual dispatch** — probe MCP, fall back to CLI,
  then raw tree.
- **Lean: (a) CLI-first.** Unblocks at 0.2.0 (one release earlier, off the gated path);
  works headless/CI where MCP config may be absent; needs zero user settings (clauDNA
  can't provision `.mcp.json` without violating its own never-touch-settings rule);
  rides E1's ratified CLI contract. MCP adds in-context *discovery*, which clauDNA
  skills don't need. (b) couples the epic to G1's ordering risk. (c) is (a) plus a probe
  sentence — allowed as prose; the *contract floor* is the CLI.
- **Ratifier:** Chris · **Status: open**
- **Consequence:** P4–P7 gate on Claudron 0.2.0, not E3. Under (b), Track B re-gates on
  E3/G1.

### Fork F2: Write-door shape — `/claudron` engine or `/claudron-write` skill
- **Context:** the archived design doc (PR #88) named "`/claudron-write` (or
  equivalent)"; SKILL_CONTRACT §4 has since ruled on tool-wrapping shape
  (engine-with-verbs, never tool×verb SKUs) — this fork records that the contract, not
  the archive, decides the name.
- **Options:** **(a) `/claudron` engine with verb modes** (`write`/`read`/`status` now,
  room for more) · **(b) single-purpose `/claudron-write`**.
- **Lean: (a)** — contract-conformant, and the `read` verb (added at panel insistence,
  see F4) has a natural home.
- **Ratifier:** Chris · **Status: open**

### Fork F3: Doc-planes end state
- **Context:** `output-guide.md:19` — the deferred reconciliation between per-project
  `documentation/` and the shared vault. **Gate: this fork locks before P1 merges** (P1
  implements its outcome).
- **Options:** **(a) two planes, one router** — both stay; publish routes by plane;
  plane assignment by content kind · **(b) collapse into the vault** · **(c) status
  quo**.
- **Lean: (a).** The planes serve different masters: `documentation/` is PR-reviewable,
  travels with the repo, public when the repo is; the vault is private, cross-project,
  lifecycle-managed. (b) moves public-repo design docs into a private vault; (c) is the
  current confusion with a second substrate arriving. (a) adds routing, removes nothing.
- **Ratifier:** Chris · **Status: open**

### Fork F4: `/notes` + `/lessons` disposition
- **Context:** #106/#107 defer disposition until a Claudron equivalent ships; P4–P6 are
  that equivalent under a **capability reading** of the wait condition (the issues
  imagined Claudron shipping the skill surface itself — the ratifier should endorse or
  reject that reading here). **The trade-off, stated plainly (panel blocker):** removal
  replaces the only zero-dependency cross-session knowledge surface with a door that
  hard-requires an external pre-1.0 CLI; `/notes` is read+write+organize and `/lessons`
  has an on-demand read path, so parity requires the `/claudron read` verb (P4) and
  honest breadcrumbs; the mission's self-contained posture and its "no hosted
  dependencies" line cut against a *hard* dependency even as its sibling-boundary line
  ("clauDNA does not store reference knowledge") cuts for removal.
- **Options:** **(a) hard removal at P7** — F4-#165 machinery, preconditioned on the
  read door being live, an installable claudron ≥0.2.0, and adoption evidence beyond a
  7-day bake (maintainer-canary pulse + zero breakage through the named channel) ·
  **(b) soft preference** — skills stay, bodies prefer the vault when detected; removal
  deferred to a later epic with usage evidence · **(c) redirect stubs** for one release,
  then remove.
- **Lean: (a), but it is a genuine call** — (b) is the honest runner-up if the ratifier
  weighs the standalone-user regression heavier than the two-writers-one-data-shape
  cost. Per-repo `.claude/lessons.md` is repo-plane and survives under every option.
- **Ratifier:** Chris · **Status: open** · **Gate: locks before P7 starts (not before
  Track B generally).**

### Fork F5: `--auto` visibility of the engine door
- **Context:** structured results currently carry no signal of which door served a run
  — and the panel showed silent degradation is the dangerous case, not door choice.
- **Options:** **(a) artifacts field + degradation surfacing** — `"engine":
  "claudron|fallback"` in `--auto` artifacts *and* an `errors[]` entry whenever an
  engine call degraded mid-run; no new telemetry writer · **(b)** new `engine_usage`
  events in skill-events.jsonl · **(c)** nothing.
- **Lean: (a)** (amended from artifacts-only at panel insistence). Claudron's own
  `events.jsonl` instruments the engine side; clauDNA surfaces only what orchestrators
  must see. **Gate: locks before P4 merges** (P4 implements it).
- **Ratifier:** Chris · **Status: open**

### Fork F6: Integration-surface ownership (panel-added)
- **Context:** the adversarial lens's strongest alternative — Claudron could ship the
  agent-facing surface itself (a Claudron-authored plugin carrying the `/claudron`
  skill and capture prompts, versioning with `engine.py`), eliminating the cross-repo
  CLI-drift tax that P4–P7 pay via envelope checks and degradation paths.
- **Options:** **(a) clauDNA ships the skills** (this epic as written) · **(b) split
  ownership** — clauDNA ships Track A + the published stacking/detection contract;
  Claudron ships `/claudron` + capture prompts as its own plugin; clauDNA's
  remember/learn/reflect engine preference lands here either way (those are edits to
  clauDNA-owned skills).
- **Lean: (a).** One install keeps the full lifecycle coherent (the marketplace story
  and SKILL_CONTRACT/CI quality control live here), and (b) does not actually dissolve
  the drift tax — the engine-preference edits to `/remember`/`/learn`/`/reflect` are
  clauDNA changes under any owner, so the contract-pinning machinery (P4's
  claudron-engine.md) is needed regardless. But this is a real placement decision the
  ratifier should make consciously; under (b), P4 shrinks to claudron-engine.md only and
  P7's replacement surface becomes a Claudron deliverable.
- **Ratifier:** Chris · **Status: open**

## Companion Plans

- Claudfather/Claudron#14 (EPIC) + #15–#20, docs at
  `documentation/plans/2026-07-07-claudron-roadmap/`. Cross-references: their E1 PR4
  (output-guide pointer), E2 PR3 (PreCompact stacking — coordinate before it merges),
  E3 PR4 (clauDNA handoff — becomes parity confirmation).
- #165 (closed) — the F4 deprecation machinery, removed-names gate, and per-phase
  release train P7 reuses; #155 (closed) — the Issue/publish substrate P1 extends.
- `08_ironclad-cycle1.md` — the panel record for this family (6 lenses; findings and
  fold dispositions).

## Risks

| Risk | Level | Impact | Mitigation |
|---|---|---|---|
| Claudron 0.2.0 slips or G1 pivots the roadmap | Med | Track B idles | Track A is independently valuable and separately ratifiable; Track B gates on a release *tag*; CLI door (F1a) is pre-gate so a G1 pivot doesn't reorder our dependencies |
| 0.2.0 ships different from its roadmap bullets | High | Specs here churn; forks re-ratify | Artifact gates + the 0.2.0 re-confirmation checkpoint before P4; Track B phase issues carry "re-verify contract against shipped CLI" as step 0 |
| Concurrent sessions race a single-writer engine (0.2.0 has no write lock; parallel worktrees are the house workflow) | High | Silent loss — worst case a reflection dies at PreCompact | Bounded retry then degrade to the raw-tree fallback for learn/reflect (doors that have one); `/claudron write` fails loudly, never silently; write-lock pull-forward requested on Claudron#16; residual risk stated in P6 |
| Pre-1.0 CLI contract drift under us | Med | Engine paths break quietly | Envelope-shape validation on **every** engine call (not a version ritual); degradation surfaced in `--auto` `errors[]` (F5a); `requires: cli: claudron>=0.2` |
| Double-prompt or zero-capture at session boundaries once both plugins ship hooks | Med | Hook fatigue, or silent knowledge loss on non-compacting sessions | Per-event stacking contract (P6) published before Claudron E2 PR3 merges; purpose-built presence marker; cross-event dedup absorption stated |
| F4 removal strands claudron-less users (capability regression) | High | Trust damage; mission tension | The regression is stated in the fork itself; preconditions (read door, adoption evidence, named breakage channel); migration guide idempotent-by-dedup; per-repo `.claude/lessons.md` untouched; F4(b) is a live option |
| Vocabulary drift between the rendered copy and SCHEMA.md | Med | Cross-repo validation disputes | Rendered table stamped with source commit + CI drift check (P2); drift fails a check, not a debate |
| Two planes confuse authors | Low | Misfiled knowledge | Doctrine + which-door table (P1); publish *advises* on plane fit (advisory-only, wording aligned); `/remember` reports which door served results |

## Complexity and Sequencing

| Phase | Size | Gate (artifacts only) | Fork gate | Parallel with |
|---|---|---|---|---|
| P1 — publish two-plane router | L | none | F3 locked | P2 prep, Track B waits |
| P2 — vocabulary SSOT | M | SCHEMA.md file on Claudron main | — | P1/P3 |
| P3 — init-project vault seam | M | P1's doctrine section merged | — | P2 |
| P4 — `/claudron` engine + engine contract | L | Claudron 0.2.0 tag + re-confirmation checkpoint | F1, F2, F5, F6 locked | P2 |
| P5 — remember/learn engine preference | M | P4 merged | — | P6 |
| P6 — reflect + stacking contract | M | P4 merged; contract posted before Claudron E2 PR3 merges | — | P5 |
| P7 — notes/lessons disposition | M | P4–P6 released; #192 gate merged; adoption evidence | F4 locked | — |

Critical path: P1 → P3 (Track A, can start now; independently ratifiable) and
0.2.0 → P4 → P5/P6 → P7 (Track B). Releases are per-phase with CHANGELOG discipline;
P7 is the only deletion release. Filing posture: the whole family files now; Track B
phase issues carry the re-confirmation step 0 rather than waiting for the tag to file.

## Reconciliation (dispositions of overlapping open issues)

- **#110** (post-lifecycle capture hook, self-rated High) — **explicit disposition, not
  just a cross-link (panel):** its hook-as-written would violate P6's one-prompter
  contract. The capture *mechanism* it wants is Claudron E2's hook pack + P6's
  reflect-subsumes-capture routing; the lifecycle-completion *trigger* it wants is
  re-scoped to Claudron's hook layer (their E2 PR3 owns session-boundary capture).
  Recorded on the issue at filing; #110 closes when P6 ships unless the fleet trigger
  resurfaces as a distinct need.
- **#112** (persist phase in protocols) — clauDNA half lands in **P6** (persist-nudge
  lines in `/session` handoff mode + `/review-work` post-verdict prose); claudlobby's
  `library/protocols/` half stays theirs. #112 closes at P6 with the pointer.
- **#106 / #107** (lessons/notes boundary) — resolved by **P7** under fork F4; closing
  comments record the capability reading of the wait condition explicitly.
- **#36** (`/index --fleet`) — **superseded at P5**: cross-repo query lands via the
  engine over `projects/<repo>/` tiers; fleet aggregation is engine-only **by design**
  (raw-tree fallback stays repo-local — stated in the close-out).
- **#50** (closed knowledge loop) — this epic is the Claudron-era continuation of its
  retrieval half; cross-linked, stays open as the umbrella.
- **#104** (SessionStart auto-resume) — unaffected; P6's SessionStart note only budgets
  co-injection. Light cross-link.
- **#116 / #159** (publish single-sink completion; §4.1 conformance audit) — **P1 is
  substantially their remaining work** (the author-skill sweep); partial-close notice
  at filing, closed or re-scoped when P1 lands.
- **#114** (formalize the deprecation lifecycle) — P7 is the third execution of the F4
  pattern; its ledger posts to #114 as the data point the formalization wants.
- **#192** (removed-names gate: directory-resurrection check) — **hard-sequenced before
  P7** (it is the resurrection guard for exactly this deletion).
- **#111** (expand /reflect triggers) — fed by P6's trigger prose; stays open.
- **#41** (`/claudna:pull`) — distinct (publish-symmetric *fetch* of published docs, not
  vault recall); stays open, cross-referenced from P5.
- **#176** (briefing on compact) — unaffected; noted in P6's budget paragraph.

## Test Plan

Epic-level (each phase doc carries its own):
- Round-trip: fresh repo → `/init-project` → `/learn <url>` → new session →
  `/remember <topic>` surfaces it — once via the engine, once via fallback.
- Retrieval delta (P5): a fixture vault where a known-relevant doc sits beyond the
  INDEX-scan's reach is found by the engine path and missed by the fallback — the
  "materially smarter" check, made concrete.
- Stacking: both plugins installed → one prompt per event (PreCompact: reflect;
  SessionEnd: Claudron capture); compact-then-end session produces an update, not a
  duplicate.
- Concurrency: two parallel sessions reflect near-simultaneously → both notes land (or
  one lands + one degrades to fallback loudly); nothing silent.
- Parity claims are **prose-diffs + behavioral spot-checks** (fallback sections
  unchanged), never "byte-identical output" attestations (LLM-interpreted skills are
  not deterministic); hook-level invariants (presence marker) get real
  `integration-test.py` rows.
- `validate-skills.py` + integration tests green at every phase; removed-names gate
  (incl. #192's directory check) green before P7.

## Verification Checklist

- [ ] Fork gates honored: F3 locked before P1 merges; F1/F2/F5/F6 before P4 merges; F4 before P7 starts
- [ ] `output-guide.md:19`'s deferral paragraph replaced by the two-plane routing table; forge's `--output docs` prose matches the shipped mechanism (P1)
- [ ] Audit-skill family output (00_ master + NN_ phases) publishes through `--to docs` without tripping the Step 1b gate (P1)
- [ ] Rendered vocabulary table carries its SCHEMA.md source stamp and a green drift check (P2)
- [ ] A repo initialized by `/init-project` yields a working `/remember` with zero manual steps (P3)
- [ ] `/claudron write` on a near-duplicate returns the routed suggestion — never a silent create or drop; `read` verb serves migrated content (P4)
- [ ] Engine calls validate the JSON envelope every call; degradation appears in `--auto` `errors[]` (P4/F5)
- [ ] `/remember` reports its door both ways; fallback prose unchanged (P5)
- [ ] One prompt per session-boundary event with both plugins installed; presence marker observable by a sibling hook (P6)
- [ ] `/notes`+`/lessons` disposition executed per locked F4, with field-remediation guidance and the migration guide in the same release (P7)
- [ ] #106/#107/#112/#36 closed with dispositions; #110/#50/#116/#159/#114/#192 carry their reconciliation comments
- [ ] Zero MCP servers shipped; zero writes to `~/.claude/settings.json` anywhere in the epic

## What NOT To Do

- **Don't ship an MCP server or write user settings** — Claudron owns the server; the
  user owns their settings.
- **Don't gate anything on a Claudron issue state** — artifact gates only (a file on
  main, a release tag).
- **Don't raise the 5-doc presentation cap** — it is a context budget, not the ceiling;
  the ceiling is the scan, and the engine replaces the scan.
- **Don't fork the schema locally** — vocabulary gaps are cross-repo comments (E2 gaps
  to Claudron#16, MCP-surface gaps to #17); local extensions use the `x-*` namespace.
- **Don't write procedural content vault-ward** — the type enum excludes `skill` by
  design; write doors refuse and point at `/claudna:skill-scaffold`.
- **Don't let any engine write fail silently** — retry, then degrade loudly (fallback
  where one exists, explicit error where not).
- **Don't deprecate `/notes`/`/lessons` before F4 is locked and its preconditions are
  met** — removal without a working, *evidenced* replacement is the #106/#107 failure
  mode.
- **Don't treat the fallback as a second product** — it is frozen compatibility
  behavior; feature asks against it are redirected to the engine path.

## Context

- Source skill: forge · Area: skills/{publish,index,init-project,claudron,remember,learn,reflect,notes,lessons,session,review-work}, plugin-hooks/, skills/_shared/ · Effort: XL across 7 phases (L+M+M+L+M+M+M) · Risk: Medium-High (mitigated per Risks) · Priority: High

## Phase issues

Epic: [#197](https://github.com/Claudfather/clauDNA/issues/197) · Plan-docs PR: #196

| Phase | Issue | Track |
|---|---|---|
| P1 — publish two-plane router | #198 | A |
| P2 — vocabulary SSOT | #199 | A |
| P3 — init-project vault seam | #200 | A |
| P4 — `/claudron` engine + engine contract | #201 | B |
| P5 — remember/learn engine preference | #202 | B |
| P6 — reflect + stacking contract | #203 | B |
| P7 — notes/lessons disposition | #204 | B |

No decision riders — the panel's open questions were folded into forks F1–F6, which
ratify on #197.
