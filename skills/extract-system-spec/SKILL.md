---
name: extract-system-spec
user-invocable: true
description: "Use when you need a portable, anonymized reconstruction spec for a whole system (or a single wing or targeted slice) — a standalone rebuild blueprint an independent team could implement in a fresh session without the original repo. Exhaustive and expensive by design: reserve it for when a full rebuild spec is genuinely worth the token spend. For finding problems in a system you are keeping, use /claudna:audit; this instead extracts a portable spec to rebuild the system elsewhere."
argument-hint: "[full-system | wing <name> | targeted <scope>] [--budget <tokens>] [--depth standard|exhaustive] [--out <path>]"
---

# Extract System Spec

Produce a single, standalone, anonymized Markdown specification from which a capable team could rebuild a system from scratch — without the original repo. Orchestrator + subagents; coverage-gated; hard-anonymized; adversarially reviewed. The full 6-phase method lives in `extraction-prompt.md` in this skill directory; this file governs *when* to run it, at *what scope*, and at *what cost*.

## When to use this — and when NOT

**Use when** the payoff of a portable rebuild blueprint justifies a large, deliberate token spend:
- Porting / re-platforming a system to a new stack or new owner.
- A vendor-neutral or anonymized spec of a proprietary or legacy system (due diligence, handoff, escrow, disaster-recovery documentation).
- Rebuilding a system cleanly while preserving its exact behavior, data semantics, and contracts.

**Do NOT use for** — cheaper tools exist:
- Finding problems in a system you are keeping → `/claudna:audit` (see the table below).
- Understanding one module or orienting quickly → read it, or `/claudna:recall`.
- Documenting a small or simple project → just write the docs.
- Casual curiosity. Reserve this for a genuine rebuild need.

### Not /claudna:audit

Same deep-recon technique, opposite purpose:

| | extract-system-spec | /claudna:audit |
|---|---|---|
| Question | "How do I rebuild this elsewhere?" | "What is wrong with this?" |
| Output | A portable, anonymized reconstruction spec | Findings — ranked issues with fixes |
| Disposition | Rebuild clean; original not kept | Keep and fix in place |
| Anonymization | Mandatory — no identity, PII, paths, symbols | N/A — works in-repo |
| Cost | Exhaustive by design; hundreds of K tokens | Bounded to the chosen concern |

## Cost

A full-system extraction is heavy multi-agent archaeology. Empirically, one full-system run on a mid-size repo produced a ~130k-word spec backed by ~11 wing dossiers, 5 adversarial reviews, and a full set of control ledgers — many subagents across several research waves. Budget accordingly. The scope dial and the Phase 0 gate keep that spend deliberate.

## Scope dial

The first argument selects scope. All three scopes run the *same* method (`extraction-prompt.md`); scope only changes how much of the system is in scope — never how thoroughly the in-scope area is covered.

| Scope | Covers | Use when |
|---|---|---|
| `full-system` (default) | Every wing + all cross-cutting seams | You need a complete rebuild blueprint |
| `wing <name>` | One functional wing + its seams | You only need to rebuild or port one capability |
| `targeted <scope>` | The specific flows/areas you name (quote multi-word scopes) | You need a bounded slice, e.g. `targeted "auth + billing flows"` |

## Procedure

### Phase 0 — scope & cost pre-flight

`<HARD-GATE>` — do this before loading the method or launching any subagent.

1. Parse args: scope (default `full-system`), `--budget <tokens>`, `--depth` (default `standard`), `--out <path>` (default `FULL_SYSTEM_SPEC.md`; `WING-<name>-SPEC.md` / `TARGETED-SPEC.md` for narrower scopes).
2. Cheap, read-only size estimate — this is NOT the Phase 1 inventory yet:
   - `git ls-files | wc -l` (fallback: `find . -type f` minus vendor/build dirs).
   - Approximate LOC over source globs; count deployable units; get rough entry-point and persisted-entity counts; note languages/frameworks.
3. Project the work and a cost band: estimated wings, subagents, research waves, deliverable size, and a rough token + wall-clock range — anchored to the reference run above and scaled by files / LOC / wings.
4. **STOP and confirm** before launching when EITHER scope is `full-system` OR the projected cost exceeds `--budget` (or the default high-cost threshold). Present the estimate, the chosen scope, and the cheaper alternatives (narrow to `wing` / `targeted`).
   - If over `--budget`: narrow scope explicitly, or stop and ask. **Never** silently reduce in-scope coverage to fit a budget — the budget governs scope, not gate-completeness.
5. Proceed only on explicit confirmation, or when the estimate is within `--budget` and scope is not `full-system`.

### Phases 1–6 — run the method

Read `extraction-prompt.md` in this skill directory and execute it faithfully as the orchestrator. Fill its template variables from Phase 0:

- `{{PROJECT_ROOT}}` → the target repo root (default: cwd).
- `{{OUTPUT_PATH}}` → `--out`.
- `{{SCOPE_NOTES}}` → derived from the scope dial:
  - `full-system` → none (inspect the full project).
  - `wing <name>` → "Restrict primary coverage to the '<name>' wing/capability and the seams where it meets the rest of the system; classify the remainder as out-of-scope context, not a coverage target."
  - `targeted <scope>` → the caller's scope notes verbatim, plus "Treat everything outside this scope as out-of-scope context."

The method owns the rigor; do not weaken it — a complete inventory + coverage ledger (Phase 1 gate), a full dossier per wing (Phase 2), cross-cutting investigations across flows / data / rules / interfaces / runtime / security / tests / UI (Phase 3), whole-system reconciliation (Phase 4), the standalone anonymized specification (Phase 5), and the fresh-reviewer adversarial panel — coverage, reconstruction, flexibility, privacy, consistency (Phase 6).

`--depth exhaustive` adds extra reconciliation + re-verification waves and a second privacy re-scan; it never removes gates. `standard` runs every gate once.

### Phase 7 — verify gates & report

1. Confirm every applicable completion gate in the method passed — or the deliverable is honestly marked **Incomplete Specification** with the blocked gates named.
2. Confirm the final Markdown exists at `--out`, that the Phase 6 privacy gate passed (plus the exhaustive re-scan if `--depth exhaustive`), and that it contains all required sections.
3. Report: output path, gate pass/fail, anonymized coverage totals, and the count of unresolved known unknowns. No project-identifying details.

## Rules

- **Read-only on the target.** The only writes are scratch research artifacts (an ignored/temp dir) and the final Markdown. Never mutate source, config, schemas, data, or external systems.
- **Coverage, not length.** Completion is gate-based. Context pressure means subdivide into another wave — never omit scope.
- **Hard anonymization.** The deliverable carries no PII, secrets, identity, source paths, symbols, or repo metadata. The private alias ledger is scratch — never shipped with the spec.
- **Never fabricate.** Uncertain or contradictory behavior is labeled, not invented.

## Red flags — you are rationalizing

| Thought | Reality |
|---|---|
| "Just run full-system, it'll be fine." | It's the most expensive path. Confirm the Phase 0 estimate first, or narrow scope. |
| "I'm over budget but close — I'll just trim a wing." | The budget governs scope, not coverage. Narrow scope explicitly or stop; never silently drop an in-scope wing. || "I found bugs; I'll note them in the spec." | That's `/claudna:audit`. The spec describes required behavior, not defects to fix. |
| "The docs describe it, so I can skip the code." | Documentation is a lead, not truth. Load-bearing claims come from inspected source. |
