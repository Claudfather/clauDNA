# Design Audit Checklist


Reference material for the `/claudna:audit design` lens. Apply these checks systematically across all pages in scope. Each finding gets an **impact rating** (High / Medium / Polish) and its category. Use the page-type classifier from Step 2 to weight findings — e.g., "no expressive typography" is High-impact on a marketing page but may be acceptable on an app UI.

## 10 Categories

**1. Visual Hierarchy & Composition** (weight: 15%)
- Clear focal point per view? One primary CTA?
- Eye flows naturally — no competing elements fighting for attention?
- Information density appropriate for page type?
- Above-the-fold content communicates purpose in 3 seconds?
- White space is intentional, not leftover?

**2. Typography** (weight: 15%)
- Font count <=3 distinct families (flag if more)
- Scale follows a ratio (1.25 major third or 1.333 perfect fourth)
- Line-height: ~1.5x body, ~1.15-1.25x headings
- Measure: 45-75 characters per line (66 ideal)
- Heading hierarchy: no skipped levels (h1 then h3 with no h2)
- Body text >= 16px, caption/label >= 12px
- `font-variant-numeric: tabular-nums` on number columns
- No letterspacing on lowercase text
- If primary font is Inter/Roboto/Open Sans/Poppins, flag as potentially generic (see `font-knowledge.md`)

**3. Color & Contrast** (weight: 10%)
- Palette coherent (<=12 unique non-gray colors)
- WCAG AA contrast: body text 4.5:1, large text (18px+) 3:1, UI components 3:1
- Semantic colors consistent (success=green, error=red, warning=amber)
- No color-only encoding — always add labels, icons, or patterns
- No red/green-only combinations (8% of men have red-green deficiency)
- Neutral palette consistently warm or cool, not mixed

**4. Spacing & Layout** (weight: 15%)
- Spacing uses a scale (4px or 8px base), not arbitrary values
- Alignment consistent — nothing floats outside the grid
- Related items closer together, distinct sections further apart (proximity principle)
- Border-radius hierarchy — not uniform bubbly radius on everything
- No horizontal scroll on mobile
- Max content width set (no full-bleed body text)

**5. Interaction States** (weight: 10%)
- Hover state on all interactive elements
- `focus-visible` ring present (never `outline: none` without replacement)
- Disabled state: reduced opacity + `cursor: not-allowed`
- Loading: skeleton shapes match real content layout
- Empty states: warm message + primary action (not just "No items.")
- Error messages: specific + include fix/next step
- Touch targets >= 44px on all interactive elements

**6. Responsive Design** (weight: 10%)
- Mobile layout makes *design* sense — not just stacked desktop columns
- Touch targets sufficient on mobile (>= 44px)
- No horizontal scroll on any viewport
- Text readable without zooming on mobile (>= 16px body)
- Navigation collapses appropriately
- No `user-scalable=no` or `maximum-scale=1` in viewport meta

**7. Motion & Animation** (weight: 5%)
- Easing: ease-out for entering, ease-in for exiting, ease-in-out for moving
- Duration: 50-700ms range (nothing slower unless page transition)
- Every animation communicates something (state change, attention, spatial relationship)
- `prefers-reduced-motion` respected
- Only `transform` and `opacity` animated (not layout properties like width, height, top, left)

**8. Content & Microcopy** (weight: 10%)
- Empty states designed with warmth (message + action + icon)
- Error messages specific: what happened + why + what to do next
- Button labels specific ("Save API Key" not "Continue" or "Submit")
- No placeholder/lorem ipsum text visible in production
- Active voice ("Install the CLI" not "The CLI will be installed")
- Destructive actions have confirmation modal or undo window

**9. AI Slop Detection** (weight: 5% of design score, but also reported as a standalone grade)

The test: would a human designer at a respected studio ever ship this? See `ai-slop-blacklist.md` for the full 10-pattern blacklist.

**10. Front-end/Back-end Alignment** (weight: 5%)
- API returns data the UI doesn't surface, or UI promises features the API doesn't support
- Design debt: inline styles, magic numbers, inconsistent tokens, no design system usage

## Grading

### Per-category grades

- **A:** Intentional, polished, delightful. Shows design thinking.
- **B:** Solid fundamentals, minor inconsistencies. Looks professional.
- **C:** Functional but generic. No major problems, no design point of view.
- **D:** Noticeable problems. Feels unfinished or careless.
- **F:** Actively hurting user experience. Needs significant rework.

### Grade computation

Each category starts at A. Each High-impact finding drops one letter grade. Each Medium-impact finding drops half a letter grade. Polish findings are noted but do not affect the grade. Minimum is F.

### Dual headline scores

- **Design Score: {A-F}** — weighted average across all 10 categories (use the weights listed above)
- **AI Slop Score: {A-F}** — standalone grade for category 9 with a brief verdict

### Presentation format

```
Design Gap Analysis
═══════════════════════════════════════════════════════════════════════════
  #   Category              Page/Area         Impact   Finding
  1   Responsive (6)        Dashboard         High     Sidebar overlaps content at 768px
  2   Interaction (5)       Login form        High     No focus indicators on inputs
  3   Content (8)           Checkout flow     Medium   3 unnecessary confirmation steps
  4   Interaction (5)       Product list      Medium   No skeleton loader, hard jump on load
  5   Typography (2)        Global styles     High     12 different font sizes, no scale
  6   AI Slop (9)           Landing page      High     3-column icon grid with purple gradient
═══════════════════════════════════════════════════════════════════════════

  Design Score: C    AI Slop Score: D
  Category Grades: Hierarchy B | Typography D | Color B | Spacing C | ...
═══════════════════════════════════════════════════════════════════════════
```

For each finding, note:
- Which screenshot shows it (reference the file)
- Which code file is responsible (component, route, style file)
- How it connects to what the user said in the design intent interview
