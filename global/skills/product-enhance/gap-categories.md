# Gap Analysis Categories

Use these categories when surfacing findings in Step 3 (Intent vs. Implementation Gap Analysis).

| Category | Description |
|----------|-------------|
| **Missing capability** | User described a need that the code doesn't address at all |
| **Partial implementation** | Feature exists but is incomplete, limited, or fragile |
| **UX friction** | The feature works but the experience is rough (error handling, edge cases, confusing flows) |
| **Misalignment** | Code does something different from what the user intended |
| **Untapped potential** | The system has building blocks that could enable something valuable but don't yet |
| **Reliability gap** | The system works in the happy path but lacks resilience (no retries, no graceful degradation, missing validation) |

## Presentation Format

Present findings as a table:

```
Intent vs. Implementation
═══════════════════════════════════════════════════════════════════════════
  #   Category              Area              Finding
  1   Missing capability    User onboarding   No guided setup flow exists
  2   UX friction           Error handling    Errors return raw stack traces
  3   Untapped potential    Data export       CSV export exists, no API
  4   Partial impl          Search            Basic search, no filtering
═══════════════════════════════════════════════════════════════════════════
```

Ask the user: "Does this match your experience? Anything I missed or got wrong?"
