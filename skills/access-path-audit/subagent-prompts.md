# Subagent Prompt Templates

Reference material for the `/access-path-audit` skill. Detailed instructions for each subagent launched during the audit.

---

## Subagent A: Access Path Inventory

Launch a general-purpose subagent:

**Prompt:** "Discover every access path into this system's core logic. Create the directory and write your findings to `/tmp/access-path-audit-<YYYY-MM-DD_HHMMSS>/research/path-inventory.md` using the Write tool. Return a 2-4 line summary when done."

The subagent should:

1. **Identify every entry point** — HTTP routes/controllers, CLI commands, Slack/Discord bot handlers, MCP tool registrations, background workers/cron jobs, WebSocket handlers, GraphQL resolvers, SDK/library public API.
2. **For each access path, record:**
   - Transport type (HTTP, stdio, WebSocket, in-process, etc.)
   - Entry point file:line
   - Authentication mechanism (or "none" with justification)
   - What domain services/modules it calls
   - Whether it shares code with other paths or has its own implementation
3. **Map the domain core** — identify the shared services/modules that multiple paths call into. This is the system's "core" that all paths should ideally route through.
4. **Note any direct database access** from transport-layer code (routes, handlers) that bypasses domain services — these are architectural shortcuts.

**If the user specified a focus area**, prioritize depth there but still do a breadth scan of all paths.

**Research file format:**
```markdown
# Access Path Inventory

## Domain Core
[Shared services/modules that multiple paths call into]
[For each: module path, what it provides, which paths use it]

## Access Paths

### Path 1: [Name] ([Transport])
- **Entry point:** file:line
- **Auth:** [mechanism or "none — {reason}"]
- **Domain services called:** [list with file:line]
- **Shared code:** [what it shares with other paths]
- **Direct DB access:** [any SQL/ORM calls in transport code]
- **Notes:** [anything unusual]

### Path 2: [Name] ([Transport])
[same structure]

## Architectural Shortcuts
[Any transport-layer code that accesses DB/external services directly without going through domain services]
```

---

## Subagent B: Cross-Cutting Concern Mapping

Launch a general-purpose subagent:

**Prompt:** "Map how cross-cutting concerns are enforced across this system's access paths. Read the scan categories from `<skill-dir>/scan-categories.md` for the checklist. Write your findings to `/tmp/access-path-audit-<YYYY-MM-DD_HHMMSS>/research/concern-mapping.md` using the Write tool. Return a 2-4 line summary when done."

The subagent should:

1. **For each concern category (A through I) in scan-categories.md:**
   - Run the grep patterns to find enforcement points
   - Record WHERE each concern is enforced for each access path (specific file:line)
   - Note the LAYER: middleware, route/handler, domain service, or not enforced
   - Answer the "Questions per path" from the scan categories

2. **Build per-concern tables** showing enforcement across paths:
   ```
   | Concern: Input Validation | API | CLI | MCP | Slack | Workers |
   |---------------------------|-----|-----|-----|-------|---------|
   | Enforced?                 | Yes | No  | Partial | No | N/A |
   | Layer                     | Route (Pydantic) | — | Backend | — | — |
   | File:line                 | routes/search.py:45 | — | direct_backend.py:89 | — | — |
   ```

3. **Flag inconsistencies** where a domain-core concern is only enforced at the transport layer.

**Research file format:**
```markdown
# Cross-Cutting Concern Mapping

## A. Authentication
[Table + notes per path]
[Questions answered]

## B. Authorization
[Table + notes per path]

[... through I. Graceful Degradation]

## Inconsistency Summary
[List of concerns where enforcement is inconsistent across paths, with evidence]
```

---

## Subagent C: Convergence — Concern Placement Analysis

Launch a third general-purpose subagent after A and B complete:

**Prompt:** "Read the path inventory and concern mapping research files in `/tmp/access-path-audit-<YYYY-MM-DD_HHMMSS>/research/`. Also read the codebase directly to verify and deepen the findings. Build a concern placement analysis and write it to `/tmp/access-path-audit-<YYYY-MM-DD_HHMMSS>/research/convergence.md` using the Write tool. Return a summary of key findings (2-4 lines)."

The convergence subagent must perform three analyses:

### Analysis 1: Concern Placement Classification

For every concern identified in the mapping, classify it:

```markdown
## Concern Placement

| Concern | Current Layer(s) | Correct Layer | Status |
|---------|-----------------|---------------|--------|
| Auth    | Transport (all paths) | Transport | CORRECT |
| Input validation | Transport (API only) | Domain | MISPLACED — gaps in other paths |
| Error sanitize | Mixed | Domain | INCONSISTENT |
```

Status values:
- **CORRECT** — concern is at the right layer and consistent
- **MISPLACED** — concern is at the wrong layer (even if consistently applied)
- **INCONSISTENT** — concern is at different layers across paths
- **MISSING** — concern is not enforced anywhere
- **APPROPRIATE-DIFFERENCE** — paths correctly differ (transport-specific concern)

### Analysis 2: Operation Trace

Pick 1-2 representative operations (preferably one read and one write) and trace them through EVERY access path. For each step, note which cross-cutting concerns are applied:

```markdown
## Operation Trace: "search for entities"

### Via API
1. HTTP request → CORSMiddleware [headers] → AuthMiddleware [auth] → RateLimitMiddleware [rate limit]
2. → search route → Pydantic validation [input validation] → validate_enum_param [input validation]
3. → Explorer.search() [domain] → PostgreSQL query
4. → JSONResponse [serialization] → SecurityHeaders [headers]

### Via MCP (DirectBackend)
1. MCP protocol → AuthMiddleware (inherited) [auth] → RateLimitMiddleware (default bucket) [rate limit]
2. → search tool → backend.search() — NO validate_enum_param [GAP]
3. → Explorer.search() [domain] → PostgreSQL query
4. → String response [serialization]

### Via Slack
1. Slack event → SlackAuth [auth] → SlackRateLimiter [rate limit]
2. → ChatService.chat() → LLM tool call → search tool — NO validation [GAP]
3. → Explorer.search() [domain] → PostgreSQL query
4. → Slack message [serialization]
```

### Analysis 3: Shared vs. Duplicated Implementation

For each cross-cutting concern, identify:
- **Shared implementation:** one module, imported by all paths (good)
- **Parallel implementation:** different modules with same logic per path (maintenance risk)
- **Single-path implementation:** exists in one path only (gap if domain concern)

```markdown
## Shared Code Analysis

| Concern | Implementation | Paths Using It | Duplication Risk |
|---------|---------------|----------------|-----------------|
| Auth middleware | myapp/api/auth.py | API, MCP(HTTP) | None — transport-specific, correct |
| Admin check | routes/analytics.py:15, routes/api_keys.py:20 | API only | DUPLICATED — identical logic in 2 files |
| Error formatting | mcp/tools/common.py | MCP only | Not shared with API or Slack |
```

**Research file format:**
```markdown
# Convergence Analysis

## Concern Placement Classification
[Full table with status for each concern]

## Operation Traces
[1-2 operations traced through all paths]

## Shared Code Analysis
[Table of implementations and duplication]

## Key Findings
[Top 3-5 findings with category classification (A/B/C/D) and severity]
```
