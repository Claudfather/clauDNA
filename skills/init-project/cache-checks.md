# Cache Audit Checks

Six checks to run. Score each PASS / WARN / FAIL.

---

### Check 1: CLAUDE.md Section Ordering

Read the project's `CLAUDE.md`. Identify each `##`-level section and classify it:

- **STATIC**: Content that does not change between sessions. Examples: workflow orchestration, core principles, task management, project overview (filled in once).
- **DYNAMIC**: Content that changes over time or varies per session. Examples: development workflow (project-specific commands), code style & conventions, commands reference, "things Claude should NOT do" (grows over time).

Check whether any STATIC section appears AFTER a DYNAMIC section. The ideal layout is all static sections first, then all dynamic sections last.

Also check for this HTML comment marker (its presence means the project is already optimized):
```
<!-- Static sections above, project-specific sections below. Keep this order for prompt cache efficiency. -->
```

**Scoring:**
- **PASS**: All static sections before all dynamic sections (or the cache-ordering comment is present)
- **WARN**: Minor ordering issue — e.g., a static footer after dynamic sections, or one static section mixed into the dynamic block
- **FAIL**: Multiple static sections appear after dynamic sections, indicating no awareness of cache-optimal ordering

---

### Check 2: CLAUDE.md Size

Count total lines in `CLAUDE.md`.

**Scoring:**
- **PASS**: 200 lines or fewer
- **WARN**: 201-350 lines (getting large — consider splitting project-specific details into `.claude/` files loaded on demand)
- **FAIL**: Over 350 lines (loaded into every API call — significant token cost)

If the file is large, identify the biggest sections by line count to help the user know where to trim.

---

### Check 3: Lessons File Isolation

Check whether `.claude/lessons.md` is being auto-loaded or referenced in a way that pulls it into every session:

1. Read `CLAUDE.md` and search for references to `.claude/lessons.md` or `lessons.md`
2. Check if `CLAUDE.md` contains instructions to "always read lessons at session start" or similar auto-load directives
3. Check if `.claude/settings.json` exists and references lessons in any auto-load configuration

The correct pattern: lessons files, where a project still has one, should be available on-demand but NOT auto-loaded into every session. Auto-loading adds variable content to the system prompt, which hurts caching.

**Scoring:**
- **PASS**: No auto-load references found. Lessons are on-demand only.
- **WARN**: CLAUDE.md mentions reviewing lessons but doesn't force auto-loading (e.g., "review lessons when relevant" — soft reference, acceptable)
- **FAIL**: Explicit auto-load instructions like "at session start, always read .claude/lessons.md" or Self-Improvement Loop says "Review lessons at session start" without qualifying it as optional

---

### Check 4: Tool & Model Stability

Scan `CLAUDE.md` and any `.claude/` configuration files for patterns that encourage mid-session tool or model changes:

- Instructions to add or remove MCP servers mid-session
- Instructions to switch models mid-session (e.g., "use Haiku for simple tasks, Opus for complex ones")
- Instructions to modify `settings.json` during a session
- References to dynamically loading or unloading tools

**Scoring:**
- **PASS**: No mid-session tool or model change patterns found
- **WARN**: Ambiguous references that could be interpreted as mid-session changes (e.g., "use the right model for the job" without clarifying this means across sessions, not within one)
- **FAIL**: Explicit instructions to switch models, add/remove tools, or modify settings mid-session

---

### Check 5: Mid-Session CLAUDE.md Edit Patterns

Scan `CLAUDE.md` for instructions that encourage editing CLAUDE.md during an active session:

- "Update CLAUDE.md after every task"
- "Add new patterns to CLAUDE.md as you discover them"
- "Keep CLAUDE.md current during work"

The correct pattern: update CLAUDE.md at session boundaries (during `/claudna:session handoff`), not mid-session. Mid-session edits invalidate the cached system prompt.

In older projects that still carry a Self-Improvement Loop section, treat its "Update CLAUDE.md" instruction as a cache-busting pattern (current clauDNA templates ship no such section).

**Scoring:**
- **PASS**: No mid-session CLAUDE.md edit instructions found, or edits are explicitly deferred to session boundaries
- **WARN**: General "update this file continuously" language without specifying when (ambiguous but common — the default template has this)
- **FAIL**: Explicit mid-session edit instructions like "after every task, update CLAUDE.md"

---

### Check 6: Rules File Configuration

Scan `.claude/rules/` directory (if it exists) for configuration issues:

1. Check each `.md` file for YAML frontmatter with `paths:` field
2. Flag files using `globs:` instead of `paths:` (wrong field name — may not be recognized, causing the rule to load every session)
3. Flag files with no `paths:` frontmatter (these load every session, same cost as CLAUDE.md)
4. Count total lines across all rules files without `paths:` — these add to base context cost

If no `.claude/rules/` directory exists, mark as PASS and move on.

**Scoring:**
- **PASS**: No rules directory, or all rules files have `paths:` frontmatter
- **WARN**: Rules files exist without `paths:` (loading every session — intentional?)
- **FAIL**: Rules files use `globs:` instead of `paths:` (likely a misconfiguration)
