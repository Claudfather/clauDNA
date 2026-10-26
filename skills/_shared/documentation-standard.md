# Documentation Standard

Shared reference for skills that read from or write to the two documentation planes — the per-project `documentation/` tree (§1–§9) and the plane doctrine covering both it and the shared-docs vault (§10). Skills reference this file at `../_shared/documentation-standard.md`.

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

Planning output (the default `--output docs` target) routes through `/claudna:publish --to docs --dir <path>` — the author writes its doc(s) to `<scratch>` (`../_shared/orchestration-guide.md` §1) and publish validates + places them. This table is the `--dir` registry: each skill passes its category directory **with its session directory appended** (`<category>/<session-name>_<YYYY-MM-DD>/`, §3) — publish places docs into exactly the `--dir` it receives, no path composition of its own.

| Skill | `--dir` |
|-------|-----------------|
| `/claudna:audit tech-debt` | `documentation/planning/tech_debt/` |
| `/claudna:audit security` | `documentation/planning/security/` |
| `/claudna:audit access-path` | `documentation/planning/access-paths/` |
| `/claudna:audit frontend-perf` | `documentation/planning/performance/` |
| `/claudna:audit design` | `documentation/planning/phases/` |
| `/claudna:audit repo-health` | `documentation/planning/repo_health/` |
| `/claudna:audit data-model` | `documentation/planning/data-model/` |
| `/claudna:audit data-model-redesign` | `documentation/planning/data-model/` (shared with the fit lens — the `<session>_<date>/` suffix and distinct master names keep runs separate) |
| `/claudna:audit scale` | `documentation/planning/scale/` |
| `/claudna:product-enhance` | `documentation/planning/phases/` |
| `/claudna:product-vision` | `documentation/planning/product-vision/` |
| `/claudna:investigate-app` | `documentation/planning/investigations/` |
| `/claudna:development-retro` | `documentation/planning/retros/` |
| `/claudna:weigh-development-paths` | `documentation/planning/decisions/` |
| `/claudna:kindle` | `documentation/planning/decisions/` |
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

A session can also hold numbered docs that aren't phases, such as an ironclad review cycle, a decision or research notes. A numbered doc whose `type:` is something other than `plan` or `audit` isn't a phase.

## 5. Status Markers

Embed these in the body of plan documents: a doc's status line, the overview's phase rows, each deliverable. They are machine-read by `/claudna:session` (resume and handoff modes) and `/claudna:build`:

| Marker | Meaning |
|--------|---------|
| `PENDING` | Not started |
| `IN PROGRESS` | Started, not finished — including work that has partly shipped |
| `✅ COMPLETE` | Done, PR merged |

**Markers and frontmatter `status:`.** Markers record the progress of the work inside a doc. Frontmatter `status:` records the doc's lifecycle in its type's vocabulary, which Claudron's [`SCHEMA.md` §Status vocabulary](https://github.com/Claudfather/Claudron/blob/main/SCHEMA.md#status-vocabulary-per-type) owns; `../_shared/output-guide.md` §3 is clauDNA's rendered copy, terminal values included. Neither can be computed from the other, so frontmatter rolls the markers up: the skill that writes a marker updates `status:` in the same edit, at three points.

1. **Work starts** (the first `IN PROGRESS`): a `draft` plan becomes `active`. A type without `active` keeps its status until the work is done.
2. **Work is done** (every marker in the doc `✅ COMPLETE`, final PR merged): `completed`, if its type has it.
3. **The doc is archived:** a terminal status, picked by §6.

Every change to `status:` also sets `updated:` to the date. Three more rules:

- **A marker never goes in frontmatter.** `status: ✅ COMPLETE` isn't a valid value.
- **`PENDING` fits `draft` or `active`.** Approval isn't a marker: an approved plan can still be waiting to start.
- **Partly shipped work is `IN PROGRESS`**, however long the rest waits — never `PENDING`.

## 6. Archive Convention

Archive a session when it has at least one phase (§4), every phase is `✅ COMPLETE` and the final PR has merged, or when it was abandoned or replaced. Every skill that archives follows these steps, whether it moves a session directory or a standalone plan doc:

1. Move it with `git mv`, so its history follows. `git mv` doesn't create `documentation/archive/`, so make it first if it's missing:

   ```
   mkdir -p documentation/archive
   git mv documentation/planning/<category>/<session>/ documentation/archive/<session>/
   # or, for a standalone plan doc:
   git mv documentation/planning/<category>/<doc>.md documentation/archive/<doc>.md
   ```

2. Give every doc a terminal frontmatter `status:` from its type's terminal values (`../_shared/output-guide.md` §3). A doc with no frontmatter first gets the fields `../_shared/output-guide.md` §3 requires; a plan's `type:` is `plan`. Then take the first rule that fits:
   1. A doc that is already terminal keeps its status, such as a `ratified` decision or a `completed` review.
   2. `superseded` if another doc replaced it and its type has `superseded`; otherwise go on to rule 3. Either way, set `superseded_by:` to the replacement as a quoted wikilink, `"[[<its title>]]"`. Claudron's `SCHEMA.md` makes the field a wikilink, and YAML reads a bare `[[…]]` as a list.
   3. `completed` if its work shipped and its type has `completed`.
   4. `archived` otherwise: abandoned work, or a type with no `completed`.

   Where the status changes, set `updated:` to the date too (§5).
3. Update cross-references to the old path.

Commit all three steps together, so no commit leaves a broken link or a live status. Nothing under `documentation/archive/` keeps a live status, because the directory doesn't say a doc is done; its `status:` does.

`/claudna:build` archives in Step 8, and `/claudna:audit repo-health` archives abandoned sessions. `/claudna:session` handoff mode flags sessions due for archiving and archived docs whose `status:` is still live (§8).

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

# Find sessions due for archiving (§6): the session has at least one phase
# (§4), every phase carries ✅ COMPLETE, and nothing in it says PENDING or
# IN PROGRESS. A session with no phases (a retro, a decision) is never due.
# A new phase doc has no marker at all, so check each phase, not just the
# markers present: numbered docs without ✅ COMPLETE, then the types that say
# which numbered docs are phases
grep -rL "✅ COMPLETE" documentation/planning/ --include="[0-9][0-9]_*.md" --exclude="00_*"
grep -rn "^type:" documentation/planning/ --include="[0-9][0-9]_*.md"
grep -rnE "IN PROGRESS|PENDING" documentation/planning/ --include="*.md"

# Check for pending plans
grep -r "PENDING" documentation/planning/

# Find archived docs whose status is still live (§6): a status that isn't
# terminal for the doc's type (../_shared/output-guide.md §3), or none at all.
# -n shows the line, so frontmatter (the first lines) isn't confused with a
# `status:` line in a doc's body
grep -rnE "^(type|status):" documentation/archive/ --include="*.md"
grep -rL "^status:" documentation/archive/ --include="*.md"
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

1. **Env override**, by mode — not a precedence chain: engine present ⇒ `CLAUDRON_VAULT_PATH`; no engine ⇒ `SHARED_DOCS_PATH` (raw tree). User-managed; no clauDNA skill ever sets env vars.
   - `CLAUDRON_VAULT_PATH` is **Claudron's** name, owned by [its `documentation/specs/CLI_CONTRACT.md` §Environment](https://github.com/Claudfather/Claudron/blob/main/documentation/specs/CLI_CONTRACT.md#environment) — how the engine resolves a vault is not restated here or downstream; changing it is a PR against that repo.
   - **`CLAUDRON_VAULT` (no `_PATH`) was removed** in Claudron 0.3.0. Neither the engine nor clauDNA reads it; honoring it would resolve a different vault than the engine does. Tell users to rename it.
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
