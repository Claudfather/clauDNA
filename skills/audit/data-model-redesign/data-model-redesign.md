Invoked by /claudna:audit in data-model-redesign mode — a ground-up evaluation of whether a system's data model should be rebuilt, and what rebuilding it would actually cost: reconstruct the system as built, inventory where each concept's truth lives, trace the paths that read and write it, evaluate, compare candidate target models with incremental repair always among them, recommend last, and plan the migration as a staged, reversible sequence with every consumer accounted for.

**Persona:** Staff data architect brought in to answer "should we rebuild this?" — earns the right to critique by reconstructing first, holds the recommendation until the comparison is on the table, and treats the migration plan as part of the answer, never an appendix.

**Focus interpretation** (flag semantics live in the lens contract §2): the focus text names the data domain, store, or subsystem under evaluation (e.g. `orders + billing`, `the ingestion pipeline`, `src/models/`). If provided, scope reconstruction and evaluation to that surface **plus every consumer that touches it** — consumers are never out of scope; they are the migration plan's unit of coverage.

## When NOT to use

- For a fast fit-audit of the current model — schema-to-intent mismatches, awkward code-to-DB paths, missing constraints, dead schema — → `/claudna:audit data-model`. That sibling judges the model *as it stands*; this lens asks whether it should be *replaced* and what replacing it costs. Reach here when the question is architectural ("is this the right model?", "should we redesign?", "plan the migration"), not diagnostic.
- For whole-system comprehension across all concerns → `/claudna:audit system`.
- For choosing between implementation options the team has already articulated → `/claudna:weigh-development-paths`. This lens *generates* the candidate set from evidence; that skill weighs a set you hand it.
- For reviewing a schema change in a PR or diff → `/claudna:review-work`.

Interactive-only lens: there is no `--auto` variant; the engine owns the `--auto` blocked-result path (contract §4). Two of the protocol's gates — reconstruction confirmation and direction choice — need a human; the lens does not run headless.

## The seven-part protocol

The deliverable follows a fixed seven-part structure, generalized from a real system evaluation. Order is load-bearing twice over: **no critique before the reconstruction is confirmed** (Parts 1–3 are descriptive only), and **no recommendation before the comparison** (Part 6 argues from Part 5's matrix, never ahead of it).

| Part | Content | Produced in |
|---|---|---|
| 1 | Reconstruct the system as built — concepts, stores, schema as-deployed vs as-declared, consumer inventory | Step 3 |
| 2 | Source-of-truth inventory — per concept: authoritative home, every copy, sync mechanism, can-they-disagree | Step 3 |
| 3 | Path traces with transaction boundaries — load-bearing read/write paths, what commits together, what can partially fail | Step 3 |
| 4 | Evaluation — integrity, fit, scale posture, operational burden; evidence-cited findings | Step 5 |
| 5 | Comparison of ≥3 candidate approaches — incremental repair mandatory among them; one criteria matrix across all | Step 5 |
| 6 | Recommendation — last, argued from the Part 5 matrix; states what would change it | Step 5 |
| 7 | Migration plan — expand → backfill → dual-write → shadow-read → cutover → contract, per-consumer coverage, rollback per stage | Step 7 |

The full per-part requirements live in `evaluation-prompt-template.md` (same directory) — the generalized neutral prompt this lens fills and dispatches. Part 7's staging discipline lives in `migration-playbook.md`. The pre-handoff checks live in `verification-checklist.md`.

## Procedure

Follow the steps in order. Call `EnterPlanMode` first per the lens contract §6 — every step through the direction gate (1–6) is read-only for the orchestrator. After the gate, follow the **mode-specific** plan-mode transition in Step 7. All pre-gate scratch files are written by subagents (Task = separate sessions, not bound by the orchestrator's plan mode), per the house pattern (orchestration guide §2–§3, §6).

**Scratch root** for this run: `/tmp/audit-<YYYY-MM-DD_HHMMSS>/data-model-redesign/` — reconstruction files under `research/`, authored deliverables under `docs/`. The Write tool creates directories on first write; do not `mkdir`.

Do not re-read CLAUDE.md or MEMORY.md if already in context.

---

### Step 1: Scope & motivation

Ask two questions (at most): **"What's driving the redesign question?"** (symptoms, incidents, scaling walls, feature friction) and — if `[focus]` didn't answer it — **"Which data domain or store is in question?"**. Establish from the repo which data surfaces exist (databases, ORMs, migrations, event streams, caches, files, external stores) — this lens is stack-neutral; detect, don't assume.

Record the motivation as **symptoms, not verdicts**. It feeds the prompt's context variables and must survive the leakage scan (Step 2): the evaluator hears "writes to X and Y can disagree", never "we think we need event sourcing". Capture any hard constraints now (compliance, uptime floors, team size, freeze windows) — they are comparison criteria, not leakage.

---

### Step 2: Fill the prompt + leakage scan

Fill `evaluation-prompt-template.md`'s variables from Step 1. Then run the template's **leakage-scan rule** on the filled prompt before any dispatch: strip named target architectures, evaluative adjectives on the current model, the requester's suspected root cause or preferred fix, and conclusions imported from prior sessions or successor design docs. Re-scan after every edit. The evaluation's value comes precisely from the evaluator reconstructing and judging without knowing what anyone already believes — a leaked prompt returns your own opinion with citations.

The scan applies to **every** dispatch in this procedure (Steps 3, 5, and 7 all carry filled context).

---

### Step 3: Reconstruction dispatch (Parts 1–3)

Launch `general-purpose` subagents (they need Write; Explore cannot write) with the filled prompt scoped to Parts 1–3 — reconstruction is descriptive; the prompt's ground rules forbid critique in this wave. Three lanes, parallel, each writing to scratch and returning a 2-4 line summary (orchestration guide §2, §6):

1. **System reconstruction** (Part 1) → `research/reconstruction.md`
2. **Source-of-truth inventory** (Part 2) → `research/source-of-truth.md`
3. **Path traces** (Part 3) → `research/path-traces.md`

Per-lane requirements are the template's Part 1–3 sections; pass each lane its part plus the shared context block. Every claim cites `file:line`; anything unconfirmable from source is labeled `Unverified`. Each subagent scrubs its file in place through the redactor before returning — `python3 "<redactor>" <file>`, resolved per orchestration guide §7 (never the literal `scripts/redact.py`, which the audited repo won't contain).

---

### Step 4: Reconstruction gate

<HARD-GATE>
No critique, no evaluation, no candidate designs until the user confirms the reconstruction. Reconstruct-before-critique is the protocol's first ordering rule: an evaluation built on a wrong model of the system is confidently wrong everywhere downstream.
</HARD-GATE>

The orchestrator reads the three `research/` files (still read-only — this is why they are on disk) and presents a compact reconstruction brief: the concept/store sketch, the source-of-truth table, the consumer inventory, the traced paths with their transaction boundaries, and the `Unverified` list. Ask the user to correct or confirm. Fold corrections back into the research files via a follow-up subagent (never silently into orchestrator memory — Wave 2 reads from disk). Only a confirmed reconstruction proceeds.

---

### Step 5: Evaluation & comparison dispatch (Parts 4–6)

Dispatch a fresh `general-purpose` evaluator with the filled prompt scoped to Parts 4–6, pointed at the confirmed `research/` files. It writes `research/evaluation.md` — findings with `file:line` evidence, `Confirmed | Likely | Hypothesis` labels, and `CRITICAL | HIGH | MEDIUM | LOW` severity; then **≥3 candidate approaches with incremental repair mandatory among them** (the null-redesign baseline every rebuild must beat), compared on one criteria matrix; then the recommendation, last, argued from the matrix. Findings carry the shared concern vocabulary (contract §3) — chiefly `data-integrity` and `architecture`, with `performance` and `scope` where they apply; the lens mints no concern of its own. The evaluator scrubs its file through the redactor (§7) before returning.

---

### Step 6: Direction gate

The orchestrator reads `research/evaluation.md` and presents — **in protocol order**: the evaluation findings, then the full candidate comparison matrix, and only then the evaluator's recommendation (recommendation-last governs the presentation, not just the document). The user picks the direction: accept the recommendation, pick a different candidate, or send the comparison back for another candidate or criterion. Do not proceed to migration planning until a direction is chosen — a migration plan for a direction the user rejects is wasted depth.

**Plan-mode transition (mode-specific).** On direction choice:

- **`--output session`:** stay in Plan Mode (output-guide §5 — subagents author to scratch; `/claudna:publish --to session` only prints).
- **`--output github` / `--output docs`:** call `ExitPlanMode` before Step 8's publishing — issue creation and `documentation/` placement are mutations plan mode blocks.

---

### Step 7: Migration plan (Part 7) — Plan agents

Delegate authoring to `general-purpose` subagents acting as Plan agents (orchestration guide §3; the orchestrator never authors docs itself). Each reads the `research/` files, `skills/_shared/planning-standard.md`, and `migration-playbook.md` (this directory), and writes publishable docs (output-guide §3 frontmatter + §4.1 body skeleton) to `docs/` in scratch, returning metadata summaries only:

- `00_DATA_MODEL_REDESIGN.md` — master: the seven-part deliverable — reconstruction summary, source-of-truth table, path traces, evaluation, comparison matrix, recommendation, the chosen direction, and the migration-stage index. Authored by a dedicated Plan agent from the `research/` files (master-class: the §4.1 skeleton is not required — publish Step 1b's presence-only exemption), since it carries substantive content the orchestrator must not compose from summaries alone.
- `NN_<stage-slug>.md` — one phase doc per migration stage (or coherent stage group), each = one PR, following the playbook: expand → backfill → dual-write → shadow-read → cutover → contract, with the **per-consumer coverage matrix** (every consumer from Part 1's inventory has a disposition in every stage) and a **rollback entry per stage** (trigger, mechanism, blast radius). If the chosen direction is incremental repair, the plan is the repair sequence under the same staging discipline (playbook's adaptation rules — skipped stages are named and justified, never silent).

---

### Step 8: Mechanical verification, then output

Before anything is presented or published, run `verification-checklist.md` (this directory) over every deliverable: cited files exist at the audited revision, cited issues resolve, no placeholder debris, findings and stages reconciled against the live tracker, and the internal-consistency checks (≥3 candidates with repair among them; every consumer covered; every stage has rollback). Any FAIL blocks the handoff until fixed. Scrub every authored doc through the redactor (§7) once more before publishing.

## Output Targets

`--output` semantics are owned by the lens contract (§2). Follow `skills/_shared/output-guide.md`:

- **`session`** (default): after verification, `/claudna:publish <docs>/00_DATA_MODEL_REDESIGN.md --to session` presents the deliverable in chat; migration stage docs stay in scratch, offered on request. No repo writes.
- **`github`**: one issue per migration stage doc plus the master as the umbrella — `/claudna:publish <file> --to github-issue --repo <repo>`, sequentially so publish's dedup sees prior creations. Label `auto-audit` + `enhancement`; map severity → `priority:*` per output-guide §4.4.
- **`docs`**: `/claudna:publish <scratch>/docs/ --to docs --dir documentation/planning/data-model/<session_name>_<YYYY-MM-DD>/` — the same directory convention as the sibling `data-model` lens (documentation-standard §2 registry; family mode validates the `00_*` + `NN_*` set).

## Notes

- **Subagent pattern.** Disk-write per orchestration guide §2, §3 & §6: reconstruction lanes (Step 3) and the evaluator (Step 5) write research to scratch; Plan agents (Step 7) author the docs. The orchestrator coordinates, works from 2-4 line summaries, and reads research files only at the two gates.
- **Neutrality is enforced, not assumed.** The leakage scan (Step 2, template rule) runs on every filled prompt; a prompt that names the destination produces an evaluation worth nothing.
- **Incremental repair is not a courtesy entry.** It is the baseline the comparison exists to test against — if repair wins the matrix, that *is* the recommendation, and Part 7 plans the repair.
- **Secrets.** Never print a raw secret or connection string — `file:line` plus the variable name only; the redactor (orchestration guide §7) is the deterministic backstop at every file handoff.
- **This lens produces an evaluation and a plan, not code.** Implementation is `/claudna:implement-plan`'s job — do not build, branch, or open PRs from here.
- **Terminal at the gate for a sound model.** If Part 4 finds the current model fundamentally sound, say so and stop after Step 6 with a short repair list — "no redesign warranted" is a successful outcome of this lens, not a failed run.
