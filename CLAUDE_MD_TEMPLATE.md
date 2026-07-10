# CLAUDE.md Template

Copy this to your project root and customize.

---

# CLAUDE.md - [Project Name]

## Project Overview

[Describe what this project does, its tech stack, and key components]

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

## Task Management

1. **Plan First**: Write plan to `.claude/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `.claude/todo.md`

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- **Demand Elegance** (Balanced):
  - For non-trivial changes: pause and ask "is there a more elegant way?"
  - If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
  - Skip this for simple, obvious fixes — don't over-engineer
  - Challenge your own work before presenting it

## Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests – then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

<!-- Static sections above, project-specific sections below. Keep this order for prompt cache efficiency. -->

## Development Workflow

```bash
# Verification loop
[your lint command]     # Lint
[your format command]   # Format
[your test command]     # Test
```

## Code Style & Conventions

[List your project-specific conventions]

## Commands Reference

```bash
# Common commands for this project
```

## Things Claude Should NOT Do

[List mistakes to avoid - update this after corrections]

## Project-Specific Patterns

[Document patterns specific to this codebase]

### Planning Doc Lifecycle
- Active plans live in `documentation/planning/<category>/<session>_<date>/`
- Completed plans are archived to `documentation/archive/<session>_<date>/` via `git mv`
- `documentation/archive/` should be added to `.claudeignore` so archived docs don't load into context
- When all phases in a session are complete, move the **entire session directory** to `documentation/archive/`
- Clean up empty parent directories after moving
- Never use `completed/` subdirectories within `documentation/planning/` — always move to `documentation/archive/`

---

_Update this file at session boundaries (e.g., during `/claudna:session handoff`)._

_If this file grows beyond ~200 lines, move domain-specific details into `.claude/rules/` files with `paths:` frontmatter for on-demand loading._
