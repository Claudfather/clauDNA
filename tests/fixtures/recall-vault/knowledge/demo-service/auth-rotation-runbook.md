---
title: Auth key rotation runbook
type: runbook
status: current
maturity: draft
created: 2026-06-20
updated: 2026-07-06
tags: [auth, rotation, demo-service]
---

Rotate the signing key quarterly. Stage the new key, dual-verify for one
deploy cycle, then retire the old key. Rollback = re-enable the retired key
(kept for 30 days).
