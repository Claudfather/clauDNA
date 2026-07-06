---
title: Phase 4 — claudlobby autonomous-runner Wrapper
type: plan
status: mostly complete (Claudlobby-side); validation deployment pending — Claudlobby#294
owner: chrisrogers37
created: 2026-05-17
tags: [autonomous-mode, phase-4, claudlobby, autonomous-runner, wrapper]
repos: [Claudlobby]
links: []
---

> **Mostly ✅ COMPLETE, Claudlobby-side (verified 2026-07-06 docs audit).** Every deliverable in this plan lives in the sibling Claudlobby repo, not clauDNA — ordinarily **UNVERIFIABLE FROM THIS REPO ALONE**. A live local checkout was available at `/Users/chris/Projects/claudlobby` (real git history, GitHub remote `Claudfather/Claudlobby`) for this audit; treat the findings below as a point-in-time spot-check, not something clauDNA's own CI/repo verifies going forward.
>
> **Timeline:** clauDNA Phases 1-3 (the prerequisite contract this phase depends on) merged 2026-05-17/18 (`d46699c`, `31accf6`, `765b2c7`). Claudlobby Phase 4 **Part A** (Tasks 1-5, schema layer — [Claudfather/Claudlobby#278](https://github.com/Claudfather/Claudlobby/issues/278)) and **Part B** (Tasks 6-9 + 11, skill body + docs — [Claudfather/Claudlobby#279](https://github.com/Claudfather/Claudlobby/issues/279)) both merged the same day, 2026-05-18 (`d98e7e0`, `a541004`) — within hours of clauDNA Phase 3 landing. **Task 10 (end-to-end validation deployment)** was deliberately descoped into its own tracked issue, **[Claudfather/Claudlobby#294 — "Phase 4 Part C — autonomous-runner validation deployment"](https://github.com/Claudfather/Claudlobby/issues/294), still OPEN** as of this audit. That is the one real gap — this phase is not abandoned or blocked; it shipped fast and the remainder is explicitly tracked.
>
> **Not superseded by the later ironclad-migration decision** (ratified 2026-06-03, ~2 weeks after this phase shipped — see `documentation/planning/2026-06-02-ironclad-migration-claudlobby-to-clauDNA.md`). That decision's principle — "clauDNA skills are subagent-only; fleet dispatch is a claudlobby concern injected at composition time" — is exactly what this phase already did: every fleet.yaml/dataclass/composer/telegram concept here lives in Claudlobby, never in clauDNA. This phase and `/ironclad`'s `fleet-dispatch-capability` override are two independent, complementary instances of the same boundary, not competing designs (see Task 10's marker below for how the two mechanisms differ). See per-task markers below for file-level evidence.

# Phase 4 Implementation Plan — claudlobby `autonomous-runner` wrapper

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a generic, configurable wrapper skill in claudlobby — `autonomous-runner` — that any bot can include in `fleet.yaml`. The wrapper takes a clauDNA procedural skill (e.g., `/claudna:implement-plan --auto`, `/claudna:tech-debt --auto`) and runs it as the bot's continuous job: picks work, classifies risk, invokes the skill, parses the §10.C structured result, and reports back to Telegram. Per-bot configuration (target repo, cadence, picker, bypass thresholds, pre/post hooks) flows through the compositor into the bot's CLAUDE.md.

**Architecture:** A new skill at `library/skills/autonomous-runner/SKILL.md`. A new dataclass `AutonomousRunnerConfig` in `claudlobby/config.py`. Schema parsing in `loader.py`. Validation in `validator.py`. CLAUDE.md composition in `composer.py`. A new risk-classifier subagent prompt template. A new bot archetype entry in docs. Unit tests for the schema. End-to-end validation deployment.

**Tech Stack:** Python 3 (claudlobby's compositor) + Markdown (skill body) + YAML (fleet config schema). Existing claudlobby idioms: `dataclass`, `yaml.safe_load`, file overlays via `Paths`.

**Repo:** claudlobby (`/Users/chris/Projects/claudlobby`). NOTE: this phase is in a different repo from Phases 1-3.

**Prerequisites:**
- Phases 1-3 merged in clauDNA. The structured-result shape (§10.C), `/implement-plan --auto`, `/tech-debt --auto` (and the other 8 `--auto` skills) are live.
- Read the design spec at `/Users/chris/Projects/claudna/documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md` §6 in full.
- Read `/Users/chris/Projects/claudlobby/README.md` and `/Users/chris/Projects/claudlobby/CLAUDE.md` to understand claudlobby's compositor model.

---

## File Structure

**Status roll-up:** ✅ COMPLETE for every row below except the validation-deployment overlay under `local/` (Task 10, PENDING). `claudlobby/loader.py` was not touched as planned — parsing landed in `config.py`'s `_coerce_bot` instead (see Task 3 marker). `docs/bot-archetypes.md` doesn't exist under that path in shipped Claudlobby; the archetype doc shipped as `library/skills/autonomous-runner/archetype.md` instead (see Task 9 marker). See per-task markers for citations.

| File | Action | Notes |
|---|---|---|
| `library/skills/autonomous-runner/SKILL.md` | Create | The wrapper skill body |
| `library/skills/autonomous-runner/risk-classifier-prompt.md` | Create | Subagent prompt template for the risk classifier |
| `claudlobby/config.py` | Modify | Add `AutonomousRunnerConfig` dataclass + field on `BotConfig` |
| `claudlobby/loader.py` | Modify | Parse `autonomous_runner` block in fleet.yaml |
| `claudlobby/validator.py` | Modify | Validate the new config block |
| `claudlobby/composer.py` | Modify | Bake the config into the bot's CLAUDE.md |
| `templates/claude.md.j2` | Modify | Add a template section for autonomous-runner config |
| `tests/test_autonomous_runner_config.py` | Create | Unit tests for the schema parsing + validation |
| `fleet.yaml.example` | Modify | Add an example autonomous-runner block |
| `docs/bot-archetypes.md` | Modify | Add "Autonomous Worker" archetype |
| `CHANGELOG.md` (claudlobby) | Modify if exists; create if not | Phase 4 entry |

---

## Task 1: Read source files and understand claudlobby internals

**✅ COMPLETE (implied)** — no artifact of its own (this is a read-only orientation pass; "No commit for Task 1"), but Tasks 2-9/11 shipped with idiom-consistent code, so the orientation evidently happened.

This phase is in an unfamiliar codebase (vs. Phases 1-3 in clauDNA). Do not skip the orientation pass.

- [ ] **Step 1: Read the design spec §6 end-to-end**

Open `/Users/chris/Projects/claudna/documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md` and read §6 (claudlobby changes) twice. Pay attention to:
- §6.1 New skill: `library/skills/autonomous-runner`
- §6.1's "Configuration via fleet.yaml" — note exact field names, types, and the `args:` block
- §6.1's Procedure (steps 1-10)
- §6.1.1 Risk classifier `structural_vs_mechanical`
- §6.1's "Behavior the wrapper deliberately does NOT do"
- §6.2 Documentation and bot archetype

- [ ] **Step 2: Read claudlobby's README and CLAUDE.md**

```bash
cat /Users/chris/Projects/claudlobby/README.md
cat /Users/chris/Projects/claudlobby/CLAUDE.md
```

Note especially:
- The composition model: library/ + fleet.yaml → runtime/bots/<name>/CLAUDE.md
- The overlay system (local/<fleet>/library/ wins over base library/)
- The `library/skills/<name>/SKILL.md` convention
- The `fleet.yaml.example` schema

- [ ] **Step 3: Read claudlobby's config.py end-to-end**

```bash
cat /Users/chris/Projects/claudlobby/claudlobby/config.py
```

Identify the existing dataclasses: `BotConfig`, `FleetConfig`, related sub-configs (TelegramConfig, McpEntry, etc.). Note the patterns: how dataclasses are composed, how YAML maps to fields, what defaults look like.

- [ ] **Step 4: Read claudlobby's loader.py and composer.py**

```bash
cat /Users/chris/Projects/claudlobby/claudlobby/loader.py
cat /Users/chris/Projects/claudlobby/claudlobby/composer.py
```

Note:
- loader.py uses `parse_frontmatter` to read library items
- composer.py reads `BotConfig`, applies templates, writes runtime files
- Templates live in `templates/claude.md.j2` (Jinja2)

- [ ] **Step 5: Read claudlobby/validator.py**

```bash
cat /Users/chris/Projects/claudlobby/claudlobby/validator.py
```

Note the existing per-bot validation pattern (expertise, voice, skills, mcp, etc.). The new validation in Phase 4 follows the same pattern.

- [ ] **Step 6: Read templates/claude.md.j2**

```bash
cat /Users/chris/Projects/claudlobby/templates/claude.md.j2
```

Note where in the template each section goes: persona → voice → skills → guardrails → protocols → resources. The autonomous-runner block needs a place in this template.

- [ ] **Step 7: Read fleet.yaml.example**

```bash
cat /Users/chris/Projects/claudlobby/fleet.yaml.example
```

Note the existing bot block structure. The new `autonomous_runner` field is a nested map under a bot.

- [ ] **Step 8: Read an existing library/skills/ entry for style reference**

```bash
ls /Users/chris/Projects/claudlobby/library/skills/
cat /Users/chris/Projects/claudlobby/library/skills/autonomous-sprint/SKILL.md
cat /Users/chris/Projects/claudlobby/library/skills/dispatch/SKILL.md
```

Match the style: frontmatter conventions, prose tone, procedure formatting. The new `autonomous-runner` skill should feel native to claudlobby.

- [ ] **Step 9: Read the existing `autonomous-sprint` and `dispatch` skills for procedural patterns**

These are the closest analogs. The new `autonomous-runner` is a single-bot, configurable version of `autonomous-sprint` (which assumes a manager-worker fleet).

No commit for Task 1.

---

## Task 2: Add `AutonomousRunnerConfig` dataclass and `BotConfig.autonomous_runner` field

**✅ COMPLETE** — `claudlobby/config.py` (Claudlobby `main`, ~line 149-183) defines `AutonomousRunnerPicker`, `AutonomousRunnerBypass`, `AutonomousRunnerConfig` with field shapes matching this plan closely. Shipped in Phase 4 Part A (commit `d98e7e0`, [Claudfather/Claudlobby#278](https://github.com/Claudfather/Claudlobby/issues/278), merged 2026-05-18).

**Files:**
- Modify: `claudlobby/config.py`
- Test: `tests/test_autonomous_runner_config.py` (create)

- [ ] **Step 1: Write a failing test**

Create `tests/test_autonomous_runner_config.py`. If the `tests/` directory does not exist in claudlobby, create it.

```python
"""Tests for AutonomousRunnerConfig parsing and defaults."""
from __future__ import annotations

import pytest

from claudlobby.config import (
    AutonomousRunnerConfig,
    AutonomousRunnerPicker,
    AutonomousRunnerBypass,
    BotConfig,
)


def test_autonomous_runner_defaults():
    """Minimal config: only skill + cadence + target_repo required."""
    cfg = AutonomousRunnerConfig(
        skill="/claudna:tech-debt",
        cadence="1h",
        target_repo="org/repo",
    )
    assert cfg.skill == "/claudna:tech-debt"
    assert cfg.cadence == "1h"
    assert cfg.target_repo == "org/repo"
    assert cfg.args == ""
    assert cfg.picker is None
    assert cfg.bypass is None
    assert cfg.pre_hooks == []
    assert cfg.post_hooks == []
    assert cfg.on_outcome == {}


def test_autonomous_runner_full_config():
    """All fields populated."""
    cfg = AutonomousRunnerConfig(
        skill="/claudna:implement-plan",
        cadence="2h",
        target_repo="example-org/data-warehouse",
        args="--source github",
        picker=AutonomousRunnerPicker(
            type="github_issues",
            label="claudna-eligible",
            state="open",
            score_by="mission_alignment",
        ),
        bypass=AutonomousRunnerBypass(
            risk_classifier="structural_vs_mechanical",
            block_on=["structural"],
            on_bypass="comment_and_label",
        ),
        pre_hooks=["/claudna:adversarial-review"],
        post_hooks=["/claudna:simplify"],
        on_outcome={
            "completed": "report",
            "bypassed": "report",
            "needs_input": "report_and_pause",
            "blocked": "report_and_pause",
            "partial": "report",
        },
    )
    assert cfg.picker.score_by == "mission_alignment"
    assert cfg.bypass.block_on == ["structural"]
    assert cfg.on_outcome["blocked"] == "report_and_pause"


def test_botconfig_has_autonomous_runner_field():
    """BotConfig accepts an autonomous_runner field, defaulting to None."""
    bot = BotConfig(name="test-bot", expertise=["software-engineering"])
    assert bot.autonomous_runner is None

    bot2 = BotConfig(
        name="auto-bot",
        expertise=["software-engineering"],
        autonomous_runner=AutonomousRunnerConfig(
            skill="/claudna:tech-debt",
            cadence="1h",
            target_repo="org/repo",
        ),
    )
    assert bot2.autonomous_runner.skill == "/claudna:tech-debt"
```

Run the tests:

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/test_autonomous_runner_config.py -v
```

Expected: ImportError or collection failure because the new dataclasses don't exist yet. This is the failing test (RED).

- [ ] **Step 2: Add the new dataclasses to `claudlobby/config.py`**

Open `claudlobby/config.py`. After the existing dataclass definitions (locate the section where `BotConfig` is defined), insert the new dataclasses. Place them BEFORE `BotConfig` so `BotConfig` can reference them.

Add the following code:

```python
@dataclass
class AutonomousRunnerPicker:
    """Picker config for autonomous-runner. Selects work items per cadence tick."""
    type: str = "github_issues"  # currently only github_issues is supported
    label: str | None = None  # required for github_issues: filter by label
    state: str = "open"  # github_issues: open | closed | all
    score_by: str = "recency"  # recency | mission_alignment | priority_label


@dataclass
class AutonomousRunnerBypass:
    """Pre-flight risk-based bypass config. See §6.1.1 of the design spec."""
    risk_classifier: str = "structural_vs_mechanical"  # only supported classifier in v1
    block_on: list[str] = field(default_factory=lambda: ["structural"])
    on_bypass: str = "comment_and_label"  # comment_and_label | comment_only | exit_silent


@dataclass
class AutonomousRunnerConfig:
    """Configuration for the library/skills/autonomous-runner wrapper skill."""
    skill: str  # required: clauDNA skill to invoke (e.g., '/claudna:implement-plan')
    cadence: str  # required: '15m' | '1h' | '6h' | '24h' (parsed by the bot lifecycle)
    target_repo: str  # required: 'org/repo' for picker scope and gh CLI calls
    args: str = ""  # optional: appended verbatim to the skill invocation (after --auto)
    picker: AutonomousRunnerPicker | None = None
    bypass: AutonomousRunnerBypass | None = None
    pre_hooks: list[str] = field(default_factory=list)
    post_hooks: list[str] = field(default_factory=list)
    on_outcome: dict[str, str] = field(default_factory=dict)
```

Then update `BotConfig`. Find the `BotConfig` dataclass and add a new field:

```python
@dataclass
class BotConfig:
    name: str
    # ... existing fields ...
    autonomous_runner: AutonomousRunnerConfig | None = None
```

(The exact insertion point depends on how `BotConfig` is currently structured. Add `autonomous_runner` as the LAST field so all existing positional uses remain unaffected.)

- [ ] **Step 3: Run the tests**

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/test_autonomous_runner_config.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/chris/Projects/claudlobby
git add claudlobby/config.py tests/test_autonomous_runner_config.py
git commit -m "$(cat <<'EOF'
feat(config): add AutonomousRunnerConfig dataclass

New dataclasses: AutonomousRunnerConfig, AutonomousRunnerPicker,
AutonomousRunnerBypass. BotConfig gains an optional autonomous_runner
field (defaults to None). Schema matches §6.1 of the
autonomous-mode-and-orchestration design spec.

Includes unit tests for defaults and full-config construction.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 3: Parse `autonomous_runner` in `loader.py`

**✅ COMPLETE, architecture differs from plan** — parsing did not land in a separate `loader.py` function as this task specifies. Claudlobby's own CHANGELOG.md states the block is "parsed from `fleet.yaml` by `_coerce_bot`" — consolidated into `config.py` instead. Functionally equivalent to this task's goal (fleet.yaml → `AutonomousRunnerConfig`), just a different file than planned. `claudlobby/loader.py` itself has no autonomous-runner-specific code.

**Files:**
- Modify: `claudlobby/loader.py`
- Test: `tests/test_autonomous_runner_loader.py` (create)

- [ ] **Step 1: Write a failing test**

Create `tests/test_autonomous_runner_loader.py`:

```python
"""Tests for fleet.yaml parsing of the autonomous_runner block."""
from __future__ import annotations

import pytest
import yaml

# Use the loader functions claudlobby exposes. If loading goes through
# config-level helpers, import from there instead.
from claudlobby.config import parse_bot_config  # adjust import to actual location


def _bot_yaml(s: str) -> dict:
    """Helper: load a YAML snippet into a dict."""
    return yaml.safe_load(s)


def test_load_minimal_autonomous_runner():
    yaml_text = """
name: test-bot
expertise:
  - software-engineering
autonomous_runner:
  skill: /claudna:tech-debt
  cadence: 1h
  target_repo: org/repo
"""
    data = _bot_yaml(yaml_text)
    bot = parse_bot_config(data)
    assert bot.autonomous_runner is not None
    assert bot.autonomous_runner.skill == "/claudna:tech-debt"
    assert bot.autonomous_runner.cadence == "1h"
    assert bot.autonomous_runner.target_repo == "org/repo"
    # Defaults
    assert bot.autonomous_runner.args == ""
    assert bot.autonomous_runner.picker is None


def test_load_full_autonomous_runner():
    yaml_text = """
name: dbt-bot
expertise:
  - data-engineering
autonomous_runner:
  skill: /claudna:implement-plan
  cadence: 2h
  target_repo: example-org/data-warehouse
  args: "--source github"
  picker:
    type: github_issues
    label: claudna-eligible
    state: open
    score_by: mission_alignment
  bypass:
    risk_classifier: structural_vs_mechanical
    block_on:
      - structural
    on_bypass: comment_and_label
  pre_hooks:
    - /claudna:adversarial-review
  post_hooks:
    - /claudna:simplify
  on_outcome:
    completed: report
    bypassed: report
    needs_input: report_and_pause
    blocked: report_and_pause
    partial: report
"""
    data = _bot_yaml(yaml_text)
    bot = parse_bot_config(data)
    cfg = bot.autonomous_runner
    assert cfg.args == "--source github"
    assert cfg.picker.label == "claudna-eligible"
    assert cfg.picker.score_by == "mission_alignment"
    assert cfg.bypass.block_on == ["structural"]
    assert cfg.bypass.on_bypass == "comment_and_label"
    assert "/claudna:adversarial-review" in cfg.pre_hooks
    assert cfg.on_outcome["blocked"] == "report_and_pause"


def test_bot_without_autonomous_runner():
    yaml_text = """
name: simple-bot
expertise:
  - software-engineering
"""
    data = _bot_yaml(yaml_text)
    bot = parse_bot_config(data)
    assert bot.autonomous_runner is None


def test_missing_required_field_raises():
    """Missing 'skill', 'cadence', or 'target_repo' should raise during parse."""
    yaml_text = """
name: bad-bot
expertise:
  - software-engineering
autonomous_runner:
  cadence: 1h
  target_repo: org/repo
"""
    data = _bot_yaml(yaml_text)
    with pytest.raises((KeyError, TypeError, ValueError)):
        parse_bot_config(data)
```

Run:

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/test_autonomous_runner_loader.py -v
```

Expected: tests fail because the loader doesn't yet parse the new block.

- [ ] **Step 2: Implement parsing in `loader.py` (or `config.py`)**

Locate the existing function that parses a bot config from a YAML dict. (Based on the existing loader.py read, this may be in `config.py` rather than `loader.py` — adjust per the actual codebase.)

If the bot-config parsing lives in a function called `parse_bot_config` (or equivalent — the test imports from `claudlobby.config`):

1. Read the existing function.
2. Add parsing for the new `autonomous_runner` block.

Example structure to add inside the function:

```python
def _parse_autonomous_runner(d: dict | None) -> AutonomousRunnerConfig | None:
    if d is None:
        return None
    if not isinstance(d, dict):
        raise ValueError(f"autonomous_runner must be a mapping, got {type(d).__name__}")
    # Required fields
    for required in ("skill", "cadence", "target_repo"):
        if required not in d:
            raise KeyError(f"autonomous_runner missing required field: {required}")
    picker = None
    if "picker" in d:
        p = d["picker"]
        picker = AutonomousRunnerPicker(
            type=p.get("type", "github_issues"),
            label=p.get("label"),
            state=p.get("state", "open"),
            score_by=p.get("score_by", "recency"),
        )
    bypass = None
    if "bypass" in d:
        b = d["bypass"]
        bypass = AutonomousRunnerBypass(
            risk_classifier=b.get("risk_classifier", "structural_vs_mechanical"),
            block_on=list(b.get("block_on", ["structural"])),
            on_bypass=b.get("on_bypass", "comment_and_label"),
        )
    return AutonomousRunnerConfig(
        skill=d["skill"],
        cadence=d["cadence"],
        target_repo=d["target_repo"],
        args=d.get("args", ""),
        picker=picker,
        bypass=bypass,
        pre_hooks=list(d.get("pre_hooks", [])),
        post_hooks=list(d.get("post_hooks", [])),
        on_outcome=dict(d.get("on_outcome", {})),
    )
```

Then in the bot-config parsing function, add:

```python
    bot.autonomous_runner = _parse_autonomous_runner(data.get("autonomous_runner"))
```

(Adjust based on whether the existing code uses constructor injection or post-hoc field assignment.)

If there is no existing `parse_bot_config` function (the loader uses a different pattern, e.g., constructing `BotConfig` directly from a YAML-loaded dict via `**kwargs`), introduce one as a thin wrapper that handles the autonomous_runner block before delegating to the existing constructor.

- [ ] **Step 3: Run the tests**

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/test_autonomous_runner_loader.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Run the full claudlobby test suite to confirm no regressions**

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/ -v
```

Expected: existing tests still pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/chris/Projects/claudlobby
git add claudlobby/loader.py claudlobby/config.py tests/test_autonomous_runner_loader.py
git commit -m "$(cat <<'EOF'
feat(loader): parse autonomous_runner block in fleet.yaml

Parses the new per-bot autonomous_runner config block: skill, cadence,
target_repo (required), plus optional picker, bypass, args, pre_hooks,
post_hooks, on_outcome. Raises on missing required fields.

Backward compatible: bots without an autonomous_runner block continue
to work unchanged.

Includes unit tests for full config, minimal config, missing block,
and missing required fields.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 4: Validate `autonomous_runner` in `validator.py`

**✅ COMPLETE** — `claudlobby/validator.py` validates the `autonomous_runner` block (CHANGELOG.md: "validated in `validate()`"). Tests landed in `tests/test_validator.py` rather than a dedicated `test_autonomous_runner_validator.py` file, but the shipped CHANGELOG claims "23 new tests across `test_config.py`, `test_validator.py`, `test_composer.py`" for Part A as a whole. A related `claudlobby/known_values.py` module appeared later (PR #391, "known-good value validation (Tier 2+3)") as a generalization of this kind of check.

**Files:**
- Modify: `claudlobby/validator.py`
- Test: extend `tests/test_autonomous_runner_loader.py` or create `tests/test_autonomous_runner_validator.py`

- [ ] **Step 1: Write failing tests for validation**

Create or extend `tests/test_autonomous_runner_validator.py`:

```python
"""Tests for autonomous_runner block validation."""
from __future__ import annotations

import pytest

from claudlobby.config import (
    AutonomousRunnerConfig,
    AutonomousRunnerPicker,
    AutonomousRunnerBypass,
    BotConfig,
    FleetConfig,
)
from claudlobby.validator import validate
from claudlobby.paths import Paths


def _make_paths(tmp_path) -> Paths:
    """Helper: create a Paths object pointing at a tmp library/."""
    # Adjust per the actual Paths constructor in claudlobby
    return Paths(repo_root=tmp_path)


def _basic_fleet(autonomous_runner: AutonomousRunnerConfig | None = None) -> FleetConfig:
    bot = BotConfig(
        name="test-bot",
        expertise=["software-engineering"],
        autonomous_runner=autonomous_runner,
    )
    return FleetConfig(bots={"test-bot": bot})


def test_validator_warns_on_unknown_skill(tmp_path):
    """If the configured clauDNA skill is not on the known --auto-eligible list, warn."""
    cfg = AutonomousRunnerConfig(
        skill="/claudna:nonexistent-skill",
        cadence="1h",
        target_repo="org/repo",
    )
    report = validate(_basic_fleet(cfg), _make_paths(tmp_path))
    assert any("unknown clauDNA skill" in w or "not on the --auto-eligible list" in w
               for w in report.warnings)


def test_validator_accepts_known_auto_skill(tmp_path):
    """A known --auto-eligible skill validates cleanly (no autonomous-runner warnings)."""
    cfg = AutonomousRunnerConfig(
        skill="/claudna:tech-debt",
        cadence="1h",
        target_repo="org/repo",
    )
    report = validate(_basic_fleet(cfg), _make_paths(tmp_path))
    # No autonomous-runner-specific warnings (other warnings may exist for expertise etc.)
    assert not any("autonomous_runner" in w and "tech-debt" in w for w in report.warnings)


def test_validator_warns_on_bad_cadence(tmp_path):
    """cadence must match a known pattern (15m, 1h, 6h, 24h, etc.)."""
    cfg = AutonomousRunnerConfig(
        skill="/claudna:tech-debt",
        cadence="banana",
        target_repo="org/repo",
    )
    report = validate(_basic_fleet(cfg), _make_paths(tmp_path))
    assert any("cadence" in w and "banana" in w for w in report.warnings)


def test_validator_errors_on_missing_picker_label_for_github_issues(tmp_path):
    """github_issues picker requires a label field."""
    cfg = AutonomousRunnerConfig(
        skill="/claudna:implement-plan",
        cadence="1h",
        target_repo="org/repo",
        picker=AutonomousRunnerPicker(type="github_issues", label=None),
    )
    report = validate(_basic_fleet(cfg), _make_paths(tmp_path))
    assert any("picker.label" in e and "required" in e for e in report.errors)


def test_validator_warns_on_unknown_on_outcome_key(tmp_path):
    cfg = AutonomousRunnerConfig(
        skill="/claudna:tech-debt",
        cadence="1h",
        target_repo="org/repo",
        on_outcome={"banana": "report"},
    )
    report = validate(_basic_fleet(cfg), _make_paths(tmp_path))
    assert any("on_outcome" in w and "banana" in w for w in report.warnings)


def test_validator_warns_on_unknown_on_outcome_action(tmp_path):
    cfg = AutonomousRunnerConfig(
        skill="/claudna:tech-debt",
        cadence="1h",
        target_repo="org/repo",
        on_outcome={"completed": "explode"},
    )
    report = validate(_basic_fleet(cfg), _make_paths(tmp_path))
    assert any("on_outcome" in w and "explode" in w for w in report.warnings)
```

Run:

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/test_autonomous_runner_validator.py -v
```

Expected: tests fail because the validator doesn't yet check autonomous_runner.

- [ ] **Step 2: Add the validation logic to `validator.py`**

In `claudlobby/validator.py`, find the per-bot validation loop (the `for bot_name, bot in fleet.bots.items():` block).

Add a constant at the top of the file (after the existing imports):

```python
# Skills known to support --auto. Phase 1 of the autonomous-mode design rolls
# these out; the wrapper validates the configured skill against this list.
# Update when new --auto skills are added in clauDNA.
_AUTO_ELIGIBLE_SKILLS = {
    "/claudna:tech-debt",
    "/claudna:security-audit",
    "/claudna:product-enhance",
    "/claudna:frontend-performance-audit",
    "/claudna:docs-review",
    "/claudna:access-path-audit",
    "/claudna:product-vision",
    "/claudna:session-handoff",
    "/claudna:visual-crawl",
    "/claudna:implement-plan",
}

# Cadence syntax: <number><unit> where unit ∈ {m, h, d}.
_CADENCE_RE = re.compile(r"^\d+[mhd]$")

# Recognized on_outcome keys and actions.
_OUTCOME_KEYS = {"completed", "bypassed", "needs_input", "blocked", "partial"}
_OUTCOME_ACTIONS = {"report", "report_and_pause", "silent"}

# NOTE on naming: the JSON `outcome` field in the §10.C structured result uses
# hyphens ("needs-input"). YAML keys for `on_outcome` use snake_case
# ("needs_input") — idiomatic for Python dict keys. When looking up the
# action in Step 9 of the wrapper procedure, normalize: outcome_key =
# outcome_string.replace("-", "_"). The validator below uses the snake_case
# form for the same reason.
```

Inside the per-bot loop (after existing checks), add:

```python
        # Autonomous-runner block validation (Phase 4)
        ar = bot.autonomous_runner
        if ar is not None:
            # Skill eligibility (warn only — clauDNA may have skills the wrapper doesn't know about yet)
            if ar.skill not in _AUTO_ELIGIBLE_SKILLS:
                report.warnings.append(
                    f"bot '{bot_name}': autonomous_runner.skill '{ar.skill}' is not on the --auto-eligible list — "
                    f"the wrapper will still invoke it, but unknown clauDNA skill may not emit a structured result"
                )

            # Cadence syntax
            if not _CADENCE_RE.match(ar.cadence):
                report.warnings.append(
                    f"bot '{bot_name}': autonomous_runner.cadence '{ar.cadence}' doesn't match <N><m|h|d> — "
                    f"the bot may not fire on the expected interval"
                )

            # target_repo shape (org/repo)
            if "/" not in ar.target_repo or ar.target_repo.count("/") != 1:
                report.warnings.append(
                    f"bot '{bot_name}': autonomous_runner.target_repo '{ar.target_repo}' should be 'org/repo' format"
                )

            # Picker
            if ar.picker is not None:
                if ar.picker.type == "github_issues" and not ar.picker.label:
                    report.errors.append(
                        f"bot '{bot_name}': autonomous_runner.picker.label is required when type='github_issues'"
                    )

            # Bypass
            if ar.bypass is not None:
                if ar.bypass.on_bypass not in {"comment_and_label", "comment_only", "exit_silent"}:
                    report.warnings.append(
                        f"bot '{bot_name}': autonomous_runner.bypass.on_bypass '{ar.bypass.on_bypass}' "
                        f"not in known set (comment_and_label, comment_only, exit_silent)"
                    )

            # on_outcome
            for k, v in ar.on_outcome.items():
                if k not in _OUTCOME_KEYS:
                    report.warnings.append(
                        f"bot '{bot_name}': autonomous_runner.on_outcome key '{k}' is not a known outcome "
                        f"(expected one of {sorted(_OUTCOME_KEYS)})"
                    )
                if v not in _OUTCOME_ACTIONS:
                    report.warnings.append(
                        f"bot '{bot_name}': autonomous_runner.on_outcome action '{v}' is not a known action "
                        f"(expected one of {sorted(_OUTCOME_ACTIONS)})"
                    )

            # Pre/post hooks: each should be a clauDNA skill name (warn if not /claudna: prefixed)
            for hook in ar.pre_hooks + ar.post_hooks:
                if not hook.startswith("/claudna:"):
                    report.warnings.append(
                        f"bot '{bot_name}': autonomous_runner hook '{hook}' is not a /claudna: skill — "
                        f"hooks should be clauDNA skill names"
                    )
```

Also add `import re` to the imports if not already present.

- [ ] **Step 3: Run the tests**

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/test_autonomous_runner_validator.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Run the full claudlobby test suite**

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/ -v
```

Expected: no regressions.

- [ ] **Step 5: Commit**

```bash
cd /Users/chris/Projects/claudlobby
git add claudlobby/validator.py tests/test_autonomous_runner_validator.py
git commit -m "$(cat <<'EOF'
feat(validator): validate autonomous_runner config block

Validates: skill eligibility against the --auto skill list, cadence
syntax, target_repo format, picker.label requirement, bypass.on_bypass
allowed values, on_outcome key/action vocabulary, hook skill-name
convention.

Mostly warnings (permissive default). One hard error: github_issues
picker requires a label.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 5: Compose `autonomous_runner` config into the bot's CLAUDE.md

**✅ COMPLETE** — Claudlobby's CHANGELOG.md confirms the block is "rendered into the bot's `CLAUDE.md` by `compose_claude_md`"; `templates/claude.md.j2` (grep-confirmed) contains the autonomous-runner rendering section. `claudlobby/composer.py` itself has no autonomous-runner-specific string match — plausibly because it passes the whole `bot` object through generically and the template does the `{% if bot.autonomous_runner %}` branching, needing no composer.py changes. Test coverage folded into `tests/test_composer.py` rather than a dedicated file.

**Files:**
- Modify: `claudlobby/composer.py`
- Modify: `templates/claude.md.j2`
- Test: `tests/test_autonomous_runner_compose.py` (create)

- [ ] **Step 1: Understand the existing template flow**

Re-read `templates/claude.md.j2` and the relevant composer functions. The autonomous-runner block needs a position in the rendered CLAUDE.md — likely after the bot's persona/skills but before/within a "duties" section. Read the template top to bottom and pick the most natural insertion point.

- [ ] **Step 2: Add a template section for autonomous-runner**

In `templates/claude.md.j2`, find a stable insertion point (after the persona/voice section, before protocols/guardrails — or wherever bot duties go). Add:

```jinja2
{% if bot.autonomous_runner %}

## Autonomous Runner — Your Continuous Job

You run continuously per the `autonomous-runner` skill from `library/skills/autonomous-runner/SKILL.md`. Your configuration:

- **Target skill:** `{{ bot.autonomous_runner.skill }}` (invoked with `--auto`)
- **Cadence:** every `{{ bot.autonomous_runner.cadence }}`
- **Target repo:** `{{ bot.autonomous_runner.target_repo }}`
{% if bot.autonomous_runner.args %}- **Additional args:** `{{ bot.autonomous_runner.args }}`{% endif %}
{% if bot.autonomous_runner.picker %}
- **Picker:** `{{ bot.autonomous_runner.picker.type }}`{% if bot.autonomous_runner.picker.label %}, label `{{ bot.autonomous_runner.picker.label }}`{% endif %}, score by `{{ bot.autonomous_runner.picker.score_by }}`
{% endif %}
{% if bot.autonomous_runner.bypass %}
- **Bypass:** classifier `{{ bot.autonomous_runner.bypass.risk_classifier }}`, block on {{ bot.autonomous_runner.bypass.block_on | join(', ') }}, action `{{ bot.autonomous_runner.bypass.on_bypass }}`
{% endif %}
{% if bot.autonomous_runner.pre_hooks %}
- **Pre-hooks:** {{ bot.autonomous_runner.pre_hooks | join(', ') }}
{% endif %}
{% if bot.autonomous_runner.post_hooks %}
- **Post-hooks:** {{ bot.autonomous_runner.post_hooks | join(', ') }}
{% endif %}
{% if bot.autonomous_runner.on_outcome %}
- **On-outcome:**
{% for k, v in bot.autonomous_runner.on_outcome.items() %}  - `{{ k }}`: `{{ v }}`
{% endfor %}
{% endif %}

Follow the procedure in `library/skills/autonomous-runner/SKILL.md` for each cadence tick. See the skill body for idle checks, quota awareness, picking, risk classification, invocation, structured-result parsing, and Telegram report-back.

{% endif %}
```

(Adjust Jinja2 syntax to match the existing template's conventions — the example above is illustrative.)

- [ ] **Step 3: Write a test that confirms the compose step produces expected output**

Create `tests/test_autonomous_runner_compose.py`:

```python
"""Tests for composing the autonomous_runner block into a bot's CLAUDE.md."""
from __future__ import annotations

from claudlobby.config import (
    AutonomousRunnerConfig,
    AutonomousRunnerPicker,
    BotConfig,
    FleetConfig,
)
from claudlobby.composer import render_claude_md


def test_compose_with_autonomous_runner():
    bot = BotConfig(
        name="dbt-bot",
        expertise=["data-engineering"],
        autonomous_runner=AutonomousRunnerConfig(
            skill="/claudna:implement-plan",
            cadence="1h",
            target_repo="example-org/data-warehouse",
            picker=AutonomousRunnerPicker(
                type="github_issues",
                label="claudna-eligible",
                score_by="mission_alignment",
            ),
        ),
    )
    output = render_claude_md(bot)
    assert "Autonomous Runner" in output
    assert "/claudna:implement-plan" in output
    assert "example-org/data-warehouse" in output
    assert "every 1h" in output or "cadence: 1h" in output
    assert "claudna-eligible" in output


def test_compose_without_autonomous_runner_omits_section():
    bot = BotConfig(name="simple-bot", expertise=["software-engineering"])
    output = render_claude_md(bot)
    assert "Autonomous Runner" not in output
```

(Adjust the imports and function names to match the actual claudlobby composer API.)

Run:

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/test_autonomous_runner_compose.py -v
```

Expected: failing initially if the template change wasn't picked up, or passing if Step 2 was done correctly.

- [ ] **Step 4: Iterate on the template until tests pass**

If the template change has issues (incorrect Jinja2 syntax, missing context, etc.), adjust until both tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/chris/Projects/claudlobby
git add claudlobby/composer.py templates/claude.md.j2 tests/test_autonomous_runner_compose.py
git commit -m "$(cat <<'EOF'
feat(composer): render autonomous_runner block into bot's CLAUDE.md

When a bot has an autonomous_runner config, the composer renders a
new section in the generated CLAUDE.md describing the target skill,
cadence, target repo, picker, bypass, hooks, and on-outcome policy.
Bots without autonomous_runner are unaffected.

Includes unit tests for both present and absent cases.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 6: Create the risk-classifier subagent prompt template

**✅ COMPLETE** — `library/skills/autonomous-runner/risk-classifier-prompt.md` exists in Claudlobby. Shipped in Phase 4 Part B (commit `a541004`, [Claudfather/Claudlobby#279](https://github.com/Claudfather/Claudlobby/issues/279), merged 2026-05-18).

**Files:**
- Create: `library/skills/autonomous-runner/risk-classifier-prompt.md`

- [ ] **Step 1: Create the directory and file**

Create the directory `library/skills/autonomous-runner/` if it does not exist. Then create `risk-classifier-prompt.md`:

````markdown
# `structural_vs_mechanical` Risk Classifier — Subagent Prompt

The `autonomous-runner` skill dispatches this subagent before invoking any `--auto` clauDNA skill against a target work item. The subagent classifies the change's risk for headless work and returns one of three labels: `mechanical`, `localized`, `structural`.

This prompt template is the source of truth. The skill body references it rather than inlining the prompt.

## Prompt template

```
You are a code-change risk classifier for headless (unattended) automation.

Read this work item description (a GitHub issue body or plan document):

---
<WORK_ITEM_TEXT>
---

And scan these files (read-only — do not edit anything):

<RELEVANT_FILE_PATHS>

Your job: classify the proposed change into one of three categories. Output ONLY a JSON block with the classification and a one-line justification — no other text.

### Categories

**mechanical**: The change is pattern-based and behavior-preserving. Examples:
- Renames (variable, function, type, file) where call-site fixes are mechanical
- Formatting / linting / style fixes
- Dependency version bumps without API changes
- Doc fixes, comment updates
- Codemod-style sweeps applying a fixed transformation
- Test additions covering existing behavior
- Adding type annotations to typed code

**localized**: The change is bounded within one module or layer of the stack and does not change how callers must use the code. Examples:
- A bug fix that changes implementation of one function, same signature
- Adding a new endpoint, function, or component without touching existing ones
- Refactoring internals of one module without changing its interface
- Configuration changes scoped to one service

**structural**: The change crosses module boundaries, changes contracts, or alters how the code must be used. Examples:
- Changing a function signature (callers must update)
- Changing an API contract or schema
- Introducing a new abstraction that replaces existing patterns
- Database schema migrations
- Auth / security model changes
- Refactors that move code between modules
- Anything that requires updating multiple unrelated callers

### Output

Output a single JSON block. No surrounding prose, no markdown fences, no follow-up.

{
  "class": "mechanical | localized | structural",
  "justification": "<one sentence>",
  "indicators": ["<bullet>", "<bullet>"]
}

### Rules

- Size does not determine class. A 500-file mechanical rename is `mechanical`. A 3-file API change is `structural`.
- When in doubt between localized and structural, pick `structural`. False positives (saying structural when localized) cost a comment-and-label cycle; false negatives (saying mechanical when structural) cost a broken PR or worse.
- If you cannot determine the class from the available context, output `class: structural` with a justification "insufficient context — defaulting to structural per safety rule".
```

## Substitution rules

The dispatcher (the `autonomous-runner` skill body in `SKILL.md`) substitutes:

- `<WORK_ITEM_TEXT>`: the full body of the GitHub issue (or plan document) the wrapper picked
- `<RELEVANT_FILE_PATHS>`: a newline-separated list of file paths the wrapper extracted from the work item — file paths referenced in the issue body, plus any files implied by `Files to modify:` / `Create:` sections of the plan

## Parsing the response

The dispatcher expects a single JSON block. Use `json.loads` to parse. Required keys:

- `class`: one of `"mechanical"`, `"localized"`, `"structural"`
- `justification`: a string (1 sentence)
- `indicators`: an array of strings (may be empty)

If parsing fails or the class is not one of the three valid values, default to `class: structural` and log the parsing error. Safer to bypass an ambiguous run than to attempt one.

## When to override the classifier

A bot config's `bypass.block_on` field controls which classes trigger a bypass:

- `block_on: [structural]` (default) — only structural changes bypass
- `block_on: []` — never bypass; trust the skill's tripwires
- `block_on: [structural, localized]` — only run pure mechanical changes (most conservative)

The classifier itself is the same regardless of the bot's policy. The policy is applied to its output.
````

- [ ] **Step 2: Verify and commit**

```bash
ls /Users/chris/Projects/claudlobby/library/skills/autonomous-runner/
wc -l /Users/chris/Projects/claudlobby/library/skills/autonomous-runner/risk-classifier-prompt.md
```

Expected: file present.

```bash
cd /Users/chris/Projects/claudlobby
git add library/skills/autonomous-runner/risk-classifier-prompt.md
git commit -m "$(cat <<'EOF'
docs: add risk-classifier subagent prompt template

The structural_vs_mechanical classifier prompt used by the
autonomous-runner skill for pre-flight risk assessment. Outputs
a JSON classification (mechanical | localized | structural) with
justification and indicators.

Bots configure which classes trigger bypass via the bypass.block_on
field in fleet.yaml.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 7: Write the `autonomous-runner` skill body

**✅ COMPLETE** — `library/skills/autonomous-runner/SKILL.md` exists (Phase 4 Part B, same as Task 6). Notably, the shipped skill invokes clauDNA skills through the Skill tool as plugin-namespaced commands (e.g. `/claudna:implement-plan --auto`) rather than the raw `<CLAUDNA_PATH>/skills/<name>/SKILL.md` filesystem-path pattern this plan's draft used in Steps 5/6 below — Claudlobby's CHANGELOG.md calls this out explicitly as a correction, not an oversight.

**Files:**
- Create: `library/skills/autonomous-runner/SKILL.md`

- [ ] **Step 1: Create the skill body**

Create `library/skills/autonomous-runner/SKILL.md`:

````markdown
---
name: autonomous-runner
description: "Generic continuous-job wrapper for clauDNA procedural skills. Configurable per bot via fleet.yaml. Picks work items per cadence, classifies risk, invokes the configured clauDNA skill with --auto, parses the structured result, and reports back to Telegram."
---

# Autonomous Runner — Your Continuous Job

The orchestration layer between a claudlobby bot and a clauDNA `--auto` skill. The bot's configuration (per fleet.yaml's `autonomous_runner` block) determines:
- WHICH clauDNA skill to invoke each cadence tick
- WHICH work items to pick (for skills like `/implement-plan` that need a specific issue)
- WHAT counts as a high-risk change to bypass before invoking
- WHAT to do with each `outcome` from the skill's structured result

This skill is invoked by the bot's `lib/start-bot.sh` lifecycle on each cadence tick. The cadence is read from `bot.conf` (the per-bot env file generated by the compositor from `bot.autonomous_runner.cadence`).

## Required config in fleet.yaml

```yaml
bots:
  - name: dbt-eng-bot
    expertise: data-engineering
    skills:
      - autonomous-runner
      # ... other skills the bot uses internally
    autonomous_runner:
      skill: /claudna:implement-plan        # required
      cadence: 1h                            # required
      target_repo: example-org/data-warehouse           # required
      args: ""                               # optional, appended after --auto
      picker:                                # required when skill needs a work item
        type: github_issues
        label: claudna-eligible
        state: open
        score_by: mission_alignment
      bypass:                                # optional; defaults to structural-only
        risk_classifier: structural_vs_mechanical
        block_on: [structural]
        on_bypass: comment_and_label
      pre_hooks: []                          # optional clauDNA skills to run before main
      post_hooks: []                         # optional clauDNA skills to run after main
      on_outcome:                            # optional; defaults to "report" for all
        completed: report
        bypassed: report
        needs_input: report_and_pause
        blocked: report_and_pause
        partial: report
```

See `docs/bot-archetypes.md` "Autonomous Worker" for example configurations.

## Procedure

Each cadence tick, follow these steps in order. If any step exits the procedure, the next cadence tick starts the procedure fresh.

### Step 1: Idle check

If a previous invocation of this procedure is still running for this bot, EXIT silently. No overlapping runs.

Check via the bot's lockfile (`<bot-runtime>/autonomous-runner.lock`) or via `pgrep` on the bot's tmux session — use whichever mechanism is established for this fleet. If unsure, default to a lockfile under the bot's runtime directory:

```bash
LOCKFILE="<bot-runtime>/autonomous-runner.lock"
if [ -f "$LOCKFILE" ]; then
  echo "Previous run still active; exiting."
  exit 0
fi
touch "$LOCKFILE"
trap "rm -f $LOCKFILE" EXIT
```

### Step 2: Quota check

Check Anthropic API quota for this fleet's account. The fleet-state mechanism (`fleet-state.json`) tracks quota state via the existing `continuous-autonomous-mode` protocol.

If quota is near the configured limit:
1. Beacon to Telegram: "Quota near limit; pausing autonomous-runner until quota recovers."
2. EXIT.

If unsure how to read quota state from this fleet, see `library/protocols/continuous-autonomous-mode.md` for the established pattern.

### Step 3: Pick work item

If `autonomous_runner.picker` is configured, pick one work item per `picker.type`.

#### type: github_issues

```bash
gh issue list \
  --repo <target_repo> \
  --label <picker.label> \
  --state <picker.state> \
  --json number,title,body,labels,createdAt
```

Score each issue per `picker.score_by`:

- **`recency`**: most recently created issue first.
- **`mission_alignment`**: read `PROJECT_MISSION.md` from the target repo's default branch (`gh api repos/<target_repo>/contents/PROJECT_MISSION.md --jq .content | base64 -d`). Score each issue's alignment with the mission's north star + guiding principles. Highest-aligned wins. If `PROJECT_MISSION.md` does not exist, fall back to `recency` and log a warning.
- **`priority_label`**: prefer issues with `priority:critical` > `priority:high` > `priority:medium` > `priority:low` labels.

If no eligible work item is found, beacon to Telegram "No eligible work for this cadence tick" and EXIT.

If `autonomous_runner.picker` is NOT configured (e.g., the target skill is `/claudna:tech-debt` which doesn't need a specific item), skip Step 3.

### Step 4: Risk classification (qualitative bypass)

If `autonomous_runner.bypass` is configured, run the risk classifier per `library/skills/autonomous-runner/risk-classifier-prompt.md`.

Dispatch a `general-purpose` subagent with the classifier prompt. Substitute:
- `<WORK_ITEM_TEXT>`: the picked issue body (from Step 3) OR the plan body if a path was provided
- `<RELEVANT_FILE_PATHS>`: file paths extracted from the issue body (regex: `\b\S+\.\S+\b` filtered to existing paths via `gh api repos/<target_repo>/contents/<path>`)

Parse the JSON result. If `class` is in `bypass.block_on`:

Per `bypass.on_bypass`:

- **`comment_and_label`**:
  ```
  gh issue comment <issue#> --repo <target_repo> --body "$(cat <<'EOF'
  ## /autonomous-runner bypassed: classified as <class>

  **Classifier justification:** <justification>

  **Indicators:**
  <bulleted indicators>

  This bot's policy bypasses <class> changes for headless work. Surface to a human for ratification or split the issue into <mechanical | localized> sub-issues.

  Bypassed by `autonomous-runner` (<bot name>) at <timestamp>.
  EOF
  )"
  gh issue edit <issue#> --repo <target_repo> --add-label "needs-input"
  ```

  If the `needs-input` label doesn't exist, create it: `gh label create needs-input --repo <target_repo> --color FBCA04 --description "Bypassed by autonomous-runner — needs human input"`.

- **`comment_only`**: post the comment without the label.
- **`exit_silent`**: log locally, do not touch the issue.

EXIT.

If the class is NOT in `bypass.block_on`, proceed.

### Step 5: Pre-hooks

For each skill in `autonomous_runner.pre_hooks`, invoke as a `general-purpose` subagent with this prompt:

```
Read the skill body at <CLAUDNA_PATH>/skills/<hook-name>/SKILL.md.

Apply the skill in non-interactive mode against the work item.
Pass the work item context via $ARGUMENTS or the standard mechanism for the skill.

Return ONLY the structured-result JSON block per
skills/_shared/orchestration-guide.md §10.C.
```

Parse each pre-hook's structured result. If any returns `outcome: blocked` or `outcome: needs-input`, abort the main invocation and exit with that outcome via Step 9 (do NOT invoke the main skill).

### Step 6: Invoke the main skill

Construct the invocation:

```
<skill> --source github <issue#> --auto <args>
```

For `/claudna:implement-plan` and similar issue-consuming skills, `<issue#>` comes from Step 3. For non-issue skills (e.g., `/claudna:tech-debt`), omit `--source github <issue#>`.

`<args>` is the verbatim `autonomous_runner.args` string from fleet.yaml.

Dispatch as a `general-purpose` subagent with this prompt:

```
Read the skill body at <CLAUDNA_PATH>/skills/<skill-name>/SKILL.md.

Apply the skill with arguments: <constructed argument string>

Return ONLY the structured-result JSON block per
skills/_shared/orchestration-guide.md §10.C.
```

Capture the subagent's full stdout. The structured result is the LAST fenced ```json block in the output.

### Step 7: Parse the structured result

Extract the last fenced JSON block from the subagent output. Parse it with `json.loads`.

Validate:
- Top-level keys present: `skill`, `outcome`, `artifacts`, `summary`, `next`, `errors`, `blocker_description`
- `outcome` is one of `completed`, `bypassed`, `needs-input`, `blocked`, `partial`

If validation fails (no JSON block, parse error, missing keys, invalid outcome), treat as `outcome: blocked` with `blocker_description: "subagent did not return a valid structured result"`.

### Step 8: Post-hooks

For each skill in `autonomous_runner.post_hooks`, invoke as a subagent. Pattern same as pre-hooks (Step 5).

Post-hooks run only when the main skill's outcome was `completed` or `partial` (something was built/changed). Skip post-hooks for `bypassed`, `needs-input`, `blocked` outcomes.

### Step 9: Apply `on_outcome` policy

Look up the action for the run's outcome in `autonomous_runner.on_outcome` (defaults to `report` if outcome not in the map).

**Naming note:** The structured-result `outcome` value uses hyphens (e.g., `"needs-input"`). The `on_outcome` map keys use snake_case (e.g., `needs_input:`). Normalize before lookup:

```python
action = on_outcome.get(outcome.replace("-", "_"), "report")
```

Action values:

- **`report`**: Post the structured result's `summary` to Telegram via the bot's existing `lib/report-back.sh`:

  ```bash
  <bot-root>/lib/report-back.sh "<summary>"
  ```

  Include the PR URL (if `artifacts.pr_url`) and issue URL (if `artifacts.issue_url`) as links.

- **`report_and_pause`**: Post the report, then write a pause marker to the bot's state:

  ```bash
  touch <bot-runtime>/autonomous-runner.paused
  ```

  Subsequent cadence ticks check for this file in Step 1 (idle check) and skip the run. The pause is cleared by a human via `rm <bot-runtime>/autonomous-runner.paused` or by a manager bot per the existing `continuous-autonomous-mode` protocol.

- **`silent`**: No Telegram post; just record locally.

### Step 10: Update fleet-state

Append the run's outcome to the bot's run history:

```bash
python3 -c "
import json, os
from datetime import datetime
state_file = '<fleet-root>/fleet-state.json'
state = json.load(open(state_file)) if os.path.exists(state_file) else {'bots': {}}
state['bots'].setdefault('<bot-name>', {}).setdefault('autonomous_runner_runs', []).append({
    'timestamp': datetime.utcnow().isoformat() + 'Z',
    'outcome': '<outcome>',
    'pr_url': '<pr_url or empty>',
    'issue_url': '<issue_url or empty>',
})
json.dump(state, open(state_file, 'w'), indent=2)
"
```

(Use the existing fleet-state mechanism if the project has one — this is a placeholder pattern.)

EXIT.

## Behavior this skill deliberately does NOT do

- **Run adversarial-review on plans.** That happens inside the planning clauDNA skill that generated the plan (see clauDNA Phase 2 of the design).
- **Run /simplify on the diff.** That happens inside `/claudna:implement-plan` Step 6.5 (see clauDNA Phase 2).
- **Enforce factuality (test runs, type checks).** That happens inside the invoked clauDNA skill.
- **Make merge decisions.** `--auto` skills never merge.
- **Apply domain rules** (e.g., dbt anti-patterns, frontend conventions). Those live in the bot's `library/expertise/<area>.md` and are composed into the bot's CLAUDE.md.

This skill is a *thin coordinator* of policy: when to fire, what to pick, when to bypass, how to report. Discipline lives in the skills.

## When to add a new picker type

Currently only `github_issues` is supported. Future picker types might include `linear_issues`, `notion_database`, `local_backlog_file`. To add:

1. Add a new type identifier to `claudlobby/config.py` `AutonomousRunnerPicker.type` documentation.
2. Implement the picker logic in this skill's Step 3.
3. Update the validator to recognize the new type.
4. Add a test.

## When to add a new on_outcome action

Currently `report`, `report_and_pause`, `silent`. To add (e.g., `escalate` that posts to a different channel):

1. Add to `_OUTCOME_ACTIONS` in `claudlobby/validator.py`.
2. Implement the action in this skill's Step 9.
3. Update tests.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running the main skill subagent and then parsing prose instead of the JSON block | The JSON block is the LAST fenced ```json block. Parse only that. Reject runs that don't have one |
| Forgetting to release the lockfile if the procedure exits early | Use `trap` (bash) or `try/finally` (Python) to ensure release |
| Bypassing the risk classifier for skills that don't have a work item (e.g., `/tech-debt`) | The classifier doesn't apply when there is no picked work item. Skip it for non-picker configs |
| Running pre-hooks AFTER the main skill | Pre-hooks run BEFORE; post-hooks after. The names are not arbitrary |
| Posting verbose JSON to Telegram | Post the `summary` field only. JSON is for the orchestrator, not the human |
| Picking work items in parallel across multiple cadence ticks | The idle check (Step 1) prevents overlap. If you see multiple runs going, the lockfile mechanism is broken |
````

- [ ] **Step 2: Verify and commit**

```bash
ls /Users/chris/Projects/claudlobby/library/skills/autonomous-runner/
wc -l /Users/chris/Projects/claudlobby/library/skills/autonomous-runner/SKILL.md
```

Expected: SKILL.md present, ~300 lines.

```bash
cd /Users/chris/Projects/claudlobby
git add library/skills/autonomous-runner/SKILL.md
git commit -m "$(cat <<'EOF'
feat(autonomous-runner): add the wrapper skill body

The generic continuous-job wrapper that takes a clauDNA --auto skill +
config + cadence and runs it as the bot's continuous job. Documents
the 10-step procedure: idle check, quota, pick, classify, pre-hooks,
invoke, parse, post-hooks, on-outcome, state update.

Configurable per bot via fleet.yaml's autonomous_runner block.

Part of the autonomous-mode-and-orchestration design (2026-05-17 spec).
EOF
)"
```

---

## Task 8: Update `fleet.yaml.example` with an autonomous-runner block

**✅ COMPLETE** — `fleet.yaml.example` (Claudlobby `main`) has a commented `autonomous_runner` block plus a full `dbt-auto-bot` example bot entry, matching this task's example almost verbatim (including the `skill`/`cadence`/`target_repo`/`picker`/`bypass`/`on_outcome` shape).

**Files:**
- Modify: `fleet.yaml.example`

- [ ] **Step 1: Add an example block to a bot in the example file**

Find a bot in `fleet.yaml.example`. Add (or append a new commented example bot) showing the autonomous_runner config:

```yaml
# Example: a bot that autonomously resolves GitHub issues in a target dbt repo.
# Uncomment and customize to enable.
#
# - name: dbt-auto-bot
#   account: default
#   expertise: data-engineering
#   voice: precise
#   skills:
#     - autonomous-runner
#   protocols:
#     - continuous-autonomous-mode
#     - report-back
#   guardrails:
#     - no-push-main
#     - verify-before-merge
#   telegram:
#     token_env: DBT_AUTO_BOT_TG_TOKEN
#     chat_ids:
#       - "-100xxxxxxxx"
#   autonomous_runner:
#     skill: /claudna:implement-plan
#     cadence: 1h
#     target_repo: example-org/data-warehouse
#     picker:
#       type: github_issues
#       label: claudna-eligible
#       state: open
#       score_by: mission_alignment
#     bypass:
#       risk_classifier: structural_vs_mechanical
#       block_on: [structural]
#       on_bypass: comment_and_label
#     on_outcome:
#       completed: report
#       bypassed: report
#       needs_input: report_and_pause
#       blocked: report_and_pause
#       partial: report
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chris/Projects/claudlobby
git add fleet.yaml.example
git commit -m "docs(example): add autonomous_runner example bot to fleet.yaml.example"
```

---

## Task 9: Add the "Autonomous Worker" bot archetype

**✅ COMPLETE, different location than planned** — shipped as a standalone `library/skills/autonomous-runner/archetype.md` co-located with the skill, NOT as an appended section in `docs/bot-archetypes.md`. Claudlobby's actual docs convention (established by its own "canonical documentation structure" work, #149) uses `documentation/bot-archetypes.md`, which was left untouched — no "Autonomous Worker" entry there. `archetype.md` states the reasoning itself: "If/when other archetypes emerge..., promote shared archetype documentation to a top-level `library/archetypes/` category" — a deliberate improvement on this plan's single-shared-file design, not a gap.

**Files:**
- Modify: `docs/bot-archetypes.md`

- [ ] **Step 1: Append a new archetype section**

Open `docs/bot-archetypes.md`. Append a new section at the end:

```markdown
---

## Autonomous Worker

A worker bot that picks GitHub issues from a target repo per a cadence, classifies risk, and runs a clauDNA `--auto` skill (typically `/claudna:implement-plan`) to resolve them. Never merges. Reports outcomes to Telegram.

### When to use

- You have a clauDNA-installed bot fleet
- You have a target repository with a healthy backlog of well-formed issues (each containing an `## Implementation Plan` section, ideally produced by `/claudna:tech-debt --auto` or similar)
- You want overnight or cadence-based PR generation without per-issue human intervention
- You're OK with PRs awaiting a human review before merge (the contract is hard: this bot never merges)

### Composition

- **Expertise:** match the target repo's domain (`data-engineering` for dbt, `software-engineering` for general repos, `frontend-design` for UI repos, etc.)
- **Skills:** include `autonomous-runner`. Other skills like `dispatch` or `delegate` are NOT needed (this is a worker, not a manager).
- **Protocols:** `continuous-autonomous-mode` (for cadence + pause discipline), `report-back` (for Telegram), `verify-before-merge` (defensive — wrapper doesn't merge, but the protocol's mindset matters).
- **Guardrails:** `no-push-main` (worker should never push to main directly; PRs only), `pii-protection` if the target repo touches sensitive data.
- **Telegram:** own bot token. Posts to the squad chat for visibility.

### Example fleet.yaml block

See `fleet.yaml.example` for a complete example (the commented `dbt-auto-bot` entry).

### Cadence sizing

- **15m**: aggressive — useful for repos with rapid issue churn and many small fixes. Risk: noise on Telegram, quota burn.
- **1h** (recommended default): steady throughput, easy to reason about.
- **6h** to **24h**: low-key background presence. Good for repos where issues accumulate over days.

### Picker scoring

- **mission_alignment** (recommended): the bot reads `PROJECT_MISSION.md` from the target repo's default branch and scores issues against the north star. Highest-aligned issue wins each tick. Requires `PROJECT_MISSION.md` to exist in the target repo.
- **recency**: simplest. Picks the most recently created eligible issue. Good for fast-moving repos.
- **priority_label**: respects issue labels (`priority:critical`, `priority:high`, etc.). Good for repos that maintain priority discipline.

### Bypass tuning

- Default (`block_on: [structural]`): conservative. Mechanical and localized changes proceed; structural changes get a `needs-input` label.
- `block_on: []`: trust the wrapper's tripwires and the clauDNA skill's verification. Useful in tightly tested codebases.
- `block_on: [structural, localized]`: most conservative — only pure mechanical changes proceed. Useful for early-stage bots, or repos where headless changes need extra caution.

### On-outcome policy

Recommended defaults:
- `completed: report` — post to Telegram and continue
- `bypassed: report` — post the bypass reason, continue (the issue was labeled `needs-input`)
- `needs_input: report_and_pause` — post the synthesis-unresolvable details, pause the bot until a human resolves them
- `blocked: report_and_pause` — environment failure; surface for investigation before retrying
- `partial: report` — note the partial outcome, continue (the partial PR is already open)

### What this archetype is NOT

- **Not a manager bot.** Doesn't dispatch other bots. Doesn't orchestrate multi-bot work.
- **Not a planning bot.** Consumes plans (issues with implementation details); doesn't write plans. Pair with a separate `claudna-planner` bot if you want auto-planned issues.
- **Not a merge bot.** Opens PRs. Humans (or a separate reviewer bot via the manager protocol) merge.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chris/Projects/claudlobby
git add docs/bot-archetypes.md
git commit -m "docs(archetypes): add Autonomous Worker bot archetype"
```

---

## Task 10: Validation deployment

**PENDING** — deliberately descoped into its own open issue: [Claudfather/Claudlobby#294 — "Phase 4 Part C — autonomous-runner validation deployment"](https://github.com/Claudfather/Claudlobby/issues/294), filed 2026-05-18 (same day as Parts A/B merged), still **OPEN** as of this 2026-07-06 audit. Claudlobby's CHANGELOG.md states plainly: "End-to-end validation deployment is deferred to Phase 4 Part C." No `local/<fleet-name>/` overlay and no real (non-`.example`) `fleet.yaml` with an `autonomous_runner` block were found in the current checkout, consistent with this never having run. This is the one genuinely incomplete piece of Phase 4 — not blocked technically (Phases 1-3 prerequisites are met, and the wrapper skill exists), just not yet executed/prioritized.

**Re: the `/ironclad` fleet-override comparison** — `/ironclad`'s `fleet-dispatch-capability` protocol (see `documentation/planning/2026-06-02-ironclad-migration-claudlobby-to-clauDNA.md`) overrides an *existing* clauDNA skill's internal dispatch step at composition time, so the same command (`/ironclad`) behaves differently under a fleet vs. standalone. `autonomous-runner` is a different shape entirely: a wholly new Claudlobby-native skill that *wraps* clauDNA `--auto` skills (invoking them as subagents on a cadence, picking work, classifying risk, reporting to Telegram) — it doesn't override any clauDNA skill's dispatch. Both respect the same boundary (no fleet concepts inside clauDNA), but neither supersedes nor substitutes for the other; they solve different problems.

**Files:**
- Possibly create: a local fleet overlay under `local/<fleet-name>/`

This task validates the end-to-end work on a real target repo.

- [ ] **Step 1: Choose a target repo**

For initial validation, use a low-stakes repo with a healthy backlog. Candidates:
- `example-org/data-warehouse` (the repo behind the user's original `/loop` prompt)
- A personal sandbox repo (recommended for first run — fewer surprises)

If using a sandbox, ensure it has:
- A `PROJECT_MISSION.md` (if using `score_by: mission_alignment`)
- 2-3 well-formed GitHub issues with `## Implementation Plan` sections and the `claudna-eligible` label
- One of those issues should be mechanical (rename, format, doc fix) to test the happy path
- Optionally: one structural issue to test the bypass path

- [ ] **Step 2: Compose a single-bot fleet**

Create a fleet overlay at `local/autonomous-runner-validation/fleet.yaml`:

```yaml
accounts:
  default:
    anthropic_token_env: ANTHROPIC_API_KEY

bots:
  validation-worker:
    account: default
    expertise: software-engineering  # or data-engineering for dbt
    voice: precise
    skills:
      - autonomous-runner
    protocols:
      - continuous-autonomous-mode
      - report-back
    guardrails:
      - no-push-main
      - verify-before-merge
    telegram:
      token_env: VALIDATION_BOT_TG_TOKEN
      chat_ids:
        - "<your-chat-id>"
    autonomous_runner:
      skill: /claudna:implement-plan
      cadence: 1h
      target_repo: <your-org>/<your-repo>
      picker:
        type: github_issues
        label: claudna-eligible
        state: open
        score_by: mission_alignment
      bypass:
        risk_classifier: structural_vs_mechanical
        block_on: [structural]
        on_bypass: comment_and_label
      on_outcome:
        completed: report
        bypassed: report
        needs_input: report_and_pause
        blocked: report_and_pause
        partial: report
```

- [ ] **Step 3: Compose and validate**

```bash
cd /Users/chris/Projects/claudlobby
claudlobby --fleet autonomous-runner-validation validate
claudlobby --fleet autonomous-runner-validation generate
```

Expected: validates cleanly (some warnings about missing env vars are OK if intentional), generates a runtime/bots/validation-worker/ directory.

Inspect the generated CLAUDE.md:

```bash
cat /Users/chris/Projects/claudlobby/local/autonomous-runner-validation/runtime/bots/validation-worker/CLAUDE.md | grep -A 20 "Autonomous Runner"
```

Expected: the Autonomous Runner section appears with the configured skill, cadence, target repo, etc.

- [ ] **Step 4: Run one cadence tick manually**

Start the bot's Claude Code session:

```bash
cd /Users/chris/Projects/claudlobby/local/autonomous-runner-validation/runtime/bots/validation-worker/
./<bot>.service start  # or systemctl/launchd command per the generated unit file
```

Or invoke claude directly in the bot's directory and trigger the autonomous-runner skill manually:

```
/autonomous-runner
```

(Adjust per the bot's actual invocation pattern.)

- [ ] **Step 5: Observe the run**

Expected behavior:
1. Skill picks an eligible issue from the target repo
2. Risk classifier classifies the change (post the classification to Telegram for visibility during validation)
3. If `mechanical` or `localized`: proceeds to invoke `/claudna:implement-plan --source github <#> --auto`
4. The clauDNA skill runs end-to-end and emits a structured result
5. The wrapper parses the result, posts the summary to Telegram, updates fleet-state

- [ ] **Step 6: Verify the artifacts**

- A PR was opened in the target repo
- The PR body contains the `🤖 Opened by /claudna:implement-plan --auto` footer
- Telegram received the summary message
- `fleet-state.json` (or equivalent) records the run

- [ ] **Step 7: Test the bypass path**

Create or find a structural issue in the target repo. Manually trigger another tick. Expected:
- Risk classifier returns `structural`
- Wrapper posts a `## /autonomous-runner bypassed: classified as structural` comment on the issue
- Wrapper adds the `needs-input` label
- Wrapper posts a bypass notification to Telegram
- No PR opened

- [ ] **Step 8: Document validation results**

Append to this plan file (`04_phase4-claudlobby-wrapper.md`) a `## Validation Deployment Results` section with:
- Date
- Target repo
- Outcomes observed (e.g., "Issue #42 → PR #51 opened, summary posted to TG. Issue #43 → bypassed (structural), needs-input label applied")
- Any deviations from expected behavior
- Follow-up items to address before broader rollout

If bugs are found, file follow-up issues or fixes before proceeding to the PR.

No commit in this task unless deviations require code fixes (in which case commit fixes separately).

---

## Task 11: Update CHANGELOG.md

**✅ COMPLETE** — Claudlobby's `CHANGELOG.md` has explicit "Phase 4 Part A" and "Phase 4 Part B" entries citing issues [#278](https://github.com/Claudfather/Claudlobby/issues/278) and [#279](https://github.com/Claudfather/Claudlobby/issues/279), and names the deferred validation deployment (Task 10 / issue #294) directly.

**Files:**
- Modify or create: `CHANGELOG.md` (in claudlobby)

- [ ] **Step 1: Add Phase 4 entries**

If `CHANGELOG.md` does not exist in claudlobby, create it. Add:

```markdown
# Changelog

## [Unreleased]

### Added
- `library/skills/autonomous-runner/`: new wrapper skill that runs a clauDNA `--auto` skill as a bot's continuous job. Configurable per bot via fleet.yaml's `autonomous_runner` block.
- `library/skills/autonomous-runner/risk-classifier-prompt.md`: subagent prompt template for `structural_vs_mechanical` risk classification.
- `AutonomousRunnerConfig`, `AutonomousRunnerPicker`, `AutonomousRunnerBypass` dataclasses in `claudlobby/config.py`.
- `BotConfig.autonomous_runner` field (defaults to `None`; bots without this block are unaffected).
- `fleet.yaml.example`: example `autonomous_runner` block on a commented bot entry.
- `docs/bot-archetypes.md`: new "Autonomous Worker" archetype.
- Unit tests for the schema parsing, validation, and CLAUDE.md composition.

### Changed
- `claudlobby/loader.py`: parses the `autonomous_runner` block.
- `claudlobby/validator.py`: validates skill eligibility, cadence syntax, target_repo format, picker requirements, bypass actions, on_outcome vocabulary, and hook skill-name convention.
- `claudlobby/composer.py` and `templates/claude.md.j2`: render an `## Autonomous Runner — Your Continuous Job` section in the bot's CLAUDE.md when the block is configured.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/chris/Projects/claudlobby
git add CHANGELOG.md
git commit -m "docs(changelog): record Phase 4 autonomous-runner wrapper additions"
```

---

## Phase 4 Verification

**PARTIAL / mixed** — Step 1 (tests), Step 3 (docs in place), and Step 4 (push for review) are done: Parts A and B merged via [Claudfather/Claudlobby#278](https://github.com/Claudfather/Claudlobby/issues/278) and [#279](https://github.com/Claudfather/Claudlobby/issues/279). Step 2 (validation deployment completed) is the same open gap as Task 10 ([#294](https://github.com/Claudfather/Claudlobby/issues/294)). By this section's own stated bar — "the phase is not done if `autonomous-runner` cannot run end-to-end against a real fleet config" — Phase 4 is not fully done, though the large majority of the build (schema, skill body, docs, examples) is shipped and merged.

- [ ] **Step 1: Full test suite passes**

```bash
cd /Users/chris/Projects/claudlobby
python3 -m pytest tests/ -v
```

Expected: all tests pass, including the new ones.

- [ ] **Step 2: Validation deployment completed (Task 10)**

Confirm Task 10's smoke tests passed against a real target repo. The phase is not done if `autonomous-runner` cannot run end-to-end against a real fleet config.

- [ ] **Step 3: Documentation in place**

```bash
ls /Users/chris/Projects/claudlobby/library/skills/autonomous-runner/
grep -c "Autonomous Worker" /Users/chris/Projects/claudlobby/docs/bot-archetypes.md
grep -c "autonomous_runner" /Users/chris/Projects/claudlobby/fleet.yaml.example
```

Expected: skill files present, archetype documented, example present.

- [ ] **Step 4: Push for review**

```bash
cd /Users/chris/Projects/claudlobby
git push -u origin <branch-name>
gh pr create --title "Phase 4: autonomous-runner wrapper skill" \
  --body "$(cat <<'EOF'
## Summary

Implements Phase 4 of the autonomous-mode-and-orchestration design (spec: clauDNA's `documentation/specs/2026-05-17-autonomous-mode-and-orchestration-design.md`).

New skill `library/skills/autonomous-runner/` that bots include in fleet.yaml as their continuous job:

- Picks GitHub issues per a configurable picker (label-filtered, scored by mission/recency/priority)
- Qualitative pre-flight risk classification via the `structural_vs_mechanical` subagent classifier — blocks structural changes from headless work by default
- Invokes the configured clauDNA `--auto` skill (e.g., /implement-plan, /tech-debt) and parses the §10.C structured result
- Reports outcomes to Telegram via existing report-back protocol
- Configurable per-bot via fleet.yaml's `autonomous_runner` block

Schema changes (config.py, loader.py, validator.py, composer.py) are additive and backward-compatible: bots without an `autonomous_runner` block work unchanged.

Depends on clauDNA Phases 1-3 being merged (specifically: §10.C structured-result shape, /implement-plan --auto, the 9 normalized --auto skills).

## Test plan

- [ ] `python3 -m pytest tests/` passes (config, loader, validator, composer tests)
- [ ] `claudlobby --fleet <test-fleet> validate` succeeds on a fleet with an autonomous-runner bot
- [ ] `claudlobby --fleet <test-fleet> generate` produces a runtime/bots/.../CLAUDE.md with the Autonomous Runner section
- [ ] Validation deployment (Task 10): end-to-end run against a real target repo produces a PR with the bot footer
- [ ] Bypass path: a structural issue gets classified, commented, labeled `needs-input`, no PR opened

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Common Mistakes for this Phase

| Mistake | Fix |
|---|---|
| Skipping Task 1's orientation pass | claudlobby is a different codebase from clauDNA. The patterns aren't identical. Read first |
| Implementing parsing/validation/compose in a single mega-commit | Each task is a separate commit. The schema layers (config → loader → validator → composer) each test independently |
| Forgetting to add `autonomous_runner: None` default on `BotConfig` | Backward compat depends on it. Without the default, existing bots fail to construct |
| Implementing the risk classifier as Python code instead of a subagent | The classifier must be an LLM call (it makes a judgment that small Python can't make well). The prompt template is the source of truth |
| Running the structured-result parser on the entire subagent output instead of the LAST JSON block | Subagents often emit prose + JSON. Match the LAST fenced `json` block — not the first, and not the whole output |
| Skipping the lockfile in Step 1 of the skill procedure | Without it, two cadence ticks could overlap and produce conflicting PRs. Lockfile is non-negotiable |
| Posting full JSON to Telegram | Post the `summary` field only. JSON is for the orchestrator, not humans |
| Updating one validator check at a time | The validator changes are a single coherent block; test them together |
| Forgetting to update `fleet.yaml.example` | New users learn from the example. Stale example = confused users |

---

## What this phase does NOT do

- Add new clauDNA skills → all clauDNA work is Phases 1-3
- Change the `/claudna:implement-plan --auto` contract → Phase 3 owns it
- Build a manager-worker dispatch wrapper → claudlobby's existing `autonomous-sprint` skill covers manager patterns
- Polling PR status after `--auto` opens it → explicit out-of-scope per §9 of the design spec
- Multi-host fleet coordination → claudlobby v1 is single-host
- Hosted billing / subscription for autonomous runs → out of scope (claudlobby is local-first per its mission)

If a use case feels like it requires any of the above, it likely belongs in a future phase or in a different repo entirely.
