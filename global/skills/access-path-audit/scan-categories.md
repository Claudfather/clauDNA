# Scan Categories

Systematic checklist of cross-cutting concerns to evaluate across access paths. For each concern, the subagent should determine: (1) is it enforced, (2) where (which layer), and (3) is that the correct layer.

Do NOT read CLAUDE.md or MEMORY.md directly — Claude already has both in its system prompt.

---

## Correct Layer Guidance

Each concern has a "correct layer" — where it should ideally be enforced. This is the key distinction the audit makes:

**Transport layer** (edge/adapter — correctly varies per path):
- Authentication (JWT, API key, OAuth, Slack tokens)
- Rate limiting (per-IP, per-key, per-user quotas)
- Request/response serialization (JSON, protobuf, CLI args)
- Protocol headers (CORS, CSP, HSTS)
- Connection management (keep-alive, timeouts, retries)

**Domain core** (shared services — must be consistent):
- Input validation (length limits, format checks, enum validation)
- Business rule enforcement (ownership, permissions beyond "is authenticated")
- Error sanitization (never leak internals regardless of path)
- Audit logging of domain events (who did what, when)
- Data integrity constraints (uniqueness, referential integrity)

**Either layer** (defense-in-depth — transport for fast-fail, domain for correctness):
- Authorization (coarse-grained at transport, fine-grained in domain)
- Input sanitization (SQL injection, XSS — transport rejects, domain validates)

---

## A. Authentication

**What to check:** How each access path verifies caller identity.

**Grep patterns:**
- Middleware: `middleware|@before_request|authenticate|verify_token|auth_required`
- JWT: `jwt\.decode|verify_jwt|Bearer|authorization.*header`
- API keys: `api.key|x-api-key|apikey|api_key_header`
- Session: `session_id|cookie.*session|express-session`
- OAuth: `oauth|google.*auth|sign_in_with`

**Questions per path:**
- Is auth enforced? By what mechanism?
- Is it fail-closed (reject by default) or fail-open (allow by default)?
- Are there bypass conditions (dev mode, health checks)?
- Is the auth mechanism appropriate for this transport? (e.g., CLI = none is fine)

**Correct layer:** Transport. Each path authenticates differently based on its transport.

---

## B. Authorization

**What to check:** How the system decides what an authenticated caller can do.

**Grep patterns:**
- Role checks: `require_admin|is_admin|has_role|has_permission|@authorize|@roles`
- Ownership: `owner_id|user_id.*==|created_by|verify_ownership`
- Scoping: `filter.*user_id|where.*owner|scope.*current_user`

**Questions per path:**
- Is there authorization beyond "is authenticated"?
- Are admin checks consistent across paths?
- Can one path access resources that another path restricts?
- Is resource ownership enforced in the domain (shared) or per-route (fragile)?

**Correct layer:** Hybrid. Coarse-grained (is admin?) at transport. Fine-grained (owns this resource?) in domain.

---

## C. Rate Limiting

**What to check:** How each path throttles requests.

**Grep patterns:**
- Libraries: `ratelimit|slowapi|express-rate-limit|throttle|limiter|bucket`
- Custom: `rate_limit|requests_per|max_requests|too_many_requests|429`
- Per-operation: different limits for different operations (read vs. write, search vs. query)

**Questions per path:**
- Is rate limiting applied? At what granularity (per-IP, per-user, per-key)?
- Do equivalent operations have equivalent limits across paths?
- Can a rate limit on one path be bypassed by using another path for the same operation?
- Is the rate limit state shared across paths or independent?

**Correct layer:** Transport. But equivalent operations should have roughly equivalent limits regardless of path.

---

## D. Input Validation

**What to check:** Where inputs are validated for format, length, type, and allowed values.

**Grep patterns:**
- Pydantic/schema: `BaseModel|@validates|Schema|Joi\.|zod\.|validator`
- Manual: `max_length|min_length|len\(.*>|\.strip\(\)|validate_|is_valid`
- Enum validation: `Enum|choices|allowed_values|in \[`
- Format: `regex|pattern|email.*valid|url.*valid|fqn.*valid`

**Questions per path:**
- Does each path validate the same inputs the same way?
- Is validation in the transport adapter (route/handler) or domain service?
- If validation is only in the transport adapter, can another path bypass it?
- Are there domain-level validation functions that all paths should be calling?

**Correct layer:** Domain core (authoritative validation). Transport can fast-fail on obvious issues.

**This is the most common source of genuine gaps.** When validation lives only in API route Pydantic models, every other path (CLI, Slack, MCP direct) bypasses it.

---

## E. Error Handling & Sanitization

**What to check:** How errors are caught, logged, and reported back to callers.

**Grep patterns:**
- Global handlers: `exception_handler|@app\.errorhandler|unhandled.*exception|error.*middleware`
- Error responses: `str\(exc\)|str\(e\)|error.*detail|traceback|stack.*trace`
- Sanitization: `generic.*error|internal.*server|sanitize.*error`
- Domain exceptions: `class.*Error.*Exception|raise.*Error|custom.*exception`

**Questions per path:**
- Do unhandled exceptions leak implementation details (stack traces, DB errors, file paths)?
- Is there a consistent domain exception hierarchy that all paths translate from?
- Does each path have a catch-all that prevents raw exceptions from reaching callers?
- Are error messages consistent across paths for the same domain error?

**Correct layer:** Domain core for exception types and sanitization. Transport layer for HTTP status codes, Slack formatting, etc.

---

## F. Logging & Audit Trail

**What to check:** What gets logged, where, and whether domain events are tracked consistently.

**Grep patterns:**
- Loggers: `logging\.getLogger|logger\s*=|console\.log|log\.(info|warn|error|debug)`
- Missing loggers: route/handler files that import their framework but NOT a logger
- Audit: `audit|record.*call|track.*usage|activity.*log|event.*log`
- Request logging: `request.*log|access.*log|middleware.*log`

**Questions per path:**
- Does every route/handler module have a logger configured?
- Are domain events (user action, data mutation, query execution) logged consistently regardless of which path triggered them?
- Is there request-level logging (who, what, when, response status)?
- Can you reconstruct "who did what" across all paths from the logs?

**Correct layer:** Domain core for domain event logging. Transport for request-level access logs.

---

## G. Security Headers & Transport Security

**What to check:** HTTP-specific protections applied to responses.

**Grep patterns:**
- Headers: `X-Content-Type|X-Frame-Options|Content-Security-Policy|Strict-Transport|Referrer-Policy|Permissions-Policy`
- CORS: `CORS|Access-Control|allowed_origins|allow_origin`
- TLS: `https|ssl|tls|certificate|verify=False|rejectUnauthorized`

**Questions per path:**
- Are security headers applied to ALL HTTP responses (including mounted sub-apps, error responses)?
- Is CORS configuration appropriate (not wildcard in production)?
- Do non-HTTP paths need equivalent protections? (Usually no — this is transport-specific.)

**Correct layer:** Transport only. Non-HTTP paths (CLI, stdio MCP) don't need these.

---

## H. Shared Code vs. Duplication

**What to check:** Whether cross-cutting implementations are shared or copy-pasted.

**Grep patterns:**
- Duplicate function signatures across different modules
- Identical logic blocks in different files (auth checks, validation, error handling)
- Helper functions that exist in one path but are re-implemented in another

**Questions:**
- Are shared concerns extracted to a common module?
- When the same check exists in multiple places, are they truly identical or have they drifted?
- If a concern needs to change, how many files must be edited?

**This category produces Category D (Duplication Risk) findings.**

---

## I. Graceful Degradation

**What to check:** How each path handles downstream failures (DB down, external service timeout, cache miss).

**Grep patterns:**
- Timeouts: `timeout|connect_timeout|read_timeout|deadline`
- Retries: `retry|backoff|tenacity|max_retries`
- Circuit breakers: `circuit.*break|fallback|degrade`
- Health checks: `health|readiness|liveness|ping`

**Questions per path:**
- If the database is down, does each path fail gracefully or crash?
- Are timeout values consistent for equivalent operations across paths?
- Do any paths have retry logic that others lack for the same operation?

**Correct layer:** Domain core for retry/fallback logic. Transport for timeout values and connection management.
