# Deep Crawl — the crawl-mode automation engine

This is the backing engine for the `qa` skill's **Crawl mode** (`qa/SKILL.md`). It supplies real, runnable Playwright recipes for screenshotting routes at three viewports, collecting console errors, exercising every interactive element (`--deep`), and simulating a chat UI. All scripts are inline Python via `python3 -c "..."` — no external script files required.

Pair this with:
- `crawl-checklist.md` — the 7 per-route check groups and their thresholds.
- `design-token-rules.md` — design-token extraction JS + comparison thresholds (ΔE2000).

## Conventions

- **Scratch dir:** `/tmp/qa-crawl-<YYYY-MM-DD_HHMMSS>/` with subdirectories `screenshots/`, `console-logs/`, `deep-crawl/`.
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

### Screenshot recipe (inline Playwright)

One per Bash call, no shell operators. Substitute `<W>`, `<H>`, `<url>`, `<output>`:

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

### Console error collection

For each route, capture JavaScript console errors and page exceptions. Write results to `<scratch>/console-logs/<route-slug>.json`:

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

2. **Dead link check:** For all `<a href>` elements, verify targets return 2xx/3xx (not 404/500). Use `curl -sI` for each unique href.

3. **Button click test:** Click each visible, non-disabled button. After click, check for:
   - New console errors (compare before/after)
   - Navigation changes (URL changed)
   - Modal/dropdown appearance (DOM mutation)

4. **Empty state detection:** Check for pages that render with no visible content, "No data" messages, or loading spinners that never resolve.

Write interaction findings to `<scratch>/research/interactions.md`.

---

## Deep interactive testing (`--deep`)

When `--deep` is set, extend interaction testing with a comprehensive harness. For each discovered route, run the deep crawl and (if the app has a chat/console interface) the chat simulation below. All testing uses inline Playwright — no external scripts required.

**Setup:** Create `<scratch>/deep-crawl/` for results. Use dark mode if the app supports it.

### Deep crawl — click every button, fill every form

Enumerates interactive elements, clicks up to 30 buttons/links with a before/after console+URL diff, fills up to 10 form inputs, and screenshots each interaction. For each route, run this Playwright script via Bash. Replace `ROUTE_URL`, `PAGE_NAME` with each discovered route. Run for every route:

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

### Chat simulation — test the conversational experience

If the app has a chat or console interface, run this to simulate a conversation. It drives the chat UI through sample queries, polling for loading spinners between turns (up to 30s) and screenshotting each turn. Replace `BASE_URL` with the app's base URL. If the app's chat page is not at `/console`, adjust the path. Use domain-specific test queries from `CLAUDE.md` or `PROJECT_MISSION.md` if available instead of the defaults:

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
