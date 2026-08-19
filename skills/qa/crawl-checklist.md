# Visual Crawl Checklist

Reference material for the `qa` skill's **Crawl mode** (`qa/SKILL.md`). Apply these checks to every discovered route. Findings are classified by category and priority. Pairs with `deep-crawl.md` (the automation engine that exercises these checks) and `design-token-rules.md` (token comparison).

## Per-Route Checks

### 1. Render Verification
- Page loads without blank screen (content visible within 5s)
- No perpetual loading spinner or skeleton
- No "hydration mismatch" console errors (SSR/CSR desync)
- No flash of unstyled content (FOUC)
- No layout shift after load (cumulative layout shift)

### 2. Console Health
- Zero `console.error` calls
- Zero unhandled promise rejections
- Zero `TypeError` / `ReferenceError` exceptions
- Warnings noted but not flagged as errors
- Network request failures (4xx/5xx in fetch/XHR)

### 3. Link Integrity
- All `<a href>` targets return 2xx or 3xx
- No `href="#"` with click handlers (accessibility antipattern)
- No `javascript:void(0)` hrefs
- External links have `rel="noopener"` (security)
- No links pointing to localhost/staging in production

### 4. Interaction Health
- All visible buttons respond to click (no dead buttons)
- Dropdowns/selects open and display options
- Form inputs accept text entry
- Modals open and close cleanly
- Navigation links actually navigate

### 5. Responsive Integrity
- No horizontal scrollbar at any viewport
- Text readable without zooming on mobile (>= 16px body)
- Touch targets >= 44px on mobile
- Images don't overflow container
- Navigation collapses appropriately on mobile
- No content clipped or hidden unintentionally

### 6. Empty States
- Pages with no data show a designed empty state (not blank or raw error)
- Empty states include a helpful message and primary action
- Tables/lists with no rows show placeholder, not broken layout

### 7. Accessibility Baseline
- `focus-visible` ring on interactive elements (never `outline: none` without replacement)
- Images have alt text (or `aria-hidden` if decorative)
- Color contrast passes WCAG AA (4.5:1 body, 3:1 large text)
- No `user-scalable=no` in viewport meta
- Form labels associated with inputs

## Priority Classification

| Priority | Criteria |
|----------|----------|
| Critical | JS exceptions on page load, blank pages, dead primary navigation |
| High | Console errors, broken interactions, dead links on main flows |
| Medium | Responsive issues, design token violations, empty state gaps |
| Low | Console warnings, minor visual inconsistencies, external link issues |

## Grouping Rules

- Multiple findings on the same page/component → one issue (list all findings)
- Same finding across multiple pages → one umbrella issue listing all affected pages
- Console errors with same stack trace → one issue regardless of which pages trigger it

## Filing Findings

Each finding should reference at least one screenshot. To persist findings as GitHub issues, file them via the `/claudna:publish` skill (`--to github-issue --repo <repo>`) or `/claudna:file-github-issue`, applying a category and priority label per finding. For chat-only analysis, present findings inline with screenshot references instead of filing.
