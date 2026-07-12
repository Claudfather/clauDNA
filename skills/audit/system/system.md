Invoked by /claudna:audit in system mode — a wide-to-deep comprehension review of a whole system (or a named subsystem): build durable maps of how it works, sweep it for correctness/reliability/performance/data-quality risk at rest, reconcile every candidate finding against the live issue tracker, then hand a maintainer junior-executable issues for the net-new work only.

**Persona:** Principal engineer joining a team cold — reads the code before opining, states assumptions out loud, separates confirmed from hypothesized, and never files a duplicate of work the team already tracks.

**Focus interpretation** (flag semantics live in the lens contract §2): the focus text is a subsystem, path, service, or data domain (e.g., `src/api/`, `the posting pipeline`, `billing`). If provided, scope the whole review — maps and sweeps — to that surface instead of the full repo.

## When NOT to use

- For a deep single-concern scan → the dedicated lens goes deeper: `/claudna:audit security`, `/claudna:audit tech-debt`, `/claudna:audit data-model`, `/claudna:audit frontend-perf`. This lens is breadth across concerns plus comprehension maps; it defers depth to those.
- For reviewing a PR or an uncommitted diff (a change, not a system at rest) → `/claudna:review-work`. For hardening a plan Issue → `/claudna:ironclad`.
- For a live production incident → `/claudna:investigate-app`.
- For a portfolio view across many repos → `/claudna:audit repo-health`.

Interactive-only lens: there is no `--auto` variant. The engine owns the `--auto` blocked-result path (contract §4). The tracker-reconciliation gate (Phase 5) needs a human; it does not run headless.

## Procedure

Follow the phases in order. Call `EnterPlanMode` first — every phase through the gate (1–5) is read-only for the orchestrator. After the Phase 5 gate, follow the **mode-specific** Plan-mode transition defined there: `--output github` exits before publishing issues; `--output session` stays in Plan Mode unless the user opts into map promotion (Phase 7). Do not exit unconditionally.

**Who writes what.** The orchestrator itself writes nothing to disk before the gate — it runs read-only discovery (Read/Grep/Glob, read-only Bash), launches subagents, and reads what they write. All pre-gate scratch files are written by **subagents** (Task = separate sessions, not bound by the orchestrator's plan mode): maps in Phase 2, findings in Phase 4. This is the house pattern (orchestration guide §2–§3, §6) and it is what makes plan mode viable for a lens that ultimately writes.

Do not spend scan budget re-reading CLAUDE.md or MEMORY.md if they are already loaded into context — use them for project understanding and spend scan effort on the code. If project instructions appear missing or contradictory (this lens ships to arbitrary marketplace repos where they may not have loaded as expected), read them once for routing and safety context before scanning.

**Scratch root** for this run: `/tmp/audit-<YYYY-MM-DD_HHMMSS>/`. All system-lens artifacts live under its `system/` subdirectory — every `system/<file>` path in this procedure is relative to the scratch root, so the maps are `/tmp/audit-<TS>/system/system-map.md`, `.../system/code-map.md`, `.../system/data-model-map.md` and the findings are `/tmp/audit-<TS>/system/findings-<lane>.md` (never a doubled `system/system/`). Subagents write here; the orchestrator reads them (at the gate) but never dumps them into the reviewed repo's working tree (see Phase 7). The Write tool creates the directory on a subagent's first write; do not `mkdir`.

---

## Phase 1: Intake & scope

Read-only. Inventory the repo like a new senior engineer and assemble a **compact intake brief** you hold in context (you do not write it to disk yet — that would need the Write tool inside plan mode). Establish, from evidence:

- Languages, frameworks, package managers, runtime versions
- Build / test / lint / type-check commands (read the CI config, `Makefile`, `package.json` scripts, `pytest.ini`, etc. — do not guess)
- Entrypoints and long-running processes (services, workers, CLIs, jobs, DAGs, cron)
- External integrations and the config/secrets pattern (note `.env` *keys* only — never values)
- What is generated / vendored and must not be reviewed deeply; out-of-scope paths (build artifacts, `node_modules/`, coverage output, media)
- Whether a **data surface** exists (DB, ORM, migrations, pipelines, warehouse, event streams, request/response schemas) — decides the data lanes below

You pass this intake brief **inline** into every Phase 2 and Phase 4 subagent prompt (subagents don't inherit your context). If the maps are promoted later (Phase 7), the durable `repo-intake.md` is written then, post-`ExitPlanMode`.

If `[focus]` was not given and the repo is large, ask **one** scoping question ("whole system, or a subsystem?") — then proceed. Do not stall on scoping.

---

## Phase 2: Comprehension mapping (parallel fan-out → durable maps)

Launch `general-purpose` subagents in parallel (they need Write; Explore cannot write), **scoped to `[focus]` if set** (a scoped review maps only the focus surface). Each receives the intake brief inline, builds one map, writes it to scratch, and returns a 2-4 line summary. **The orchestrator never reads the full maps into its context** (orchestration guide §2, §6) — it works from the summaries.

Map lanes (see `subagent-prompts.md` for the full brief and each map's template):

1. **Architecture & execution flow** → `system/system-map.md`
2. **Code map** → `system/code-map.md`
3. **Data model & data flow** → `system/data-model-map.md` — **only if a data surface exists** (per Phase 1). If none, skip this lane and note "no data surface". Do not force a data-model map onto a stateless service.

Each map carries an **accuracy self-check**: the subagent re-opens **2 or more** cited files and confirms each load-bearing claim before writing it, labelling anything it could not confirm from source `Unverified`. Maps are only worth inheriting if they are true.

---

## Phase 3: Validation baseline

Read-only. Identify the safest validation commands from Phase 1 (test collect/run, lint, type-check, `dbt parse`/`compile`) and run the cheap ones. **Ask before** anything expensive, networked, or production-connected (migrations, live DB, deploys). Hold the results in context for the gate and the final report; the durable `validation-log.md` (command, exit code, result, interpretation per run) is written in Phase 7 if the artifacts are promoted.

**Baseline-failure capture (do not skip):** if tests/lints/builds already fail before any change, that is *baseline state*. Record it as such and never attribute a pre-existing failure to a finding. A red suite on arrival is itself a finding — but a separate one, correctly attributed.

---

## Phase 4: Concern sweep (parallel fan-out → candidate findings)

Launch `general-purpose` subagents, one per concern lane, each given the intake brief inline and scoped to `[focus]` if set. Each writes candidate findings to `system/findings-<lane>.md` (evidence with `file:line`, a `Confirmed | Likely | Hypothesis` label, and a `CRITICAL | HIGH | MEDIUM | LOW` severity) and returns a 2-4 line summary. Full briefs in `subagent-prompts.md`.

Primary lanes (the coverage no dedicated lens provides — spend the effort here):

1. **Correctness at rest** — null/empty/missing-field assumptions, ordering, pagination, retries, timezones, idempotency, swallowed exceptions, races, state mutation, incomplete migrations.
2. **Reliability & operations** — non-idempotent jobs, missing/unsafe retries, missing timeouts, incomplete failure recovery, absent alerting/health checks, local↔prod divergence, partial-failure cleanup.
3. **Backend performance & scalability** — N+1 queries, full scans where a filter/index belongs, unbounded memory, loading whole datasets, poor pagination, missing/incorrect caching. (Anything client-side — rendering, fetch waterfalls, state/memoization, bundle/loading — belongs to `/claudna:audit frontend-perf`.)
4. **Data-quality correctness** *(only if a data surface exists)* — wrong grain, join fanout, silent dedup, incorrect incremental predicates, non-idempotent loads, timezone drift, off-by-one windows, backfill hazards, missing constraints/tests.

Breadth lanes (surface obvious risk; **defer depth** — do not reproduce the dedicated lens's full checklist):

5. **Security & secrets** — committed/leaking secrets, missing authz at a boundary, unsafe logging, insecure defaults. For a full scan, cross-reference `/claudna:audit security`.
6. **Maintainability** — coupling, duplicate logic, missing domain concepts, untested business logic. For a full scan, cross-reference `/claudna:audit tech-debt`.

**Do not force findings.** A clean lane reports "no material findings" — that is a valid, valuable result. Invented, evidence-free advice is worse than silence. Lanes overlap at the edges (idempotency, migrations, hidden business logic); that is fine — the gate's de-fragment step (Phase 5.3) collapses any candidate two lanes both surfaced.

---

## Phase 5: Triage & tracker reconciliation — THE GATE

<HARD-GATE>
No finding proceeds to drafting until it has been reconciled against the live issue tracker. This gate runs in **every** output mode (`session` and `github`) — reconciliation is a triage step, not a filing courtesy. Skipping it produces duplicate work against a tracker the maintainer is actively grooming, which is worse than filing nothing.
</HARD-GATE>

To reconcile, the orchestrator now reads the `system/findings-<lane>.md` files from scratch (still read-only — this is why the findings are on disk: retrievable at the gate without having flowed through the fan-out returns). For any lane whose subagent returned `SCRATCH-WRITE-BLOCKED` (write-blocked fallback, `subagent-prompts.md`), reconcile from its compact inline table instead — the file is absent by design, not by error. Assemble the deduplicated candidate list, then:

1. **Fetch the tracker.** `gh issue list --repo <owner/repo> --state open --limit 300` plus the recently-closed set (`--state closed --limit 60`). **A bulk fetch can miss issues outside that window**, so for each candidate also run a targeted `gh issue list --repo <owner/repo> --search "<key terms>" --state all --limit 50` — `--state all` is mandatory here: `gh issue list` defaults to open-only, and the `regressed` bucket depends on the search returning *closed* matches. Bucket from the returned state: open exact match → `duplicate of #N`; open related → `extends #N`; closed exact/near recurrence → `regressed #N`; no match → `net-new`. If the repo has no GitHub remote or `gh` is unavailable, say so and reconcile against whatever tracker exists (`documentation/`, a TODO file) — never silently skip.
2. **Reconcile every candidate** into exactly one bucket:

   | Bucket | Meaning | Fate |
   |---|---|---|
   | **net-new** | No open or recently-closed issue covers this | → drafts in Phase 6 |
   | **extends #N** | Related to an open #N but adds a distinct, unfiled facet | → drafts, `Related: #N` |
   | **regressed #N** | A closed #N's problem is back | → drafts, references #N |
   | **duplicate of #N** | An existing issue already covers it | → dropped; report the `#N` |

3. **Merge & de-fragment** the draft set (net-new + extends + regressed): collapse near-identical findings into one umbrella issue; split one finding that is really two unrelated fixes. Do not bundle unrelated fixes because they sit in nearby files.
4. **Present the partition** and stop for confirmation:

```
System review — <scope> (<date>)
Candidates: <n>  →  net-new: <a>   extends: <b>   regressed: <c>   duplicate: <d>
  will draft (<a+b+c>):
    [HIGH]    <title>                 — <lane>     net-new
    [HIGH]    <title>                 — <lane>     extends #212
    [MEDIUM]  <title>                 — <lane>     regressed, was #397
  dropped as duplicate (<d>):
    <title>                           → already #513
    <title>                           → already #527
Proceed to draft the <a+b+c> issues? (maps stay in scratch until Phase 7)
```

If `<a+b+c>` is **0** — every candidate is already tracked — do not print the "Proceed?" prompt: report the reconciliation (what mapped to which existing issue) and stop at the terminal-at-gate case (Notes). Otherwise, do not draft until the user confirms.

The value of this review is the draft set surfaced *cleanly* — the duplicate column is what proves the review respected the team's existing work.

**Plan-mode transition (mode-specific).** On confirmation:
- **`--output github`:** call `ExitPlanMode` — the orchestrator itself invokes `/claudna:publish` (which runs `gh issue create`, a mutation plan mode blocks), so it must exit.
- **`--output session`:** stay in Plan Mode (consistent with output-guide §5, "Plan Mode remains active throughout"). The findings docs are authored by subagents to scratch — subagents run in separate sessions and are not bound by the orchestrator's plan mode — and `/claudna:publish --to session` only prints to chat (no mutation). No `ExitPlanMode` needed, and no write ever reaches the reviewed repo.
- **Phase 7 map promotion (either mode):** if the user opts in, that is a genuine write — call `ExitPlanMode` at that point if still in plan mode.

---

## Phase 6: Findings output (draft set only)

Delegate issue-doc authoring to **`general-purpose` subagents acting as Plan agents** (output guide §4.7; orchestration guide §3) — "Plan agent" is a role, not a subagent type, and only `general-purpose` has the Write tool (Explore is read-only). The orchestrator must not author docs itself. Launch one per finding (or per umbrella cluster from Phase 5.3); each reads its `findings-<lane>.md` from scratch (or, for a write-blocked lane, receives the finding detail inline in its prompt from the orchestrator's gate reconciliation), reads `issue-depth-standard.md` for the depth bar, writes a doc (frontmatter + the output-guide §4.1 body skeleton, junior-executable per the depth standard) to scratch, and returns only a metadata summary (path, title, severity, effort). The §4.1 body is what publish validates; the depth standard is what makes the issue self-sufficient.

Before publishing, scrub every authored doc in scratch through the redactor — `python3 "<redactor>" <scratch-dir>/<file>.md` per doc, where `<redactor>` is resolved per orchestration guide §7 (not the literal `scripts/redact.py`, which won't exist in an arbitrary reviewed repo) — the mechanical gate that catches any raw value the security or other lanes quoted, independent of per-subagent memory. Then the orchestrator routes each doc through `/claudna:publish` (see Output Targets) — **always publish, never `gh` directly**. Publish validates, dedups a second time per-medium, applies labels, and files. File sequentially so publish's dedup sees prior creations; carry the Phase-5 bucket into each doc (`Related: #N` for extends, a regression note referencing #N for regressed); collect the returned URLs; end with a batch summary that also lists the dropped duplicates (per the Phase 5 partition).

---

## Phase 7: Offer to promote the maps

The comprehension maps are the review's most reusable artifact — but they default to **scratch-only** (the target working tree stays clean; house rules). At the end, offer:

> "The system/code/data maps (plus the repo-intake and validation log) are in scratch. Promote them as a durable `type: knowledge` doc in the vault, drop them in `documentation/` if you give an explicit `--dir`, or leave them ephemeral?"

**The scratch maps are research artifacts, not publish-ready docs** — `/claudna:publish` deep-validates frontmatter and rejects a malformed manuscript, and a `knowledge` doc requires frontmatter plus a non-trivial body with a leading heading (output-guide §3, publish §1a). So on opt-in, first **compose one consolidated `system-knowledge.md`** in scratch with valid frontmatter, then publish that single file:

```yaml
---
title: "System map — <owner/repo or scope>"
type: knowledge
status: current
owner: audit
created: <YYYY-MM-DD>
tags: [system-map, audit, knowledge]
repos: [<owner/repo>]
---
```

Body = a leading `# System map — <scope>` heading, then the repo-intake, validation-log, system-map, code-map, and (if present) data-model-map as `##` sections. Then `/claudna:publish <scratch>/system/system-knowledge.md --to vault` (vault is the default `--to`).

- **Publish a *file*, never the scratch directory** — a directory source is the docs adapter's family mode only (`--dir`, docs-only); the vault adapter takes a single doc.
- **`documentation/` needs an explicit `--dir`** — the archive convention (orchestration guide §8) registers no `system` subdirectory, so `/claudna:publish <file> --to docs --dir <user-supplied>` rather than inventing a path. (Maps are reference knowledge, not planning docs, so vault is the better default.)
- Never write any of it into the reviewed repo's tree unprompted.

---

## Output Targets

`--output` semantics are owned by the lens contract (§2). This lens supports `github` and `session` (default). Follow `skills/_shared/output-guide.md`:

- **`session`** (default): reconcile (Phase 5), then present the draft-set findings + the map summaries + the dropped-duplicate list in chat. Route the doc via `/claudna:publish <file> --to session`. No repo writes.
- **`github`**: Plan subagents author each draft finding as a doc (frontmatter + §4.1 body + the depth standard), then the orchestrator runs `/claudna:publish <file> --to github-issue --repo <repo>`. Map sweep severity → priority tag directly (`CRITICAL → priority:critical`, `HIGH → priority:high`, `MEDIUM → priority:medium`, `LOW → priority:low`) per output-guide §4.4. Publish owns validation, dedup, and labels.

Reconciliation (Phase 5) happens **before** either target — it is not a github-only step.

---

## Notes

- **Subagent pattern.** Disk-write, per orchestration guide §2, §3 & §6. Map lanes (Phase 2) and concern lanes (Phase 4) run in parallel and write to scratch; authoring (Phase 6) is delegated to Plan subagents. The orchestrator coordinates, works from 2-4 line summaries during fan-out, and reads the findings files only at the gate — it never holds a full map.
- **Severity vocabulary.** The sweep uses `CRITICAL | HIGH | MEDIUM | LOW` (matching the sibling lenses and output-guide §4.4) — not a P0–P3 scale. CRITICAL = data loss / security exposure / outage risk / broken critical path; HIGH = high-impact bug, major data-quality issue, serious reliability problem; MEDIUM = medium correctness/observability/test gap; LOW = cleanup/docs/naming.
- **Secrets.** Never print a raw secret value. Report file:line + the variable name; the redactor (orchestration guide §7) is the deterministic backstop — each subagent scrubs its findings file in place (`python3 "<redactor>" <file>`, `<redactor>` resolved per §7 — never the literal `scripts/redact.py`, which the reviewed repo won't contain) before returning, masking any captured value to `[REDACTED]`, and the orchestrator scrubs the scratch docs again before publishing (Phase 6).
- **Evidence over vibes.** Every finding cites `file:line` and carries a `Confirmed | Likely | Hypothesis` label. Hypotheses state what would confirm or falsify them.
- **This lens produces maps + issues, not code.** Remediation is `/claudna:implement-plan`'s job. Do not build, branch, or open PRs from here.
- **Terminal at the gate for a clean repo.** If Phase 5 finds every candidate already tracked, say so and stop — a review that confirms the tracker is current is a successful review, not a failed one.
