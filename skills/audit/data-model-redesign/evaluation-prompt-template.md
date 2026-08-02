# Evaluation Prompt Template

Reference material for the `/claudna:audit data-model-redesign` lens. This is the generalized, **neutral** prompt the lens fills and dispatches to fresh-context evaluator subagents — generalized from a real single-system data-model evaluation, with every system-specific fact replaced by a template variable. The prompt's neutrality is the method: the evaluator reconstructs and judges the system without knowing what the requester already believes, so its conclusions are evidence, not an echo.

The seven-part protocol below is the required deliverable structure. The lens dispatches it in waves (`{{RUN_PARTS}}` scopes each dispatch): Parts 1–3 before the reconstruction gate, Parts 4–6 after it, Part 7 after the direction gate.

---

## Template variables

| Variable | Fill with | Leakage risk |
|---|---|---|
| `{{SYSTEM_NAME}}` | The system or subsystem under evaluation | low |
| `{{REPO_PATHS}}` | Repo roots / directories in scope | low |
| `{{DATA_SURFACES}}` | Detected stores, schema locations, migration dirs, event streams, caches — *locations, not opinions* | low |
| `{{FOCUS}}` | The `[focus]` scope, if any | low |
| `{{MOTIVATION}}` | Why the question is being asked — **symptoms only** (incidents, friction, scaling observations) | **high** — the usual leak vector |
| `{{SCALE_FACTS}}` | Measured sizes, rates, growth — numbers with sources | medium |
| `{{CONSTRAINTS}}` | Hard constraints: compliance, uptime floors, team capacity, freeze windows | medium |
| `{{RUN_PARTS}}` | Which protocol parts this dispatch executes (`1-3`, `4-6`, or `7`) | low |
| `{{SCRATCH_DIR}}` | The run's scratch root; output paths per the lens procedure | low |
| `{{RECONSTRUCTION_FILES}}` | Paths of the confirmed Part 1–3 files (waves 2+ only) | low |
| `{{CHOSEN_DIRECTION}}` | The direction picked at the lens's direction gate (Part 7 dispatch only) | low — post-decision by design |

---

## The leakage-scan rule

Before dispatching a filled prompt, scan the **entire filled text** — mechanically first (search for the marker patterns below), then one adversarial read-through asking: *could the evaluator infer from this prompt what answer the requester expects?* Strip or neutralize every hit, then **re-scan after every edit** until a pass returns clean. The scan applies to every dispatch wave.

What counts as leakage:

1. **Named destinations.** Any target architecture, technology, or pattern appearing as a *destination* rather than an observed current state — "move to event sourcing", "the new normalized schema", "when we're on Postgres". Current-state facts ("orders are stored as JSON blobs in `orders.payload`") are fine; futures are not.
2. **Verdict adjectives on the current model.** "Legacy", "broken", "spaghetti", "tech-debt-ridden", "outgrown". Symptoms stay, verdicts go: "writes to `users` and `profiles` can disagree (incident 2026-05-12)" is a symptom; "the denormalization is a mess" is a verdict.
3. **The requester's suspected root cause or preferred fix**, however hedged — "probably because there's no FK", "a document store might fit better". The evaluator forms its own hypotheses from Parts 1–3.
4. **Imported conclusions.** Findings from earlier audits, prior evaluations, or design docs for a successor system. The evaluator may *discover* such documents in the repo and weigh them as artifacts; the prompt must not inject their conclusions as context.
5. **Outcome-presupposing phrasing** in `{{MOTIVATION}}` / `{{SCALE_FACTS}}` / `{{CONSTRAINTS}}` — "when we redesign…", "the migration should…", "the replacement needs to…". Constraints bind *any* outcome, including no-change: phrase them that way.

A prompt that fails the scan and ships anyway produces an evaluation worth nothing — the evaluator hands back the requester's opinion with citations, and the comparison in Part 5 becomes theater.

---

## The prompt

Fill, scan, dispatch. Ground rules and part requirements are part of the prompt text.

````markdown
You are evaluating the data model of {{SYSTEM_NAME}} ({{REPO_PATHS}}; data surfaces: {{DATA_SURFACES}}; scope: {{FOCUS}}). Execute Parts {{RUN_PARTS}} of the protocol below and write each part's output to {{SCRATCH_DIR}} as directed. Return only a 2-4 line summary per part.

Context — treat as observations, not conclusions:
- Motivation: {{MOTIVATION}}
- Scale: {{SCALE_FACTS}}
- Hard constraints (bind every candidate, including "change nothing"): {{CONSTRAINTS}}

Ground rules:
- Work only from the code, schemas, migrations, and data surfaces in scope. Every claim cites `file:line` (or a schema/migration identifier). A claim you cannot confirm from source is labeled `Unverified`.
- Parts 1–3 are descriptive. Record what IS — no critique, no adjectives, no "should". If you notice a problem while reconstructing, keep a private note and hold it for Part 4.
- Parts 4+ read the confirmed reconstruction from {{RECONSTRUCTION_FILES}} and may not contradict it silently — a discovered error in the reconstruction is reported, not papered over.
- Label every judgment `Confirmed | Likely | Hypothesis`; a Hypothesis states what would confirm or falsify it.
- Never reproduce a secret or credential value; cite `file:line` + the variable name only.

## Part 1 — Reconstruct the system as built
- Domain concepts and the stores that hold them; schema **as-deployed vs as-declared** (migrations vs ORM/model definitions vs any raw DDL — flag disagreements).
- The **consumer inventory**: every reader and writer of the in-scope data — services, endpoints, background jobs, reports/analytics, ad-hoc scripts, external integrations. This inventory is load-bearing: Part 7's coverage matrix is diffed against it.
- End with **known unknowns**: what you could not determine and why.

## Part 2 — Source-of-truth inventory
One table row per domain concept: authoritative home | every duplicate/derived/cached copy | the mechanism that keeps them in sync (or "none") | **can they disagree** (yes/no, and how a disagreement would be detected). Flag every concept with more than one plausible source of truth.

## Part 3 — Path traces with transaction boundaries
Trace the load-bearing paths end-to-end (entry → logic → store), marking every transaction boundary: what commits together, what can partially fail, where retries re-enter, where consistency is assumed but not enforced. At minimum trace: the highest-volume write path, the most complex multi-store write, and the read path serving the most critical decision.

## Part 4 — Evaluation
Judge the current model against Parts 1–3 on: **integrity** (where copies can disagree — evidenced, not asserted), **fit** (paths where the model fights the application), **scale posture** (what breaks at the growth in the context block), **operational burden** (migrations, backfills, on-call surface). Findings carry `file:line` evidence, a `Confirmed | Likely | Hypothesis` label, and `CRITICAL | HIGH | MEDIUM | LOW` severity. Do not force findings — a sound model is a reportable result.

## Part 5 — Candidate approaches (three or more)
At least three candidate target models. **One candidate MUST be incremental repair of the current model** — keep the architecture, fix the Part 4 defects in place. It is the null-redesign baseline every rebuild must beat, not a courtesy entry. For each candidate: a sketch grounded in Part 1's concepts; what it fixes (mapped to Part 4 findings); what it costs or breaks; migration exposure (which consumers move, roughly how much data). Then **one criteria matrix across all candidates** — same criteria for every column, including the Part 4 dimensions and the hard constraints. No candidate is evaluated on criteria the others aren't.

## Part 6 — Recommendation (last)
Only after Part 5's matrix, argued strictly from it — introduce no new evidence here. State the recommendation, the runner-up, and **what would change the recommendation** (the observation or measurement that flips it).

## Part 7 — Migration plan
For {{CHOSEN_DIRECTION}}, per the staging discipline in the lens's migration playbook: expand → backfill → dual-write → shadow-read → cutover → contract. Per-consumer coverage — every consumer from Part 1's inventory has an explicit disposition at every stage — and a rollback entry (trigger, mechanism, blast radius) per stage. Stages that collapse or are skipped are named and justified, never silently absent.
````
