"""scripts/crawl_page.py: the qa crawl's bundled runner reads each step from a job file.

What is pinned here needs no browser: which jobs are refused, that every output
stays inside the crawl's scratch dir, and the `links` verb end to end against a
local HTTP server.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("crawl_page", REPO / "scripts" / "crawl_page.py")
crawl_page = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crawl_page)


def _job(scratch: Path, name: str, body: object) -> Path:
    jobs = scratch / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    path = jobs / name
    path.write_text(json.dumps(body))
    return path


def _browser_job(scratch: Path, verb: str) -> tuple[Path, Path]:
    jobs = {
        "shot": ({"url": "http://127.0.0.1:1/unused", "width": 10, "height": 10,
                  "output": "screenshots/page.png"}, "screenshots/page.png"),
        "console": ({"url": "http://127.0.0.1:1/unused", "output": "console/errors.json"}, "console/errors.json"),
        "deep": ({"url": "http://127.0.0.1:1/unused", "page_name": "page", "output_dir": "deep/page"}, "deep/page"),
        "chat": ({"base_url": "http://127.0.0.1:1/unused", "output_dir": "chat/page"}, "chat/page"),
    }
    body, output = jobs[verb]
    return _job(scratch, f"{verb}.json", body), scratch / output


def _block_playwright_imports(directory: Path) -> None:
    directory.mkdir()
    (directory / "sitecustomize.py").write_text(
        "import sys\n"
        "class BlockPlaywright:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname == 'playwright' or fullname.startswith('playwright.'):\n"
        "            raise ModuleNotFoundError('blocked for test', name=fullname)\n"
        "sys.meta_path.insert(0, BlockPlaywright())\n"
    )


def _fake_playwright_driver_failure(directory: Path) -> None:
    package = directory / "playwright"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "async_api.py").write_text(
        "class Manager:\n"
        "    async def __aenter__(self):\n"
        "        raise RuntimeError('fake driver startup failure')\n"
        "    async def __aexit__(self, *args):\n"
        "        return False\n"
        "def async_playwright():\n"
        "    return Manager()\n"
    )


def _run_cli(tmp_path: Path, verb: str, job: Path, *, pythonpath: Path | None = None):
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    return subprocess.run(
        [sys.executable, "-B", str(REPO / "scripts" / "crawl_page.py"), verb, str(job)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=10,
    )


def test_a_complete_job_loads_with_outputs_resolved_under_scratch(tmp_path):
    job = crawl_page.load_job("console", _job(tmp_path, "job-001.json", {"url": "http://x/", "output": "logs/a.json"}))
    assert job["output"] == str((tmp_path / "logs" / "a.json").resolve())


@pytest.mark.parametrize(
    "verb, body, says",
    [
        ("nope", {"url": "http://x/"}, "unknown verb"),
        ("shot", {"url": "http://x/", "width": 1}, "missing field"),
        ("console", ["not", "an", "object"], "JSON object"),
    ],
)
def test_a_malformed_job_is_refused_by_name(tmp_path, verb, body, says):
    with pytest.raises(crawl_page.JobError, match=says):
        crawl_page.load_job(verb, _job(tmp_path, "job-001.json", body))


@pytest.mark.parametrize("output", ["../escape.json", "/etc/escape.json", "logs/../../escape.json"])
def test_an_output_outside_the_scratch_dir_is_refused(tmp_path, output):
    scratch = tmp_path / "scratch"
    with pytest.raises(crawl_page.JobError, match="outside"):
        crawl_page.load_job("console", _job(scratch, "job-001.json", {"url": "http://x/", "output": output}))


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "ftp://x/"])
def test_only_http_urls_reach_the_browser(url):
    with pytest.raises(crawl_page.JobError, match="http"):
        crawl_page.page_url(url)


class _Site(BaseHTTPRequestHandler):
    def do_HEAD(self):  # noqa: N802 — http.server's method name
        self.send_response(200 if self.path == "/ok" else 404)
        self.end_headers()

    def log_message(self, *args):  # keep the test output clean
        pass


def test_links_records_each_status_and_skips_what_is_not_http(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright", None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        path = _job(
            tmp_path,
            "job-001.json",
            {"urls": [f"{base}/ok", f"{base}/gone", "mailto:someone@example.com"], "output": "research/links.json"},
        )
        assert crawl_page.main(["links", str(path)]) == 0
    finally:
        server.shutdown()
    results = json.loads((tmp_path / "research" / "links.json").read_text())
    assert results[f"{base}/ok"] == 200
    assert results[f"{base}/gone"] == 404
    assert results["mailto:someone@example.com"].startswith("skipped")


@pytest.mark.parametrize("verb", ["shot", "console", "deep", "chat"])
def test_browser_cli_reports_missing_playwright_without_traceback_or_outputs(tmp_path, verb):
    blocker = tmp_path / "blocker"
    _block_playwright_imports(blocker)
    job, output = _browser_job(tmp_path, verb)

    proc = _run_cli(tmp_path, verb, job, pythonpath=blocker)

    assert proc.returncode == 2
    assert "optional Python Playwright package is missing" in proc.stderr
    assert "requirements-crawl.txt" in proc.stderr
    assert "python3 -m playwright install chromium" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert proc.stdout == ""
    assert not output.exists()


def test_cli_driver_entry_failure_is_actionable_without_traceback_or_outputs(tmp_path):
    fake_package = tmp_path / "fake-package"
    _fake_playwright_driver_failure(fake_package)
    job, output = _browser_job(tmp_path, "shot")

    proc = _run_cli(tmp_path, "shot", job, pythonpath=fake_package)

    assert proc.returncode == 2
    assert "Playwright could not start its driver" in proc.stderr
    assert "requirements-crawl.txt" in proc.stderr
    assert "python3 -m playwright install chromium" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert proc.stdout == ""
    assert not output.exists()


class _MissingChromium:
    async def launch(self, **options):
        raise RuntimeError("Executable doesn't exist; browser not installed")


class _PlaywrightFixture:
    def __init__(self):
        self.chromium = _MissingChromium()


class _PlaywrightFixtureContext:
    async def __aenter__(self):
        return _PlaywrightFixture()

    async def __aexit__(self, *args):
        return False


@pytest.mark.parametrize("verb", ["shot", "console", "deep", "chat"])
def test_browser_startup_failure_is_actionable_and_creates_no_outputs(tmp_path, capsys, monkeypatch, verb):
    monkeypatch.setattr(crawl_page, "playwright_session", _PlaywrightFixtureContext)
    job, output = _browser_job(tmp_path, verb)

    result = crawl_page.main([verb, str(job)])
    captured = capsys.readouterr()

    assert result == 2
    assert "Playwright could not launch Chromium" in captured.err
    assert "requirements-crawl.txt" in captured.err
    assert "python3 -m playwright install chromium" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""
    assert not output.exists()


def test_navigation_failure_remains_a_crawl_finding_after_browser_startup(tmp_path, capsys, monkeypatch):
    class Page:
        def on(self, *args):
            pass

        async def goto(self, *args, **kwargs):
            raise RuntimeError("fake navigation failure")

    class Context:
        async def new_page(self):
            return Page()

    class Browser:
        async def new_context(self, **kwargs):
            return Context()

        async def close(self):
            pass

    class Chromium:
        async def launch(self, **kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

    class PlaywrightContext:
        async def __aenter__(self):
            return Playwright()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(crawl_page, "playwright_session", PlaywrightContext)
    job, output = _browser_job(tmp_path, "deep")

    result = crawl_page.main(["deep", str(job)])
    captured = capsys.readouterr()
    findings = json.loads((output / "page_results.json").read_text())

    assert result == 0
    assert "page did not load" in captured.out
    assert captured.err == ""
    assert "install" not in captured.out.lower()
    assert findings[0]["type"] == "page-load-error"
    assert findings[0]["detail"] == "fake navigation failure"


def test_a_refused_job_exits_2_and_says_why(tmp_path, capsys):
    path = _job(tmp_path, "job-001.json", {"url": "http://x/"})
    assert crawl_page.main(["console", str(path)]) == 2
    assert "missing field" in capsys.readouterr().err


def _garbage_server():
    """A TCP server that answers every request with a line that is not HTTP."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)

    def serve():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            conn.recv(4096)
            conn.sendall(b"NOT HTTP\r\n\r\n")
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    return sock


@pytest.mark.parametrize(
    "name", ["../x", "a/b", "..", ".", "a\\b", "", "/abs", "x/../../y", ".hidden", "-x", "a b", "a$(b)", "a`b`", "a'b", "a\x00b"]
)
def test_page_name_must_match_the_page_name_pattern(tmp_path, name):
    body = {"url": "http://x/", "page_name": name, "output_dir": "deep-crawl/p"}
    with pytest.raises(crawl_page.JobError, match="page_name"):
        crawl_page.load_job("deep", _job(tmp_path, "job-003.json", body))


def test_a_page_name_that_matches_the_pattern_loads(tmp_path):
    body = {"url": "http://x/", "page_name": "docs-api_v2.1", "output_dir": "deep-crawl/p"}
    assert crawl_page.load_job("deep", _job(tmp_path, "job-003.json", body))["page_name"] == "docs-api_v2.1"


def test_the_crawl_doc_states_the_runners_page_name_pattern():
    assert crawl_page.PAGE_NAME.pattern in (REPO / "skills" / "qa" / "deep-crawl.md").read_text()


def test_links_records_every_url_it_is_given(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    garbage = _garbage_server()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    urls = [
        f"{base}/ok",
        f"{base}/a b",
        f"{base}/a\nb",
        f"{base}/`x`/$(y)?q='\"",
        f"http://127.0.0.1:{garbage.getsockname()[1]}/x",
        "http://127.0.0.1:99999999999999999999/x",
    ]
    try:
        path = _job(tmp_path, "job-001.json", {"urls": urls, "output": "research/links.json"})
        assert crawl_page.main(["links", str(path)]) == 0
    finally:
        server.shutdown()
        garbage.close()
    results = json.loads((tmp_path / "research" / "links.json").read_text())
    assert set(results) == set(urls)
    assert results[urls[0]] == 200
    assert all(str(results[urls[i]]).startswith("error") for i in (1, 2, 4, 5))
