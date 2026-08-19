# Design Token Comparison Rules

Reference material for the `qa` skill's **Crawl mode** (`qa/SKILL.md`) design-token phase. Extract observed tokens from each route, load the project's reference tokens, then compare — flagging anything off the design system. Pairs with `deep-crawl.md` (the automation engine) and `crawl-checklist.md` (per-route checks).

---

## Step 1: Extract observed tokens

For each route at desktop viewport, extract via Playwright JavaScript evaluation (run over the first 500 elements via `getComputedStyle`):

**Fonts:**
```javascript
[...new Set([...document.querySelectorAll('*')].slice(0,500).map(e => getComputedStyle(e).fontFamily))]
```

**Colors:**
```javascript
[...new Set([...document.querySelectorAll('*')].slice(0,500).flatMap(e => [getComputedStyle(e).color, getComputedStyle(e).backgroundColor]).filter(c => c !== 'rgba(0, 0, 0, 0)'))]
```

**Font sizes:**
```javascript
[...new Set([...document.querySelectorAll('*')].slice(0,500).map(e => getComputedStyle(e).fontSize))]
```

**Spacing (padding/margin):**
```javascript
[...new Set([...document.querySelectorAll('*')].slice(0,200).flatMap(e => {const s=getComputedStyle(e); return [s.padding, s.margin].filter(v => v !== '0px')}))]
```

---

## Step 2: Load reference tokens

Load the design token reference from (in priority order):

1. **Explicit config** — `--tokens <path>` argument if provided
2. **Tailwind config** — `tailwind.config.js` / `tailwind.config.ts` (theme.extend.colors, fontFamily, spacing)
3. **CSS custom properties** — `:root` variables in global CSS files
4. **tokens.json** — Design token file (Style Dictionary, Figma Tokens format)
5. **Theme files** — `theme.ts`, `theme.js`, `styled-components` theme objects
6. **Fallback defaults** — generic web design best practices (below), used when no project-specific tokens are available

### Fallback design defaults

When no project-specific tokens are available, flag deviations from these baselines:

#### Typography
- **Font families:** Flag if more than 3 distinct families are in use
- **Font sizes:** Should follow a scale (e.g., 12, 14, 16, 18, 20, 24, 30, 36, 48, 60, 72)
- **Body text:** >= 16px
- **Line height:** 1.4-1.6 for body, 1.1-1.3 for headings
- **Measure:** 45-75 characters per line

#### Colors
- **Palette size:** Flag if more than 12 unique non-gray colors
- **Consistency:** Same semantic meaning should use same color (all errors same red)
- **Contrast:** WCAG AA minimums (4.5:1 body, 3:1 large text, 3:1 UI components)

#### Spacing
- **Scale:** Should use a consistent base (4px or 8px increments)
- **Flag:** Arbitrary values like 13px, 17px, 23px that aren't on any scale

#### Border Radius
- **Consistency:** Should use 2-3 distinct values (e.g., 4px, 8px, 16px), not random values per component

---

## Step 3: Compare against reference

Compare observed vs reference and flag:
- **Font families** not in the design system
- **Colors** not in the palette (allow close matches within ΔE < 5)
- **Font sizes** not on the type scale
- **Spacing values** not on the spacing scale

### Color matching
- Use CIE ΔE2000 for perceptual color distance
- **ΔE < 2:** Imperceptible — pass
- **ΔE 2-5:** Close match — note but don't flag
- **ΔE > 5:** Distinct color — flag as violation if not in palette

### Font matching
- Exact family name match (case-insensitive)
- Ignore generic fallbacks (sans-serif, serif, monospace)
- Flag if a font is loaded but never used, or used but not loaded

### Size matching
- Exact px match against scale
- Allow ±1px tolerance for sub-pixel rendering
- Flag sizes that don't appear on any defined scale

---

## Reporting format

For each token violation:
```
[TOKEN] <category> — <observed value> not in design system
  Page: <route>
  Element: <selector or description>
  Expected: <closest system value> or <system values available>
  Screenshot: <file reference>
```

To persist token violations, file them via the `/claudna:publish` skill (`--to github-issue --repo <repo>`) or `/claudna:file-github-issue` with a `design-token-violation` category label. Group the same violation across multiple pages into one umbrella issue.
