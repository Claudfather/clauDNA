---
title: Retry and backoff patterns
type: knowledge
status: current
maturity: draft
created: 2026-03-15
updated: 2026-06-01
tags: [retry, backoff, resilience]
---

Jittered exponential backoff avoids thundering-herd retries. Cap attempts;
distinguish retryable (429, 503, timeouts) from terminal (4xx) failures.
Idempotency keys make retries safe for writes.
