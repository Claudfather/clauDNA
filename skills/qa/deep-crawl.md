# Deep Crawl — the crawl-mode automation engine

This is the backing engine for the `qa` skill's **Crawl mode** (`qa/SKILL.md`). It supplies real, runnable Playwright recipes for screenshotting routes at three viewports, collecting console errors, exercising every interactive element (`--deep`), and simulating a chat UI. Every step runs the bundled runner `<claudna-root>/scripts/crawl_page.py` from a JSON job file, so a route found on the site never becomes part of a command.

Pair this with:
- `crawl-checklist.md` — the 7 per-route check groups and their thresholds.
- `design-token-rules.md` — design-token extraction JS + comparison thresholds (ΔE2000).

## Conventions

- **Scratch dir:** `<scratch>/`, made with `mktemp -d "${TMPDIR:-/tmp}/qa-crawl.XXXXXX"`, with subdirectories `screenshots/`, `console-logs/`, `deep-crawl/`.
- **One screenshot per Bash call.** No shell operators (`&&`, `||`, `;`, `|`). Playwright commands are single-shot.
- **Sequential routes, parallel viewports.** Capture the three viewports of one route in parallel (3 Bash calls), but process routes one at a time — keeps browser memory pressure low and avoids resource exhaustion on constrained hardware.
- **Screenshots are evidence.** Every finding must reference at least one screenshot file.
- After each route, read the screenshots to visually inspect them.
- Detect Chrome/Chromium first: `which chromium`, `which google-chrome`, `which chromium-browser` in parallel. If you have a project-specific screenshot helper configured, prefer it over the inline path.

---

## Screenshot crawl

### Viewport matrix

For each discovered route, capture screenshots at three viewports:

| Viewport | Width × Height | Name |
|----------|---------------|------|
| Desktop | 1440 × 900 | `<route-slug>_desktop.png` |
| Tablet | 768 × 1024 | `<route-slug>_tablet.png` |
| Mobile | 375 × 812 | `<route-slug>_mobile.png` |

### The bundled runner

Every browser step runs one bundled script, `<claudna-root>/scripts/crawl_page.py` (resolve `<claudna-root>` per `../_shared/claudna-root.md`). A route found on the site goes into a JSON job file, written with the Write tool, and never into a command line or program text. Name job files by number (`<scratch>/jobs/job-001.json`), never after a route. Every output path in a job must stay inside `<scratch>`. `<route-slug>`, the name of a route's files and the `deep` verb's `page_name`, must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$`: replace every other character of the route with `-`, drop leading characters that are not letters or digits, cut it to 100 characters, and use `home` when nothing is left. The runner refuses a job that breaks either rule.

### Screenshot recipe

For each route and viewport, write a job:

```json
{"url": "<url>", "width": <W>, "height": <H>, "output": "<scratch>/screenshots/<route-slug>_<viewport>.png"}
```

then run it, one per Bash call:

```bash
python3 "<claudna-root>/scripts/crawl_page.py" shot "<scratch>/jobs/job-001.json"
```

**Parallelism:** Capture all three viewports of a single route in parallel (3 Bash calls). Process routes sequentially to avoid overloading the browser.

### Console error collection

For each route, write a job and run the `console` verb. It writes the page's console errors, warnings and uncaught exceptions to `output` as JSON:

```json
{"url": "<url>", "output": "<scratch>/console-logs/<route-slug>.json"}
```

```bash
python3 "<claudna-root>/scripts/crawl_page.py" console "<scratch>/jobs/job-002.json"
```

---

## Interaction testing (standard)

For each route, use Playwright to:

1. **Enumerate interactive elements:**
   ```javascript
   [...document.querySelectorAll('a,button,input,select,textarea,[role=button],[role=link],[onclick]')]
     .map(e => ({
       tag: e.tagName,
       text: (e.textContent || '').trim().slice(0, 50),
       href: e.href || null,
       type: e.type || null,
       disabled: e.disabled || false,
       rect: e.getBoundingClientRect()
     }))
   ```

2. **Dead link check:** Put the unique `<a href>` targets into one job (`{"urls": [...], "output": "<scratch>/research/links.json"}`) and run the `links` verb. It records each target's HTTP status (HEAD, then GET when HEAD is refused); anything 4xx/5xx is a dead link. Never put an href on a command line.

3. **Button click test:** Click each visible, non-disabled button. After click, check for:
   - New console errors (compare before/after)
   - Navigation changes (URL changed)
   - Modal/dropdown appearance (DOM mutation)

4. **Empty state detection:** Check for pages that render with no visible content, "No data" messages, or loading spinners that never resolve.

Write interaction findings to `<scratch>/research/interactions.md`.

---

## Deep interactive testing (`--deep`)

When `--deep` is set, extend interaction testing with a comprehensive harness. For each discovered route, run the deep crawl and (if the app has a chat/console interface) the chat simulation below. All testing runs the bundled runner above, driven by JSON job files.

**Setup:** Create `<scratch>/deep-crawl/` for results. Use dark mode if the app supports it.

### Deep crawl — click every button, fill every form

Enumerates interactive elements, clicks up to 30 buttons/links with a before/after console+URL diff, fills up to 10 form inputs, and screenshots each interaction. For every route, write a job and run the `deep` verb:

```json
{"url": "<url>", "page_name": "<route-slug>", "output_dir": "<scratch>/deep-crawl/<route-slug>"}
```

```bash
python3 "<claudna-root>/scripts/crawl_page.py" deep "<scratch>/jobs/job-003.json"
```

It writes `<page_name>_results.json` and the before, after, click and form screenshots into `output_dir`.

### Chat simulation — test the conversational experience

If the app has a chat or console interface, run the `chat` verb. It drives the chat UI through sample queries, polling for loading spinners between turns (up to 30s), and screenshots each turn. Set `path` when the chat page is not at `/console`. Use domain-specific test queries from `CLAUDE.md` or `PROJECT_MISSION.md` in `queries` if there are any; they are data in the job file like everything else, and the runner uses three generic queries when `queries` is absent:

```json
{"base_url": "<base-url>", "path": "/console", "output_dir": "<scratch>/deep-crawl/chat", "queries": ["What can you help me with?"]}
```

```bash
python3 "<claudna-root>/scripts/crawl_page.py" chat "<scratch>/jobs/job-004.json"
```

### After deep testing

Read all screenshots from `<scratch>/deep-crawl/` to visually inspect results. Read `*_results.json` files for structured findings.

Merge deep findings into the findings list with appropriate severity:
- `page-load-error` → Critical
- `interaction-error` (click caused console errors) → High
- `form-error` (form submission caused errors) → High
- Chat failures (input not found, query timeout, errors on submit) → High
- `interaction-timeout` (element not clickable) → Medium
- `form-interaction-failed` → Medium

---

## Findings & output

Classify each finding by category and priority (see `crawl-checklist.md` for the full criteria):

| Category | Examples |
|----------|----------|
| `visual-bug` | Layout broken at viewport, overflow, clipping |
| `console-error` | JS errors, unhandled exceptions |
| `dead-link` | 404s, broken hrefs |
| `interaction-bug` | Button does nothing, dropdown doesn't open |
| `empty-state` | No content rendered, perpetual loading |
| `design-token-violation` | Off-palette color, non-system font, wrong size |
| `responsive-issue` | Content unreadable on mobile, touch target too small |
| `accessibility` | Missing focus indicators, no alt text, contrast failure |

Priority mapping:
- **Critical:** JS exceptions, dead links on primary flows, broken layouts
- **High:** Console errors, interaction failures, empty states
- **Medium:** Design token violations, responsive issues
- **Low:** Minor visual inconsistencies, warnings

**Filing findings.** Every finding must reference at least one screenshot. To persist findings as GitHub issues, file them via the `/claudna:publish` skill (`--to github-issue --repo <repo>`) or `/claudna:file-github-issue`. Group related findings: multiple findings on the same page/component → one issue; the same finding across multiple pages → one umbrella issue listing affected pages; console errors with the same stack trace → one issue regardless of which pages trigger it. For chat-only analysis, present findings inline with screenshot references instead of filing.

**Don't fix code here.** This engine identifies problems. Apply fixes separately afterward.
