# Retrieval-delta scenario — `claudron recall` → `/claudna:recall`

A worked example for the `/claudna:recall` orientation briefing (skills/recall/SKILL.md,
Step 2). The vault beside this file has two tiers:

- **Project tier** (`knowledge/demo-service/`) — membership, recency-sorted:
  `auth-rotation-runbook.md` (updated 2026-07-06) then `rate-limit-decision.md`
  (updated 2026-05-04).
- **Fleet tier** (`shared/`) — relevance-ranked when there is a query:
  `api-rate-limits.md`, `retry-backoff-patterns.md`.

Plus `CONVENTIONS.md`, always injected verbatim (uncapped).

## The delta: same vault, two leads

`claudron recall --json` returns one flat `notes` list; `score` is `null` on
project-tier entries and an integer on fleet-tier entries. `/recall` splits on
that signal and **leads adaptively**.

### Bare recall — leads with the project (recency)

`claudron recall` (cwd = demo-service, no query). Fleet tier stays index-only
(the project name is a weak relevance term), so the briefing leads with what is
fresh **here**:

```
## Vault conventions
<CONVENTIONS.md body>

### This project — most recent
- **Auth key rotation runbook** (runbook, draft) — Rotate the signing key quarterly… `knowledge/demo-service/auth-rotation-runbook.md`
- **Rate-limit the public API at 30 req/s** (decision, current) — The public API caps at 30 req/s per key… `knowledge/demo-service/rate-limit-decision.md`
```

### Queried recall — leads with the fleet (relevance)

`claudron recall --query "rate limit"`. Now the fleet tier scores, and the
briefing leads with **what the fleet knows about the topic**, project second:

```
## Vault conventions
<CONVENTIONS.md body>

### Fleet — most relevant to "rate limit"
- **API rate-limit patterns across the fleet** (knowledge, current) — Most upstreams return 429 with a Retry-After… `shared/api-rate-limits.md`

### This project — most recent
- **Rate-limit the public API at 30 req/s** (decision, current) — The public API caps at 30 req/s per key… `knowledge/demo-service/rate-limit-decision.md`
```

The delta is the **lead**: a bare recall orients you to this project's fresh
context; a queried recall orients you to the fleet's most relevant knowledge —
same vault, different door in.
