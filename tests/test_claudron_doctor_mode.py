"""`/claudna:claudron doctor`: the human front-end to `claudron doctor` (Claudron #190, part C).

The mode is prose an LLM executes, so these are text assertions, in the style of
`test_claudron_degradation.py`. They pin the four properties #190 asks for. Each
can rot on its own:

1. It is a MODE of the existing engine skill (a dispatch row and a depth file),
   not a new skill.
2. It gates on the capability the engine declares, never on the version.
3. Every check is the engine's. The only commands the mode runs are the ladder's
   probe, `claudron status` and `claudron doctor`, so it cannot grow a private
   check that drifts from the engine.
4. The one write, `--fix`, runs only after a read-only diagnosis and an explicit
   yes, and never in `--auto`. No allow rule the setup guide recommends approves it,
   so the permission prompt stays a second gate.
"""

from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "claudron"
SKILL = SKILL_DIR / "SKILL.md"
DOCTOR = SKILL_DIR / "doctor.md"
ENGINE = REPO_ROOT / "skills" / "_shared" / "claudron-engine.md"
SETUP_GUIDE = REPO_ROOT / "SETUP_GUIDE.md"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

FENCE = re.compile(r"```bash\n(.*?)```", re.S)
STEP = re.compile(r"^## (Step [^\n]*)$", re.M)


def doctor_text() -> str:
    return DOCTOR.read_text() if DOCTOR.is_file() else ""


def bash_commands(text: str) -> list[str]:
    """Every non-blank line inside a ```bash fence, in order."""
    return [line.strip() for block in FENCE.findall(text) for line in block.splitlines() if line.strip()]


def steps(text: str) -> list[tuple[str, str]]:
    """(heading, body) for each `## Step …` section, in order."""
    marks = list(STEP.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1), text[m.end() : end]))
    return out


def claudron_allow_rules() -> list[str]:
    """The `permissions.allow` entries SETUP_GUIDE §7.3 recommends for the engine."""
    section = SETUP_GUIDE.read_text().split("### 7.3", 1)[1].split("\n### ", 1)[0]
    return json.loads(re.search(r"```json\n(.*?)```", section, re.S).group(1))["permissions"]["allow"]


def approves(rule: str, command: str) -> bool:
    """Whether a `Bash(...)` allow rule covers a command, by the glob the plugin's
    PreToolUse hook applies: `*` matches anything, including flags that follow."""
    m = re.fullmatch(r"Bash\((.*)\)", rule)
    return bool(m) and fnmatch.fnmatchcase(command, m.group(1))


class TestItIsAModeNotASkill:
    def test_the_dispatch_table_routes_doctor_to_its_depth_file(self):
        assert re.search(r"^\| `doctor` \|.*\| `doctor\.md` \|$", SKILL.read_text(), re.M)
        assert DOCTOR.is_file()

    def test_the_argument_hint_names_the_verb(self):
        hint = re.search(r'^argument-hint: "(.*)"$', SKILL.read_text(), re.M).group(1)
        assert "doctor" in hint

    def test_no_separate_doctor_skill_exists(self):
        assert not (REPO_ROOT / "skills" / "doctor").exists()


class TestItGatesOnTheCapability:
    def test_the_gate_reads_data_capabilities_for_doctor(self):
        text = doctor_text()
        assert "data.capabilities" in text
        assert '"doctor"' in text

    def test_no_version_floor_anywhere_in_the_mode(self):
        # A floor such as `>= 0.5.2` cannot express the capability: a dev build
        # sorts before its own release (Claudron CLI_CONTRACT §Capability probe).
        text = doctor_text()
        assert text, "precondition: the depth file exists"
        assert not re.search(r"(>=|≥)\s*v?\d", text)
        # Nor can a floor with no comparison sign ("engine_version is 0.5.2 or later",
        # #353), so the mode names no version number at all. §3.1 is a section, not one.
        assert not re.search(r"\d+\.\d+", re.sub(r"§\d+(?:\.\d+)*", "§", text))

    def test_the_shared_contract_names_capabilities_as_the_feature_gate(self):
        section_1 = ENGINE.read_text().split("## 2.")[0]
        assert "data.capabilities" in section_1
        assert "is the capability probe" not in section_1


class TestEveryCheckIsTheEngines:
    def test_the_mode_runs_only_the_engines_doors(self):
        cmds = bash_commands(doctor_text())
        assert cmds, "precondition: the depth file shows the commands it runs"
        for cmd in cmds:
            assert re.match(r"^(command -v claudron$|claudron (status|doctor)\b)", cmd), cmd

    def test_the_envelope_table_asserts_the_doctor_payload(self):
        row = next(
            (line for line in ENGINE.read_text().splitlines() if line.startswith("| `doctor` → `doctor` |")),
            "",
        )
        for key in ("vault_format", "engine_format", "pending", "fixable"):
            assert key in row, key

    def test_the_validator_recognizes_a_doctor_invocation(self):
        from skill_checks import invokes_claudron

        assert invokes_claudron("claudron doctor --json")


class TestFixOnlyAfterAnExplicitYes:
    def test_the_diagnosis_runs_first_and_is_read_only(self):
        doctor_calls = [c for c in bash_commands(doctor_text()) if c.startswith("claudron doctor")]
        assert doctor_calls, "precondition: the mode runs claudron doctor"
        assert "--fix" not in doctor_calls[0]
        assert "--json" in doctor_calls[0]

    def test_fix_runs_only_in_the_step_that_asks_first(self):
        fix_steps = [
            heading for heading, body in steps(doctor_text()) if any("--fix" in c for c in bash_commands(body))
        ]
        assert len(fix_steps) == 1, fix_steps
        assert "confirm" in fix_steps[0].lower()

    def test_auto_never_runs_fix(self):
        auto = [body for heading, body in steps(doctor_text()) if "--auto" in heading]
        assert auto, "precondition: the mode defines its --auto behavior"
        assert "never runs `--fix`" in auto[0]
        assert not [c for c in bash_commands(auto[0]) if "--fix" in c]


class TestTheOneWriteKeepsItsConditions:
    """Review on #352: the tests above pin WHERE `--fix` may appear, not WHEN it runs.
    Deleting "only on an explicit yes" left every one of them green."""

    def test_the_write_step_asks_for_an_explicit_yes_and_refuses_without_a_human(self):
        body = next(b for h, b in steps(doctor_text()) if "confirm" in h.lower())
        assert "Only on an explicit yes" in body
        assert "no human in the session, do not run `--fix`" in body

    def test_home_and_root_are_named_in_both_branches_and_not_offered(self):
        text = doctor_text()
        assert text.count("home directory or `/`") == 2
        assert "do not offer it" in text

    def test_a_named_home_or_root_is_refused_before_any_engine_call(self):
        # `claudron status --json --vault <path>` already writes `.claudron/` into the
        # named directory, so the refusal has to come before that call, not after it.
        step1 = next(b for h, b in steps(doctor_text()) if h.startswith("Step 1"))
        para = next(p for p in step1.split("\n\n") if "explicit `--vault <path>`" in p)
        refusal = para.find("home directory or `/`")
        call = para.find("claudron status --json --vault <path>")
        assert refusal != -1, para
        assert call == -1 or refusal < call, para
        assert "stop" in para[refusal : refusal + 120], para


class TestNothingToApplyMeansNoD001:
    def test_empty_fixable_with_a_d001_is_not_nothing_to_apply(self):
        # Real 0.5.3: a vault that records an older format with nothing pending has
        # `fixable: []` and one D001, and `--fix` records the format and commits.
        step5 = next(b for h, b in steps(doctor_text()) if h.startswith("Step 5"))
        sentence = next(line for line in step5.splitlines() if "nothing to apply" in line)
        # The polarity is what matters: "nothing to apply, even with a `D001` finding"
        # names D001 too (#353).
        assert "there is no `D001` finding" in sentence, sentence


# The CLIs a private vault check would reach for: git, the engine's other verbs, and
# the file readers. Inline code that starts with one of these and has arguments is a
# command line; other inline code (fields, flags, codes) is not checked.
PROSE_COMMAND_HEADS = ("git", "claudron", "ls", "cat", "find", "stat", "test", "grep", "rg", "jq")


class TestTheProseKeepsItsRules:
    """#353: rules in the prose that an edit could delete, or break, with every test
    above still green. A line is pinned only where the edit changes what the skill does.
    The three sentences that describe a format-only `D001` (Step 4's row, Step 5, Step
    6's `data.repairs` line) stay unpinned on purpose: they describe what happens, and
    the stop rule pinned above is what protects the user."""

    def test_an_unknown_code_gets_the_engines_message_and_no_guess(self):
        # Claudron is adding D-codes (the per-host checks under Claudron #190), so this
        # rule decides what a user sees for a code the table does not know.
        step4 = next(b for h, b in steps(doctor_text()) if h.startswith("Step 4"))
        assert "For a code not in this table, show the engine's message verbatim" in step4
        assert "Never guess what it means" in step4

    def test_the_table_is_handed_to_the_user_not_run(self):
        # Without this sentence, the table's `claudron index` or `git rm --cached` read
        # as steps to run. The prose check below exempts the table because of it.
        step4 = next(b for h, b in steps(doctor_text()) if h.startswith("Step 4"))
        assert "This verb runs none of these commands itself; they are what to hand the user." in step4

    def test_the_prose_names_no_command_outside_the_engines_doors(self):
        # The fence check above cannot see a command written in prose: "run `git
        # check-ignore -v .claudron`" passed every test. Outside Step 4's hand-off table,
        # a command line in inline code is a door the mode runs, or the remedy Step 1 prints.
        body = re.sub(r"```.*?```", "", doctor_text(), flags=re.S)
        prose, in_step4 = [], False
        for line in body.splitlines():
            if line.startswith("## "):
                in_step4 = line.startswith("## Step 4")
            if not (in_step4 and line.startswith("|")):
                prose.append(line)
        commands = [
            span
            for span in re.findall(r"`([^`\n]+)`", "\n".join(prose))
            if len(span.split()) > 1 and span.split()[0] in PROSE_COMMAND_HEADS
        ]
        assert commands, "precondition: the prose names the doors the mode runs"
        for span in commands:
            assert re.match(r"^claudron (status|doctor)\b", span) or span == "claudron init <path> --personal", span


class TestNoAllowRuleApprovesTheWrite:
    """#353: `claudron doctor --fix` writes the vault, and the skill's question before it
    should not be its only gate. A `*` also matches the flags that follow, so
    `Bash(claudron *)`, `Bash(claudron doctor *)` and `Bash(claudron doctor --json *)`
    each approve `--fix` with no prompt."""

    WRITES = (
        "claudron doctor --fix --json",
        "claudron doctor --json --fix",
        "claudron doctor --json --vault /v --fix",
        "claudron sync --push",
        "claudron promote --to canonical <note>",
        "claudron plug",
    )

    def test_the_setup_guide_rules_leave_the_write_to_a_prompt(self):
        rules = claudron_allow_rules()
        # Positive control: the rules do match the reads, so a miss below is real.
        assert any(approves(r, "claudron doctor --json") for r in rules), rules
        assert any(approves(r, "claudron status --json") for r in rules), rules
        for cmd in self.WRITES:
            assert not [r for r in rules if approves(r, cmd)], cmd

    def test_the_grant_allowlist_accepts_the_guides_doctor_rule_and_no_wildcard(self):
        # The guide and the grant allowlist (#360) name one doctor form, whichever of
        # the two lands second.
        import skill_checks

        check = getattr(skill_checks, "check_settings_grants", None)
        if check is None:
            pytest.skip("the grant allowlist (#360) is not on this tree")
        doctor_rules = [r for r in claudron_allow_rules() if "claudron doctor" in r]
        assert doctor_rules == ["Bash(claudron doctor --json)"]
        assert check(doctor_rules) == []
        for rule in (
            "Bash(claudron *)",
            "Bash(claudron doctor *)",
            "Bash(claudron doctor --json *)",
            "Bash(claudron doctor:*)",
        ):
            assert check([rule]), rule
