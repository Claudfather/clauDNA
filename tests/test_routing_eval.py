"""Tests for the routing-eval harness (``scripts/routing_eval.py``), with no model calls.

Every case here drives the harness with canned stream-json, through a fake
runner or a fake ``claude`` executable, so CI exercises the parser, the
verdict rule, the isolation flags, the budget stop and the exit codes for
free. The live run is ``make routing-eval``, on demand or by PR label.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import routing_eval as re_  # noqa: E402


def stream(*skills, cost=0.02, subtype="error_max_turns", is_error=True) -> str:
    """A stream-json transcript whose assistant calls Skill with each of ``skills`` in turn."""
    lines = ["warning: something printed on stdout"]
    lines.append(json.dumps({"type": "system", "subtype": "init", "tools": ["Skill"]}))
    for skill in skills:
        content = [{"type": "text", "text": "Let me use a skill."},
                   {"type": "tool_use", "name": "Skill", "input": {"skill": skill, "args": "x"}}]
        lines.append(json.dumps({"type": "assistant", "message": {"content": content}}))
    if not skills:
        lines.append(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "391"}]}}))
    lines.append(json.dumps({"type": "result", "subtype": subtype, "is_error": is_error, "total_cost_usd": cost}))
    return "\n".join(lines) + "\n"


def scripted(*outputs):
    """A runner that answers successive attempts with ``outputs`` and records each call."""
    calls = []
    queue = list(outputs)

    def run(argv, env, cwd):
        calls.append((argv, dict(env), cwd))
        return queue.pop(0), ""

    run.calls = calls
    return run


MODAL = re_.Case("deploy my modal app", "modal", "deploy")
CONTROL = re_.Case("what is 17 times 23?", None)


def _evaluate(cases, runner, *, runs=3, need=2, budget=10.0, env=None):
    return re_.evaluate(cases, runs=runs, need=need, model="m", claude_bin="claude", budget_usd=budget,
                        runner=runner, base_env=env or {"HOME": "/h", "PATH": "/bin"}, log=lambda _: None)


# --- parsing -------------------------------------------------------------------------------------------


def test_parse_takes_the_first_skill_call_and_the_cost():
    attempt = re_.parse_stream(stream("claudna:modal", "claudna:audit", cost=0.03))
    assert (attempt.skill, attempt.args, attempt.cost_usd, attempt.error) == ("claudna:modal", "x", 0.03, None)


def test_parse_reports_no_pick_when_nothing_was_called():
    attempt = re_.parse_stream(stream())
    assert attempt.skill is None and attempt.error is None


def test_parse_treats_a_max_turns_stop_as_normal_but_a_failed_run_as_an_error():
    assert re_.parse_stream(stream("claudna:modal", subtype="error_max_turns")).error is None
    assert re_.parse_stream(stream("claudna:modal", subtype="success", is_error=False)).error is None
    assert "error_during_execution" in re_.parse_stream(stream(subtype="error_during_execution")).error


@pytest.mark.parametrize("out", ["", "not json at all\n", '{"type": "assistant"\n'])
def test_parse_without_a_result_record_is_an_error_not_a_pick(out):
    attempt = re_.parse_stream(out)
    assert attempt.error and "no result record" in attempt.error


# --- verdicts ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("skill,ok", [("claudna:modal", True), ("modal", True), ("claudna:railway", False),
                                      (None, False)])
def test_a_row_passes_on_its_skill_with_or_without_the_prefix(skill, ok):
    assert re_.picked(re_.Attempt(skill, None, 0.0), MODAL) is ok


@pytest.mark.parametrize("skill,ok", [(None, True), ("other-plugin:thing", True), ("security-review", True),
                                      ("claudna:audit", False), ("audit", False)])
def test_a_control_passes_unless_a_claudna_skill_fires_prefixed_or_bare(skill, ok):
    assert re_.picked(re_.Attempt(skill, None, 0.0), CONTROL, frozenset({"audit", "session"})) is ok


def test_skill_names_are_the_skill_directories():
    names = re_.skill_names()
    assert {"audit", "session", "modal"} <= names and "_shared" not in names


def test_an_errored_attempt_never_counts_as_a_pick_even_for_a_control():
    assert not re_.picked(re_.Attempt(None, None, 0.0, error="run failed"), CONTROL)


def test_a_known_failure_reports_xfail_or_xpass_never_fail():
    known = re_.Case("step back", "ironclad", known_failure="misroutes today")
    assert re_.Verdict(known, [], False).status == "XFAIL"
    assert re_.Verdict(known, [], True).status == "XPASS"
    assert re_.Verdict(MODAL, [], False).status == "FAIL"


def test_two_of_three_passes_and_one_of_three_fails():
    two = scripted(stream("claudna:modal"), stream("claudna:railway"), stream("claudna:modal"))
    one = scripted(stream("claudna:modal"), stream("claudna:railway"), stream())
    assert _evaluate([MODAL], two)[0][0].passed
    assert not _evaluate([MODAL], one)[0][0].passed


# --- isolation -----------------------------------------------------------------------------------------


def test_each_attempt_runs_isolated_with_only_the_skill_tool():
    runner = scripted(stream("claudna:modal"))
    _evaluate([MODAL], runner, runs=1, need=1)
    argv, _, cwd = runner.calls[0]
    assert cwd.name == "work" and not any(cwd.iterdir() if cwd.exists() else [])  # an empty scratch dir
    flags = dict(zip(argv, argv[1:]))
    assert argv[:3] == ["claude", "-p", MODAL.utterance]
    assert flags["--plugin-dir"] == str(re_.REPO_ROOT)
    assert flags["--setting-sources"] == ""
    assert flags["--tools"] == "Skill" and flags["--max-turns"] == "1"
    assert "--strict-mcp-config" in argv and flags["--output-format"] == "stream-json"


def test_the_child_env_is_an_allowlist_with_a_scratch_state_dir():
    caller = {"HOME": "/h", "PATH": "/bin", "ANTHROPIC_API_KEY": "k", "CLAUDE_CODE_SESSION_ID": "parent",
              "CLAUDNA_HARVEST": "1", "CLAUDRON_VAULT_PATH": "/vault", "https_proxy": "http://p",
              "AWS_REGION": "us-east-1", "CLAUDE_CONFIG_DIR": "/cfg", "SECRET_TOKEN": "nope"}
    runner = scripted(stream("claudna:modal"))
    _evaluate([MODAL], runner, runs=1, need=1, env=caller)
    env = runner.calls[0][1]
    assert set(env) == {"HOME", "PATH", "ANTHROPIC_API_KEY", "https_proxy", "AWS_REGION", "CLAUDE_CONFIG_DIR",
                        "CLAUDNA_SESSION_CHILD", "CLAUDNA_STATE_DIR"}
    assert env["CLAUDNA_SESSION_CHILD"] == "1"  # the store records nothing and starts no worker
    assert env["CLAUDNA_STATE_DIR"] != str(Path.home() / ".claudna")


# --- budget and cases ----------------------------------------------------------------------------------


def test_the_budget_stops_the_run_and_caps_each_attempt_at_what_is_left():
    runner = scripted(*[stream("claudna:modal", cost=0.2)] * 6)
    verdicts, spent, stopped = _evaluate([MODAL, MODAL], runner, budget=0.5)
    assert stopped and spent == pytest.approx(0.6)
    assert len(runner.calls) == 3 and len(verdicts) == 1  # the first case finished; the second never started
    caps = [dict(zip(argv, argv[1:]))["--max-budget-usd"] for argv, _, _ in runner.calls]
    assert caps == ["0.25", "0.25", "0.10"]  # the cap, then what is left


def test_repeated_errors_stop_the_run_and_name_the_childs_stderr():
    calls = []

    def broken(argv, env, cwd):
        calls.append(argv)
        return "", "Invalid API key: please run /login"

    logs = []
    verdicts, _, stopped = re_.evaluate([MODAL, MODAL], runs=3, need=2, model="m", claude_bin="claude",
                                        budget_usd=10, runner=broken, base_env={}, log=logs.append)
    assert stopped and len(calls) == re_.MAX_ERRORS_IN_A_ROW and verdicts == []
    assert "Invalid API key" in logs[-1]


def test_each_verdict_is_handed_over_as_it_finishes():
    seen = []
    runner = scripted(*[stream("claudna:modal")] * 3, *[stream("claudna:neon", cost=5)] * 3)
    re_.evaluate([MODAL, MODAL], runs=3, need=2, model="m", claude_bin="claude", budget_usd=1.0, runner=runner,
                 base_env={}, log=lambda _: None, on_verdict=seen.append)
    assert len(seen) == 1 and seen[0].passed  # the second case hit the budget; the first was kept


def test_a_timed_out_run_keeps_what_it_streamed(monkeypatch):
    import subprocess

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("claude", 90, output=stream("claudna:modal").encode(), stderr=b"slow")

    monkeypatch.setattr(subprocess, "run", timeout)
    out, err = re_.subprocess_runner(["claude"], {}, Path("."))
    assert re_.parse_stream(out).skill == "claudna:modal" and err.startswith("timed out")


def test_load_cases_takes_eval_rows_then_controls(tmp_path):
    matrix = tmp_path / "m.yaml"
    matrix.write_text(
        "rows:\n"
        "  - {utterance: a, keywords: [a], expect: modal, phase: P2, eval: true}\n"
        "  - {utterance: b, keywords: [b], expect: neon, phase: P2}\n"
        "controls:\n  - {utterance: c}\n")
    assert re_.load_cases(matrix) == [re_.Case("a", "modal"), re_.Case("c", None)]
    matrix.write_text(matrix.read_text().replace("eval: true}", "eval: true, known_failure: why}"))
    assert re_.load_cases(matrix)[0].known_failure == "why"
    assert [c.utterance for c in re_.load_cases(matrix, all_rows=True)] == ["a", "b", "c"]


def test_the_real_matrix_has_about_ten_eval_rows_and_controls_whose_skills_exist():
    cases = re_.load_cases()
    rows = [c for c in cases if c.expect is not None]
    assert 8 <= len(rows) <= 15 and len(cases) > len(rows)
    for case in rows:
        assert (REPO_ROOT / "skills" / case.expect / "SKILL.md").is_file(), case


# --- the CLI, end to end through a fake claude ---------------------------------------------------------


def _fake_claude(tmp_path: Path, transcript: str) -> Path:
    canned = tmp_path / "transcript.jsonl"
    canned.write_text(transcript)
    script = tmp_path / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if '--version' in sys.argv: print('9.9.9 (Claude Code)'); sys.exit(0)\n"
        f"sys.stdout.write(open({str(canned)!r}).read()); sys.exit(1)\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_main_writes_results_and_exits_by_verdict(tmp_path, monkeypatch, capsys):
    matrix = tmp_path / "m.yaml"
    matrix.write_text("rows:\n  - {utterance: a, keywords: [a], expect: modal, phase: P2, eval: true}\n")
    monkeypatch.setattr(re_, "MATRIX", matrix)
    out = tmp_path / "results.jsonl"
    assert re_.main(["--claude-bin", str(_fake_claude(tmp_path, stream("claudna:modal"))), "--out", str(out)]) == 0
    row = json.loads(out.read_text())
    assert row["claude"] == "9.9.9 (Claude Code)" and row["passed"] is True and len(row["attempts"]) == 3
    assert "1 PASS;" in capsys.readouterr().out
    assert re_.main(["--claude-bin", str(_fake_claude(tmp_path, stream("claudna:neon")))]) == 1
    matrix.write_text(matrix.read_text().replace("eval: true}", "eval: true, known_failure: why}"))
    assert re_.main(["--claude-bin", str(_fake_claude(tmp_path, stream("claudna:neon")))]) == 0  # XFAIL
    assert "1 XFAIL" in capsys.readouterr().out


def test_k_filters_by_utterance_or_skill(tmp_path, monkeypatch, capsys):
    matrix = tmp_path / "m.yaml"
    matrix.write_text("rows:\n  - {utterance: deploy it, keywords: [a], expect: modal, phase: P2, eval: true}\n"
                      "  - {utterance: query it, keywords: [b], expect: neon, phase: P2, eval: true}\n")
    monkeypatch.setattr(re_, "MATRIX", matrix)
    fake = str(_fake_claude(tmp_path, stream("claudna:neon")))
    assert re_.main(["--claude-bin", fake, "-k", "ne"]) == 0
    assert "1 cases" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        re_.main(["--claude-bin", fake, "-k", "nothing-matches"])


def test_main_exits_2_when_claude_cannot_run(capsys):
    assert re_.main(["--claude-bin", "/nonexistent/claude"]) == 2
    assert "can't run" in capsys.readouterr().err


def test_main_rejects_a_pass_rule_it_cannot_meet():
    with pytest.raises(SystemExit):
        re_.main(["--runs", "2", "--pass", "3"])
