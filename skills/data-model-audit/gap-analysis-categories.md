# Gap Analysis Categories

Reference material for the `/data-model-audit` skill. These categories are used in Step 4 (Fit Analysis) to classify and rank findings, and in Step 5 to structure the report.

---

## Categories

| Category | What It Finds | Example |
|----------|--------------|---------|
| **Schema Gaps** | Code working around missing columns/tables/relationships | Manual joins in Python that should be FK relationships |
| **Schema Bloat** | Columns/tables with no code references | Legacy columns from removed features |
| **Structural Friction** | Overly complex queries caused by poor modeling | Aggregating across 4 joins for what should be a single lookup |
| **Missing Constraints** | Business rules enforced only in Python, not in DB | Uniqueness checks in code but no UNIQUE constraint |
| **Performance Anti-patterns** | N+1 queries, missing indexes on hot paths | API endpoint that lazy-loads related objects in a loop |
| **Model Drift** | Discrepancies between ORM models, migrations, and actual DB | Migration adds column that ORM model doesn't define |

---

## Severity Guidance

Rank findings by impact: **HIGH > MEDIUM > LOW**.

- **HIGH** — Active bugs, data integrity risks, or significant performance problems on hot paths
- **MEDIUM** — Friction that slows development or causes subtle issues, but isn't breaking
- **LOW** — Cleanup opportunities, dead schema elements, minor inconsistencies

---

## Finding Detail Template

Each finding in the report MUST include:

```markdown
### N. [Finding Title] — Impact: HIGH/MEDIUM/LOW
**Category:** [one of the six categories above]
**Evidence:**
- Code: `app/services/billing.py:45` manually constructs invoice line items
  by querying 3 tables and merging results in Python
- Schema: `invoices` table has no `line_items` relationship; `invoice_items`
  table exists but has no FK to `invoices`
**Recommendation:**
- Schema: Add FK from `invoice_items.invoice_id` to `invoices.id`,
  add SQLAlchemy `relationship()` on the Invoice model
- Code: Replace manual construction in billing.py with
  `invoice.items` relationship traversal
```

Each finding MUST include:
- **What:** the mismatch, in plain language
- **Evidence:** specific code paths (file:line) AND schema elements
- **Impact:** HIGH / MEDIUM / LOW
- **Recommendation:** coordinated changes to BOTH schema and code sides

---

## Report Structure

### Summary Table

```
Findings (ranked by impact)
═══════════════════════════════════════════════════════════════════════════════════
  #   Impact   Category              Finding
  1   HIGH     Schema Gap            [title]
  2   HIGH     Structural Friction   [title]
  3   MEDIUM   Missing Constraint    [title]
  4   MEDIUM   Performance           [title]
  5   LOW      Schema Bloat          [title]
═══════════════════════════════════════════════════════════════════════════════════
```

### Report Header

```
Data Model Audit: [Project Name]
═══════════════════════════════════════════════════════════════════════════════════

Scope
  Analyzed:           [files/modules/tables]
  Schema sources:     [ORM models, Alembic migrations, raw SQL]
  Entry points:       [N routes, M tasks, etc.]

Code-to-Schema Map
  [Table]             [Code paths that touch it]        [Read/Write]
  users               auth.py:45, api/users.py:23       R/W
  orders              api/orders.py:12, tasks/billing    R/W
  legacy_metrics      (none)                             -
```

### Report Footer

```
Summary
  Total findings:     X (Y high, Z medium, W low)
  Top recommendation: [single most impactful change, one sentence]
```
