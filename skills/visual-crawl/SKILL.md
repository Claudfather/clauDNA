---
name: visual-crawl
user-invocable: true
description: "Autonomous visual crawl + screenshot + issue-filing for frontend apps. Discovers routes, screenshots at 3 viewports, tests interactions, compares design tokens, and files GitHub issues for every finding. Supports --deep for full interactive testing (click every button, simulate chat, verify forms). Supports --output github (default), --output session, --auto, --url, --local."
argument-hint: "[--auto] [--deep] [--output github|session] [--url <base-url>] [--local] [focus-area]"
allowed-tools:
  - "Bash(which *)"
  - "Bash(test *)"
  - "Bash(curl *)"
  - "Bash(lsof *)"
  - "Bash(npm run *)"
  - "Bash(pnpm *)"
  - "Bash(yarn *)"
  - "Bash(python3 *)"
  - "Bash(npx *)"
  - "Bash(node *)"
  - "Bash(ls *)"
  - "Bash(mkdir *)"
  - "Bash(cat *)"
  - "Bash(gh *)"
  - "Read(*)"
  - "Write(*)"
  - "Glob(*)"
  - "Grep(*)"
  - "Task(*)"
  - "Agent(*)"
  - "EnterPlanMode"
  - "ExitPlanMode"
---

# Visual Crawl — Autonomous Frontend Audit

Systematic visual crawl of a frontend application. Discovers routes, screenshots every page at three viewports, tests interactions for errors, compares observed styles against design tokens, and files GitHub issues with screenshot evidence for every finding.

## Arguments

Parse `$ARGUMENTS` at invocation:
- `--auto`: Fully non-interactive. Implies `--output github`. Crawl, screenshot, test, file issues, return summary.
- `--deep`: Full interactive testing. Extends Phase 3 with: click every button/link and verify result, fill and submit forms, simulate chat conversations with sample queries, screenshot before/after each interaction, report broken flows. Uses Playwright for interaction testing (inline Python scripts; see Phase 3 below).
- `--output github`: Write findings as GitHub Issues (default). See output guide (`skills/_shared/output-guide.md`).
- `--output session`: Present findings in chat only, no persistence.
- `--url <base-url>`: Crawl a deployed URL (e.g., `--url https://app.example.com`).
- `--local`: Spin up a local dev server from the project directory and crawl it.
- Remaining text is a focus area or constraint (e.g., "only the dashboard pages").

If neither `--url` nor `--local` is specified, ask the user.

## When NOT to use

- For design critique and enhancement proposals → use `/claudna:design-review`
- For frontend performance (flickering, re-renders, layout shifts) → use `/claudna:frontend-performance-audit`
- For code quality/tech debt → use `/claudna:tech-debt`
- For security vulnerabilities → use `/claudna:security-audit`

**Enter Plan Mode.** Call `EnterPlanMode`. All discovery and crawl steps are read-only. If declined, proceed by convention.

---

## Phase 1: Setup & Route Discovery

### Step 1: Environment Setup

Scratch dir: `/tmp/visual-crawl-<YYYY-MM-DD_HHMMSS>/`. Create subdirectories: `screenshots/`, `research/`, `console-logs/`.

Use Playwright via inline Python scripts (see Step 4) for screenshots. If you have a project-specific screenshot helper configured, prefer that over the inline path.

Detect Chrome/Chromium: `which chromium`, `which google-chrome`, `which chromium-browser` in parallel.

### Step 2: Determine Base URL

**If `--url <base-url>`:** Use directly. Verify reachable with `curl -sI <base-url>`.

**If `--local`:**
1. Read `package.json` for start/dev scripts and port
2. Check if dev server is already running: `lsof -i :<port>` and `curl -s http://localhost:<port>`
3. If not running, start it: `npm run dev` (or `pnpm dev`, `yarn dev`) in background
4. Wait for server to be ready (poll with curl, max 30s)
5. Base URL = `http://localhost:<port>`

**If neither:** Ask the user (skip in `--auto` — error out).

### Step 3: Route Discovery

Launch **Explore subagents** in parallel:

**Subagent A — File-based route discovery:**
- Scan for Next.js App Router: `app/**/page.tsx`, `app/**/page.jsx`
- Scan for Next.js Pages Router: `pages/**/*.tsx`, `pages/**/*.jsx`
- Scan for React Router: grep for `<Route`, `createBrowserRouter`, `path:` patterns
- Scan for other frameworks: `routes/`, `views/`, URL patterns in config
- Write discovered routes to `<scratch>/research/routes.md`

**Subagent B — Sitemap and link discovery:**
- Check `<base-url>/sitemap.xml`
- Check `<base-url>/robots.txt` for sitemap references
- Fetch the homepage HTML, extract all `<a href>` links
- Write discovered URLs to `<scratch>/research/sitemap-links.md`

Merge results into a deduplicated route list. Present to user for confirmation (skip in `--auto`).

---

## Phase 2: Screenshot Crawl

### Step 4: Viewport Screenshots

For each discovered route, capture screenshots at three viewports:

| Viewport | Width × Height | Name |
|----------|---------------|------|
| Desktop | 1440 × 900 | `<route-slug>_desktop.png` |
| Tablet | 768 × 1024 | `<route-slug>_tablet.png` |
| Mobile | 375 × 812 | `<route-slug>_mobile.png` |

**Screenshot command** (one per Bash call, no shell operators) — inline Playwright:

```bash
python3 -c "
import asyncio
from playwright.async_api import async_playwright
async def shot():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(viewport={'width': <W>, 'height': <H>}, device_scale_factor=2)
        pg = await ctx.new_page()
        await pg.goto('<url>', wait_until='networkidle', timeout=30000)
        await pg.wait_for_timeout(1000)
        await pg.screenshot(path='<output>', full_page=True)
        await b.close()
asyncio.run(shot())
"
```

**Parallelism:** Capture all three viewports of a single route in parallel (3 Bash calls). Process routes sequentially to avoid overloading the browser.

After each route, read the screenshots to visually inspect them.

### Step 5: Console Error Collection

For each route, capture JavaScript console errors:

```bash
python3 -c "
import asyncio, json
from playwright.async_api import async_playwright
async def check():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        pg = await b.new_page()
        errors = []
        pg.on('console', lambda m: errors.append({'type': m.type, 'text': m.text}) if m.type in ('error', 'warning') else None)
        pg.on('pageerror', lambda e: errors.append({'type': 'exception', 'text': str(e)}))
        await pg.goto('<url>', wait_until='networkidle', timeout=30000)
        await pg.wait_for_timeout(2000)
        print(json.dumps(errors, indent=2))
        await b.close()
asyncio.run(check())
"
```

Write results to `<scratch>/console-logs/<route-slug>.json`.

---

## Phase 3: Interaction Testing

### Step 6: Interactive Element Audit (standard)

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

2. **Dead link check:** For all `<a href>` elements, verify targets return 2xx/3xx (not 404/500). Use `curl -sI` for each unique href.

3. **Button click test:** Click each visible, non-disabled button. After click, check for:
   - New console errors (compare before/after)
   - Navigation changes (URL changed)
   - Modal/dropdown appearance (DOM mutation)

4. **Empty state detection:** Check for pages that render with no visible content, "No data" messages, or loading spinners that never resolve.

Write interaction findings to `<scratch>/research/interactions.md`.

### Step 6b: Deep Interactive Testing (`--deep` only)

When `--deep` is set, extend Phase 3 with comprehensive interaction testing. For each discovered route, run the deep crawl and (if the app has a chat/console interface) the chat simulation below. All testing uses inline Playwright — no external scripts required.

**Setup:** Create `<scratch>/deep-crawl/` for results. Use dark mode if the app supports it.

#### Deep Crawl — click every button, fill every form

For each route, run this Playwright script via Bash:

```bash
python3 -c "
import asyncio, json, os
from playwright.async_api import async_playwright

async def deep_test(url, page_name, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    findings = []
    console_errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={'width':1440,'height':900}, color_scheme='dark', device_scale_factor=2)
        page = await ctx.new_page()
        page.on('console', lambda m: console_errors.append({'type':m.type,'text':m.text}) if m.type=='error' else None)
        page.on('pageerror', lambda e: console_errors.append({'type':'exception','text':str(e)}))

        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
        except Exception as e:
            findings.append({'type':'page-load-error','severity':'critical','detail':str(e)})
            await browser.close()
            return findings

        await page.wait_for_timeout(1500)
        await page.screenshot(path=f'{output_dir}/{page_name}_before.png', full_page=True)

        # Discover interactive elements
        elements = await page.evaluate('''() => {
            return [...document.querySelectorAll('a,button,input,select,textarea,[role=button],[role=link],[onclick],[tabindex]')]
            .map((e,i) => ({
                i, tag:e.tagName.toLowerCase(), type:e.type||null,
                text:(e.textContent||'').trim().slice(0,80), href:e.href||null,
                placeholder:e.placeholder||null, disabled:e.disabled,
                visible: (r=e.getBoundingClientRect(), r.width>0 && r.height>0),
                id:e.id||null, name:e.name||null,
                ariaLabel:e.getAttribute('aria-label')||null
            })).filter(e => e.visible && !e.disabled)
        }''')

        # Click buttons/links (cap at 30)
        clicks_ok = clicks_fail = 0
        for el in [e for e in elements if e['tag'] in ('button','a')][:30]:
            pre_url = page.url
            pre_errs = len(console_errors)
            desc = el.get('text') or el.get('ariaLabel') or f\"{el['tag']}#{el.get('id','?')}\"
            try:
                sel = f\"#{el['id']}\" if el.get('id') else f\"{el['tag']}:has-text('{el['text'][:40]}')\" if el.get('text') else f\"{el['tag']}[aria-label='{el.get('ariaLabel','')}']\"
                await page.click(sel, timeout=3000)
                await page.wait_for_timeout(800)
                if len(console_errors) > pre_errs:
                    findings.append({'type':'interaction-error','severity':'high','element':desc,'detail':console_errors[-1]['text'][:200]})
                    clicks_fail += 1
                else:
                    clicks_ok += 1
                if page.url != pre_url:
                    await page.goto(url, wait_until='networkidle', timeout=30000)
                    await page.wait_for_timeout(1000)
                if len(console_errors) > pre_errs or page.url != pre_url:
                    await page.screenshot(path=f'{output_dir}/{page_name}_click_{clicks_ok+clicks_fail}.png')
            except Exception as e:
                if 'timeout' in str(e).lower():
                    findings.append({'type':'interaction-timeout','severity':'medium','element':desc,'detail':str(e)[:200]})
                clicks_fail += 1

        # Test form inputs (cap at 10)
        forms_tested = 0
        for inp in [e for e in elements if e['tag'] in ('input','textarea') and e.get('type') not in ('hidden','submit')][:10]:
            forms_tested += 1
            desc = inp.get('placeholder') or inp.get('name') or inp.get('ariaLabel') or 'input'
            try:
                sel = f\"#{inp['id']}\" if inp.get('id') else f\"{inp['tag']}[name='{inp['name']}']\" if inp.get('name') else f\"{inp['tag']}[placeholder='{inp.get('placeholder','')[:40]}']\"
                pre_errs = len(console_errors)
                await page.fill(sel, 'test query from visual crawl', timeout=3000)
                await page.press(sel, 'Enter')
                await page.wait_for_timeout(2000)
                if len(console_errors) > pre_errs:
                    findings.append({'type':'form-error','severity':'high','element':desc,'detail':console_errors[-1]['text'][:200]})
                await page.screenshot(path=f'{output_dir}/{page_name}_form_{forms_tested}.png')
            except Exception as e:
                findings.append({'type':'form-interaction-failed','severity':'medium','element':desc,'detail':str(e)[:200]})

        await page.screenshot(path=f'{output_dir}/{page_name}_after.png', full_page=True)
        await browser.close()

    print(f'Elements: {len(elements)}, Clicks: {clicks_ok}/{clicks_ok+clicks_fail}, Forms: {forms_tested}, Findings: {len(findings)}')
    with open(f'{output_dir}/{page_name}_results.json','w') as f:
        json.dump(findings, f, indent=2)
    return findings

asyncio.run(deep_test('ROUTE_URL', 'PAGE_NAME', '<scratch>/deep-crawl/PAGE_NAME'))
"
```

Replace `ROUTE_URL`, `PAGE_NAME` with each discovered route. Run for every route.

#### Chat Simulation — test the conversational experience

If the app has a chat or console interface, run this to simulate a conversation:

```bash
python3 -c "
import asyncio, json, os
from playwright.async_api import async_playwright

async def chat_test(base_url, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    queries = ['What can you help me with?', 'Show me the most recent records', 'Generate a summary of <example metric>']
    # Override with domain-specific queries from CLAUDE.md or PROJECT_MISSION.md if available
    results = []
    console_errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={'width':1440,'height':900}, color_scheme='dark', device_scale_factor=2)
        page = await ctx.new_page()
        page.on('console', lambda m: console_errors.append(m.text) if m.type=='error' else None)

        chat_url = f\"{base_url.rstrip('/')}/console\"
        try:
            await page.goto(chat_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            print(f'Could not load chat page: {e}')
            await browser.close()
            return

        await page.screenshot(path=f'{output_dir}/chat_initial.png', full_page=True)

        for i, query in enumerate(queries):
            turn = {'query': query, 'turn': i+1, 'errors': [], 'response_received': False}
            try:
                # Find chat input
                input_sel = None
                for sel in ['textarea', \"input[type='text']\", \"[placeholder*='Ask']\", \"[placeholder*='query']\", \"[placeholder*='Search']\", \"[placeholder*='message']\", \"[role='textbox']\"]:
                    try:
                        el = await page.wait_for_selector(sel, timeout=2000)
                        if el: input_sel = sel; break
                    except: continue

                if not input_sel:
                    turn['errors'].append('Could not find chat input')
                    results.append(turn); continue

                pre_errs = len(console_errors)
                await page.fill(input_sel, query)
                await page.screenshot(path=f'{output_dir}/chat_turn{i+1}_typed.png')
                await page.press(input_sel, 'Enter')

                # Wait for response (up to 30s)
                await page.wait_for_timeout(3000)
                for _ in range(27):
                    loading = await page.evaluate('''() => document.querySelectorAll('[class*=loading],[class*=spinner],[class*=pulse],[class*=skeleton]').length > 0''')
                    if not loading: break
                    await page.wait_for_timeout(1000)
                turn['response_received'] = True

                if len(console_errors) > pre_errs:
                    turn['errors'].extend(console_errors[pre_errs:])

                await page.screenshot(path=f'{output_dir}/chat_turn{i+1}_response.png', full_page=True)
            except Exception as e:
                turn['errors'].append(str(e)[:200])
            results.append(turn)
            print(f\"Turn {i+1}: '{query[:50]}' — {'OK' if not turn['errors'] else 'ERRORS: ' + '; '.join(str(e)[:80] for e in turn['errors'][:2])}\")

        await browser.close()
    with open(f'{output_dir}/chat_results.json','w') as f:
        json.dump(results, f, indent=2, default=str)

asyncio.run(chat_test('BASE_URL', '<scratch>/deep-crawl/chat'))
"
```

Replace `BASE_URL` with the app's base URL. If the app's chat page is not at `/console`, adjust the path. Use domain-specific test queries from CLAUDE.md or PROJECT_MISSION.md if available instead of the defaults.

#### After deep testing

Read all screenshots from `<scratch>/deep-crawl/` to visually inspect results. Read `*_results.json` files for structured findings.

Merge deep findings into the Phase 5 findings list with appropriate severity:
- `page-load-error` → Critical
- `interaction-error` (click caused console errors) → High
- `form-error` (form submission caused errors) → High
- Chat failures (input not found, query timeout, errors on submit) → High
- `interaction-timeout` (element not clickable) → Medium
- `form-interaction-failed` → Medium

---

## Phase 4: Design Token Comparison

### Step 7: Extract Observed Tokens

For each route at desktop viewport, extract via Playwright JavaScript evaluation:

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

### Step 8: Compare Against Reference Tokens

Load design token reference from (in priority order):
1. `--tokens <path>` argument if provided
2. Project's `tokens.json`, `tailwind.config.js/ts`, CSS custom properties (`:root` vars)
3. `design-hard-rules.md` in this skill's directory (fallback defaults)

Compare observed vs reference:
- **Font families** not in the design system
- **Colors** not in the palette (allow close matches within ΔE < 5)
- **Font sizes** not on the type scale
- **Spacing values** not on the spacing scale

Write token comparison to `<scratch>/research/token-comparison.md`.

---

## Phase 5: Analysis & Output

### Step 9: Findings Compilation

Classify each finding:

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

### Step 10: Output

**Exit Plan Mode.** Call `ExitPlanMode`.

**If `--output github` or `--auto`:**

Create GitHub Issues per output guide (`skills/_shared/output-guide.md`):
- One issue per finding (or group related findings on same page)
- Include screenshot attachments (desktop + mobile for visual bugs)
- Apply labels: `auto-audit`, `visual-crawl`, category label, priority label
- Dedup against existing open issues (Section 4.5 of output guide)
- Create batch summary issue linking all findings

**If `--output session`:**

Present findings in chat with inline screenshot references. Stay in Plan Mode.

Return structured summary:
```
Visual Crawl Summary
════════════════════════════════════════════════════
Routes crawled: N
Screenshots taken: N (N routes × 3 viewports)
Console errors found: N
Dead links found: N
Interaction failures: N
Design token violations: N
GitHub issues created: N
════════════════════════════════════════════════════
```

---

## Autonomous Mode (`--auto`)

When `--auto` is set:
1. Skip Plan Mode — go straight to crawl
2. Skip user confirmation gates
3. Implies `--output github`
4. Must have `--url` or `--local` (cannot prompt for URL)
5. Create GitHub Issues for all findings at Medium priority or above
6. Return structured summary for tracking

`--auto` and `--deep` can be combined: `--auto --deep --url https://app.example.com` runs a full interactive crawl with issue filing, no human in the loop.

---

## Notes

- **One screenshot per Bash call.** No shell operators (`&&`, `||`, `;`, `|`). Playwright commands are single-shot.
- **Sequential routes, parallel viewports.** Don't open multiple browser instances for different routes simultaneously — sequential keeps memory pressure low and avoids resource exhaustion on constrained hardware.
- **Screenshots are evidence.** Every finding must reference at least one screenshot file.
- **Don't fix code.** This skill identifies problems. Use `/claudna:implement-plan` or manual fixes afterward.
- **Respect robots.txt.** If a deployed URL has `Disallow` rules, honor them unless the user explicitly overrides.
- **Timeout handling.** If a page doesn't load within 30 seconds, log a finding (possible server issue) and continue to next route.
- **Subagents for research.** Use Explore subagents for route discovery and codebase analysis. Use general-purpose subagents for disk writes. Keep orchestrator context lean.
- Orchestration guide Section 10 for shared reminders.

---

## Output Targets

Follow the output guide at `skills/_shared/output-guide.md`:
- For `github` (default): structured issue body (Section 4), dedup check (Section 4.5), labels (Section 4.3). Apply `visual-crawl` label + category-specific label.
- For `session`: present findings in chat, stay in Plan Mode (Section 5)
