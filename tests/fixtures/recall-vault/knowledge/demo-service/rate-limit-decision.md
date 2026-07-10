---
title: Rate-limit the public API at 30 req/s
type: decision
status: ratified
maturity: current
created: 2026-05-02
updated: 2026-05-04
tags: [rate-limit, api, demo-service]
---

The public API caps at 30 req/s per key. Chosen over per-IP limiting because
keys map to billing accounts. Revisit if we add a burst tier.
