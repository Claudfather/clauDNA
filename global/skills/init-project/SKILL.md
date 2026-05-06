---
name: init-project
description: "Use when setting up a new project or adding standard Claude Code configuration (CLAUDE.md, CHANGELOG.md, .claude/) to an existing project."
allowed-tools: Read(*), Write(*), Edit(*), Glob(*), Grep(*), Bash(git *), Bash(ls *)
---

# Initialize Project

Set up a project with standard clauDNA configuration: `CLAUDE.md`, `CHANGELOG.md`, and `.claude/lessons.md`. Works for both new repos and existing projects that lack these files.

## Procedure

Follow these steps exactly in order.

### Step 1: Assess Current State

Scan the project root for existing configuration:

- `CLAUDE.md` — project instructions for Claude Code
- `CHANGELOG.md` — structured change history
- `.claude/lessons.md` — project-specific lessons

Also scan for signals about the project:

- `README.md` — project description, tech stack
- `package.json`, `Cargo.toml`, `pyproject.toml`, `*.xcodeproj`, `go.mod` — tech stack detection
- `.git/` — is this a git repo?
- Existing source directories — understand the project structure

Present findings:

```
Project Assessment
═══════════════════════════════════════════════════════
  Project root:    /path/to/project
  Git repo:        yes/no
  Tech stack:      [detected from manifest files]

  CLAUDE.md:       ✓ exists / ✗ missing
  CHANGELOG.md:    ✓ exists / ✗ missing
  .claude/lessons.md: ✓ exists / ✗ missing
═══════════════════════════════════════════════════════
```

If all three exist, tell the user and ask if they want to align any to the clauDNA template. If none exist, proceed to Step 2. If some exist, note which will be created vs. skipped.

### Step 2: Gather Project Context

Ask the user these questions (skip any that are obvious from Step 1):

1. **Project name and one-line description**
2. **Key commands** — build, lint, test, dev server (whatever applies)
3. **Any known "gotchas"?** — things Claude should NOT do, common mistakes, domain-specific traps

Keep the interview short. If the codebase is readable, infer what you can and confirm with the user rather than asking from scratch.

### Step 3: Create CLAUDE.md

Generate `CLAUDE.md` using the template at [references/CLAUDE_MD_TEMPLATE.md](references/CLAUDE_MD_TEMPLATE.md).

**Customization rules:**
- Fill in the Project Overview section with real project details
- Populate the Architecture section by scanning the actual directory structure (use `ls` and `Glob`). Show the real tree, not a placeholder.
- Fill in Development Workflow with the actual commands from Step 2
- Fill in Commands Reference with the actual commands
- Add any gotchas from Step 2 to "Things Claude Should NOT Do"
- Keep all static sections (Workflow Orchestration, Core Principles, etc.) exactly as templated — these are universal
- Remove placeholder comments (`<!-- Customize -->`) after filling in

**For large projects** (200+ lines after customization): Consider creating `.claude/rules/` files with `paths:` frontmatter to scope domain-specific rules to matching files. Keep CLAUDE.md under 200 lines — only universal rules and safety constraints.

**Do NOT:**
- Leave `[bracket placeholders]` in the output
- Remove static sections the user didn't ask about
- Over-fill sections with speculation — empty with a note is better than wrong

### Step 4: Create CHANGELOG.md

Generate `CHANGELOG.md` using the template at [references/CHANGELOG_TEMPLATE.md](references/CHANGELOG_TEMPLATE.md).

**Customization rules:**
- If this is a new project, create a single `## [Unreleased]` section
- If the project has existing git history, create version sections from tags and populate with summaries of the commits
- Use `git log --oneline` and `git tag` to build history
- Follow the Keep a Changelog format: `### Added`, `### Fixed`, `### Changed`, `### Removed`, `### Refactored`
- Entry format: `- **Feature Name** — Description`

### Step 5: Create .claude/lessons.md

Create `.claude/lessons.md` with any gotchas from Step 2. If none were provided, create the file with a header only:

```markdown
# Lessons
```

This file will accumulate organically as Claude makes mistakes and gets corrected.

### Step 6: Verify & Confirm

Show the user what was created:

```
Project Initialized
═══════════════════════════════════════════════════════
  Created:
    ✓ CLAUDE.md          (N lines — project instructions)
    ✓ CHANGELOG.md       (N lines — change history)
    ✓ .claude/lessons.md (N lines — lessons)

  Skipped:
    - CLAUDE.md (already exists)
═══════════════════════════════════════════════════════
```

Ask: **"Want me to commit these files?"**

If yes, stage only the created/modified files and commit with:
```
docs: initialize project configuration (CLAUDE.md, CHANGELOG.md, .claude/)
```

---

## Rules

- **Never overwrite existing files without asking.** If `CLAUDE.md` already exists, ask before replacing or merging.
- **Infer before asking.** Read the codebase first. Ask the user to confirm/correct, not to describe from scratch.
- **Keep static sections intact and ordered first.** The Workflow Orchestration, Core Principles, Self-Improvement Loop, and Task Management sections are universal clauDNA conventions. They must appear before project-specific dynamic sections for cache efficiency.
- **Architecture must be real.** Scan the actual directory tree. Don't write a placeholder tree structure.
- **CHANGELOG must reflect real history.** Use `git log` and `git tag`. Don't invent entries.
