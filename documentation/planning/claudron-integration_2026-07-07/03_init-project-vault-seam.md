---
title: "[plan] P3: init-project provisions the vault seam — the consumer finally gets a producer"
type: plan
status: draft
owner: chris
created: 2026-07-07
updated: 2026-07-07
tags: [planning, claudron, init-project]
repos: clauDNA
links:
---

# P3 — init-project provisions the vault seam

Part of the Claudron-integration epic (`00_OVERVIEW.md`). Size: **M**. Gate: P1's
doctrine section merged (this phase provisions what that doctrine defines).

## Summary

`/claudna:remember` resolves its shared-docs root from `SHARED_DOCS_PATH` or a "Shared
Documentation" CLAUDE.md section (`remember:26`) — and nothing in clauDNA ever creates
either. This phase makes `/claudna:init-project` the producer: it provisions the
CLAUDE.md section (the project-native, plugin-writable door) with a parseable format
that distinguishes engine-managed roots from raw trees, handles the three detection
states (vault, claudron-no-vault, no-claudron), and opens the consolidated
"Claudron integration" SETUP_GUIDE section every later phase appends to.

## Evidence

- `skills/remember/SKILL.md:26` — the two resolution doors; `skills/init-project/SKILL.md`
  Steps 1–7 provision neither. Repo grep: consumers = `remember`, `index`; producers =
  none (since PR #4, 2026-05-11).
- CLAUDE.md rule: never write `~/.claude/settings.json` → the env var cannot be
  plugin-provisioned; the CLAUDE.md section is the only door init-project may create.
- **The seam-incoherence hazard (panel):** if the section points at an engine-managed
  vault, that tree has **no INDEX.md** (the engine owns vault indexing) — a fallback
  consumer INDEX-scanning it gets nothing and must not be told to run `/claudna:index`
  against it. The section format must carry the distinction.
- **The missing ladder branch (panel):** claudron installed + no vault initialized is
  the most likely first-run state; the remedy is `claudron init`, not install/upgrade
  and not a raw-tree scaffold.
- Residue: `documentation/specs/repo-documentation-standard.md` is a deprecated-in-place
  stub retained solely because `init-project/SKILL.md:125` links it (panel:
  precedent-check) — this phase already edits both sites.
- Claudron `02-session-loop.md` deliverable 5 — the 0.2.0 quickstart is
  `claudron init --personal` (guidance text confirms exact flags at the epic's 0.2.0
  re-confirmation checkpoint; "adopt" appears in their docs as validate-tier leniency,
  not a confirmed init flag).

## Implementation Plan

### Dependencies
P1's doctrine section (documentation-standard). No Claudron release (guidance text
only).

### Blocks
Every fresh-repo consumer of `/remember`; P5 reads the section annotation.

### Steps

1. **Section contract** in `skills/_shared/documentation-standard.md`: a CLAUDE.md
   section headed `## Shared Documentation`; first non-empty line = the root path
   (absolute or `~`-relative), optionally annotated `(claudron vault)` for
   engine-managed roots. Consumers parse exactly this. **Precedence rule:**
   `CLAUDRON_VAULT_PATH`/`SHARED_DOCS_PATH` env > section; on disagreement the env wins
   and the consumer notes the mismatch. **Annotation semantics:** a `(claudron vault)`
   root is engine-indexed — fallback consumers must not INDEX-scan it or suggest
   `/claudna:index`; their degraded message is "engine-managed root; install claudron
   or point the section at a raw tree."

   ```markdown
   ## Shared Documentation

   ~/vault  (claudron vault)
   Cross-project knowledge lives here — see /claudna:remember.
   ```

2. **New init-project Step 7.5 — "Shared knowledge seam."** Three-branch ladder:
   - **Vault resolvable** (`CLAUDRON_VAULT_PATH` set, or `claudron` on PATH and
     `claudron status --json` resolves) → write the section with the vault path +
     `(claudron vault)` annotation. Print-not-execute posture for anything mutating.
   - **claudron present, no vault** → print `claudron init --personal` guidance (exact
     flags re-confirmed at 0.2.0), offer to re-run detection after; never scaffold a
     raw tree that would shadow an about-to-exist vault.
   - **No claudron** → offer the minimal raw-tree scaffold
     (`shared/{knowledge/<repo>,planning/active,decisions}` + stub INDEX.md via
     `/claudna:index`) at a user-chosen path defaulting to a **stable absolute
     `~/shared`** (a cwd-relative sibling default fragments the store per parent
     directory — panel), then write the section (no annotation). Declining → skip with
     the SETUP_GUIDE pointer.
3. **Template update** — `references/CLAUDE_MD_TEMPLATE.md` gains the section as a
   commented optional block below the static boundary. Idempotency: re-run detects an
   existing section and offers update, never duplicates.
4. **Stub retirement** — delete `documentation/specs/repo-documentation-standard.md`;
   repoint `init-project/SKILL.md:125` at `skills/_shared/documentation-standard.md`
   (no-stub house pattern applied to our own residue).
5. **SETUP_GUIDE** — open the single consolidated **"Claudron integration"** section
   (seam, env override, precedence rule, claudron pointer); P4/P6/P7 append to it
   rather than scattering four insertion points.

## Test Plan

- Three-branch ladder exercised: vault present → annotated section; claudron-no-vault →
  init guidance, no scaffold; no claudron → `~/shared` scaffold + unannotated section.
- `/remember` immediately resolves the root in branches 1 and 3; in branch 1 with
  claudron subsequently removed, remember's degraded message names the engine-managed
  root (no `/index` suggestion).
- Re-run idempotency; env-vs-section disagreement → env wins with notice.
- `validate-skills.py` green; reference check green after the stub retirement.

## Verification Checklist

- [ ] Both resolution doors of `remember:26` have producers (env documented; section provisioned)
- [ ] Section format + precedence + annotation semantics specced in documentation-standard and honored by remember/index
- [ ] Raw-tree default is a stable absolute path; checklist wording allows exactly that one out-of-repo write
- [ ] `repo-documentation-standard.md` stub gone; no dangling references
- [ ] SETUP_GUIDE has one Claudron-integration section (opened here)

## What NOT To Do

- Don't run `claudron init`/`migrate` for the user — print the command.
- Don't set env vars or touch shell profiles or user settings.
- Don't scaffold a raw tree when claudron is installed but uninitialized — that
  branch's remedy is `claudron init`, not a shadow tree.
- Don't suggest `/claudna:index` against an annotated vault root — ever.

## Context

- Source skill: forge · Area: skills/init-project, skills/_shared/documentation-standard.md, documentation/specs/, SETUP_GUIDE.md · Effort: M · Risk: Low · Priority: High
- Dependencies: P1 (doctrine) · Blocks: P5 (annotation consumer), fresh-repo /remember
