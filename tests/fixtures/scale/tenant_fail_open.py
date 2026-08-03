"""Golden fixture: a FAIL-OPEN tenant boundary (every isolation seam is optional).

Exercised by tests/test_scale_lens.py: every machine-checked fail-open
pattern in skills/audit/scale/scan-categories.md must match this file.
The hazards are deliberate:

- optional tenant argument with a ``None`` default (scoping by convention);
- scoping applied only when the caller happens to pass a tenant;
- nullable tenant-ownership column and a globally-unique slug;
- global prefix lookup over an unscoped keyspace;
- maintenance/global access smuggled through an explicit ``tenant_id=None``.

This file is static audit material — it is never imported by the test suite.
"""

from __future__ import annotations


def column(type_name: str, foreign_key: str | None = None, nullable: bool = False) -> dict:
    return {"type": type_name, "foreign_key": foreign_key, "nullable": nullable}


DOCUMENT_TABLE = {
    "id": column("integer"),
    # HAZARD: ownership is optional at the schema layer.
    "tenant_id": column("integer", foreign_key="tenants.id", nullable=True),
    # HAZARD: uniqueness is global — UNIQUE (slug), not UNIQUE (tenant_id, slug).
    "slug": column("text"),
    "body": column("text"),
}


class DocumentRepository:
    """Repository whose tenant scope is optional at every interface."""

    def __init__(self, db, cache: dict[str, dict]):
        self._db = db
        # HAZARD: cache keys are bare slugs — cross-tenant by construction.
        self._cache = cache

    def list_documents(self, tenant_id: int | None = None) -> list[dict]:
        query = "SELECT id, tenant_id, slug, body FROM documents"
        params: list[object] = []
        # HAZARD: the filter exists only when the argument happens to be provided.
        if tenant_id is not None:
            query += " WHERE tenant_id = ?"
            params.append(tenant_id)
        return self._db.execute(query, params).fetchall()

    def get_by_slug(self, slug: str) -> dict | None:
        # HAZARD: slug is globally unique, so this read crosses tenants silently.
        cached = self._cache.get(slug)
        if cached is not None:
            return cached
        row = self._db.execute(
            "SELECT id, tenant_id, slug, body FROM documents WHERE slug = ?", [slug]
        ).fetchone()
        if row is not None:
            self._cache[slug] = row
        return row

    def find_by_key_prefix(self, prefix: str) -> list[dict]:
        # HAZARD: global prefix lookup over an unscoped keyspace.
        return [doc for key, doc in self._cache.items() if key.startswith(prefix)]

    def purge_expired(self) -> list[dict]:
        # HAZARD: the maintenance path gets global reach by omitting the tenant.
        return self.list_documents(tenant_id=None)
