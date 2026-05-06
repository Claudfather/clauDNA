---
name: docs-review
description: "Use when project documentation may be stale, inaccurate, or incomplete and needs a thorough audit against the codebase. Supports --auto for non-interactive audits, --output github for issue creation, and --output session for chat-only analysis."
argument-hint: "[--auto] [--output github|session] [scope-path]"
---

# Documentation Review

Rigorously audit project documentation against the actual codebase. Update inaccuracies, mark development plan statuses, archive stale docs, and identify gaps — ensuring full handoff-readiness.

**Framing principle:** This project is being handed off to another engineering team. There must be zero gaps. Any engineer who picks up the codebase should be able to fully understand it, have complete context, and confidently edit and enhance the codebase without asking the original team a single question.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Fully non-interactive. Auto-fixes stale docs, creates GitHub Issues for gaps (implies `--output github`). See orchestration guide Section 10.
- `--output github`: Create GitHub Issues for documentation gaps. See output guide (`~/.claude/skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- Remaining text is the scope path (e.g., `docs/`, `documentation/`). If provided, skip asking in Step 1.

## When NOT to use

- For code quality/tech debt → use `/tech-debt`
- For security vulnerabilities → use `/security-audit`
- For writing new docs from scratch → just ask Claude directly

## Procedure

Follow these steps exactly in order.

### Step 1: Scope Selection

Ask the user:

1. **"Review a specific folder?"** → user provides a path (e.g., `./documentation`, `./docs`)
2. **"Global review?"** → scan the entire project for documentation files

If the user chooses a global review, search for:
- All `*.md` files in the repo
- Common doc directories: `docs/`, `documentation/`, `doc/`

Automatically detect and exclude archive/legacy folders from the active review set:
- `archive/`, `legacy/`, `.archive/`, `old/`, `deprecated/`
- Note their existence to the user but do not include them in the active audit

### Step 2: Discovery & Inventory

Find all documentation files within scope. Categorize each doc:

| Category | Description |
|----------|-------------|
| **Coding overview** | Describes architecture, systems, code structure, APIs |
| **Development plan** | Describes phases of work, roadmaps, feature plans |
| **Guide/runbook** | How-to, setup, operational procedures |
| **Reference** | API docs, config references, schemas, changelogs |
| **Other** | Anything that doesn't fit above |

Present the inventory as a table:

```
Documentation Inventory
═══════════════════════════════════════════════════════
  File                        Category           Modified
  docs/architecture.md        Coding overview    2025-01-15
  docs/roadmap.md             Development plan   2025-02-01
  README.md                   Guide/runbook      2025-02-10
  CHANGELOG.md                Reference          2025-02-10
═══════════════════════════════════════════════════════
  4 files found (1 overview, 1 plan, 1 guide, 1 reference)
```

Ask the user to confirm the inventory and categories before proceeding. The user may exclude files or recategorize.

### Step 3: Coding Overview Audit

For each document categorized as **Coding overview**:

1. Read the document thoroughly
2. Use subagents (Task tool with `Explore` type) to trace every claim back to real code:
   - File path references → verify files exist at stated paths
   - Function/class mentions → verify they exist and match descriptions
   - Architecture claims → verify the described patterns in the actual code
   - Integration descriptions → verify connections between systems
   - Config references → verify config files and their current values
3. **Update statements to be true** — fix inaccuracies, wrong file paths, renamed functions, changed APIs
4. **Remove things no longer valid** — deleted features, removed integrations, dead code references
5. **Add detail where missing** — new modules not yet documented, undocumented config, implicit patterns. Think: "What would confuse a senior engineer on day 1?"
6. After edits, show a summary of what changed and why

**Important:** Only modify documentation files. Never touch code files.

### Step 4: Development Plan Audit

For each document categorized as **Development plan**:

1. Read the plan and its phases/sections
2. Use subagents to cross-reference each item against the codebase
3. Mark each section/phase with a status:

| Status | Meaning |
|--------|---------|
| `✅ COMPLETED` | Code exists, feature is implemented |
| `🔧 IN PROGRESS` | Partial implementation exists |
| `📋 PENDING` | No implementation found |

4. Update the doc in place with status markers
5. If the **entire document** is fully completed or no longer valid (superseded, abandoned):
   - Ask the user for confirmation
   - Move it using `git mv` so the rename is tracked in history (ask user for preferred location, default to `archive/` in the doc's parent directory)
   - Create the archive directory first with `mkdir -p` if it doesn't exist
   - Note the move in the summary

### Step 5: Gap Analysis

After reviewing all docs, identify:

- **Undocumented systems** — code modules, services, or significant logic with no corresponding documentation
- **Missing setup/onboarding steps** — things a new engineer would need to know to get started
- **Stale cross-references** — docs linking to other docs that have moved, been archived, or deleted
- **Missing context** — decisions, trade-offs, or "why" explanations that aren't captured anywhere

Present findings as a list and ask the user which gaps to address:
- Create new documentation
- Extend existing documentation
- Skip (note for later)

Execute the user's choices — create or update docs as requested.

### Step 6: Summary Report

Print a final report:

```
Documentation Review Complete
═══════════════════════════════════════════════════════
Files reviewed:    N total
  Coding overview: N (N updated)
  Development plan: N (N updated, N archived)
  Guide/runbook:   N (N updated)
  Reference:       N
  Other:           N

Changes made:
  - docs/architecture.md: Fixed 3 file paths, added new API section
  - docs/roadmap.md: Marked Phase 1 ✅, Phase 2 🔧, Phase 3 📋
  - docs/old-plan.md: Archived → archive/old-plan.md (fully completed)

Gaps identified:
  - No documentation for the auth middleware module
  - Missing onboarding guide for local development setup
  - 2 broken cross-references fixed

Handoff readiness: [assessment]
Could a new engineer onboard from these docs alone?
═══════════════════════════════════════════════════════
```

## Notes

- Uses subagents heavily for codebase exploration — keeps main context clean while doing deep code tracing.
- Always asks before archiving or creating new files.
- Every edit decision is filtered through: "Would a new engineer understand this?"
- Does NOT touch code files — only documentation.
- Archive folder detection is flexible — looks for existing `archive/`, `legacy/`, `.archive/`, or asks the user.
- If the project has no documentation at all, suggest a minimal doc set: README, architecture overview, and development plan.

---

## Output Targets

This skill supports `--output github` and `--output session` in addition to the default inline-fix behavior.

Follow the output guide at `~/.claude/skills/_shared/output-guide.md`:
- For `github`: use the structured issue body format (Section 4), check for duplicates (Section 4.5), apply labels (Section 4.3). Apply `docs` label. Auto-fix verifiable inaccuracies first, then create issues for gaps requiring human judgment.
- For `session`: present findings in chat, stay in Plan Mode (Section 5)
- Default: fix docs inline and ask about gaps (current behavior)

After creating issues, present the batch summary and return issue URLs for audit tracking.

---

## Autonomous Mode (--auto)

When `--auto` is set (see orchestration guide Section 10):
1. Use scope from `$ARGUMENTS` or default to global review
2. Skip user confirmation of inventory (Step 2) — proceed with auto-categorization
3. Auto-fix verifiable inaccuracies in coding overviews (wrong file paths, renamed functions) — commit fixes directly
4. Auto-mark development plan statuses
5. Auto-archive fully completed plans
6. Create GitHub Issues for gaps that require human judgment (new docs to write, structural decisions)
7. Return structured summary for audit tracking
