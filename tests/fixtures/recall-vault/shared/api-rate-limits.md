---
title: API rate-limit patterns across the fleet
type: knowledge
status: current
maturity: current
created: 2026-04-10
updated: 2026-06-28
tags: [rate-limit, api, retry]
---

Most upstreams return `429` with a `Retry-After` header; honor it before
falling back to backoff. Token-bucket limiters smooth bursts better than
fixed windows. Batch endpoints exist for reads, rarely for writes.
