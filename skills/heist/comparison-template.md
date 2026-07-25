# Comparison & Execution Templates

Templates for the deep-dive comparison subagent (Step 5) and the ADOPT / ENHANCE execution subagents (Step 6).

---

## Comparison Subagent Prompt

> You are comparing a foreign repo's [type: skill / config pattern / approach] against clauDNA's existing capabilities.
>
> **Foreign item:** Read the full source. If API mode, fetch via `gh api repos/<org>/<repo>/contents/<path>` or WebFetch on `https://raw.githubusercontent.com/<org>/<repo>/<branch>/<path>`. If local mode, read from `/tmp/heist-<timestamp>/repo/<path>`.
> Also read the scout's research file at `/tmp/heist-<timestamp>/research/<relevant-scout>.md` for additional context.
>
> **Our equivalent:** Read `skills/<similar-skill>/SKILL.md` in the clauDNA repo checkout
> [Or: "We have nothing similar — this is a potential adoption target."]
>
> **Write comparison to:** `/tmp/heist-<timestamp>/comparisons/<item-slug>.md` using the Write tool. (The Write tool creates parent directories automatically — do not use `mkdir`.)
> **Return only a 2-4 line summary** with your recommendation (ADOPT / ENHANCE / SKIP) and key reasoning.

### Comparison Report Format

```
# Comparison: [Item Name]

## Source
- Repo: org/repo
- File(s): [paths in foreign repo]

## What It Does
[2-3 sentence description of the foreign item]

## What We Have
[2-3 sentence description of our closest equivalent, or "Nothing similar"]

## Key Differences
[Bullet list — what theirs does that ours doesn't, and vice versa]

## Novel Elements Worth Taking
[Specific techniques or content worth adopting regardless of recommendation]

## Recommendation
ADOPT / ENHANCE / SKIP
[Reasoning — why this recommendation]

## If ADOPT — Suggested Outline
[Name, description, key sections for the new SKILL.md]

## If ENHANCE — Suggested Changes
[Which file to edit, what to add/change]

## Attribution
Source: https://github.com/org/repo — [specific file path]
```

---

## ADOPT Subagent Prompt

> Create a new clauDNA skill based on the comparison report.
>
> **Read:** `/tmp/heist-<timestamp>/comparisons/<item-slug>.md` for the full comparison.
> **Read:** The foreign source file(s). If API mode, fetch via `gh api` or WebFetch. If local mode, read from `/tmp/heist-<timestamp>/repo/<path>`.
> **Read:** 2-3 existing clauDNA skills from `skills/` in the repo to match conventions.
>
> **Write to:** `skills/<name>/SKILL.md` (new skill directory in the repo)
>
> **Follow these conventions:**
> - YAML frontmatter with `name`, `description` (starts with "Use when..."), `allowed-tools`
> - `argument-hint` if the skill takes arguments
> - Description is trigger-only — do NOT summarize the workflow
> - `## Procedure` with numbered steps
> - User gates between major phases
> - No shell operators in Bash commands (no `&&`, `|`, `;`)
> - Do NOT add an attribution comment to the file. Include the source repo + path in your return summary so the orchestrator can credit it in the commit message and CHANGELOG.
>
> **Critical:** Produce a self-contained skill. If the foreign skill references other skills from its repo, inline or remove those dependencies.
>
> Return the file path and a 2-line summary of what you created.

---

## ENHANCE Subagent Prompt

> Enhance an existing clauDNA skill based on the comparison report.
>
> **Read:** `/tmp/heist-<timestamp>/comparisons/<item-slug>.md` for the full comparison.
> **Read:** The existing skill at `skills/<name>/SKILL.md`.
> **Read:** The foreign source. If API mode, fetch via `gh api` or WebFetch. If local mode, read from `/tmp/heist-<timestamp>/repo/<path>`.
>
> **Edit:** `skills/<name>/SKILL.md` using the Edit tool.
>
> **Rules:**
> - Add specific improvements identified in the comparison — do not rewrite the whole skill
> - Preserve existing structure and conventions
> - Do NOT add an attribution comment. Note the source in your return summary so it can be credited in the commit message and CHANGELOG.
> - Do NOT remove existing content unless it's clearly superseded
>
> Return a summary of what you changed and why.
