#!/usr/bin/env python3
"""Routing evals: does a plain prompt make Claude pick the skill we expect?

Runs the live layer of ``tests/fixtures/routing-matrix.yaml`` headless: each
row marked ``eval: true`` (``--all`` for every row), and each ``control``, an
utterance that must resolve to no clauDNA skill. One attempt is one isolated
``claude -p`` run (:func:`build_command`, :func:`child_env`) whose only tool is
``Skill``, so the pick is read from the transcript's first Skill call, not
judged. A case passes when at least ``--pass`` of ``--runs`` attempts pick
right. A row marked ``known_failure: <why>`` reports XFAIL when it fails and
XPASS when it passes (time to drop the marker); neither fails the run.

Exit 0 when nothing unexpected failed, 1 when a case failed or the run
stopped early (budget, or repeated setup errors), 2 when ``claude`` can't be run.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX = REPO_ROOT / "tests" / "fixtures" / "routing-matrix.yaml"
PREFIX = "claudna:"
#: The router under test, by alias so it tracks the current Sonnet. Haiku is a
#: useful probe (``--model haiku``) but no gate: it hands rows Sonnet routes
#: right to Claude Code's built-in skills or to none.
DEFAULT_MODEL = "sonnet"
TIMEOUT_S = 90  #: one attempt is one model turn; a run that takes longer is stuck
#: Per-attempt spend cap passed to ``claude`` (lowered to what the run's budget has left).
ATTEMPT_CAP_USD = 0.25
#: Errored attempts in a row that end the run: by then it's setup (auth, network), not routing.
MAX_ERRORS_IN_A_ROW = 3
#: Environment the child inherits by name or prefix; everything else is dropped.
ENV_ALLOW = ("HOME", "PATH", "LANG", "LC_ALL", "TERM", "USER", "TMPDIR", "CLAUDE_CONFIG_DIR",
             "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
             "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
             "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS")
ENV_ALLOW_PREFIXES = ("ANTHROPIC_", "AWS_", "GOOGLE_", "CLOUD_ML_")  # API, Bedrock and Vertex credentials

#: ``(argv, env, cwd) -> (stdout, stderr)``: how one attempt is run (a fake in tests).
Runner = Callable[[list, Mapping[str, str], Path], "tuple[str, str]"]


@dataclass(frozen=True)
class Case:
    utterance: str
    expect: str | None  #: the skill's bare name; None for a control (no clauDNA skill)
    mode: str | None = None  #: recorded in the results, not judged
    known_failure: str | None = None  #: why this row is expected to fail, until it's fixed


@dataclass(frozen=True)
class Attempt:
    skill: str | None  #: the first Skill call's skill, as Claude wrote it
    args: str | None  #: its args, recorded (the mode, when the skill takes one)
    cost_usd: float
    error: str | None = None  #: why the transcript can't be judged, if it can't


@dataclass(frozen=True)
class Verdict:
    case: Case
    attempts: list
    passed: bool

    @property
    def status(self) -> str:
        if self.case.known_failure:
            return "XPASS" if self.passed else "XFAIL"
        return "PASS" if self.passed else "FAIL"


def load_cases(path: Path | None = None, *, all_rows: bool = False) -> list[Case]:
    """The rows to evaluate (``eval: true`` ones unless ``all_rows``), then the controls."""
    doc = yaml.safe_load((MATRIX if path is None else path).read_text())
    rows = [r for r in doc.get("rows", []) if all_rows or r.get("eval") is True]
    cases = [Case(r["utterance"], r["expect"], r.get("mode"), r.get("known_failure")) for r in rows]
    return cases + [Case(c["utterance"], None) for c in doc.get("controls", [])]


def build_command(utterance: str, *, claude_bin: str, model: str, cap_usd: float = ATTEMPT_CAP_USD) -> list[str]:
    """One isolated attempt: this checkout's plugin and no other settings, MCP or tools but Skill.

    The same isolation the session store's summarizer gives its child
    (``lib/claudna/session_store/summarize.py``), except the one tool it keeps.
    """
    return [claude_bin, "-p", utterance, "--plugin-dir", str(REPO_ROOT), "--setting-sources", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--tools", "Skill",
            "--max-turns", "1", "--max-budget-usd", f"{cap_usd:.2f}", "--no-session-persistence",
            "--output-format", "stream-json", "--verbose", "--model", model]


def child_env(base: Mapping[str, str], state_dir: Path) -> dict[str, str]:
    """The allowlisted environment, marked as a clauDNA child so the session store stays out of it.

    ``CLAUDNA_SESSION_CHILD`` (``session_store/paths.py``) makes the store's
    hooks record nothing and start no worker; the scratch ``CLAUDNA_STATE_DIR``
    is the backstop. The SessionStart briefing still runs: users see it, so the
    router should too.
    """
    env = {k: v for k, v in base.items() if k in ENV_ALLOW or k.startswith(ENV_ALLOW_PREFIXES)}
    env["CLAUDNA_SESSION_CHILD"] = "1"
    env["CLAUDNA_STATE_DIR"] = str(state_dir)
    return env


def parse_stream(text: str) -> Attempt:
    """The first Skill call in a stream-json transcript, and the run's cost.

    Non-JSON lines are dropped (a CLI can print warnings on stdout). A run
    that hit ``--max-turns`` is normal here: one turn is all the pick needs.
    """
    records = []
    for line in text.splitlines():
        if line.startswith("{"):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    call = next((block.get("input") or {} for rec in records if rec.get("type") == "assistant"
                 for block in (rec.get("message") or {}).get("content") or []
                 if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill"),
                {})
    skill, args = call.get("skill"), call.get("args")
    result = next((r for r in records if r.get("type") == "result"), None)
    if result is None:
        return Attempt(skill, args, 0.0, error="no result record: the run died or the output isn't stream-json")
    error = None
    if result.get("is_error") and result.get("subtype") != "error_max_turns":
        error = f"run failed: {result.get('subtype')}"
    return Attempt(skill, args, float(result.get("total_cost_usd") or 0.0), error)


def skill_names() -> frozenset[str]:
    """clauDNA's skills by bare name, so a pick written without the prefix is still recognised."""
    return frozenset(p.name for p in (REPO_ROOT / "skills").iterdir() if (p / "SKILL.md").is_file())


def picked(attempt: Attempt, case: Case, ours: frozenset[str] = frozenset()) -> bool:
    """Did this attempt resolve the way ``case`` expects? ``ours``: clauDNA's bare skill names."""
    if attempt.error is not None:
        return False
    skill = attempt.skill or ""
    bare = skill[len(PREFIX):] if skill.startswith(PREFIX) else skill
    if case.expect is None:  # a control: any clauDNA skill is a wrong pick (another plugin's isn't ours to judge)
        return not (skill.startswith(PREFIX) or bare in ours)
    return bare == case.expect


def _text(stream) -> str:
    return stream.decode("utf-8", "replace") if isinstance(stream, bytes) else stream or ""


def subprocess_runner(argv: list, env: Mapping[str, str], cwd: Path) -> tuple[str, str]:
    try:
        proc = subprocess.run(argv, env=dict(env), cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as exc:  # its output is bytes even with text=True
        return _text(exc.stdout), f"timed out after {TIMEOUT_S}s " + _text(exc.stderr)
    return proc.stdout, proc.stderr


def evaluate(cases: list[Case], *, runs: int, need: int, model: str, claude_bin: str, budget_usd: float,
             runner: Runner = subprocess_runner, base_env: Mapping[str, str] | None = None,
             log: Callable[[str], None] = print,
             on_verdict: Callable[[Verdict], None] = lambda _v: None) -> tuple[list[Verdict], float, bool]:
    """Run every case ``runs`` times; ``(verdicts, spent, stopped early)``.

    Each attempt runs in an empty scratch directory, so where the script is
    run from never reaches the router. A run stops early when the budget is
    spent, or after :data:`MAX_ERRORS_IN_A_ROW` errored attempts (a setup
    failure, named with the child's stderr). ``on_verdict`` gets each case as
    it finishes, so a run killed part way keeps what it had.
    """
    verdicts, spent, errors_in_a_row, ours = [], 0.0, 0, skill_names()
    with tempfile.TemporaryDirectory(prefix="claudna-routing-eval-") as scratch:
        state, work = Path(scratch) / "state", Path(scratch) / "work"
        work.mkdir()
        env = child_env(os.environ if base_env is None else base_env, state)
        for case in cases:
            attempts = []
            for _ in range(runs):
                if spent >= budget_usd:
                    log(f"budget of ${budget_usd:.2f} spent: stopping")
                    return verdicts, spent, True
                cap = max(0.01, min(ATTEMPT_CAP_USD, budget_usd - spent))
                out, err = runner(build_command(case.utterance, claude_bin=claude_bin, model=model, cap_usd=cap),
                                  env, work)
                attempt = parse_stream(out)
                if attempt.error is not None and err.strip():
                    attempt = Attempt(attempt.skill, attempt.args, attempt.cost_usd,
                                      f"{attempt.error}; stderr: {err.strip().splitlines()[-1][:200]}")
                spent += attempt.cost_usd
                attempts.append(attempt)
                errors_in_a_row = errors_in_a_row + 1 if attempt.error else 0
                if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                    log(f"{errors_in_a_row} attempts in a row errored, last: {attempt.error}. Stopping: "
                        "check that claude runs and is logged in (or ANTHROPIC_API_KEY is set)")
                    return verdicts, spent, True
            verdict = Verdict(case, attempts, sum(picked(a, case, ours) for a in attempts) >= need)
            verdicts.append(verdict)
            on_verdict(verdict)
            got = ", ".join(a.error or a.skill or "(none)" for a in attempts)
            log(f"{verdict.status:<5}  {case.expect or '(control)':<16} {case.utterance!r} -> {got}")
    return verdicts, spent, False


def claude_version(claude_bin: str) -> str | None:
    try:
        out = subprocess.run([claude_bin, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--pass", dest="need", type=int, default=2, help="attempts that must pick right (default 2)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--all", action="store_true", help="every matrix row, not just the eval: true ones")
    ap.add_argument("-k", dest="match", help="only cases whose utterance or expected skill contains this")
    ap.add_argument("--out", type=Path, help="write one JSON line per case here")
    ap.add_argument("--budget-usd", type=float, default=2.0, help="stop once the runs have cost this much")
    ap.add_argument("--claude-bin", default="claude")
    args = ap.parse_args(argv)
    if not 1 <= args.need <= args.runs:
        ap.error("--pass must be between 1 and --runs")
    cases = [c for c in load_cases(all_rows=args.all)
             if not args.match or args.match in c.utterance or args.match in (c.expect or "")]
    if not cases:
        ap.error(f"no case matches -k {args.match!r}")

    claude_bin = shutil.which(args.claude_bin)
    version = claude_version(claude_bin) if claude_bin else None
    if version is None:
        print(f"error: can't run {args.claude_bin!r}: install Claude Code, or pass --claude-bin", file=sys.stderr)
        return 2
    print(f"{len(cases)} cases x {args.runs} runs on {args.model}, {version}")
    with (args.out.open("w", encoding="utf-8") if args.out else open(os.devnull, "w")) as fh:
        def record(v: Verdict) -> None:
            fh.write(json.dumps({"claude": version, "model": args.model, "status": v.status, **asdict(v)}) + "\n")
            fh.flush()

        verdicts, spent, stopped = evaluate(cases, runs=args.runs, need=args.need, model=args.model,
                                            claude_bin=claude_bin, budget_usd=args.budget_usd, on_verdict=record)
    counts = {s: sum(v.status == s for v in verdicts) for s in ("PASS", "FAIL", "XFAIL", "XPASS")}
    print(", ".join(f"{n} {s}" for s, n in counts.items() if n) + f"; ${spent:.2f} spent")
    if counts["XPASS"]:
        print("a known_failure row passed: drop its marker in the matrix if it holds")
    return 1 if counts["FAIL"] or stopped else 0


if __name__ == "__main__":
    sys.exit(main())
