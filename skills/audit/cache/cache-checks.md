# Cache Hygiene Checks — criteria & scoring

Detailed criteria for the six checks the `cache` lens runs (see `cache.md` for the procedure). Each check returns **PASS / WARN / FAIL**; all are read-only.

Prompt caching is a prefix match: static content at the front of the prompt is cached and reused, and any byte change earlier in the prefix invalidates the cache from that point on. Every token also ships on every call, cached or not. Each check targets one user-controllable invalidation or bloat factor. Findings carry the **performance** concern area (contract §3) — this lens does not mint its own.

---

## 1. Section ordering

**What:** Static content (project overview, architecture, conventions) should sit *before* dynamic content (current task state, "today's focus", changing checklists) in `CLAUDE.md`. A dynamic section near the top pushes the invalidation point earlier, throwing away the cache below it on every change.

**How:** Read `CLAUDE.md`. Classify each `##` section as static (rarely edited) or dynamic (edited within a session / per task). Find the first dynamic section and measure how much static content sits *after* it (count non-blank static lines; a later dynamic section doesn't count toward the static tally).

| Score | Criteria |
|---|---|
| PASS | No static section follows a dynamic one. |
| WARN | One dynamic section interleaved, < 30 lines of static content after it. |
| FAIL | Dynamic content near the top with ≥ 30 lines of static content after it (re-cached on every dynamic edit). |

## 2. CLAUDE.md size

**What:** Every token in `CLAUDE.md` ships on every API call. Large files cost tokens continuously even when cached.

**How:** `wc -l CLAUDE.md`; count tokens if available.

| Score | Criteria |
|---|---|
| PASS | ≤ 200 lines. |
| WARN | 201–350 lines — trim, or move detail to on-demand `.claude/` files. |
| FAIL | > 350 lines — material per-call token cost; factor aggressively. |

## 3. Auto-loaded growing files

**What:** Any file unconditionally pulled into every request — a lessons/notes log, an "append findings here" file, or a rules file without path scoping — adds variable content to the cached prefix and invalidates it whenever the file grows.

**How:** Look for instructions in `CLAUDE.md` or hooks that auto-load a growing file into context every turn. On-demand loading (read when relevant) is fine; unconditional per-turn loading is not. Score the *instruction*, not the file's current size — an unconditional-load directive is the invalidation risk whether or not the target file exists or is large yet.

| Score | Criteria |
|---|---|
| PASS | No growing file auto-loaded; read on demand only. |
| WARN | A small (< 50-line) file auto-loaded every turn. |
| FAIL | A growing log/notes file auto-loaded on every turn. |

## 4. Tool & model stability

**What:** Adding/removing tools or switching models mid-session invalidates the entire cache and rebuilds from scratch.

**How:** Look for instructions that switch model mid-task, or hooks/MCP config that add or remove tools partway through a session.

| Score | Criteria |
|---|---|
| PASS | Stable tool set and model across a session. |
| WARN | Conditional tool addition documented but rare. |
| FAIL | Instructions that routinely switch model or toolset mid-session. |

## 5. Mid-session edits

**What:** Editing `CLAUDE.md` during a session invalidates the cached prefix for the rest of that session.

**How:** Grep `CLAUDE.md` for language instructing continuous self-editing ("update this file as you go", "keep this section current", "append findings here").

| Score | Criteria |
|---|---|
| PASS | No mid-session self-edit instructions. |
| WARN | "Update continuously" language present but not load-bearing. |
| FAIL | Workflow depends on editing `CLAUDE.md` mid-session. |

## 6. Rules-file scoping

**What:** `.claude/rules/` files with `paths:` frontmatter load only for matching files; without it they load unconditionally, bloating every prompt.

**How:** For each file under `.claude/rules/`, confirm it has `paths:` frontmatter scoping it to relevant globs.

| Score | Criteria |
|---|---|
| PASS | All rules files have `paths:` scoping (or there are none). |
| WARN | A rules file lacks `paths:` but is small (< ~50 lines). |
| FAIL | A rules file ≥ ~50 lines loads unconditionally (no `paths:` scoping). |

---

## Scoring

Run all six, then present the combined findings (see `cache.md` § Step 3). For every WARN/FAIL give a one-line fix and the caching impact. **Diagnostic, not prescriptive** — some cache-unfriendly patterns are deliberate; note the trade-off rather than flagging blindly. If `CLAUDE.md` does not exist, report that and skip all checks.
