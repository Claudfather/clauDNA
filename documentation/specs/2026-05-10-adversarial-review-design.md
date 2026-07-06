# Adversarial Review Skill Design

**Date:** 2026-05-10
**Skill name:** `adversarial-review`
**Directory:** `skills/adversarial-review/`
**Pattern:** Read-only diagnostic with optional `--dispatch` for multi-reviewer mode, optional `--output github` for issue filing

## Purpose

Challenge a plan, design, or proposal before committing resources to building it. Surfaces weaknesses, gaps, unstated assumptions, and failure modes through structured analysis grounded in established decision science methodologies.

**What makes this different from code review skills:** This reviews *plans*, not *code*. The question isn't "is this code correct?" but "should we build this at all, and if so, is this the right shape?" It operates before implementation begins, not after.

**Relationship to other skills:**
- `/review-pr` — reviews code after implementation. Adversarial review operates before.
- `/weigh-development-paths` — compares implementation options at a junction. Adversarial review challenges whether the *direction* is right, not just which path to take.
- `/product-vision` — explores what to build. Adversarial review challenges what's been proposed.

## Modes

| Mode | Flag | Description |
|------|------|-------------|
| **Single** | (default) | One consolidated review through all phases |
| **Dispatch** | `--dispatch` | 5 parallel subagent reviewers (Architect, Skeptic, Operator, User, Counter-Planner) + optional 10th Man contrarian |
| **Response** | `--respond` | Steel-man response protocol for plan authors addressing findings |

## Methodology Sources

The skill synthesizes 9 established techniques:

1. **Pre-Mortem** (Gary Klein) — prospective hindsight, ~30% accuracy gain
2. **Murphyjitsu** (CFAR) — iterative surprise calibration
3. **Reference Class Forecasting** (Kahneman/Tversky) — outside view for planning fallacy
4. **Via Negativa** (Taleb/Munger) — subtract before adding
5. **Assumption Mapping** (Gothelf/Seiden) — 2x2 impact x confidence prioritization
6. **Dialectical Inquiry** — fully developed counter-proposals
7. **10th Man Rule** (Israeli Military Intelligence) — mandatory dissent on unanimous consensus
8. **Steel-Manning** (Dennett) — strongest-form restatement before rebuttal
9. **Press Release Test** (Amazon) — value clarity check

## Phase Structure

| Phase | Name | Purpose |
|-------|------|---------|
| 1 | Understand | Read plan + context scan (codebase, PRs, prior attempts) |
| 2 | Pre-Mortem | "It failed. Why?" — 5 concrete failure reasons before structured analysis |
| 3 | Seven Lenses | First Principles, Gaps + Assumption Map, Edge Cases, Alternatives, Implementation Risk + Reference Class, Press Release, Counter-Plan |
| 4 | Murphyjitsu | "Would I be surprised if this failed?" convergence loop |
| 5 | Dispatch | (optional) Parallel multi-reviewer synthesis + 10th Man Rule |
| 6 | Synthesize | Categorize (Blocker/Risk/Gap/Question/Observation), output structured review |

## Output Format

Structured review with: Pre-Mortem results, Overall Assessment, Blockers, Risks, Gaps, Assumption Map, Questions, First Principles Check, Press Release Test, Counter-Plan, Alternatives table, Reference Class, Murphyjitsu Verdict, Summary Table.

## Design Decisions

- **Pre-mortem before lenses:** Primes the reviewer's mindset for critical thinking. The unstructured "assume failure" step often surfaces the most valuable insights.
- **Seven lenses, not five:** Added Press Release Test (catches value clarity gaps) and Counter-Plan (forces fully developed alternative, not just a name).
- **Murphyjitsu as convergence:** Prevents reviews from ending with a laundry list of risks but no conviction about readiness. Forces a binary: "surprised by failure, or not?"
- **10th Man only on unanimous consensus:** Avoids wasting compute on contrarian analysis when real disagreements already exist.
- **Steel-man response protocol is post-review:** Keeps the review itself adversarial; the response phase is where the author gets to engage.
