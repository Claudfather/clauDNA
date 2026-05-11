# Design Token Comparison Rules

Reference material for the visual-crawl skill's design token comparison phase. These rules define what constitutes a token violation and how to detect it.

## Token Sources (Priority Order)

1. **Explicit config** — `--tokens <path>` argument
2. **Tailwind config** — `tailwind.config.js` / `tailwind.config.ts` (theme.extend.colors, fontFamily, spacing)
3. **CSS custom properties** — `:root` variables in global CSS files
4. **tokens.json** — Design token file (Style Dictionary, Figma Tokens format)
5. **Theme files** — `theme.ts`, `theme.js`, `styled-components` theme objects
6. **Fallback defaults** — Generic web design best practices (below)

## Fallback Design Defaults

When no project-specific tokens are available, flag deviations from these baselines:

### Typography
- **Font families:** Flag if more than 3 distinct families are in use
- **Font sizes:** Should follow a scale (e.g., 12, 14, 16, 18, 20, 24, 30, 36, 48, 60, 72)
- **Body text:** >= 16px
- **Line height:** 1.4-1.6 for body, 1.1-1.3 for headings
- **Measure:** 45-75 characters per line

### Colors
- **Palette size:** Flag if more than 12 unique non-gray colors
- **Consistency:** Same semantic meaning should use same color (all errors same red)
- **Contrast:** WCAG AA minimums (4.5:1 body, 3:1 large text, 3:1 UI components)

### Spacing
- **Scale:** Should use a consistent base (4px or 8px increments)
- **Flag:** Arbitrary values like 13px, 17px, 23px that aren't on any scale

### Border Radius
- **Consistency:** Should use 2-3 distinct values (e.g., 4px, 8px, 16px), not random values per component

## Comparison Logic

### Color Matching
- Use CIE ΔE2000 for perceptual color distance
- ΔE < 2: Imperceptible — pass
- ΔE 2-5: Close match — note but don't flag
- ΔE > 5: Distinct color — flag as violation if not in palette

### Font Matching
- Exact family name match (case-insensitive)
- Ignore generic fallbacks (sans-serif, serif, monospace)
- Flag if a font is loaded but never used, or used but not loaded

### Size Matching
- Exact px match against scale
- Allow ±1px tolerance for sub-pixel rendering
- Flag sizes that don't appear on any defined scale

## Reporting Format

For each token violation:
```
[TOKEN] <category> — <observed value> not in design system
  Page: <route>
  Element: <selector or description>
  Expected: <closest system value> or <system values available>
  Screenshot: <file reference>
```
