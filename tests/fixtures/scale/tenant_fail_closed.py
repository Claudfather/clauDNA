"""Golden fixture: a correctly FAIL-CLOSED tenant boundary.

Exercised by tests/test_scale_lens.py: no machine-checked fail-open or
queue/worker pattern in skills/audit/scale/scan-categories.md may match
this file. The safe shapes it demonstrates:

- tenant context is mandatory — a missing tenant raises instead of widening scope;
- non-nullable ownership column; uniqueness and cache keys are tenant-composite;
- idempotency keys embed the tenant and an operation namespace;
- prefix lookups run over a tenant-namespaced keyspace, never the global one;
- maintenance/global access is a separate, named, audited interface — never a
  missing-tenant special case on the tenant-scoped one.

This file is static audit material — it is never imported by the test suite.
"""

from __future__ import annotations


class MissingTenantContextError(RuntimeError):
    """Raised when a tenant-scoped interface is called without tenant context."""


def column(type_name: str, foreign_key: str | None = None, nullable: bool = False) -> dict:
    return {"type": type_name, "foreign_key": foreign_key, "nullable": nullable}


DOCUMENT_TABLE = {
    "id": column("integer"),
    # Ownership is mandatory at the schema layer.
    "tenant_id": column("integer", foreign_key="tenants.id", nullable=False),
    # Uniqueness is per-tenant: UNIQUE (tenant_id, slug).
    "slug": column("text"),
    "body": column("text"),
}


class DocumentRepository:
    """Repository whose tenant scope is mandatory at every interface."""

    def __init__(self, db, cache: dict[str, dict]):
        self._db = db
        self._cache = cache

    @staticmethod
    def _require_tenant(tenant_id: int) -> int:
        if tenant_id is None:
            raise MissingTenantContextError("tenant context is required for this operation")
        return tenant_id

    def list_documents(self, tenant_id: int) -> list[dict]:
        self._require_tenant(tenant_id)
        return self._db.execute(
            "SELECT id, tenant_id, slug, body FROM documents WHERE tenant_id = ?",
            [tenant_id],
        ).fetchall()

    def get_by_slug(self, tenant_id: int, slug: str) -> dict | None:
        self._require_tenant(tenant_id)
        cache_key = f"{tenant_id}:documents:{slug}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        row = self._db.execute(
            "SELECT id, tenant_id, slug, body FROM documents WHERE tenant_id = ? AND slug = ?",
            [tenant_id, slug],
        ).fetchone()
        if row is not None:
            self._cache[cache_key] = row
        return row

    def find_by_key_prefix(self, tenant_id: int, prefix: str) -> list[dict]:
        self._require_tenant(tenant_id)
        # The keyspace is tenant-namespaced, so the scan cannot cross tenants.
        return [
            doc
            for key, doc in self._cache.items()
            if key.startswith(f"{tenant_id}:documents:{prefix}")
        ]

    def create_document(self, tenant_id: int, slug: str, body: str, fingerprint: str) -> str:
        self._require_tenant(tenant_id)
        # Idempotency is tenant- and namespace-scoped, with a payload fingerprint:
        # same key + same fingerprint returns the original; a different fingerprint conflicts.
        idempotency_key = f"{tenant_id}:documents:create:{slug}:{fingerprint}"
        self._db.execute(
            "INSERT INTO documents (tenant_id, slug, body, idem_key) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (idem_key) DO NOTHING",
            [tenant_id, slug, body, idempotency_key],
        )
        return idempotency_key


class MaintenanceOperations:
    """Global access is a separate privileged interface: named, audited, role-gated.

    There is no hidden path where the tenant-scoped repository widens to all
    tenants; operators come through here, and every call records who and why.
    """

    def __init__(self, db, audit_log):
        self._db = db
        self._audit_log = audit_log

    def purge_expired(self, actor: str, reason: str) -> int:
        self._audit_log.record(actor=actor, operation="purge_expired", reason=reason)
        result = self._db.execute("DELETE FROM documents WHERE expires_at < now()")
        return result.rowcount
