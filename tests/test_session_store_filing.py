"""Tests for writing harvested blocks (lib/claudna/session_store/filing.py) and the door calls it makes — spec §7.2.

What these guard:

* **Harvest edits only what harvest wrote.** A block amends a subject note
  only when every exact match is a session draft tagged ``harvest:subject``;
  a reviewed note, an authored draft or a web capture with the name gets a
  per-claim draft instead. The amend carries ``expect_trust: external``.
* **A new subject is a draft plus a fact**, in the session's project; when
  dedup routes it elsewhere, or Claudron refuses the amend, the claim goes
  per claim. One odd block never stops a run.
* **Every write is recorded as it lands, with the run id**, and harvest only
  files when the engine declares :data:`filing.FILING_CAPS`; a failed
  ``status`` leaves the session for the next run.
* **The door** sends names as ``--flag=value`` argv (one ``--alias`` each),
  JSON on stdin, and reads a refused amend's envelope as an answer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from test_session_store_harvest import BLOCK as HARVEST_BLOCK
from test_session_store_harvest import ON, _never_the_real_tools, summarized_session  # noqa: F401 (autouse)

from claudna.session_store import claudron, filing, harvest

BLOCK = {**HARVEST_BLOCK, "subject_hint": {**HARVEST_BLOCK["subject_hint"], "aliases": ["stg db"]},
         "section_hint": "Operations"}
ALL_CAPS = filing.FILING_CAPS
REAL = {name: getattr(claudron, name) for name in ("capabilities", "vault_root")}  # before any stub


class FakeVault:
    """``resolve`` and ``amend`` over an in-memory vault, and a capture that files notes into it."""

    def __init__(self):
        self.notes, self.captures, self.amends, self.resolves = {}, [], [], []
        self.capture_action, self.refuse = "created", False

    def add(self, path, title, *, trust="external", source_type="session", tags=(filing.SUBJECT_TAG,),
            aliases=(), tier="project:webapp"):
        self.notes[path] = {"path": path, "title": title, "trust": trust, "source_type": source_type,
                            "tags": list(tags), "aliases": list(aliases), "tier": tier}

    def resolve(self, names, *, project, cwd, env, vault=None):
        """Like Claudron's: exact names first, then any note sharing a word, in the project asked."""
        self.resolves.append((names, project))
        folded, words = [n.lower() for n in names], set(" ".join(names).lower().split())

        def exact(n):
            return any(t.lower() in folded for t in [n["title"], *n["aliases"]])
        hits = [n for n in self.notes.values() if n["tier"] == f"project:{project}"
                and (exact(n) or words & set(n["title"].lower().split()))]
        return [{**n, "match_type": "title", "exact": exact(n)} for n in sorted(hits, key=lambda n: not exact(n))]

    def amend(self, request, cwd, env, vault=None, *, run_id=None):
        self.amends.append((request, run_id))
        if self.refuse:
            return {"action": "rejected", "reason": "the note reads as 'trusted' now", "path": None, "vault": vault}
        refs = self.notes[request["note"]].setdefault("facts", {}).setdefault(request["fact"], set())
        fresh = request["evidence"]["ref"] not in refs
        refs.add(request["evidence"]["ref"])
        return {"action": "updated" if fresh else "unchanged", "reason": "", "path": request["note"], "vault": vault}

    def capture(self, finding, cwd, env, vault=None, run_id=None):
        self.captures.append((finding, run_id))
        path = f"projects/webapp/n{len(self.captures)}.md"
        if self.capture_action == "created":
            self.add(path, finding["title"], tags=finding["tags"])
        return {"action": self.capture_action, "path": path if self.capture_action == "created" else "other.md",
                "vault": vault}


@pytest.fixture
def fake(monkeypatch):
    vault = FakeVault()
    monkeypatch.setattr(claudron, "resolve", vault.resolve)
    monkeypatch.setattr(claudron, "amend", vault.amend)
    return vault


def file(fake, block=BLOCK, sid="s1", index=1, recorded=None):
    finding = harvest.finding_of(block, sid=sid, index=index, project="webapp", trust_aware=True)
    target = filing.Target(cwd="/work", env={}, vault="/v", project="webapp", run_id="harvest-1",
                           capture=fake.capture)
    return filing.file_block(block, finding, sid=sid, index=index, target=target,
                             record=(recorded if recorded is not None else []).append)


class TestFileBlock:
    def test_a_new_subject_is_a_session_draft_with_the_fact_appended(self, fake):
        recorded = []
        assert file(fake, recorded=recorded) == "created"
        ((subject, run_id),) = fake.captures
        assert subject["title"] == "(unverified) staging DB" and subject["source_type"] == "session"
        assert subject["source_url"] == "session:s1:1" and run_id == "harvest-1"
        assert {filing.HARVEST_TAG, filing.SUBJECT_TAG} <= set(subject["tags"]) and subject["project"] == "webapp"
        assert "staging" not in subject["body"]  # the model-written name never reaches a body line
        ((request, amend_run),) = fake.amends
        assert request == {"note": "projects/webapp/n1.md", "op": "append_fact", "section": "Operations",
                           "fact": BLOCK["claim"], "evidence": {"ref": "session:s1:1", "asserted_by": "user"},
                           "expect_trust": "external"}
        assert amend_run == "harvest-1"
        assert [(r["action"], r["path"]) for r in recorded] == [("created", "projects/webapp/n1.md"),
                                                                ("updated", "projects/webapp/n1.md")]
        assert fake.resolves[0] == (["staging DB", "stg db", "(unverified) staging DB"], "webapp")

    def test_the_next_fact_about_it_is_filed_under_the_same_subject(self, fake):
        file(fake)
        assert file(fake, {**BLOCK, "claim": "Staging restores from Monday's prod snapshot."}, sid="s2") == "filed"
        assert len(fake.captures) == 1 and fake.amends[-1][0]["note"] == "projects/webapp/n1.md"

    def test_the_same_fact_again_writes_nothing_and_another_session_adds_evidence(self, fake):
        file(fake)
        recorded = []
        assert file(fake, recorded=recorded) == "known" and recorded == []  # a replay: nothing landed
        assert file(fake, sid="s2") == "filed"  # recurrence: only its evidence lands
        assert fake.notes["projects/webapp/n1.md"]["facts"][BLOCK["claim"]] == {"session:s1:1", "session:s2:1"}

    def test_a_note_that_only_shares_a_word_is_not_the_subject(self, fake):
        file(fake)
        file(fake, {**BLOCK, "subject_hint": {"name": "Payments API", "kind": "service"}, "claim": "Charges retry."})
        assert [f["title"] for f, _ in fake.captures] == ["(unverified) staging DB", "(unverified) Payments API"]

    def test_an_alias_names_the_subject(self, fake):
        fake.add("projects/webapp/db.md", "Database", aliases=["Stg DB"])
        file(fake)
        assert fake.captures == [] and fake.amends[0][0]["note"] == "projects/webapp/db.md"

    def test_the_same_name_in_another_project_is_another_subject(self, fake):
        fake.add("projects/billing/s.md", "(unverified) staging DB", tier="project:billing")
        assert file(fake) == "created" and fake.amends[0][0]["note"] == "projects/webapp/n1.md"

    @pytest.mark.parametrize("trust,source_type,tags", [
        ("trusted", "session", [filing.SUBJECT_TAG]),  # promoted: reviewed memory now, a person's to edit
        ("draft", "", []),                               # an authored draft (a bot's plan)
        ("external", "url", [filing.SUBJECT_TAG]),      # a web capture carrying the tag
        ("external", "session", [filing.HARVEST_TAG]),   # a per-claim harvest draft, not a subject
    ])
    def test_an_exact_match_that_is_not_a_harvest_subject_is_never_edited(self, fake, trust, source_type, tags):
        fake.add("projects/webapp/s.md", "staging DB", trust=trust, source_type=source_type, tags=tags)
        assert file(fake) == "created" and fake.amends == []
        ((finding, run_id),) = fake.captures
        assert finding["title"].startswith("(unverified) staging DB: ") and run_id == "harvest-1"

    def test_any_foreign_exact_match_wins_over_a_harvest_subject(self, fake):
        """Order among exact matches is a title sort; ownership must not depend on it."""
        fake.add("projects/webapp/a.md", "(unverified) staging DB")
        fake.add("projects/webapp/b.md", "staging DB", trust="trusted", tags=[])
        file(fake)
        assert fake.amends == [] and fake.captures[0][0]["title"].startswith("(unverified) staging DB: ")

    def test_when_dedup_routes_the_new_subject_elsewhere_the_claim_goes_per_claim(self, fake):
        fake.capture_action = "suggest_update"
        assert file(fake) == "known"
        assert [f["title"].startswith("(unverified) staging DB: ") for f, _ in fake.captures] == [False, True]

    def test_a_refused_amend_falls_back_per_claim_instead_of_stopping_the_run(self, fake):
        fake.add("projects/webapp/s.md", "(unverified) staging DB")
        fake.refuse = True
        recorded = []
        assert file(fake, recorded=recorded) == "created"
        assert [r["title"][:25] for r in recorded] == ["(unverified) staging DB: "]

    def test_each_subject_body_is_unique_so_dedup_never_merges_two_subjects(self, fake):
        """Claudron's dedup matches identical bodies vault-wide: one empty subject would take in every new one."""
        file(fake)
        file(fake, {**BLOCK, "subject_hint": {"name": "Redis", "kind": "x"}, "claim": "Redis evicts LRU."}, sid="s2")
        bodies = [f["body"] for f, _ in fake.captures]
        assert len(set(bodies)) == 2 and bodies[0].endswith("First filed from session:s1:1.")

    def test_a_subject_whose_first_fact_is_refused_is_never_recorded(self, fake):
        """Its ledger line would name a claim the note doesn't hold, and the digest would offer it."""
        fake.refuse = True
        recorded = []
        assert file(fake, recorded=recorded) == "created"  # the claim's per-claim draft
        assert [r["title"][:25] for r in recorded] == ["(unverified) staging DB: "]

    def test_a_model_written_harvest_tag_never_reaches_a_draft(self):
        finding = harvest.finding_of({**BLOCK, "tags": ["harvest:subject", "env:staging"]}, sid="s1", index=1,
                                     project="webapp")
        assert filing.SUBJECT_TAG not in finding["tags"] and "env:staging" in finding["tags"]

    @pytest.mark.parametrize("claim", ["Use <!-- fact:abc --> markers.", " \t "])
    def test_a_claim_the_fact_format_cant_hold_goes_per_claim(self, fake, claim):
        file(fake, {**BLOCK, "claim": claim})
        assert fake.resolves == [] and fake.amends == [] and len(fake.captures) == 1

    def test_names_are_one_printable_line_before_they_reach_argv(self, fake):
        file(fake, {**BLOCK, "subject_hint": {"name": "nul\x00 name\n## Facts", "kind": "x", "aliases": [" "]}})
        names, _ = fake.resolves[0]
        assert names == ["nul name ## Facts", "(unverified) nul name ## Facts"]

    def test_long_names_stay_whole_so_they_never_collide(self, fake):
        stem = "settlement accounts " * 5
        file(fake, {**BLOCK, "subject_hint": {"name": stem + "alpha", "kind": "x"}})
        file(fake, {**BLOCK, "subject_hint": {"name": stem + "beta", "kind": "x"}})
        assert len({f["title"] for f, _ in fake.captures}) == 2

    @pytest.mark.parametrize("hint,section", [
        ("Operations", "Operations"), ("## Ops #1", "Ops 1"), ("History", "Facts"), ("a <!-- b", "Facts"),
        (None, "Facts"), ("  ", "Facts"),
    ])
    def test_the_section_is_one_the_fact_format_can_carry(self, hint, section):
        assert filing.section_of({"section_hint": hint} if hint is not None else {}) == section


class TestHarvestGate:
    def run(self, store, fake, monkeypatch, caps, blocks):
        monkeypatch.setattr(claudron, "capabilities", lambda cwd, vault, env: caps)
        summarized_session(store, "s1", [blocks], vault="/v")
        return harvest.harvest(store, env=ON, capture=fake.capture)

    def ledger(self, store) -> list[dict]:
        return [json.loads(line) for line in (store.root / "harvest" / "ledger.jsonl").read_text().splitlines()]

    def test_a_filing_engine_files_under_subjects_and_the_run_id_is_recorded(self, store, fake, monkeypatch):
        report = self.run(store, fake, monkeypatch, ALL_CAPS,
                          [BLOCK, {**BLOCK, "claim": "Staging restores from Monday's prod snapshot."}])
        assert (report.created, report.filed, report.known) == (1, 1, 0)
        assert report.run_id.startswith("harvest-") and {r for _, r in fake.amends} == {report.run_id}
        assert "1 fact(s) filed under existing subjects" in harvest.liveness_line(report)
        assert [(r["action"], r["run_id"]) for r in self.ledger(store)] == [
            ("created", report.run_id), ("updated", report.run_id), ("updated", report.run_id)]
        assert json.loads((store.root / "harvest" / "last_run.json").read_text())["run_id"] == report.run_id

    def test_without_subject_filing_it_writes_per_claim_session_drafts(self, store, fake, monkeypatch):
        self.run(store, fake, monkeypatch, ALL_CAPS - {"subject-filing"}, [BLOCK])
        ((finding, run_id),) = fake.captures
        assert fake.amends == [] and run_id is not None
        assert (finding["source_type"], finding["source_url"]) == ("session", "session:s1:1")

    def test_an_engine_before_trust_aware_reads_gets_inline_and_no_run_id(self, store, fake, monkeypatch):
        self.run(store, fake, monkeypatch, frozenset(), [BLOCK])
        ((finding, run_id),) = fake.captures
        assert finding["source_type"] == "inline" and "source_url" not in finding and run_id is None
        assert filing.HARVEST_TAG in finding["tags"]  # what Claudron's doctor m003 migrates on upgrade

    def test_a_failed_status_leaves_the_session_for_the_next_run(self, store, fake, monkeypatch):
        report = self.run(store, fake, monkeypatch, None, [BLOCK])
        assert fake.captures == [] and "claudron status failed" in report.errors[0]
        assert harvest.harvest(store, env={**ON, "CLAUDNA_HARVEST_INTERVAL_H": "0"}, capture=fake.capture).segments == 0

    def test_run_ids_differ_within_one_second(self):
        assert harvest.RunReport(started_epoch=1.0).run_id != harvest.RunReport(started_epoch=1.0).run_id


FAKE = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
verb = next(a for a in argv if a in ("status", "resolve", "amend", "capture"))
stdin = sys.stdin.read() if verb in ("amend", "capture") else ""
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": argv, "stdin": stdin}) + "\\n")
amend = os.environ.get("FAKE_AMEND", "updated")
replies = {
    "status": {"root": os.environ["FAKE_ROOT"], "capabilities": ["subjects", "amend", "runs", 7]},
    "resolve": {"name": "x", "candidates": [{"path": "k/a.md", "exact": True}, "junk"]},
    "amend": {"action": amend, "path": os.environ["FAKE_ROOT"] + "/k/a.md", "reason": "refused" * (amend == "rejected")},
    "capture": {"action": "created", "path": "k/n.md"},
}
print(json.dumps({"ok": amend != "rejected" or verb != "amend", "command": verb, "errors": [], "warnings": [],
                  "data": replies[verb]}))
sys.exit(2 if verb == "amend" and amend == "rejected" else 0)
"""


class TestDoor:
    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        for name, real in REAL.items():  # the door itself, against a fake binary
            monkeypatch.setattr(claudron, name, real)
        claudron._STATUS.clear()
        fake = tmp_path / "claudron"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        root = tmp_path / "vault"
        root.mkdir()
        yield {"PATH": os.environ["PATH"], "CLAUDNA_CLAUDRON_BIN": str(fake), "FAKE_LOG": str(tmp_path / "log"),
               "FAKE_ROOT": str(root.resolve())}
        claudron._STATUS.clear()

    def calls(self, env) -> list[dict]:
        return [json.loads(line) for line in Path(env["FAKE_LOG"]).read_text().splitlines()]

    def test_capabilities_come_from_the_same_cached_status_as_the_root(self, env):
        assert claudron.capabilities("/w", "/v", env) == {"subjects", "amend", "runs"}  # non-strings dropped
        assert claudron.vault_root("/w", "/v", env) == Path(env["FAKE_ROOT"])
        assert len(self.calls(env)) == 1

    def test_a_failed_status_is_unknown_capabilities_not_none(self, env):
        assert claudron.capabilities("/w", "/v", {**env, "CLAUDNA_CLAUDRON_BIN": "/nonexistent"}) is None

    def test_resolve_sends_one_alias_flag_per_name_and_the_project(self, env):
        found = claudron.resolve(["-rf staging", "a, b", "c"], project="webapp", cwd="/w", env=env, vault="/v")
        assert found == [{"path": "k/a.md", "exact": True}]
        (call,) = self.calls(env)
        assert call["argv"] == ["--vault", "/v", "resolve", "--name=-rf staging", "--alias=a, b", "--alias=c",
                                "--limit=10", "--json", "--project=webapp"]

    def test_amend_sends_the_request_and_run_id_on_stdin_and_answers_vault_relative(self, env):
        answer = claudron.amend({"note": "k/a.md", "op": "append_fact"}, "/w", env, "/v", run_id="harvest-1")
        assert answer == {"action": "updated", "reason": "", "path": "k/a.md", "vault": env["FAKE_ROOT"]}
        amend_call = next(c for c in self.calls(env) if "amend" in c["argv"])
        assert json.loads(amend_call["stdin"]) == {"note": "k/a.md", "op": "append_fact", "run_id": "harvest-1"}

    def test_a_refused_amend_is_an_answer_not_a_failure(self, env):
        answer = claudron.amend({"note": "k/a.md", "op": "append_fact"}, "/w", {**env, "FAKE_AMEND": "rejected"}, "/v")
        assert (answer["action"], answer["reason"]) == ("rejected", "refused")

    def test_capture_carries_the_run_id_only_when_given(self, env):
        claudron.capture({"type": "knowledge", "title": "t"}, "/w", env, "/v", run_id="harvest-1")
        claudron.capture({"type": "knowledge", "title": "t"}, "/w", env, "/v")
        stdins = [json.loads(c["stdin"]) for c in self.calls(env) if "capture" in c["argv"]]
        assert [s.get("run_id") for s in stdins] == ["harvest-1", None]


class TestMemoryHomes:
    """With ``memory-homes`` (Claudron#200 §2) a block is filed under its home's own type, kind and sections."""

    def test_a_block_becomes_its_homes_type_with_its_kind(self):
        finding = harvest.finding_of(BLOCK, sid="s1", index=1, project="webapp", trust_aware=True, homes=True)
        assert (finding["type"], finding["kind"]) == ("entity", "service")
        assert harvest.finding_of({**BLOCK, "home": "practice"}, sid="s1", index=1, project="w",
                                  homes=True)["type"] == "practice"
        assert harvest.finding_of(BLOCK, sid="s1", index=1, project="w")["type"] == "knowledge"  # older engine

    def test_a_person_block_is_still_held_back(self):
        person = {**BLOCK, "home": "person", "subject_hint": {"name": "Dana", "kind": "person"}}
        assert harvest.finding_of(person, sid="s1", index=1, project="w", homes=True) is None

    @pytest.mark.parametrize("home,hint,section", [
        ("entity", "behavior & GOTCHAS", "Behavior & gotchas"), ("entity", "Operations", "Facts"),
        ("concept", None, "Definition"), ("practice", "why", "Why"), ("decision", "History", "Context"),
        (None, "Background", "Background"), ("knowledge", "Background", "Background"),
    ])
    def test_a_fact_goes_only_under_one_of_its_notes_home_sections(self, home, hint, section):
        assert filing.section_of({"home": "entity", "section_hint": hint}, home) == section

    def test_the_section_follows_the_note_not_the_block(self, fake):
        """A concept block filed into an entity subject goes under an entity section, never `Definition`."""
        fake.add("projects/webapp/s.md", "(unverified) staging DB", tags=[filing.SUBJECT_TAG])
        fake.notes["projects/webapp/s.md"]["type"] = "entity"
        block = {**BLOCK, "home": "concept", "section_hint": "Definition"}
        finding = harvest.finding_of(block, sid="s1", index=1, project="webapp", trust_aware=True, homes=True)
        target = filing.Target(cwd="/w", env={}, vault="/v", project="webapp", run_id="r", capture=fake.capture,
                               homes=True)
        filing.file_block(block, finding, sid="s1", index=1, target=target, record=[].append)
        assert fake.amends[0][0]["section"] == "Facts"

    def test_an_engine_without_homes_keeps_the_hint_even_for_a_decision(self, fake):
        block = {**BLOCK, "home": "decision", "section_hint": "Background"}
        finding = harvest.finding_of(block, sid="s1", index=1, project="webapp", trust_aware=True)
        target = filing.Target(cwd="/w", env={}, vault="/v", project="webapp", run_id="r", capture=fake.capture)
        filing.file_block(block, finding, sid="s1", index=1, target=target, record=[].append)
        assert fake.amends[0][0]["section"] == "Background"

    def test_the_subject_draft_is_the_home_and_the_fact_lands_in_its_section(self, fake):
        block = {**BLOCK, "section_hint": "Operating it"}
        finding = harvest.finding_of(block, sid="s1", index=1, project="webapp", trust_aware=True, homes=True)
        target = filing.Target(cwd="/w", env={}, vault="/v", project="webapp", run_id="r", capture=fake.capture,
                               homes=True)
        filing.file_block(block, finding, sid="s1", index=1, target=target, record=[].append)
        ((subject, _),) = fake.captures
        assert (subject["type"], subject["kind"]) == ("entity", "service")
        assert fake.amends[0][0]["section"] == "Operating it"
