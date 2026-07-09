---
name: init-project
user-invocable: true
description: "Use when setting up a new project or adding standard Claude Code configuration (CLAUDE.md, CHANGELOG.md, .claude/, documentation/) to an existing project."
allowed-tools: Read(*), Write(*), Edit(*), Glob(*), Grep(*), Bash(git *), Bash(ls *), Bash(mkdir *), Bash(printenv *), Bash(command -v *), Bash(claudron status *)
---

# Initialize Project

Set up a project with standard clauDNA configuration: `CLAUDE.md`, `CHANGELOG.md`, `.claude/lessons.md`, `PROJECT_MISSION.md`, the `documentation/` planning structure, and the shared-docs seam (a `## Shared Documentation` section in CLAUDE.md — Step 7.5). Works for both new repos and existing projects that lack these files.

## Procedure

Follow these steps exactly in order.

### Step 1: Assess Current State

Scan the project root for existing configuration:

- `CLAUDE.md` — project instructions for Claude Code
- `CHANGELOG.md` — structured change history
- `.claude/lessons.md` — project-specific lessons
- `PROJECT_MISSION.md` — project mission statement
- `documentation/planning/` — planning structure for skills
- CLAUDE.md `## Shared Documentation` section — the shared-docs seam (Step 7.5)

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

  CLAUDE.md:            ✓ exists / ✗ missing
  CHANGELOG.md:         ✓ exists / ✗ missing
  .claude/lessons.md:   ✓ exists / ✗ missing
  PROJECT_MISSION.md:   ✓ exists / ✗ missing
  documentation/:       ✓ exists / ✗ missing
  Shared docs seam:     ✓ declared (<root path>) / ✗ not declared
═══════════════════════════════════════════════════════
```

If everything already exists, tell the user and ask if they want to align any of it to the clauDNA template. If none exist, proceed to Step 2. If some exist, note which will be created vs. skipped.

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
- Remove placeholder comments (`<!-- Customize -->`) after filling in — but leave the commented `## Shared Documentation` block alone; Step 7.5 owns it

**For large projects** (200+ lines after customization): Consider creating `.claude/rules/` files with `paths:` frontmatter to scope domain-specific rules to matching files. Keep CLAUDE.md under 200 lines — only universal rules and safety constraints.

**Cache efficiency guidelines** (these affect prompt cache hit rates across every API call). For detailed scoring criteria (PASS/WARN/FAIL for each check), see [cache-checks.md](cache-checks.md) in this skill directory.
- Static sections first, dynamic sections last. Add `<!-- Static sections above, project-specific sections below. Keep this order for prompt cache efficiency. -->` at the boundary.
- Keep CLAUDE.md under 200 lines (WARN). Over 350 lines is a FAIL — significant token cost per call.
- Don't auto-load `.claude/lessons.md` — keep lessons on-demand via `/claudna:lessons`.
- Don't add instructions to edit CLAUDE.md mid-session — defer edits to session boundaries (`/claudna:session handoff`).
- Don't add instructions to switch models or tools mid-session — both invalidate the entire prompt cache.
- If using `.claude/rules/`, ensure each file has `paths:` frontmatter (not `globs:`) to scope when each rule loads.

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

### Step 6: Create PROJECT_MISSION.md

If `PROJECT_MISSION.md` doesn't exist, create it. Use the project name and description from Step 2:

```markdown
# [Project Name] — Mission

[One-paragraph mission statement: what this project does, who it's for, what success looks like.]
```

If the user provided a clear description in Step 2, write a real mission statement. If not, create the stub and note that `/claudna:product-vision` will flesh it out. This file anchors `/claudna:product-vision` ideation and gives all skills a shared understanding of the project's purpose.

### Step 7: Scaffold documentation/

If `documentation/planning/` doesn't exist, create the standard planning structure. This is the shared directory layout that planning and audit skills write to (see `skills/_shared/documentation-standard.md` for the full spec).

Create these directories with `.gitkeep` files:

```
documentation/
├── planning/
│   ├── phases/.gitkeep
│   ├── tech_debt/.gitkeep
│   ├── security/.gitkeep
│   ├── access-paths/.gitkeep
│   ├── product-vision/.gitkeep
│   └── investigations/.gitkeep
├── decisions/.gitkeep
├── specs/.gitkeep
├── guides/.gitkeep
└── archive/.gitkeep
```

If `documentation/` already exists, scan for missing subdirectories and create only what's missing.

**Directory purposes:**
- `planning/` — skill output from `/claudna:audit tech-debt`, `/claudna:audit security`, `/claudna:product-enhance`, `/claudna:product-vision`. Session subdirectories created at runtime.
- `decisions/` — Architecture Decision Records (ADRs). Why we chose X over Y. Permanent, not archived.
- `specs/` — Technical specifications, API contracts, data schemas. Living docs.
- `guides/` — Setup guides, onboarding, runbooks. Living docs.
- `archive/` — Completed planning sessions moved here after all phases merge.

### Step 7.5: Shared Knowledge Seam

Provision the `## Shared Documentation` CLAUDE.md section — the root that `/claudna:remember` and `/claudna:index` resolve. The section format, `(claudron vault)` annotation semantics, and env-over-section precedence are contract-bound in `skills/_shared/documentation-standard.md` §10 — write exactly that format.

**Idempotency first.** If CLAUDE.md already has a `## Shared Documentation` section, show it and offer to update it by re-running the detection below — never write a second section. (The CLAUDE.md template ships the section as a commented placeholder — treat that as absent, and replace the commented block with the real section when writing.)

Detect which of three states applies, in order:

**(a) Vault resolvable.** `CLAUDRON_VAULT_PATH` is set (check with `printenv CLAUDRON_VAULT_PATH`), or `claudron` is on PATH (`command -v claudron`) and `claudron status --json` reports a vault path. Write the section with the resolved path (prefer the `~`-relative form when it's under the home directory) and the `(claudron vault)` annotation:

```markdown
## Shared Documentation

~/vault  (claudron vault)
Cross-project knowledge lives here — see /claudna:remember.
```

Detection is read-only (`claudron status` is safe to run). **Print-not-execute for anything mutating:** never run `claudron init`, `claudron migrate`, or any other writing claudron command — show the command and let the user run it.

**(b) claudron present, no vault.** `claudron` is on PATH but no vault resolves (no env var, and `claudron status --json` errors or reports no vault). Print the remedy — do not run it, and do **not** scaffold a raw tree (it would shadow the vault the user is about to create):

```
claudron is installed but no vault is initialized. Run:

  claudron init --personal

then re-invoke /claudna:init-project — Step 7.5 will detect the vault and
write the CLAUDE.md section.
```

(If `claudron init --personal` is rejected, the flags have moved — `claudron --help` shows the current form.) Offer to re-run this step's detection once the user has initialized.

**(c) No claudron.** Offer the minimal raw-tree scaffold. Ask where the shared root should live, defaulting to the **stable absolute `~/shared`** — never a cwd-relative sibling like `../shared`, which fragments the store per parent directory. On yes:

1. Create `<root>/knowledge/<repo-name>/`, `<root>/planning/active/`, and `<root>/decisions/` (`mkdir -p`).
2. Invoke `/claudna:index <root> --recursive` to write the stub INDEX.md files — index is the sole INDEX.md writer; don't write them by hand.
3. Write the section into CLAUDE.md with the path only, **no annotation** (raw trees are INDEX-discovered):

```markdown
## Shared Documentation

~/shared
Cross-project knowledge lives here — see /claudna:remember.
```

The scaffold is the only write this skill makes outside the project, and only at the path the user chose. If the user declines, skip the seam entirely and point at SETUP_GUIDE's "Claudron Integration" section for setting it up later.

### Step 8: Verify & Confirm

Show the user what was created:

```
Project Initialized
═══════════════════════════════════════════════════════
  Created:
    ✓ CLAUDE.md              (N lines — project instructions)
    ✓ CHANGELOG.md           (N lines — change history)
    ✓ .claude/lessons.md     (N lines — lessons)
    ✓ PROJECT_MISSION.md     (N lines — mission statement)
    ✓ documentation/         (10 directories: planning, decisions, specs, guides, archive)
    ✓ Shared docs seam       (## Shared Documentation → ~/shared; raw tree scaffolded)

  Skipped:
    - CLAUDE.md (already exists)
═══════════════════════════════════════════════════════
```

Report the seam line as whichever Step 7.5 branch ran: the annotated vault section, the raw-tree scaffold + section, printed `claudron init` guidance (nothing written), or skipped.

Ask: **"Want me to commit these files?"**

If yes, stage only the created/modified files and commit with:
```
docs: initialize project configuration (CLAUDE.md, CHANGELOG.md, .claude/, documentation/)
```

A Step 7.5 raw-tree scaffold lives outside the repo — never stage it; only the CLAUDE.md section ships with the commit.

---

## Rules

- **Never overwrite existing files without asking.** If `CLAUDE.md` already exists, ask before replacing or merging.
- **Infer before asking.** Read the codebase first. Ask the user to confirm/correct, not to describe from scratch.
- **Keep static sections intact and ordered first.** The Workflow Orchestration, Core Principles, Self-Improvement Loop, and Task Management sections are universal clauDNA conventions. They must appear before project-specific dynamic sections for cache efficiency.
- **Architecture must be real.** Scan the actual directory tree. Don't write a placeholder tree structure.
- **CHANGELOG must reflect real history.** Use `git log` and `git tag`. Don't invent entries.

---

## Optional: Notification Setup (macOS)

During Step 8, if the user is on macOS, mention notification options:

**iTerm2 (recommended):** Profiles → Terminal → check "Send notification when idle" (set idle time to ~5 seconds). iTerm2 will alert when any terminal tab is waiting for input.

**Hook-based:** The clauDNA plugin ships a notification hook in `plugin-hooks/hooks.json` that fires a macOS notification when Claude needs input. It activates automatically when the plugin is enabled.

**Manual trigger:** `osascript -e 'display notification "Message" with title "Claude Code"'`

**iTerm2 tab management tips:**
- Right-click tab → "Edit Tab Title" to name Claude sessions
- Right-click tab → "Tab Color" to color-code worktrees/tasks
- Profiles → General → Badge → `\(session.path)` for directory badges

This is informational context — do not block initialization on notification setup.
