"""The one user-facing Claudron degradation notice (#337).

Six skills depend on the Claudron CLI and every one of them degrades when it is
absent. Before #337 each wrote its own sentence — or, on `index`, none at all —
so the same condition looked like a different event depending on which skill hit
it. `skills/_shared/claudron-engine.md` §3.1 now owns one shape, and these tests
pin the two halves that can rot independently: the shape is defined in §3.1 with
a row per consumer, and every consumer routes to §3.1 instead of restating it.

These are text assertions because the surface is prose an LLM executes; there is
no unit to run. What they buy is that a skill cannot quietly reintroduce a
bespoke message, and §3.1 cannot lose a consumer row while the skills still
point at it.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
ENGINE = SKILLS_DIR / "_shared" / "claudron-engine.md"

#: Consumer → the files that must route to §3.1. Verb engines carry their
#: degradation branches in depth files, not in SKILL.md, so the map is per-file.
CONSUMER_FILES = {
    "capture": ["capture/SKILL.md"],
    "claudron": ["claudron/lookup.md", "claudron/status.md", "claudron/doctor.md"],
    "index": ["index/SKILL.md"],
    "init-project": ["init-project/SKILL.md"],
    "publish": ["publish/SKILL.md"],
    "recall": ["recall/SKILL.md"],
}


def engine_text() -> str:
    return ENGINE.read_text()


def section_31() -> str:
    text = engine_text()
    start = text.index("### 3.1 The standard degradation notice")
    end = text.index("\n## ", start)
    return text[start:end]


class TestNoticeIsDefinedOnce:
    def test_section_exists(self):
        assert "### 3.1 The standard degradation notice" in engine_text()

    def test_notice_carries_the_canonical_shape(self):
        body = section_31()
        for fragment in (
            "Claudron unavailable (<verdict>)",
            "<fallback>",
            "Install / configure:",
            "https://github.com/Claudfather/Claudron",
        ):
            assert fragment in body, f"§3.1 must state {fragment!r}"

    def test_notice_names_the_verdicts_it_interpolates(self):
        body = section_31()
        for verdict in ("absent", "present-no-vault", "engine failure"):
            assert verdict in body, f"§3.1 must explain <verdict> value {verdict!r}"

    def test_every_consumer_has_a_fallback_row(self):
        body = section_31()
        for consumer in CONSUMER_FILES:
            assert f"/claudna:{consumer}" in body, f"§3.1 needs a row for {consumer}"

    def test_the_auto_contract_is_stated(self):
        body = section_31()
        assert "errors[]" in body, "§3.1 must say the notice lands in errors[] under --auto"
        assert "No silent fallback" in body


class TestConsumersRouteToTheSharedNotice:
    def test_each_consumer_file_cites_section_31(self):
        missing = []
        for files in CONSUMER_FILES.values():
            for rel in files:
                text = (SKILLS_DIR / rel).read_text()
                if "§3.1" not in text:
                    missing.append(rel)
        assert missing == [], f"files not routing to claudron-engine.md §3.1: {missing}"

    def test_no_consumer_keeps_the_old_bespoke_wording(self):
        # The pre-#337 sentences, each of which described the same condition in
        # its own words. A recurrence here means a skill went back to improvising.
        stale = [
            "Claudron vault unavailable — wrote to the raw tree",
            "Claudron vault unavailable — scanning the raw tree's INDEX.md instead",
            "Claudron vault unavailable — writing the raw tree",
            "Claudron: not installed",
        ]
        offenders = []
        for md in sorted(SKILLS_DIR.rglob("*.md")):
            text = md.read_text()
            for phrase in stale:
                if phrase in text:
                    offenders.append(f"{md.relative_to(SKILLS_DIR)}: {phrase!r}")
        assert offenders == [], f"bespoke degradation wording survives: {offenders}"

    def test_index_announces_the_degradation_at_all(self):
        # index had no message before #337 — it simply indexed, which is the
        # silent-fallback case the issue was filed about.
        text = (SKILLS_DIR / "index" / "SKILL.md").read_text()
        assert "claudron-engine.md` §3.1" in text
        assert "errors[]" in text
