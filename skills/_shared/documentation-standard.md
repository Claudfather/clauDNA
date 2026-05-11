# Documentation Standard

Shared reference for skills that read from or write to the `documentation/` directory. Skills reference this file at `skills/_shared/documentation-standard.md`.

---

## 1. Directory Layout

Every repo initialized with `/claudna:init-project` has this structure:

```
<repo-root>/
├── PROJECT_MISSION.md
├── CHANGELOG.md
├── CLAUDE.md
├── .claude/
│   ├── lessons.md
│   └── settings.json
└── documentation/
    ├── planning/                    # Active plans and audits (skill output)
    │   ├── phases/                  # /claudna:product-enhance
    │   ├── tech_debt/               # /claudna:tech-debt
    │   ├── security/                # /claudna:security-audit
    │   ├── access-paths/            # /claudna:access-path-audit
    │   ├── product-vision/          # /claudna:product-vision
    │   └── investigations/          # Ad-hoc research
    ├── decisions/                   # Architecture Decision Records
    ├── specs/                       # Technical specifications
    ├── guides/                      # Setup, onboarding, runbooks
    └── archive/                     # Completed plans moved here
```

## 2. Planning Output Paths

When writing planning output (default `--output docs` target), use these paths:

| Skill | Output directory |
|-------|-----------------|
| `/claudna:tech-debt` | `documentation/planning/tech_debt/` |
| `/claudna:product-enhance` | `documentation/planning/phases/` |
| `/claudna:security-audit` | `documentation/planning/security/` |
| `/claudna:access-path-audit` | `documentation/planning/access-paths/` |
| `/claudna:product-vision` | `documentation/planning/product-vision/` |

If the target directory doesn't exist, create it (with `.gitkeep`) before writing. Don't fail on missing directories.

## 3. Session Naming

Session directories follow: `<session-name>_<YYYY-MM-DD>`

Example: `api-rate-limiting_2026-05-10`

The `/claudna:name-session` skill generates these. Session names are kebab-case slugified descriptors.

## 4. File Naming Within Sessions

| Prefix | Purpose |
|--------|---------|
| `00_` | Master document — overview, inventory, dependency graph |
| `01_` through `NN_` | Numbered phases, each = one PR |

The `00_` file uses a type-specific name: `00_TECH_DEBT.md`, `00_SECURITY_AUDIT.md`, `00_ACCESS_PATH_AUDIT.md`, or `00_OVERVIEW.md`.

Phase files use: `NN_<phase-slug>.md` (e.g., `01_input-validation.md`).

## 5. Status Markers

Embed these in plan documents. They are machine-read by `/claudna:context-resume`, `/claudna:session-handoff`, and `/claudna:implement-plan`:

| Marker | Meaning |
|--------|---------|
| `PENDING` | Not started |
| `IN PROGRESS` | Currently being implemented |
| `✅ COMPLETE` | Done, PR merged |

## 6. Archive Convention

When all phases are `✅ COMPLETE` and the final PR is merged:

```
git mv documentation/planning/<category>/<session>/ documentation/archive/<session>/
```

`/claudna:implement-plan` does this in Step 8. `/claudna:session-handoff` flags completed-but-unarchived sessions.

## 7. Non-Planning Directories

These hold permanent documentation, not ephemeral planning artifacts:

| Directory | Content | File naming |
|-----------|---------|-------------|
| `decisions/` | ADRs — why we chose X over Y | `<NNN>-<slug>.md` (e.g., `001-use-neon-over-supabase.md`) |
| `specs/` | Technical specifications, API contracts | `<slug>.md` (e.g., `api-endpoints.md`) |
| `guides/` | Setup, onboarding, runbooks | `<slug>.md` (e.g., `local-setup.md`) |

These are not archived — they're living documents that evolve with the codebase.

## 8. Reading Documentation State

Skills that scan documentation state (e.g., `/claudna:context-resume`, `/claudna:session-handoff`, `/claudna:repo-health`):

```bash
# Find in-progress plans
grep -r "IN PROGRESS" documentation/planning/

# Find completed but unarchived sessions
# (all phases ✅ COMPLETE but still in planning/)
grep -rl "✅ COMPLETE" documentation/planning/ | xargs -I{} dirname {} | sort -u

# Check for pending plans
grep -r "PENDING" documentation/planning/
```

## 9. PROJECT_MISSION.md

Lives at repo root (not in `documentation/`). Contains a one-paragraph mission statement: what this project does, who it's for, what success looks like. Read by `/claudna:product-vision` to anchor ideation. Created by `/claudna:init-project`, refined by `/mission`.
