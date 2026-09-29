"""Host-portability checks (b)-(d) and the <claudna-root> definition (#336).

SKILL_CONTRACT §1.1 and §5.1. Check (a), the `_shared/` spelling, has its own
file (test_shared_paths.py); the end-to-end test here runs all four through
validate-skills.py, so the validator's two call sites are pinned too.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from skill_checks import (  # noqa: E402
    CLAUDNA_ROOT_BEGIN,
    CLAUDNA_ROOT_END,
    check_cwd_script_calls,
    check_plugin_cache_paths,
    check_plugin_variables,
    check_resolver_pointer,
)

CACHE = "~/.claude/plugins/cache/Claudfather/claudna/1.0.0/scripts/redact.py"


def _definition(path: Path) -> str:
    text = path.read_text()
    return text[text.index(CLAUDNA_ROOT_BEGIN) : text.index(CLAUDNA_ROOT_END) + len(CLAUDNA_ROOT_END)]


def test_the_run_time_copy_of_the_candidate_list_matches_the_contract() -> None:
    contract = _definition(REPO_ROOT / "SKILL_CONTRACT.md")
    assert "${CLAUDE_PLUGIN_ROOT}" in contract
    assert contract == _definition(REPO_ROOT / "skills" / "_shared" / "claudna-root.md")


@pytest.fixture
def skills(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    (root / "_shared").mkdir(parents=True)
    (root / "demo").mkdir()
    return root


def _file(skills: Path, rel: str, body: str) -> Path:
    path = skills / rel
    path.write_text(body)
    return path


@pytest.mark.parametrize(
    "body",
    [
        'Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/x.py"`, or elsewhere `<claudna-root>/scripts/x.py`.\n',
        '```\npython3 "${CLAUDE_PLUGIN_ROOT}/scripts/x.py"\n```\n\n(Unfilled? Use `<claudna-root>/scripts/x.py`.)\n',
        f"{CLAUDNA_ROOT_BEGIN}\n1. What Claude Code filled in for `${{CLAUDE_PLUGIN_ROOT}}`.\n{CLAUDNA_ROOT_END}\n",
    ],
)
def test_a_plugin_variable_passes_in_a_skill_md_beside_its_fallback(skills: Path, body: str) -> None:
    md_file = _file(skills, "demo/SKILL.md", body)
    assert check_plugin_variables(body, md_file, skills) == []


@pytest.mark.parametrize(
    ("rel", "body", "expected"),
    [
        (
            "demo/SKILL.md",
            'Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/x.py"`.\n',
            "demo/SKILL.md:1: `${CLAUDE_PLUGIN_ROOT}` has no",
        ),
        (
            "demo/SKILL.md",
            '```\n"${CLAUDE_SKILL_DIR}/x"\n```\n\nNo fallback here.\n',
            "demo/SKILL.md:2: `${CLAUDE_SKILL_DIR}` has no",
        ),
        (
            "demo/topic.md",
            "`${CLAUDE_PLUGIN_ROOT}/scripts/x.py` or `<claudna-root>`\n",
            "demo/topic.md:1: `${CLAUDE_PLUGIN_ROOT}` is filled in only",
        ),
        (
            "_shared/doc.md",
            "`${CLAUDE_PLUGIN_ROOT}/scripts/x.py`\n",
            "_shared/doc.md:1: `${CLAUDE_PLUGIN_ROOT}` is filled in only",
        ),
    ],
)
def test_a_plugin_variable_fails_anywhere_else(skills: Path, rel: str, body: str, expected: str) -> None:
    md_file = _file(skills, rel, body)
    [error] = check_plugin_variables(body, md_file, skills)
    assert error.startswith(expected)


def test_a_cache_path_passes_only_in_the_definition_or_a_claude_code_only_skill(skills: Path) -> None:
    body = f"Scrub with {CACHE}.\n"
    md_file = _file(skills, "demo/SKILL.md", body)
    [error] = check_plugin_cache_paths(body, md_file, skills, {})
    assert error.startswith("demo/SKILL.md:1: a Claude Code plugin-cache path")
    assert check_plugin_cache_paths(body, md_file, skills, {"hosts": ["claude-code"]}) == []
    assert len(check_plugin_cache_paths(body, md_file, skills, {"hosts": ["claude-code", "cursor"]})) == 1
    shared = _file(skills, "_shared/doc.md", f"{CLAUDNA_ROOT_BEGIN}\n4. {CACHE}\n{CLAUDNA_ROOT_END}\n{body}")
    [error] = check_plugin_cache_paths(shared.read_text(), shared, skills, None)
    assert error.startswith("_shared/doc.md:4:")


def test_a_working_directory_script_call_passes_only_in_a_repo_clone_skill(skills: Path) -> None:
    body = 'Run `python3 scripts/redact.py out.txt`; never `python3 "<claudna-root>/scripts/redact.py"` wrongly.\n'
    md_file = _file(skills, "demo/SKILL.md", body)
    [error] = check_cwd_script_calls(body, md_file, skills, {})
    assert error.startswith("demo/SKILL.md:1: `python3 scripts/redact.py` runs from the working directory")
    assert check_cwd_script_calls(body, md_file, skills, {"requires-context": "repo-clone"}) == []
    mention = "The validator (`scripts/validate-skills.py`) enforces this.\n"
    assert check_cwd_script_calls(mention, md_file, skills, {}) == []


def test_a_file_using_the_placeholder_points_at_its_definition(skills: Path) -> None:
    body = "x\nForward: Read <claudna-root>/skills/_shared/guide.md\n"
    md_file = _file(skills, "demo/SKILL.md", body)
    [error] = check_resolver_pointer(body, md_file, skills)
    assert error.startswith("demo/SKILL.md:2: uses `<claudna-root>` but never points at `claudna-root.md`")
    pointed = body + "Fill it in per `../_shared/claudna-root.md` before sending.\n"
    assert check_resolver_pointer(pointed, md_file, skills) == []
    assert check_resolver_pointer("no placeholder here\n", md_file, skills) == []


def _findings(tree: Path) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    env["SCHEMA_DRIFT_OFFLINE"] = "1"
    run = subprocess.run(
        [sys.executable, str(tree / "scripts" / "validate-skills.py")], capture_output=True, text=True, env=env
    )
    assert run.returncode in (0, 1), run.stdout + run.stderr
    return [line.strip() for line in run.stdout.splitlines() if line.startswith("    - ")]


PORTABILITY = (
    "is not relative to this file",
    "is anchored to a root no other host sets",
    "names nothing under skills/_shared/",
    "is filled in only in a SKILL.md body",
    "fallback on its line",
    "a Claude Code plugin-cache path",
    "runs from the working directory",
    "never points at `claudna-root.md`",
)


def test_the_validator_reports_each_check_once_from_both_of_its_loops(tmp_path: Path) -> None:
    # Only scripts/ and skills/ are copied, so repo-wide gates may report the
    # files left behind; the test compares findings, not exit codes.
    for name in ("scripts", "skills"):
        shutil.copytree(REPO_ROOT / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    clean = _findings(tmp_path)
    assert not [f for f in clean if any(p in f for p in PORTABILITY)], clean

    railway = tmp_path / "skills" / "railway" / "SKILL.md"
    text = railway.read_text()
    assert text.count("`../_shared/infra-cli-contract.md`") == 1
    railway.write_text(
        text.replace("`../_shared/infra-cli-contract.md`", "`skills/_shared/infra-cli-contract.md`")
        + f"\nScrub with {CACHE}.\nOr run `python3 scripts/redact.py out.txt`.\nForward <claudna-root>/skills/x.\n"
    )
    contract = tmp_path / "skills" / "_shared" / "infra-cli-contract.md"
    contract.write_text(contract.read_text() + '\nRun `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/redact.py" f`.\n')

    new = [f for f in _findings(tmp_path) if f not in clean]
    expected = [
        ("railway/SKILL.md:", "`skills/_shared/infra-cli-contract.md` is not relative to this file"),
        ("railway/SKILL.md:", "a Claude Code plugin-cache path"),
        ("railway/SKILL.md:", "`python3 scripts/redact.py` runs from the working directory"),
        ("_shared/infra-cli-contract.md:", "`${CLAUDE_PLUGIN_ROOT}` is filled in only in a SKILL.md body"),
        ("railway/SKILL.md:", "uses `<claudna-root>` but never points at `claudna-root.md`"),
    ]
    for where, what in expected:
        assert sum(where in f and what in f for f in new) == 1, (where, what, new)
    assert len(new) == len(expected), new
