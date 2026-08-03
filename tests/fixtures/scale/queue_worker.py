"""Golden fixture: a distributed queue/worker with cross-process failure windows.

Exercised by tests/test_scale_lens.py: every machine-checked
queue/worker pattern in skills/audit/scale/scan-categories.md must
match this file. The hazards are deliberate, one per failure-window class
(skills/audit/scale/failure-windows.md):

- idempotency key derived from the job id alone — not tenant/namespace scoped
  (window 1: replay across tenants can collide or falsely deduplicate);
- claim query that re-admits rows already in ``processing`` once their
  ``claimed_at`` is stale, with no fencing token (window 4: a paused worker
  and its successor both own the job);
- finalization keyed on the job id alone — a stale worker that lost its lease
  can still mark the job done (window 4);
- blind retry of an externally visible publish after an ambiguous timeout
  (window 6: the effect may have happened twice);
- process-local rate limiter guarding a shared provider budget — the budget
  multiplies with every added replica (window 10 / scan category E);
- fixed, unjittered poll interval — after a shared outage every replica wakes
  and retries on the same tick (window 12: post-recovery retry herd).

This file is static audit material — it is never imported by the test suite.
"""

from __future__ import annotations

import time

LEASE_SECONDS = 30
POLL_INTERVAL_SECONDS = 5

# HAZARD: 'processing' rows become claimable again on staleness alone; the new
# claim carries no fencing token the original holder would fail to present.
CLAIM_SQL = (
    "UPDATE jobs SET status = 'processing', claimed_at = now() "
    "WHERE id = (SELECT id FROM jobs "
    "            WHERE status IN ('ready', 'processing') "
    "              AND (claimed_at IS NULL OR claimed_at < now() - interval '30 seconds') "
    "            ORDER BY enqueued_at LIMIT 1 FOR UPDATE SKIP LOCKED) "
    "RETURNING id, tenant_id, payload"
)

# HAZARD: finalization is keyed on id alone — no lease/fencing token in the
# WHERE clause, so a stale worker that lost its lease can still finalize.
FINALIZE_SQL = "UPDATE jobs SET status = 'done' WHERE id = %s"


class InMemoryRateLimiter:
    """HAZARD: process-local limiter — the 'global' budget multiplies per replica."""

    def __init__(self, limit_per_minute: int):
        self._limit = limit_per_minute
        self._window: list[float] = []

    def acquire(self) -> None:
        now = time.monotonic()
        self._window = [t for t in self._window if now - t < 60.0]
        while len(self._window) >= self._limit:
            time.sleep(0.05)
            now = time.monotonic()
            self._window = [t for t in self._window if now - t < 60.0]
        self._window.append(now)


class PublishWorker:
    """Worker loop that claims jobs and performs an externally visible publish."""

    def __init__(self, db, provider):
        self._db = db
        self._provider = provider
        self._limiter = InMemoryRateLimiter(limit_per_minute=60)

    def run_once(self) -> bool:
        job = self._db.execute(CLAIM_SQL).fetchone()
        if job is None:
            return False
        job_id, _tenant_id, payload = job

        # HAZARD: the dedup key ignores which tenant (and which provider
        # account) the effect belongs to.
        idempotency_key = f"job-{job_id}"

        self._limiter.acquire()
        try:
            self._provider.publish(payload, idempotency_key)
        except TimeoutError:
            self._provider.publish(payload, idempotency_key)  # HAZARD: blind retry — the first send may have landed

        self._db.execute(FINALIZE_SQL, [job_id])
        return True

    def run_forever(self) -> None:
        while True:
            if not self.run_once():
                # HAZARD: every replica sleeps the same fixed interval, so after a
                # shared outage they all wake — and retry — on the same tick.
                time.sleep(POLL_INTERVAL_SECONDS)
