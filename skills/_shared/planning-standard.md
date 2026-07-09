# Planning Standard

Shared quality standard for all skills that produce planning documents, audit reports, or remediation plans. Skills reference this file instead of inlining quality requirements.

---

## Quality Standard

These plans will be handed off to a **junior engineering team for implementation**. The plans are the sole artifact for knowledge transfer — the junior team will not have access to the original author for clarification. Therefore:

- **Extreme attention to detail is mandatory.** Every file path, every function name, every import statement must be explicit. Never say "update the imports" without showing exactly which imports change and how.
- **Reference code explicitly.** Don't describe changes abstractly — show the exact code that exists today and the exact code it should become.
- **Eliminate ambiguity.** If there are two ways to do something, pick one and explain why. Don't leave decisions to the implementer.
- **Ensure separation of concerns.** Each PR should touch a distinct set of files. Verify that no two phases modify the same files unless there is an explicit dependency between them.
- **Prevent parallel conflicts.** Identify which phases can safely run in parallel (touch disjoint files) and which must be sequential. Document this clearly.
- **Include context generously.** Explain *why* each change is being made, not just *what* to change. The junior team needs to understand the reasoning to make good judgment calls during implementation.

**Note:** Individual skills may specify additional domain-specific quality requirements. Plan agents must follow BOTH these shared standards AND any skill-specific additions provided in their launch prompt.

---

## Phase Doc Structure

Each phase doc represents **exactly 1 PR**, and is authored as a **publishable doc**: YAML frontmatter per `skills/_shared/output-guide.md` §3 (`title`, `type`, `status`, `owner`, `created`, plus `tags`/`repos` as applicable) over the §4.1 body skeleton (`## Summary`, `## Evidence`, `## Implementation Plan` with `### Dependencies`/`### Blocks`/`### Steps`, `## Test Plan`, `## Verification Checklist`, `## What NOT To Do`, `## Context`) — `/claudna:publish` validates exactly that shape and rejects docs without it. The content sections below map onto and ride alongside that skeleton (forge models the same layering):

| This standard's section | Lands in |
|---|---|
| 1. Header (PR title, risk, effort, files) | frontmatter `title:` + the `## Context` line (effort/risk) |
| 2. Context (why it matters, the gap) | `## Summary` + `## Evidence` |
| 3. Dependencies | `## Implementation Plan` → `### Dependencies` / `### Blocks` |
| 4. Detailed Implementation Plan | `## Implementation Plan` → `### Steps` |
| 5. Test Plan | `## Test Plan` |
| 6. Documentation Updates | inside `### Steps`, or an added section |
| 7. Stress Testing & Edge Cases | an added section (rides alongside the skeleton) |
| 8. Verification Checklist | `## Verification Checklist` |
| 9. "What NOT To Do" | `## What NOT To Do` |

The content requirements, at minimum:

1. **Header** — PR title, risk level, estimated effort, files created/modified/deleted
2. **Context** — Why this change matters. Link back to user intent and the gap it addresses.
3. **Dependencies** — Which phases must be completed first, and which phases this unlocks
4. **Detailed Implementation Plan**
   - Explicit code references: file paths, line numbers, function names, class names
   - Before/after code examples showing exact changes
   - Step-by-step instructions leaving zero ambiguity
   - New files to create with their full initial content or detailed skeleton
5. **Test Plan**
   - New tests to write (with descriptions of what they verify)
   - Existing tests to modify
   - Coverage expectations
   - Manual verification steps
6. **Documentation Updates**
   - README changes
   - API doc changes
   - Inline comment updates
   - User-facing documentation (if applicable)
7. **Stress Testing & Edge Cases**
   - Edge cases to handle
   - Load/performance considerations (if relevant)
   - Error scenarios and expected behavior
8. **Verification Checklist** — tests to run, commands to execute, things to manually check
9. **"What NOT To Do" Section** — common pitfalls, anti-patterns, things that look right but are wrong

**Note:** Some skills have domain-specific sections that replace or augment items above (e.g., Visual Specification and Accessibility Checklist for design-review, or Root Cause Explanation and cascade diagrams for frontend-performance-audit). When a skill specifies custom sections, Plan agents should use those in place of or in addition to the defaults.
