# Documentation Standard

Shared reference for skills that read from or write to the two documentation planes — the per-project `documentation/` tree (§1–§9) and the plane doctrine covering both it and the shared-docs vault (§10). Skills reference this file at `skills/_shared/documentation-standard.md`.

---

## 1. Directory Layout

Every repo initialized with `/claudna:init-project` has this structure:

```
<repo-root>/
├── PROJECT_MISSION.md
├── CHANGELOG.md
├── CLAUDE.md
├── .claude/
│   └── settings.json
└── documentation/
    ├── planning/                    # Active plans and audits (skill output)
    │   ├── phases/                  # /claudna:product-enhance
    │   ├── tech_debt/               # /claudna:audit tech-debt
    │   ├── security/                # /claudna:audit security
    │   ├── access-paths/            # /claudna:audit access-path
    │   ├── product-vision/          # /claudna:product-vision
    │   └── investigations/          # Ad-hoc research
    ├── decisions/                   # Architecture Decision Records
    ├── specs/                       # Technical specifications
    ├── guides/                      # Setup, onboarding, runbooks
    └── archive/                     # Completed plans moved here
```

## 2. Planning Output Paths — the `--dir` registry

Planning output (the default `--output docs` target) routes through `/claudna:publish --to docs --dir <path>` — the author writes its doc(s) to a scratch directory and publish validates + places them. This table is the `--dir` registry: each skill passes its category directory **with its session directory appended** (`<category>/<session-name>_<YYYY-MM-DD>/`, §3) — publish places docs into exactly the `--dir` it receives, no path composition of its own.

| Skill | `--dir` |
|-------|-----------------|
| `/claudna:audit tech-debt` | `documentation/planning/tech_debt/` |
| `/claudna:audit security` | `documentation/planning/security/` |
| `/claudna:audit access-path` | `documentation/planning/access-paths/` |
| `/claudna:audit frontend-perf` | `documentation/planning/performance/` |
| `/claudna:audit design` | `documentation/planning/phases/` |
| `/claudna:audit repo-health` | `documentation/planning/repo_health/` |
| `/claudna:audit data-model` | `documentation/planning/data-model/` |
| `/claudna:product-enhance` | `documentation/planning/phases/` |
| `/claudna:product-vision` | `documentation/planning/product-vision/` |
| `/claudna:investigate-app` | `documentation/planning/investigations/` |
| `/claudna:development-retro` | `documentation/planning/retros/` |
| `/claudna:weigh-development-paths` | `documentation/planning/decisions/` |
| `/claudna:forge` (docs output) | `documentation/planning/<topic-slug>/` |

If the target directory doesn't exist, publish creates it before writing (Write tool creates parents). Don't fail on missing directories. Categories beyond §1's scaffolded tree (`performance/`, `repo_health/`, `data-model/`, `retros/`, `decisions/`) are created on demand the same way.

## 3. Session Naming

Session directories follow: `<session-name>_<YYYY-MM-DD>`

Example: `api-rate-limiting_2026-05-10`

The `/claudna:session` engine's name mode generates these. Session names are kebab-case slugified descriptors.

## 4. File Naming Within Sessions

| Prefix | Purpose |
|--------|---------|
| `00_` | Master document — overview, inventory, dependency graph |
| `01_` through `NN_` | Numbered phases, each = one PR |

The `00_` file uses a type-specific name: `00_TECH_DEBT.md`, `00_SECURITY_AUDIT.md`, `00_ACCESS_PATH_AUDIT.md`, or `00_OVERVIEW.md`.

Phase files use: `NN_<phase-slug>.md` (e.g., `01_input-validation.md`).

## 5. Status Markers

Embed these in plan documents. They are machine-read by `/claudna:session` (resume and handoff modes) and `/claudna:implement-plan`:

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

`/claudna:implement-plan` does this in Step 8. `/claudna:session` handoff mode flags completed-but-unarchived sessions.

## 7. Non-Planning Directories

These hold permanent documentation, not ephemeral planning artifacts:

| Directory | Content | File naming |
|-----------|---------|-------------|
| `decisions/` | ADRs — why we chose X over Y | `<NNN>-<slug>.md` (e.g., `001-use-neon-over-supabase.md`) |
| `specs/` | Technical specifications, API contracts | `<slug>.md` (e.g., `api-endpoints.md`) |
| `guides/` | Setup, onboarding, runbooks | `<slug>.md` (e.g., `local-setup.md`) |

These are not archived — they're living documents that evolve with the codebase.

## 8. Reading Documentation State

Skills that scan documentation state (e.g., `/claudna:session` resume and handoff modes, `/claudna:audit repo-health`):

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

## 10. The Two Documentation Planes

Documentation lives on two planes, and `/claudna:publish` is the single router over both. Plane fit is advised, never blocked (see the publish adapters).

| | `documentation/` (this standard, §1–§9) | The shared-docs vault |
|---|---|---|
| **Content** | Work-in-flight + repo-coupled records: plans, audits, reviews, ADRs, specs, guides | Cross-project referential knowledge: knowledge pages, runbooks, cross-repo decisions |
| **Lives** | In the repo, versioned with the code | Outside any one repo (`shared/{knowledge,decisions,runbooks,planning/…}` raw tree, or a Claudron vault) |
| **Reviewed via** | Pull requests | Lifecycle management (status/supersession; curation) |
| **Discovered via** | git + status-marker greps (§8) | Raw tree: INDEX.md (`/claudna:index` writes it, `/claudna:recall` scans it) · Claudron vault: engine-indexed, no INDEX.md (annotation semantics below) |
| **Visibility** | Public when the repo is | Private by default |
| **Publish adapter** | `--to docs --dir <path>` (§2 registry) | `--to vault` (the default adapter) |

### The Shared Documentation section — locating the root

Consumers find the shared-docs root through two doors, env first:

1. **Env override:** `CLAUDRON_VAULT_PATH` (engine-managed vault) or `SHARED_DOCS_PATH` (raw tree). If both are set, that order wins. User-managed — no clauDNA skill ever sets env vars.
   - **`CLAUDRON_VAULT_PATH` is Claudron's contract, not ours.** The name, its precedence against `--vault` and the engine's walk-up, and the migration record live once in [Claudron's `docs/CLI_CONTRACT.md` §Environment](https://github.com/Claudfather/Claudron/blob/main/docs/CLI_CONTRACT.md#environment). Do not restate that ladder here or downstream — a change to it is a PR against that repo first.
   - **`CLAUDRON_VAULT` (no `_PATH`) is gone.** Claudron removed it in 0.3.0; the engine does not read it, and neither do we. A consumer honoring a name the engine ignores resolves a *different vault* than the engine does — the two-vaults hazard the removal exists to end, pointing the other way. If a user still exports it, the engine says so on stderr at the moment it matters; the remedy is to rename the variable.
   - `SHARED_DOCS_PATH` is **fallback-mode only** — it addresses a raw documentation tree and is never consulted once an engine has been detected.
2. **CLAUDE.md section:** a section headed exactly `## Shared Documentation`. `/claudna:init-project`'s shared-docs seam step is the sole producer; `/claudna:recall` and `/claudna:index` parse it.

The section format is parseable, not prose:

- **The first non-empty line after the heading is the root path** — absolute or `~`-relative.
- **Tolerant extraction:** if that first line is a sentence rather than a bare path (fleet-templated CLAUDE.md files, e.g. ``Fleet-shared docs at `/path`:``), take the first backtick-quoted path in it. Producers still write the bare form — the tolerance exists for externally-templated sections, not as a second format.
- **An optional `(claudron vault)` annotation** after the path marks the root as engine-managed. Everything after the path line is free prose for humans.
- **A heading inside an HTML comment (`<!-- -->`) is not a section** — the CLAUDE.md template ships a commented placeholder; consumers treat it as absent.

```markdown
## Shared Documentation

~/vault  (claudron vault)
Cross-project knowledge lives here — see /claudna:recall.
```

**Precedence.** Env wins. When an env var and the section disagree, consumers use the env value and print a mismatch notice naming both paths.

**Annotation semantics.** A `(claudron vault)` root — or any root resolved from `CLAUDRON_VAULT_PATH` — is engine-indexed and carries **no INDEX.md**: fallback consumers must never INDEX-scan it and never suggest `/claudna:index` against it. Their degraded message: "engine-managed root; install claudron or point the section at a raw tree." (For env-derived roots, append: "(root came from `CLAUDRON_VAULT_PATH` — unset it to fall back)", since the section remedy alone can't override env precedence.) An unannotated root is a raw tree — INDEX.md discovery per this standard applies.

### Which door writes the vault?

Three doors write vault-ward — partitioned by intent:

| Intent | Door |
|---|---|
| Save knowledge — a note you write, external content (article, repo, transcript, file), or the current session's learnings (bare `/claudna:capture`) | `/claudna:capture` — routes text / URL / file / session to the vault; needs the Claudron CLI, else falls back to the raw tree |
| Route a finished, frontmattered doc | `/claudna:publish --to vault` |

Skills writing the `documentation/` plane are not listed here — they all go through `publish --to docs` per the §2 registry.
