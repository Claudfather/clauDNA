---
title: "[plan] P7: /notes + /lessons vault preference — F4 locked (b); removal deferred behind adoption evidence"
type: plan
status: draft
owner: chris
created: 2026-07-07
updated: 2026-07-07
tags: [planning, claudron, deprecation, notes, lessons]
repos: clauDNA
links:
---

# P7 — `/notes` + `/lessons` vault preference (F4 locked (b), 2026-07-08)

> **RATIFICATION NOTE:** Fork F4 locked **(b) soft preference** on #197 — the runner-up
> over the lean this doc was drafted around. The executed scope is the "Under F4(b)"
> branch already specced below: **step 1 ships (migration guide, now optional
> guidance), steps 2–3 become soft-preference body edits** (both skills prefer the
> engine when a vault is detected, unchanged otherwise, with `--auto` `engine`/`errors[]`
> visibility per F5), **and hard removal re-files as its own future issue** gated on
> adoption evidence — inheriting steps 2–6 below as its ready-made playbook (#192 moves
> to that issue's gates; #106/#107 stay open with the soft-preference disposition).
> Size reshapes M→S. The original (a)-primary text is retained below as the deferred
> playbook.

Part of the Claudron-integration epic (`00_OVERVIEW.md`). Size: **M**. Gates: **fork F4
locked** (this phase executes whichever option is ratified); P4–P6 released;
**#192's directory-resurrection gate merged** (the guard for exactly this deletion);
adoption evidence per F4's preconditions. Removal approval rides the epic ratification.

## Summary

#106 and #107 both say: don't deprecate before an equivalent ships. P4–P6 are that
equivalent under the **capability reading** of the wait condition — `/claudron
write|read` is the deliberate save/browse door, `/reflect` the distillation door, the
vault the store — a reading the F4 ratification explicitly endorses or rejects (the
issues imagined Claudron shipping the skill surface itself; the panel flagged the
difference). Under F4(a) this phase retires both skills per the house deprecation
machinery, with the capability regression priced (fork F4 states it), field remediation
for already-initialized repos, and an idempotent migration guide in the same release.
Under F4(b) it instead lands the soft-preference bodies and re-files removal behind
usage evidence. Per-repo `.claude/lessons.md` survives under every option.

## Evidence

- #106 / #107 — the wait condition + "knowledge storage is Claudron's territory";
  `PROJECT_MISSION.md` boundary line — against its own self-contained/no-hosted-deps
  posture (the tension fork F4 prices; claudron is local, but it is an external hard
  dependency for a previously zero-dependency surface).
- Capability surface being replaced (panel blocker): `/notes` is read+write+organize
  (`skills/notes/SKILL.md:4,:69`); `/lessons` has an on-demand read path
  (`skills/lessons/SKILL.md:41-45`). Parity = P4's `read` verb + `/remember` for
  search + honest breadcrumbs; post-migration browsing without the read verb would
  have no clauDNA door — hence the P4 precondition.
- **Field footprint (panel):** `init-project`'s template stamps "Review lessons when
  relevant (via `/claudna:lessons`)" into every initialized repo's CLAUDE.md
  (`references/CLAUDE_MD_TEMPLATE.md:47`) — removal without remediation leaves every
  prior user instructing a dead skill. `SKILL_CONTRACT.md:104` itself uses `/notes` as
  a live example and is **not** excluded by the removed-names gate — the gate will
  catch it, which is exactly why the sweep list is derived *by running the gate*, not
  by hand.
- The machinery: #165 F4 pattern (hard removal, breadcrumbs, `removed-skills.txt`,
  per-phase release, SETUP_GUIDE §4.3.1 pin/rollback); #192 (directory-resurrection
  check) open — sequenced ahead of this phase; #114 (formalize the lifecycle) —
  this is the pattern's third execution and posts its ledger there.
- CLAUDE.md rule "Never touch `~/.claude/notes/`" — migration is user-executed;
  the engine's dedup routing makes it idempotent (re-runs route to
  `suggest_update`, never duplicate).

## Implementation Plan

### Dependencies
F4 locked; P4–P6 released + one bake window (7 days, fixtures green, **breakage
channel** = issues labeled `claudron-integration` + the maintainer-canary checklist —
"no reports" is only meaningful because the channel is named); #192 merged; adoption
evidence (maintainer vault pulse per Claudron's own G1 metric + zero channel breakage,
or explicit ratifier waiver).

### Blocks
Closes #106, #107. Posts the lifecycle data point to #114.

### Steps

*(Steps 2–6 assume F4(a). Under F4(b): step 1 still ships, steps 2–3 are replaced by
soft-preference edits to both skill bodies — prefer the vault when detected, unchanged
otherwise — and removal re-files as its own future issue behind usage evidence.)*

1. **Migration guide first** (SETUP_GUIDE append + release notes): user-run one-time
   import of `~/.claude/notes/` — per-file `/claudron write` (or `claudron capture`
   loop) with type `knowledge` (patterns/projects), `decision` (decisions/), lesson
   entries as knowledge notes tagged `lesson`. **Operational semantics:**
   idempotent-by-dedup (re-run safe — collisions route to `suggest_update`);
   half-failure recovery = re-run the loop (idempotency is the recovery); verification
   pass = `claudron validate` + a `/claudron read` spot-check. Print-not-execute: the
   plugin never touches `~/.claude/notes/`.
2. **Remove `skills/notes/` + `skills/lessons/`;** add both to
   `scripts/removed-skills.txt`; **derive the sweep by running the gate** (known
   catches it must find: SKILL_CONTRACT.md:104's `/notes` example, orchestration-guide
   §13's utility list, init-project prose, README tables, SETUP_GUIDE) and fix every
   hit in the same PR.
3. **Breadcrumbs:** `/claudron` description gains `Replaces /notes.`; `/reflect` gains
   `Replaces /lessons.` (bare-slash form per §2.1 rule 6). The correction-capture
   trigger ("after ANY correction") moves into reflect's body; reading lessons back =
   `/claudron read` / `/remember` (named in the breadcrumb docs).
4. **Field remediation:** update `references/CLAUDE_MD_TEMPLATE.md` in the same
   release; migration guide includes the existing-repo step — re-run
   `/claudna:init-project` (idempotent section update) or hand-patch the
   Self-Improvement Loop line; `/claudna:using-claudna`'s Installation Health check
   gains a stale-reference row (flags dead `/claudna:lessons` mentions in the current
   repo's CLAUDE.md).
5. **`.claude/lessons.md` stays** — init-project Step 5 unchanged; framing note:
   "repo-local gotchas; cross-project lessons live in the vault via /claudna:reflect."
6. **Release:** per-phase version bump. **Semver statement (mission alignment):**
   pre-1.0, removals ship as minor bumps per house precedent (#165's seven releases),
   with a CHANGELOG breaking-change entry + pin/rollback pointer; if the plugin has
   crossed 1.0 by then, this phase waits for the next major. #106/#107 closed with the
   capability-reading disposition; ledger posted to #114.

## Test Plan

- Removed-names gate green repo-wide (both names, all four reference forms, plus
  #192's directory check).
- Routing fixtures: "save a note about X" → `/claudron write`; "remember this
  correction" → `/reflect`; "what did we learn about X" → `/remember` (rows added in
  the retired names' symptom vocabulary).
- Migration dry-run against a fixture `~/.claude/notes/` tree: valid vault notes,
  `claudron validate` clean, re-run produces zero duplicates (idempotency proven).
- Template diff shows no dead references; Installation Health flags a seeded stale one.
- `validate-skills.py` + integration tests green.

## Verification Checklist

- [ ] F4 lock comment names the option executed and endorses/rejects the capability reading of #106/#107's wait condition
- [ ] (F4a) Picker entries gone; breadcrumbs live; read path named in them
- [ ] Sweep derived by gate run; zero surviving references incl. SKILL_CONTRACT's example
- [ ] Migration guide (idempotent, verified, half-failure-recoverable) ships in the same release — never later
- [ ] CLAUDE.md template updated + existing-repo remediation documented + Installation Health row live
- [ ] Semver statement honored; #106/#107 closed; #114 data point posted; plugin still never touches `~/.claude/notes/`

## What NOT To Do

- Don't ship removal before the migration guide — the #106/#107 failure mode.
- Don't auto-migrate `~/.claude/notes/` — the no-touch rule binds the plugin even at
  deprecation time.
- Don't leave redirect stubs (F4a) — hard removal + breadcrumbs; stubs are picker cost
  with no capability.
- Don't hand-list the sweep — run the gate; it knows more than the plan does.
- Don't remove `.claude/lessons.md` provisioning — repo plane, different artifact.

## Context

- Source skill: forge · Area: skills/notes (removed under F4a), skills/lessons (removed under F4a), skills/reflect, skills/claudron, skills/using-claudna, skills/init-project/references/, scripts/, SETUP_GUIDE.md · Effort: M · Risk: Medium-High (breaking change; capability regression priced in F4) · Priority: Medium
- Dependencies: F4 locked; P4–P6 baked; #192 merged; adoption evidence · Blocks: closes #106/#107; feeds #114
