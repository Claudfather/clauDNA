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
   yes, and never in `--auto`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "claudron"
SKILL = SKILL_DIR / "SKILL.md"
DOCTOR = SKILL_DIR / "doctor.md"
ENGINE = REPO_ROOT / "skills" / "_shared" / "claudron-engine.md"

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
