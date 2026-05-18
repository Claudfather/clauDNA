"""Tests for skill_checks behavioral check functions.

Run: python3 -m pytest scripts/test_skill_checks.py -v

If pytest is not available, run as a script: python3 scripts/test_skill_checks.py
(prints PASS/FAIL per assertion).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make this directory importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_checks import (
    check_auto_no_ask_user,
    check_output_github_reference,
    check_structured_result_emission,
)


# ------------------------------------------------------------------
# check_structured_result_emission
# ------------------------------------------------------------------

def test_auto_without_structured_result_fails():
    fm = {"argument-hint": "[--auto] [scope]"}
    body = "# Test\n\nSkip Plan Mode and do things.\n"
    errors = check_structured_result_emission(fm, body)
    assert len(errors) == 1
    assert "structured-result" in errors[0]


def test_auto_with_structured_result_mention_passes():
    fm = {"argument-hint": "[--auto]"}
    body = "# Test\n\nEmit the structured result JSON block.\n"
    errors = check_structured_result_emission(fm, body)
    assert errors == []


def test_auto_with_hyphenated_structured_result_passes():
    fm = {"argument-hint": "[--auto]"}
    body = "# Test\n\nEmit the structured-result shape per §10.C.\n"
    errors = check_structured_result_emission(fm, body)
    assert errors == []


def test_auto_with_section_reference_passes():
    fm = {"argument-hint": "[--auto]"}
    body = "# Test\n\nSee `skills/_shared/orchestration-guide.md` §10.C for shape.\n"
    errors = check_structured_result_emission(fm, body)
    assert errors == []


def test_no_auto_skips_check():
    """Skills that don't declare --auto are not required to emit structured result."""
    fm = {"argument-hint": "[scope-path]"}
    body = "# Test\n\nNo structured result mention here.\n"
    errors = check_structured_result_emission(fm, body)
    assert errors == []


def test_non_string_argument_hint_skips_check():
    fm = {"argument-hint": None}
    body = "# Test\n"
    errors = check_structured_result_emission(fm, body)
    assert errors == []


# ------------------------------------------------------------------
# check_auto_no_ask_user (existing — regression coverage)
# ------------------------------------------------------------------

def test_auto_with_ask_user_question_fails():
    fm = {"argument-hint": "[--auto]"}
    body = "# Test\n\nUse AskUserQuestion to gather input.\n"
    errors = check_auto_no_ask_user(fm, body)
    assert len(errors) == 1


def test_no_auto_allows_ask_user_question():
    fm = {"argument-hint": "[scope-path]"}
    body = "# Test\n\nUse AskUserQuestion for clarification.\n"
    errors = check_auto_no_ask_user(fm, body)
    assert errors == []


# ------------------------------------------------------------------
# check_output_github_reference (existing — regression coverage)
# ------------------------------------------------------------------

def test_output_github_without_guide_reference_fails():
    fm = {"argument-hint": "[--output github]"}
    body = "# Test\n\nWrites issues.\n"
    errors = check_output_github_reference(fm, body)
    assert len(errors) == 1


def test_output_github_with_guide_reference_passes():
    fm = {"argument-hint": "[--output github]"}
    body = "# Test\n\nSee output-guide.md for format.\n"
    errors = check_output_github_reference(fm, body)
    assert errors == []


# ------------------------------------------------------------------
# Script runner (fallback if pytest unavailable)
# ------------------------------------------------------------------

def _run_as_script() -> int:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(_run_as_script())
