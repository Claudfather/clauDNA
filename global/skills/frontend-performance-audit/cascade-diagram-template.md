# Cascade Diagram & Findings Template — Frontend Performance Audit

Reference templates for Phase 3 output. Present these after all scans complete.

---

## Findings Table

```
Performance Audit Findings
═══════════════════════════════════════════════════════════════════════════════════
  #   Severity   Category            Finding                           Location
  1   CRITICAL   Render cascade      selection object recreated        page-client.tsx:37
  2   CRITICAL   Render cascade      useEffect depends on object ref   panel.tsx:103
  3   HIGH       Observer overhead   11 IntersectionObserver thresholds scroll-spy.ts:53
  4   HIGH       State management    URL sync triggers parent re-render panel.tsx:337
  5   MEDIUM     Memoization gap     SectionNav missing React.memo()   section-nav.tsx:19
  6   MEDIUM     Fetch patterns      No client-side caching            api.ts:84
  7   LOW        Bundle              Component file >1000 lines        panel.tsx
═══════════════════════════════════════════════════════════════════════════════════
```

## Cascade Diagram

**Always include this** — it is the most valuable artifact of the audit.

```
Render Cascade (root cause → symptom)
═══════════════════════════════════════════════════════════════════════════════════
  1. Page loads → ExplainPanel mounts → useEffect fetches data
  2. Context loads → sections render → ScrollSpy detects "overview"
  3. ScrollSpy fires onSectionChangeExternal
  4. handleSectionChange calls router.replace("?section=overview")
  5. URL changes → useSearchParams() re-renders ExplainPageClient
  6. New selection object created (same values, new reference)         ← ROOT CAUSE
  7. useEffect([selection]) fires again → re-fetches everything
  8. Loading skeleton → data → sections → ScrollSpy → GOTO 3          ← LOOP
═══════════════════════════════════════════════════════════════════════════════════
```

## Severity Definitions

- **CRITICAL** — Causes visible user-facing symptoms (flickering, multiple reloads, data loss). Fix first.
- **HIGH** — Amplifies other issues or causes measurable performance degradation. Fix to prevent recurrence.
- **MEDIUM** — Unnecessary work that doesn't cause visible symptoms yet but will at scale. Fix for quality.
- **LOW** — Best practice violations, minor inefficiencies. Fix opportunistically.
