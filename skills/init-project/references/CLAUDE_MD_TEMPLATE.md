# CLAUDE.md - [Project Name]

This file provides project-specific guidance for Claude Code.

---

## Workflow Orchestration

### Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately – don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- **Demand Elegance** (Balanced):
  - For non-trivial changes: pause and ask "is there a more elegant way?"
  - If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
  - Skip this for simple, obvious fixes — don't over-engineer
  - Challenge your own work before presenting it

### Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `.claude/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `.claude/todo.md`

<!-- Static sections above, project-specific sections below. Keep this order for prompt cache efficiency. -->

<!-- Optional: shared-docs seam. /claudna:init-project Step 7.5 replaces this block with a
     real section when a shared knowledge root exists; to add it by hand, uncomment and set
     the path (first non-empty line = root path; append `(claudron vault)` only for an
     engine-managed root). Contract: skills/_shared/documentation-standard.md §10.
     Delete this block if the project doesn't use shared docs.

## Shared Documentation

~/shared
Cross-project knowledge lives here — see /claudna:recall.
-->

---

## Project Overview

<!-- Fill in: project name, description, tech stack -->

### Architecture

<!-- Fill in: actual directory tree from scanning the codebase -->

### Key Principles

<!-- Fill in: domain-specific principles, sync rules, invariants -->

---

## Development Workflow

<!-- Fill in: actual commands -->

1. Make changes
2. Run linter: `[lint command]`
3. Run formatter: `[format command]`
4. Run tests: `[test command]`
5. Before creating PR: run full lint and test suite

## Commands Reference

```sh
# Verification loop
[lint command]        # Lint
[format command]      # Format
[test command]        # Test
```

## Code Style & Conventions

<!-- Fill in: project-specific conventions -->

## Things Claude Should NOT Do

<!-- Fill in: known gotchas, common mistakes, domain traps -->

## Project-Specific Patterns

<!-- Fill in: patterns unique to this codebase -->

---

_Update this file at session boundaries (e.g., during `/claudna:session handoff`)._

_If this file grows beyond ~200 lines, move domain-specific details into `.claude/rules/` files with `paths:` frontmatter for on-demand loading._
