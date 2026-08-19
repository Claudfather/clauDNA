---
name: kindle
user-invocable: true
argument-hint: "[topic-or-idea]"
description: "Use before any creative work — creating features, building components, adding functionality, or modifying behavior. The ideation phase: discovers intent and requirements into an approved spec before /claudna:forge plans and /claudna:ironclad hardens. Requires a presented design and user approval before any implementation. For an on-demand, codebase-driven opportunity scan not gated on active creative work, use /claudna:product-vision instead."
---

# Kindle

Light the fire. Turn a raw, unformed idea into a spec a plan can be forged from — through collaborative discovery, not by jumping to implementation.

kindle is the **ideation phase** of clauDNA's planning pipeline:

> **idea → `kindle` (discover) → spec → `forge` (plan) → `ironclad` (harden) → `build` (build)**

It owns the front of the funnel: eliciting *what* to build and *whether* it's worth building. It deliberately does **not** compare implementation approaches (that's `forge`'s decision forks) or run the adversarial review panel (that's `ironclad`'s lenses). When the spec is approved, hand to `forge`.

<HARD-GATE>
Do NOT write code, scaffold a project, or take any implementation action until you have presented a design and the user has approved it. This applies to EVERY project regardless of perceived simplicity. "Simple" projects are where unexamined assumptions waste the most work — a design can be short, but you MUST present it and get approval.
</HARD-GATE>

**Right-size the gate — but never skip it.** The HARD-GATE is non-negotiable for *every* change; what scales is its *depth*. A trivial change is a one-sentence design + a quick yes, then you implement directly (no `forge` needed — that's `forge`'s own right-size call). Substantial or multi-PR work runs the full pipeline: discover → spec → `forge`. A deadline justifies a *smaller* design and a *faster* approval; it never justifies *zero* approval.

## Checklist

Create a task per item and complete them in order.

1. **Explore project context** — files, docs, recent commits.
2. **Pick a lens if one fits** (see Lenses) — adopt its question pattern for the discovery.
3. **Ask clarifying questions — one at a time.** Purpose, constraints, success criteria. Prefer multiple-choice.
4. **Present the design** — in sections scaled to complexity; get approval after each.
5. **Write the spec** — a contract-compliant `type: decision` doc; publish it.
6. **Spec self-review** — placeholders, contradictions, scope, ambiguity; fix inline.
7. **User reviews the spec.**
8. **Hand to forge** (when a plan is warranted) — for substantial work the only skill kindle invokes next is `forge`; a trivial change implements directly after the gate.

## The discovery process

- Check the current project state first (files, docs, recent commits).
- **Scope check:** if the request spans multiple independent subsystems ("a platform with chat, billing, analytics…"), flag it and decompose *before* refining details. Each sub-project gets its own kindle → forge → build cycle.
- **One question per message.** Prefer multiple-choice; open-ended is fine. Focus on purpose / constraints / success criteria.
- **Surface directions, not plans.** Where useful, name 2-3 high-level *directions* for what to build. Leave *implementation-approach* forks to `forge` (decision forks) and *premise demolition* (is this the right problem? alternatives? the 10-star version?) to `ironclad`'s lenses. kindle discovers and shapes; it does not plan or harden.
- **Design for isolation and clarity:** break the system into small units with one clear purpose, well-defined interfaces, independently testable. If a unit can't be understood without reading its internals, the boundaries need work.
- **In existing codebases:** explore the current structure first and follow existing patterns; include targeted improvements where existing problems affect the work, but don't propose unrelated refactoring.

## Presenting & writing the spec

- Once you understand what you're building, present the design — architecture, components, data flow, error handling, testing — each section scaled to its complexity, with approval after each.
- Write the validated spec to a scratch file (frontmatter `type: decision`, `status: draft`, per `skills/_shared/output-guide.md` §3 and `skills/_shared/documentation-standard.md`), then delegate placement to `/claudna:publish <file> --to docs --dir documentation/planning/decisions/<topic-slug>_<YYYY-MM-DD>/` — publish is the single placement path for finished docs; kindle never writes directly into `documentation/planning/`. `type: decision` carries no `## Implementation Plan` skeleton requirement (correct — a kindle spec has no implementation plan yet; that's `forge`'s job) and its `draft → ratified` status lifecycle matches this gate.
- **Self-review** with fresh eyes: placeholder scan (TBD/TODO/vague), internal consistency (do sections contradict? does architecture match the features?), scope (focused enough for one plan, or decompose?), ambiguity (could a requirement be read two ways? pick one, make it explicit). Fix inline.
- **User review gate:** "Spec written at `<published-path>`. Review it and tell me if you want changes before I forge the plan." Only proceed on approval. On approval, update the frontmatter `status: draft` → `ratified`. (Checkpoint the change with `/claudna:ship commit` if you want a durable record before moving on.)

## Lenses

Beyond default requirements-gathering, kindle has specialized exploration lenses. Ask which fits the work and adopt its question pattern.

### Lens: Office Hours (YC-style)

**When:** the user is exploring a product idea, asking "is this worth building," or pressure-testing a wedge. Six forcing questions — ask one at a time:

1. **Demand reality.** Who specifically, today, has this problem badly enough to hack a solution? (Not "everyone would love this" — *who already does it by hand?*)
2. **Status quo.** What are they doing instead right now? Why is that painful enough to switch?
3. **Desperate specificity.** Name the first 5 customers by title, company type, and channel where you'd reach them.
4. **Narrowest wedge.** What's the smallest slice of this problem you can solve end-to-end in a week?
5. **Observation.** Have you watched someone struggle with this, or is this reasoning from principle? What did you see?
6. **Future-fit.** If this works, what's the natural compounding — does v1 earn you v2, or do you restart go-to-market for each feature?

If the idea fails Q1 or Q2, the wedge is wrong. Go back to the problem statement, not the solution.

### Lens: Product Vision (architecture-aware)

**When:** the user is exploring what a codebase could become — compound plays, 1-2 hop features, aligning to a mission.

Adopt `/claudna:product-vision`'s own question pattern and scoring mechanics directly (its Phase 1-3: codebase exploration across 5 facets via the disk-write subagent pattern, 1-hop/2-hop feature discovery, deprecation candidates, compound plays, Impact × Effort × Mission-Alignment scoring) rather than restating them here — the two skills would drift out of sync otherwise. Once the user picks a play, proceed to the regular discovery flow on it. For the full standalone report (GitHub Issues, `--auto` mode, deprecation tracking), point the user at `/claudna:product-vision` directly instead of running the lens inline.

### Lens: Product Enhancement (gap analysis)

**When:** the user has a specific product area with issues to triage, or wants to find enhancement opportunities through systematic gap analysis.

1. Inventory the current feature surface (walk the UI / API / CLI; list every entry point).
2. For each entry point, ask: "What's the obvious next thing a user wants here that we don't do?"
3. Rank gaps by frequency × severity (how often it blocks users × how painful when it does).
4. Group related gaps into coherent enhancement themes.
5. Present the top 3-5 themes; user picks; proceed to the regular discovery flow.

> Lightweight, in-ideation gap analysis. For a full ranked punch-list across five enhancement lenses (wedge / friction / coverage / differentiation / cost-of-change), use `/claudna:product-enhance`.

## After the design → forge

Once the spec is approved, invoke `/claudna:forge` to author the implementation plan — pass it the published spec's path as the "existing rough plan" input. Do NOT invoke any other implementation skill — `/claudna:forge` is the next step (it hardens via `/claudna:ironclad` and builds via `/claudna:build`).

## Red flags — STOP, you're rationalizing past the gate

| Rationalization | Reality |
|---|---|
| "It's just one button — getting a yes is pure ceremony." | "It's just one X" is exactly the case the gate warns about. The cheap part is the code; the expensive part is building the wrong thing. The gate costs one sentence. |
| "The user said 'just build it' / 'no time for process'." | That justifies a *shorter* design and *faster* approval — never *zero*. Shrink the gate; don't skip it. |
| "I already know this codebase, the design is obvious." | Obvious to you ≠ agreed with the user. The unexamined assumption (which data? client vs. server?) is what torpedoes the result. |
| "It's too simple to need discovery." | Simple projects are where unexamined assumptions waste the most work. A short design is fine; *no* design is not. |

All of these mean: present a design (sized to the work), get approval, *then* implement.

## Key principles

- **One question at a time** — don't overwhelm.
- **YAGNI ruthlessly** — strip unnecessary features from every design.
- **Surface directions; defer plans and critiques** — forks belong to `forge`, adversarial review to `ironclad`.
- **Incremental validation** — present, get approval, then move on.
