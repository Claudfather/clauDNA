---
name: lessons
description: "Use when Claude has been corrected and the lesson should be captured, or when you want to review past lessons."
---

# Lessons Manager

Self-improvement loop for Claude - capture and review lessons from corrections.

## Lessons Location

Global lessons: `~/.claude/notes/lessons/`
Project lessons: `.claude/lessons.md` (in project root)

## After ANY Correction

When the user corrects you, IMMEDIATELY:

1. **Acknowledge** the correction
2. **Extract the pattern** - What general rule would prevent this?
3. **Write the lesson** — use the Read tool to get current content, then the Edit tool to append:

**Global lesson** → append to `~/.claude/notes/lessons/global.md`:
```markdown
## YYYY-MM-DD: [Category] Brief Title

**Mistake:** What I did wrong
**Correction:** What I should have done
**Rule:** General rule to prevent this
```

**Project-specific lesson** → append to `.claude/lessons.md`:
```markdown
## YYYY-MM-DD: Brief Title

**Mistake:** ...
**Rule:** ...
```

## Reviewing Lessons (On Demand)

When the user asks to review lessons, or when starting a session where past mistakes are relevant:
- Read `~/.claude/notes/lessons/global.md`
- Read `.claude/lessons.md` (skip if it doesn't exist)

## Lesson Categories

- `[Code Style]` - Formatting, naming, conventions
- `[Architecture]` - Design decisions, patterns
- `[Testing]` - Test coverage, verification
- `[Git]` - Commit messages, PR workflow
- `[Communication]` - How to explain, ask questions
- `[Tool Use]` - Bash, SQL, specific tools

## Self-Improvement Prompt

After being corrected, say:
> "Let me add this to my lessons so I don't make this mistake again."

Then update the lessons file.
