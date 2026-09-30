#!/usr/bin/env python3
"""Run one step of the qa skill's crawl against one page, from a JSON job file.

The qa skill (skills/qa/deep-crawl.md) writes each job with the Write tool and runs:

    python3 <claudna-root>/scripts/crawl_page.py <verb> <job-file>

A route found on the site being crawled is data. It reaches the browser from the
job file, never from a command line or from program text. Keep it that way: a
route can hold a quote, a backtick or `$(...)`.

Verbs and the job fields each reads:

    shot     url, width, height, output
    console  url, output
    links    urls (a list), output
    deep     url, page_name, output_dir
    chat     base_url, output_dir, path (default "/console"), queries (optional list)

Every output path must resolve inside the directory that holds the job file's
directory (the crawl's scratch dir), so a file name built from a route cannot
write anywhere else.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REQUIRED = {
    "shot": ("url", "width", "height", "output"),
    "console": ("url", "output"),
    "links": ("urls", "output"),
    "deep": ("url", "page_name", "output_dir"),
    "chat": ("base_url", "output_dir"),
}

DEFAULT_CHAT_QUERIES = [
    "What can you help me with?",
    "Show me the most recent records",
    "Generate a summary of the main metric",
]


class JobError(ValueError):
    """The job file cannot be run as written."""


def load_job(verb: str, job_path: Path) -> dict:
    if verb not in REQUIRED:
        raise JobError(f"unknown verb {verb!r}; expected one of {', '.join(REQUIRED)}")
    try:
        job = json.loads(job_path.read_text())
    except (OSError, ValueError) as err:
        raise JobError(f"cannot read job file {job_path}: {err}") from err
    if not isinstance(job, dict):
        raise JobError("the job file must hold a JSON object")
    missing = [k for k in REQUIRED[verb] if k not in job]
    if missing:
        raise JobError(f"{verb}: missing field(s) {', '.join(missing)}")
    root = job_path.resolve().parent.parent
    for key in ("output", "output_dir"):
        if key in job:
            job[key] = str(inside(root, job[key]))
    return job


def inside(root: Path, value: object) -> Path:
    """``value`` as a path, refused unless it resolves inside ``root``."""
    path = (root / str(value)).resolve() if not os.path.isabs(str(value)) else Path(str(value)).resolve()
    if path != root and root not in path.parents:
        raise JobError(f"output {value!r} resolves outside the crawl's scratch dir {root}")
    return path


def page_url(value: object) -> str:
    url = str(value)
    if not url.startswith(("http://", "https://")):
        raise JobError(f"not an http(s) URL: {url!r}")
    return url


# --- verbs -----------------------------------------------------------------


async def shot(job: dict) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": int(job["width"]), "height": int(job["height"])}, device_scale_factor=2
        )
        page = await ctx.new_page()
        await page.goto(page_url(job["url"]), wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=job["output"], full_page=True)
        await browser.close()
    return f"screenshot: {job['output']}"


async def console(job: dict) -> str:
    from playwright.async_api import async_playwright

    errors: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.on(
            "console",
            lambda m: errors.append({"type": m.type, "text": m.text}) if m.type in ("error", "warning") else None,
        )
        page.on("pageerror", lambda e: errors.append({"type": "exception", "text": str(e)}))
        await page.goto(page_url(job["url"]), wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await browser.close()
    Path(job["output"]).parent.mkdir(parents=True, exist_ok=True)
    Path(job["output"]).write_text(json.dumps(errors, indent=2))
    return f"console: {len(errors)} error(s)/warning(s) -> {job['output']}"


def links(job: dict) -> str:
    """HEAD each URL (GET when HEAD is refused) and record its status."""
    results = {}
    for raw in job["urls"]:
        url = str(raw)
        if not url.startswith(("http://", "https://")):
            results[url] = "skipped: not http(s)"
            continue
        status: object = None
        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(url, method=method)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = resp.status
                break
            except urllib.error.HTTPError as err:
                status = err.code
                if err.code != 405:
                    break
            except (urllib.error.URLError, OSError, ValueError) as err:
                status = f"error: {err}"
                break
        results[url] = status
    Path(job["output"]).parent.mkdir(parents=True, exist_ok=True)
    Path(job["output"]).write_text(json.dumps(results, indent=2))
    dead = [u for u, s in results.items() if isinstance(s, int) and s >= 400]
    return f"links: {len(results)} checked, {len(dead)} returned 4xx/5xx -> {job['output']}"


async def deep(job: dict) -> str:
    """Click up to 30 buttons/links and fill up to 10 inputs, with a console and URL diff."""
    from playwright.async_api import async_playwright

    url = page_url(job["url"])
    name = str(job["page_name"])
    out = Path(job["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    findings: list[dict] = []
    console_errors: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900}, color_scheme="dark", device_scale_factor=2
        )
        page = await ctx.new_page()
        page.on(
            "console", lambda m: console_errors.append({"type": m.type, "text": m.text}) if m.type == "error" else None
        )
        page.on("pageerror", lambda e: console_errors.append({"type": "exception", "text": str(e)}))

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:  # noqa: BLE001 — any load failure is the finding
            findings.append({"type": "page-load-error", "severity": "critical", "detail": str(e)})
            await browser.close()
            (out / f"{name}_results.json").write_text(json.dumps(findings, indent=2))
            return f"deep: page did not load -> {out / (name + '_results.json')}"

        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(out / f"{name}_before.png"), full_page=True)

        elements = await page.evaluate(
            """() => {
            return [...document.querySelectorAll('a,button,input,select,textarea,[role=button],[role=link],[onclick],[tabindex]')]
            .map((e,i) => ({
                i, tag:e.tagName.toLowerCase(), type:e.type||null,
                text:(e.textContent||'').trim().slice(0,80), href:e.href||null,
                placeholder:e.placeholder||null, disabled:e.disabled,
                visible: (r=e.getBoundingClientRect(), r.width>0 && r.height>0),
                id:e.id||null, name:e.name||null,
                ariaLabel:e.getAttribute('aria-label')||null
            })).filter(e => e.visible && !e.disabled)
        }"""
        )

        clicks_ok = clicks_fail = 0
        for el in [e for e in elements if e["tag"] in ("button", "a")][:30]:
            pre_url = page.url
            pre_errs = len(console_errors)
            desc = el.get("text") or el.get("ariaLabel") or f"{el['tag']}#{el.get('id', '?')}"
            try:
                if el.get("id"):
                    sel = f"#{el['id']}"
                elif el.get("text"):
                    sel = f"{el['tag']}:has-text('{el['text'][:40]}')"
                else:
                    sel = f"{el['tag']}[aria-label='{el.get('ariaLabel', '')}']"
                await page.click(sel, timeout=3000)
                await page.wait_for_timeout(800)
                if len(console_errors) > pre_errs:
                    findings.append(
                        {
                            "type": "interaction-error",
                            "severity": "high",
                            "element": desc,
                            "detail": console_errors[-1]["text"][:200],
                        }
                    )
                    clicks_fail += 1
                else:
                    clicks_ok += 1
                if page.url != pre_url:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1000)
                if len(console_errors) > pre_errs or page.url != pre_url:
                    await page.screenshot(path=str(out / f"{name}_click_{clicks_ok + clicks_fail}.png"))
            except Exception as e:  # noqa: BLE001 — a failed click is a finding, not a crash
                if "timeout" in str(e).lower():
                    findings.append(
                        {"type": "interaction-timeout", "severity": "medium", "element": desc, "detail": str(e)[:200]}
                    )
                clicks_fail += 1

        forms_tested = 0
        for inp in [
            e for e in elements if e["tag"] in ("input", "textarea") and e.get("type") not in ("hidden", "submit")
        ][:10]:
            forms_tested += 1
            desc = inp.get("placeholder") or inp.get("name") or inp.get("ariaLabel") or "input"
            try:
                if inp.get("id"):
                    sel = f"#{inp['id']}"
                elif inp.get("name"):
                    sel = f"{inp['tag']}[name='{inp['name']}']"
                else:
                    sel = f"{inp['tag']}[placeholder='{(inp.get('placeholder') or '')[:40]}']"
                pre_errs = len(console_errors)
                await page.fill(sel, "test query from visual crawl", timeout=3000)
                await page.press(sel, "Enter")
                await page.wait_for_timeout(2000)
                if len(console_errors) > pre_errs:
                    findings.append(
                        {
                            "type": "form-error",
                            "severity": "high",
                            "element": desc,
                            "detail": console_errors[-1]["text"][:200],
                        }
                    )
                await page.screenshot(path=str(out / f"{name}_form_{forms_tested}.png"))
            except Exception as e:  # noqa: BLE001
                findings.append(
                    {"type": "form-interaction-failed", "severity": "medium", "element": desc, "detail": str(e)[:200]}
                )

        await page.screenshot(path=str(out / f"{name}_after.png"), full_page=True)
        await browser.close()

    (out / f"{name}_results.json").write_text(json.dumps(findings, indent=2))
    return (
        f"deep: elements {len(elements)}, clicks {clicks_ok}/{clicks_ok + clicks_fail}, "
        f"forms {forms_tested}, findings {len(findings)} -> {out / (name + '_results.json')}"
    )


async def chat(job: dict) -> str:
    """Drive a chat UI through sample queries, screenshotting each turn."""
    from playwright.async_api import async_playwright

    out = Path(job["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    queries = [str(q) for q in (job.get("queries") or DEFAULT_CHAT_QUERIES)]
    chat_url = page_url(job["base_url"]).rstrip("/") + "/" + str(job.get("path", "/console")).lstrip("/")
    results: list[dict] = []
    console_errors: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900}, color_scheme="dark", device_scale_factor=2
        )
        page = await ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        try:
            await page.goto(chat_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
        except Exception as e:  # noqa: BLE001
            await browser.close()
            return f"chat: could not load {chat_url}: {e}"

        await page.screenshot(path=str(out / "chat_initial.png"), full_page=True)
        inputs = [
            "textarea",
            "input[type='text']",
            "[placeholder*='Ask']",
            "[placeholder*='query']",
            "[placeholder*='Search']",
            "[placeholder*='message']",
            "[role='textbox']",
        ]
        for i, query in enumerate(queries):
            turn = {"query": query, "turn": i + 1, "errors": [], "response_received": False}
            try:
                input_sel = None
                for sel in inputs:
                    try:
                        if await page.wait_for_selector(sel, timeout=2000):
                            input_sel = sel
                            break
                    except Exception:  # noqa: BLE001 — try the next selector
                        continue
                if not input_sel:
                    turn["errors"].append("Could not find chat input")
                    results.append(turn)
                    continue
                pre_errs = len(console_errors)
                await page.fill(input_sel, query)
                await page.screenshot(path=str(out / f"chat_turn{i + 1}_typed.png"))
                await page.press(input_sel, "Enter")
                await page.wait_for_timeout(3000)
                for _ in range(27):
                    loading = await page.evaluate(
                        "() => document.querySelectorAll('[class*=loading],[class*=spinner],[class*=pulse],[class*=skeleton]').length > 0"
                    )
                    if not loading:
                        break
                    await page.wait_for_timeout(1000)
                turn["response_received"] = True
                if len(console_errors) > pre_errs:
                    turn["errors"].extend(console_errors[pre_errs:])
                await page.screenshot(path=str(out / f"chat_turn{i + 1}_response.png"), full_page=True)
            except Exception as e:  # noqa: BLE001
                turn["errors"].append(str(e)[:200])
            results.append(turn)
        await browser.close()

    (out / "chat_results.json").write_text(json.dumps(results, indent=2, default=str))
    failed = sum(1 for t in results if t["errors"])
    return f"chat: {len(results)} turn(s), {failed} with errors -> {out / 'chat_results.json'}"


VERBS = {"shot": shot, "console": console, "links": links, "deep": deep, "chat": chat}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: crawl_page.py <shot|console|links|deep|chat> <job-file>", file=sys.stderr)
        return 2
    verb, job_file = argv
    try:
        job = load_job(verb, Path(job_file))
    except JobError as err:
        print(f"crawl_page: {err}", file=sys.stderr)
        return 2
    fn = VERBS[verb]
    try:
        summary = asyncio.run(fn(job)) if asyncio.iscoroutinefunction(fn) else fn(job)
    except JobError as err:
        print(f"crawl_page: {err}", file=sys.stderr)
        return 2
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
