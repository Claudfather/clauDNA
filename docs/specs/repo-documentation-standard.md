# Repo Documentation Standard

**Date:** 2026-05-10
**Status:** Active
**Enforced by:** `/init-project` scaffolding, skill output conventions

## Purpose

Define the standard documentation structure that clauDNA skills assume exists within repositories. Skills like `/implement-plan`, `/session-handoff`, `/context-resume`, `/tech-debt`, `/security-audit`, `/product-enhance`, and `/product-vision` all read from and write to a shared directory layout. This spec codifies that layout so `/init-project` can scaffold it and all skills interoperate without ad-hoc directory creation.

## Directory Layout

```
<repo-root>/
├── PROJECT_MISSION.md                        # What this project is and why it exists
├── CHANGELOG.md                              # Keep a Changelog format
├── CLAUDE.md                                 # Claude Code project instructions
├── .claude/
│   ├── lessons.md                            # Project-specific lessons
│   └── settings.json                         # Permissions
└── documentation/
    ├── planning/                             # Active plans and audits
    │   ├── phases/                           # /product-enhance output
    │   │   └── <session>_<YYYY-MM-DD>/
    │   ├── tech_debt/                        # /tech-debt output
    │   │   └── <session>_<YYYY-MM-DD>/
    │   ├── security/                         # /security-audit output
    │   │   └── <session>_<YYYY-MM-DD>/
    │   ├── access-paths/                     # /access-path-audit output
    │   │   └── <session>_<YYYY-MM-DD>/
    │   ├── product-vision/                   # /product-vision output
    │   │   └── <session>_<YYYY-MM-DD>/
    │   └── investigations/                   # Ad-hoc research and debugging docs
    │       └── <topic>_<YYYY-MM-DD>.md
    └── archive/                              # Completed plans moved here
        └── <session>_<YYYY-MM-DD>/
```

Session subdirectories are created by skills at runtime — `/init-project` only scaffolds the category directories.

## File Conventions

### Root-Level Files

| File | Created by | Purpose |
|------|-----------|---------|
| `PROJECT_MISSION.md` | `/init-project`, `/product-vision` | One-paragraph mission statement. What this project does, who it's for, what success looks like. Skills like `/product-vision` read this to anchor ideation. |
| `CHANGELOG.md` | `/init-project` | Keep a Changelog format. `/session-handoff` checks `[Unreleased]` against session commits. |
| `CLAUDE.md` | `/init-project` | Claude Code project instructions. Static universal sections first (cache efficiency), project-specific below. |
| `.claude/lessons.md` | `/init-project` | Accumulated corrections and gotchas. Updated by the Self-Improvement Loop. |

### Planning Session Directories

Each planning skill writes to its designated subdirectory under `documentation/planning/`. The naming convention is consistent:

**Directory name:** `<session-name>_<YYYY-MM-DD>`

Session names are slugified descriptors (e.g., `api-rate-limiting_2026-05-10`, `auth-middleware-rewrite_2026-05-08`). The `/name-session` skill generates these.

**File naming within a session:**

| File | Purpose |
|------|---------|
| `00_OVERVIEW.md` or `00_<TYPE>.md` | Master document — inventory, dependency graph, summary |
| `01_<phase-slug>.md` | First implementation phase (one PR) |
| `02_<phase-slug>.md` | Second implementation phase |
| `NN_<phase-slug>.md` | Nth phase |

The `00_` prefix always denotes the overview/master document. Numbered phases (`01_` through `NN_`) each represent one PR's worth of work.

### Status Markers

Skills embed status markers in plan documents. These are read by `/context-resume`, `/session-handoff`, and `/implement-plan`:

| Marker | Meaning |
|--------|---------|
| `PENDING` | Not started |
| `IN PROGRESS` | Currently being implemented |
| `✅ COMPLETE` | Done, PR merged |

`/context-resume` greps `documentation/planning/` for `IN PROGRESS` and `PENDING` to suggest what to work on. `/session-handoff` checks for completed-but-unarchived sessions (all phases `✅ COMPLETE`).

### Archive Convention

When all phases in a session are `✅ COMPLETE` and the final PR is merged, `/implement-plan` archives via `git mv`:

```
documentation/planning/<category>/<session>/ → documentation/archive/<session>/
```

`/session-handoff` flags completed-but-unarchived sessions and offers to archive them. `/context-resume` flags them too and suggests archiving.

## Skill Output Matrix

| Skill | Writes to | Creates `00_` overview | Creates numbered phases |
|-------|-----------|----------------------|----------------------|
| `/tech-debt` | `planning/tech_debt/` | `00_TECH_DEBT.md` | Yes |
| `/product-enhance` | `planning/phases/` | `00_OVERVIEW.md` | Yes |
| `/security-audit` | `planning/security/` | `00_SECURITY_AUDIT.md` | Yes |
| `/access-path-audit` | `planning/access-paths/` | `00_ACCESS_PATH_AUDIT.md` | Yes |
| `/product-vision` | `planning/product-vision/` | Varies | No (ideation, not phases) |
| `/adversarial-review` | None (session output) | N/A | N/A |
| `/implement-plan` | Reads from any of the above | N/A | N/A |
| `/session-handoff` | Reads `planning/` for status | N/A | N/A |
| `/context-resume` | Reads `planning/` for status | N/A | N/A |

## What `/init-project` Scaffolds

`/init-project` creates the base directory structure with `.gitkeep` files so git tracks empty directories:

```
documentation/
├── planning/
│   ├── phases/.gitkeep
│   ├── tech_debt/.gitkeep
│   ├── security/.gitkeep
│   ├── access-paths/.gitkeep
│   ├── product-vision/.gitkeep
│   └── investigations/.gitkeep
└── archive/.gitkeep
```

Plus `PROJECT_MISSION.md` at the repo root (stub if user doesn't provide mission context).

Skills create their session subdirectories at runtime — the scaffold just ensures the category directories exist.

## Design Decisions

- **Category directories under `planning/`** rather than flat session dirs: Skills need to find their own output type quickly. `documentation/planning/security/` is scannable; `documentation/planning/` with 20 mixed sessions is not.
- **`documentation/` not `docs/`**: `docs/` is commonly used for user-facing documentation (GitHub Pages, API docs). `documentation/` is development-internal — plans, audits, investigations. Keeping them separate avoids conflicts.
- **`.gitkeep` for empty dirs**: Git doesn't track empty directories. `.gitkeep` is the standard convention to preserve structure. Skills should not fail if the directory doesn't exist (create it), but the scaffold means they usually find it ready.
- **`investigations/` is freeform**: Unlike the structured planning subdirs, `investigations/` holds ad-hoc markdown — debugging notes, research, decision records. No numbered phases, no status markers. Just `<topic>_<YYYY-MM-DD>.md`.
- **`PROJECT_MISSION.md` at root, not in `documentation/`**: It's a project-level identity doc, like `README.md` or `CLAUDE.md`. `/product-vision` reads it to anchor feature ideation. It should be visible at the top level.
