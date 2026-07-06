# Repo Documentation Standard

**Date:** 2026-05-10
**Status:** Deprecated — superseded by `skills/_shared/documentation-standard.md`
**Enforced by:** `/init-project` scaffolding, skill output conventions

> **Deprecated (2026-07-06 docs audit).** This file and [`skills/_shared/documentation-standard.md`](../../skills/_shared/documentation-standard.md) described the same directory layout and had drifted apart — this copy still referenced the retired `/context-resume` skill (renamed to `/session-resume`) and was missing `/forge`, `/ironclad`, and `/publish` from its Skill Output Matrix. `skills/_shared/documentation-standard.md` is the copy skills actually read from at runtime, so it's now the single source of truth; this file's body has been removed to stop the drift. It is kept as a stub only because `skills/init-project/SKILL.md:125` links to it as "the full spec."

## Purpose

Define the standard documentation structure that clauDNA skills assume exists within repositories. This spec codifies that layout so `/init-project` can scaffold it and all skills interoperate without ad-hoc directory creation.

**See [`skills/_shared/documentation-standard.md`](../../skills/_shared/documentation-standard.md) for the full, current spec** — directory layout, planning output paths, session naming, status markers, archive convention, and the skill output matrix all live there now.
