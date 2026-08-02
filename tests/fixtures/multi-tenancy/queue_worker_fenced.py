"""Golden fixture: a correctly FENCED distributed queue/worker.

The negative control for the machine-checked queue/worker patterns in
skills/audit/multi-tenancy/scan-categories.md: this file implements the *fix*
for every hazard in queue_worker.py, so no pattern may match it — a heuristic
that fires here cannot tell the bug from its fix and would make the lens flag
healthy code. The safe shapes:

- claims issue a fresh lease token and re-admit only expired leases;
  finalization must present the matching token (a stale worker's write
  affects zero rows and is recorded, never silently accepted);
- idempotency keys embed the tenant and an operation namespace;
- an ambiguous provider outcome (timeout after send) holds the operation for
  reconciliation — there is no second call;
- the rate limiter is injected and backed by shared storage — one budget
  across all replicas, keyed per tenant;
- recovery polls are jittered so replicas spread their wake-ups instead of
  herding on the same tick after a shared outage.

This file is static audit material — it is never imported by the test suite.
"""

from __future__ import annotations

import random
import time
import uuid

CLAIM_SQL = (
    "UPDATE jobs SET status = 'processing', lease_token = %s, "
    "lease_expires_at = now() + interval '30 seconds' "
    "WHERE id = (SELECT id FROM jobs "
    "            WHERE status = 'ready' "
    "               OR (status = 'processing' AND lease_expires_at < now()) "
    "            ORDER BY enqueued_at LIMIT 1 FOR UPDATE SKIP LOCKED) "
    "RETURNING id, tenant_id, payload"
)

# Finalization is fenced: the WHERE clause demands the lease token this worker
# was issued at claim time, so a successor's re-claim invalidates our write.
FINALIZE_SQL = "UPDATE jobs SET status = 'done' WHERE id = %s AND lease_token = %s"


class FencedPublishWorker:
    """Worker whose finalization and external effects are lease-fenced."""

    def __init__(self, db, provider, operations, shared_limiter, poll_interval_seconds: float = 5.0):
        self._db = db
        self._provider = provider
        # Durable provider-operation records: ambiguity and stale-finalization
        # outcomes land here for reconciliation/operator review.
        self._operations = operations
        # Injected, backed by shared storage — one deployment-wide budget.
        self._limiter = shared_limiter
        self._poll_interval = poll_interval_seconds

    def run_once(self) -> bool:
        lease_token = str(uuid.uuid4())
        job = self._db.execute(CLAIM_SQL, [lease_token]).fetchone()
        if job is None:
            return False
        job_id, job_tenant, payload = job

        # Scoped to the owning tenant and the operation namespace.
        idempotency_key = f"tenant-{job_tenant}:publish:{job_id}"

        self._limiter.acquire(job_tenant)
        try:
            self._provider.publish(payload, idempotency_key)
        except TimeoutError:
            # The response was lost: the effect may or may not have landed.
            # Hold the operation as ambiguous for reconciliation — a second
            # call here could duplicate an externally visible effect.
            self._operations.mark_ambiguous(job_id, lease_token)
            return True

        rows = self._db.execute(FINALIZE_SQL, [job_id, lease_token]).rowcount
        if rows == 0:
            # Our lease expired while we worked and a successor re-claimed the
            # job — the fence rejected our finalization; record it and stop.
            self._operations.mark_stale_finalization(job_id, lease_token)
        return True

    def wait_for_work(self) -> None:
        # Jittered poll: replicas spread wake-ups instead of herding after a
        # shared outage ends.
        time.sleep(self._poll_interval * (0.5 + random.random()))
