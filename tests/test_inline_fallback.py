"""The no-subagent inline fallback (#338).

Six skills assume the host can dispatch subagents. A host that loads `skills/`
but has no Task/Agent-style primitive (or ignores `agents/`) had no documented
way to run them at all — `ironclad` went further and called itself
"subagent-only". `skills/_shared/orchestration-guide.md` §14 is now the one
fallback, and these tests pin the two halves that rot independently: §14 defines
the path and its honest cost, and each of the six skills routes to it.

Text assertions, because the surface is prose an LLM executes. What they buy:
the fallback cannot lose its independence caveat (the part a reader is most
tempted to drop), and a skill cannot quietly go back to assuming dispatch.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
GUIDE = SKILLS_DIR / "_shared" / "orchestration-guide.md"

#: Skill → the file(s) whose dispatch step must name the fallback. Some skills
#: hold the dispatch in a depth/lens file rather than in SKILL.md, and audit
#: binds the fallback through its shared lens contract.
DISPATCH_FILES = {
    "adversarial-review": ["adversarial-review/SKILL.md"],
    "audit": [
        "audit/SKILL.md",
        "_shared/audit-lens-contract.md",
        "audit/access-path/access-path.md",
        "audit/data-model/data-model.md",
        "audit/docs/docs.md",
    ],
    "build-all": ["build-all/SKILL.md"],
    "forge": ["forge/SKILL.md"],
    "ironclad": ["ironclad/SKILL.md"],
    "worktree": ["worktree/SKILL.md"],
}


def guide_text() -> str:
    return GUIDE.read_text()


def section_14() -> str:
    text = guide_text()
    return text[text.index("## 14. No-subagent hosts") :]


class TestSection14Exists:
    def test_heading(self):
        assert "## 14. No-subagent hosts — the inline sequential fallback" in guide_text()

    def test_has_detection_inline_cost_and_agent_subsections(self):
        body = section_14()
        for heading in (
            "### 14.1 Detection",
            "### 14.2 The inline sequential path",
            "### 14.3 What the inline path costs",
            "### 14.4 When a skill names a bundled agent",
            "### 14.5 Which skills carry this fallback",
        ):
            assert heading in body, f"§14 missing {heading!r}"

    def test_dispatch_stays_the_primary_path(self):
        body = section_14()
        assert "primary path" in body
        assert "frozen" in body, "the inline path must carry the no-new-capability freeze"

    def test_disk_contract_is_the_load_bearing_rule(self):
        # Downstream phases (collect, retry, aggregate, publish) read from disk.
        # Writing to the same paths is what lets them run unchanged.
        body = section_14()
        assert "same directory, same filename, same format" in body
        assert "unchanged" in body

    def test_detection_forbids_probing_by_dispatch(self):
        assert "Never probe by dispatching" in section_14()

    def test_independence_cost_is_stated_not_softened(self):
        body = section_14()
        assert "Independence is gone." in body
        assert "share context" in body
        assert "weaker evidence" in body

    def test_inline_runs_announce_themselves(self):
        body = section_14()
        assert "No subagent dispatch available" in body
        assert "errors[]" in body, "--auto must record the inline path"

    def test_every_governed_skill_has_a_row(self):
        body = section_14()
        table = body[body.index("### 14.5") :]
        for skill in DISPATCH_FILES:
            assert f"/claudna:{skill}" in table, f"§14.5 needs a row for {skill}"


class TestSkillsRouteToTheFallback:
    def test_each_dispatch_file_names_section_14(self):
        missing = []
        for files in DISPATCH_FILES.values():
            for rel in files:
                if "§14" not in (SKILLS_DIR / rel).read_text():
                    missing.append(rel)
        assert missing == [], f"files not routing to orchestration-guide §14: {missing}"

    def test_ironclad_is_no_longer_subagent_only(self):
        text = (SKILLS_DIR / "ironclad" / "SKILL.md").read_text()
        assert "subagent-only" not in text.lower(), (
            "ironclad's 'subagent-only' claim is false on a host without dispatch"
        )
        assert "subagent-preferred" in text.lower()

    def test_ironclad_declares_an_inline_run_mode(self):
        text = (SKILLS_DIR / "ironclad" / "SKILL.md").read_text()
        assert "<fleet|subagent|inline> mode" in text, (
            "the mode indicator must be able to say the run was inline"
        )

    def test_worktree_states_the_permission_consequence(self):
        # Worktree's Step 3b reserves worktree-directory work for subagents
        # precisely because it prompts. Inline, the orchestrator does that work,
        # so the prompts are the fallback's real cost and must be stated up front.
        text = (SKILLS_DIR / "worktree" / "SKILL.md").read_text()
        assert "permission prompt" in text
        assert "one worktree at a time" in text

    def test_adversarial_review_flags_the_groupthink_interaction(self):
        text = (SKILLS_DIR / "adversarial-review" / "SKILL.md").read_text()
        assert "10th Man Rule regardless" in text, (
            "inline reviewers are the correlated-bias case the guard exists for"
        )
