---
name: notes
description: "Use when you want to save, read, or organize persistent notes across Claude sessions."
---

# Notes Manager

Maintain persistent notes across Claude sessions.

## Notes Directory

Global notes: `~/.claude/notes/`

Structure:
```
~/.claude/notes/
├── projects/           # Per-project learnings
│   ├── api-server.md
│   ├── data-pipeline.md
│   └── myproject.md
├── patterns/           # Reusable patterns discovered
│   ├── snowflake.md
│   ├── streamlit.md
│   └── python.md
└── decisions/          # Key decisions and rationale
    └── YYYY-MM-DD-topic.md
```

## Instructions

When asked to take notes or after completing significant work:

1. **Identify the category**:
   - Project-specific learning → `~/.claude/notes/projects/{project}.md`
   - General pattern/technique → `~/.claude/notes/patterns/{topic}.md`
   - Important decision → `~/.claude/notes/decisions/{date}-{topic}.md`

2. **Append to existing notes** (don't overwrite):
   ```markdown
   ## YYYY-MM-DD: Topic

   ### Context
   What was the task/problem?

   ### Solution
   What worked?

   ### Lessons
   - Key takeaway 1
   - Key takeaway 2
   ```

3. **Reference notes** when starting related work:
   - Check `~/.claude/notes/projects/{project}.md` before working on a project
   - Review patterns that might apply

## Commands

**Save a note:** Read the current content with the Read tool, then use the Edit tool to append:
```markdown
## 2024-01-15: Topic here

Content here...
```

**Read project notes:** Use the Read tool on `~/.claude/notes/projects/<project>.md`

**List all notes:** Use the Glob tool with pattern `**/*.md` in `~/.claude/notes/`

## Auto-Note Prompt

After completing a PR or significant task, Claude should ask:
> "Should I add notes about this work to `~/.claude/notes/projects/{project}.md`?"
