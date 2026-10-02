"""Tests for subject filing (lib/claudna/session_store/filing.py) and the door calls it makes — spec §7.2.

What these guard:

* **Harvest edits only what harvest wrote.** A block amends a subject note
  only on an exact match that is an external draft tagged
  ``origin:session-harvest``; any other exact match (a trusted note, an
  authored draft, a web capture) gets a per-claim draft instead.
* **A new subject is a draft plus a fact.** No exact match captures a
  bannered subject draft (``source_type: session``) and appends the fact to
  it; when dedup routes that capture elsewhere, the claim goes per-claim.
* **Every write carries the run id**, and harvest only files when the engine
  declares ``subjects``, ``amend`` and ``runs``.
* **The door** sends argv in ``--flag=value`` form, JSON on stdin, and
  checks each envelope; capabilities come from the same cached ``status``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from conftest import ACTOR, ORIGIN, segment_summary

from claudna.session_store import claudron, filing, harvest
from claudna.session_store.fsio import atomic_write_json

BLOCK = {"home": "entity", "subject_hint": {"name": "staging DB", "kind": "service", "aliases": ["stg db"]},
         "claim": "The staging DB is reset nightly at 02:00 UTC.", "asserted_by": "user", "tags": ["env:staging"],
         "section_hint": "Operations"}
ALL_CAPS = filing.FILING_CAPS | {harvest.TRUST_CAP}


class FakeVault:
    """``resolve`` and ``amend`` over an in-memory vault, plus a capture that files notes into it."""

    def __init__(self, notes=None, capture_action="created"):
        self.notes = {n["path"]: n for n in (notes or [])}
        self.captures, self.amends, self.capture_action = [], [], capture_action

    def resolve(self, name, *, aliases, note_type, cwd, env, vault=None):
        """Like Claudron's: exact names first, then any note sharing a word, all labelled ``title``."""
        names = [n.lower() for n in (name, *aliases)]
        words = set(" ".join(names).split())

        def exact(n):
            return any(t.lower() in names for t in [n["title"], *n.get("aliases", [])])
        hits = [n for n in self.notes.values() if exact(n) or words & set(n["title"].lower().split())]
        return [{**n, "match_type": "title"} for n in sorted(hits, key=lambda n: not exact(n))]

    def amend(self, request, cwd, env, vault=None, *, run_id=None):
        self.amends.append((request, run_id))
        note = self.notes[request["note"]]
        facts = note.setdefault("facts", {})
        refs = facts.setdefault(request["fact"], set())
        outcome = "unchanged" if request["evidence"]["ref"] in refs else "evidence_added" if refs else "fact_added"
        refs.add(request["evidence"]["ref"])
        return {"action": "unchanged" if outcome == "unchanged" else "updated", "outcome": outcome,
                "fact_id": "f" * 12, "path": request["note"], "vault": vault}

    def capture(self, finding, cwd, env, vault=None, run_id=None):
        self.captures.append((finding, run_id))
        path = f"knowledge/n{len(self.captures)}.md"
        if self.capture_action == "created":
            self.notes[path] = {"path": path, "title": finding["title"], "trust": "external",
                                "tags": finding["tags"]}
        return {"action": self.capture_action, "path": path if self.capture_action == "created" else "other.md",
                "vault": vault}


@pytest.fixture
def fake(monkeypatch):
    vault = FakeVault()
    monkeypatch.setattr(claudron, "resolve", vault.resolve)
    monkeypatch.setattr(claudron, "amend", vault.amend)
    return vault


def file(fake, block=BLOCK, sid="s1", index=1):
    finding = harvest.finding_of(block, sid=sid, index=index, project="webapp", trust_aware=True)
    return filing.file_block(block, finding, sid=sid, index=index, cwd="/work", env={}, vault="/v",
                             run_id="harvest-1", capture=fake.capture)


class TestFileBlock:
    def test_a_new_subject_is_a_session_draft_with_the_fact_appended(self, fake):
        answer = file(fake)
        ((subject, run_id),) = fake.captures
        assert subject["title"] == "(unverified) staging DB" and subject["source_type"] == "session"
        assert subject["source_url"] == "session:s1:1" and filing.HARVEST_TAG in subject["tags"]
        assert subject["project"] == "webapp" and run_id == "harvest-1"
        ((request, amend_run),) = fake.amends
        assert request == {"note": "knowledge/n1.md", "op": "append_fact", "section": "Operations",
                           "fact": BLOCK["claim"], "evidence": {"ref": "session:s1:1", "asserted_by": "user"}}
        assert amend_run == "harvest-1"
        assert (answer["action"], answer["path"], answer["title"], answer["amended"]) == \
            ("created", "knowledge/n1.md", "(unverified) staging DB", False)

    def test_the_next_fact_about_it_is_filed_under_the_same_subject(self, fake):
        file(fake)
        answer = file(fake, {**BLOCK, "claim": "Staging restores from Monday's prod snapshot."}, sid="s2")
        assert len(fake.captures) == 1 and fake.amends[-1][0]["note"] == "knowledge/n1.md"
        assert (answer["action"], answer["amended"]) == ("updated", True)

    def test_a_note_that_only_shares_a_word_is_not_the_subject(self, fake):
        """Live-caught: every subject draft shares "(unverified)", and resolve calls that a ``title`` match."""
        file(fake)
        file(fake, {**BLOCK, "subject_hint": {"name": "Payments API", "kind": "service"}, "claim": "Charges are idempotent."})
        assert [f["title"] for f, _ in fake.captures] == ["(unverified) staging DB", "(unverified) Payments API"]
        assert fake.amends[-1][0]["note"] == "knowledge/n2.md"

    def test_an_alias_names_the_subject(self, fake):
        fake.notes["k/db.md"] = {"path": "k/db.md", "title": "Database", "aliases": ["Stg DB"], "trust": "external",
                                 "tags": [filing.HARVEST_TAG]}
        file(fake)  # BLOCK's hint carries the alias "stg db"
        assert fake.captures == [] and fake.amends[0][0]["note"] == "k/db.md"

    def test_the_same_fact_again_writes_nothing_and_another_session_adds_evidence(self, fake):
        file(fake)
        assert file(fake)["action"] == "unchanged"  # a replay of the same segment
        assert file(fake, sid="s2")["action"] == "updated"  # recurrence: only its evidence lands
        assert fake.notes["knowledge/n1.md"]["facts"][BLOCK["claim"]] == {"session:s1:1", "session:s2:1"}

    @pytest.mark.parametrize("trust,tags", [
        ("trusted", [filing.HARVEST_TAG]),  # promoted: reviewed memory now, a person's to edit
        ("draft", []),                       # an authored draft (a bot's plan)
        ("external", []),                    # a web capture: external, but not harvest's
    ])
    def test_an_exact_match_harvest_did_not_write_is_never_edited(self, fake, trust, tags):
        fake.notes["k/staging.md"] = {"path": "k/staging.md", "title": "staging DB", "trust": trust, "tags": tags}
        answer = file(fake)
        assert fake.amends == []
        ((finding, run_id),) = fake.captures
        assert finding["title"].startswith("(unverified) staging DB: ") and run_id == "harvest-1"
        assert answer["title"] == finding["title"]

    def test_when_dedup_routes_the_new_subject_elsewhere_the_claim_goes_per_claim(self, fake):
        fake.capture_action = "suggest_update"
        answer = file(fake)
        assert [f["title"].startswith("(unverified) staging DB: ") for f, _ in fake.captures] == [False, True]
        assert fake.amends == [] and answer["action"] == "suggest_update"

    def test_a_claim_carrying_fact_markup_goes_per_claim(self, fake):
        file(fake, {**BLOCK, "claim": "Use <!-- fact:abc --> markers."})
        assert fake.amends == [] and len(fake.captures) == 1

    @pytest.mark.parametrize("hint,section", [
        ("Operations", "Operations"), ("## Ops #1", "Ops 1"), ("History", "Facts"), ("a <!-- b", "Facts"),
        (None, "Facts"), ("  ", "Facts"),
    ])
    def test_the_section_is_one_the_fact_format_can_carry(self, hint, section):
        assert filing.section_of({"section_hint": hint} if hint is not None else {}) == section


class TestHarvestGate:
    @pytest.fixture(autouse=True)
    def _stubs(self, monkeypatch):
        monkeypatch.setattr(claudron, "vault_root", lambda cwd, vault, env: Path(vault) if vault else None)

    def session(self, store, blocks):
        h = store.session("s1")
        h.open_session("startup", actor=ACTOR, origin={**ORIGIN, "repo": "webapp", "cwd": "/work"},
                       transcript_path="/t.jsonl", harvest={"enabled": True, "vault": "/v"})
        h.open_segment("session_open", 10)
        h.seal_segment(15, "precompact")
        atomic_write_json(h.paths.segment(1).dir / "summary.json", segment_summary("s1", 1, blocks, start=10, end=15))
        h.append("summary.completed", {"job_id": "j1", "artifact": "seg-001/summary.json",
                                       "input_sha256": "0" * 64, "duration_ms": 1}, seg=1)
        h.close_session("other")

    def test_a_filing_engine_files_under_subjects_and_the_run_id_is_recorded(self, store, fake, monkeypatch):
        monkeypatch.setattr(claudron, "capabilities", lambda cwd, vault, env: ALL_CAPS)
        self.session(store, [BLOCK, {**BLOCK, "claim": "Staging restores from Monday's prod snapshot."}])
        report = harvest.harvest(store, env={"CLAUDNA_HARVEST": "1"}, capture=fake.capture)
        assert (report.created, report.filed, report.known) == (1, 1, 0)
        assert report.run_id.startswith("harvest-") and {r for _, r in fake.amends} == {report.run_id}
        assert "1 fact(s) filed under existing subjects" in harvest.liveness_line(report)
        ledger = [json.loads(line) for line in (store.root / "harvest" / "ledger.jsonl").read_text().splitlines()]
        assert {(r["action"], r["path"], r["run_id"]) for r in ledger} == {
            ("created", "knowledge/n1.md", report.run_id), ("updated", "knowledge/n1.md", report.run_id)}
        last = json.loads((store.root / "harvest" / "last_run.json").read_text())
        assert last["run_id"] == report.run_id

    def test_an_engine_without_the_pipes_gets_per_claim_drafts(self, store, fake, monkeypatch):
        monkeypatch.setattr(claudron, "capabilities", lambda cwd, vault, env: frozenset({harvest.TRUST_CAP}))
        self.session(store, [BLOCK])
        harvest.harvest(store, env={"CLAUDNA_HARVEST": "1"}, capture=fake.capture)
        ((finding, run_id),) = fake.captures
        assert fake.amends == [] and run_id is None  # no `runs`: the flag would be refused
        assert (finding["source_type"], finding["source_url"]) == ("session", "session:s1:1")

    def test_an_engine_before_trust_aware_reads_gets_inline(self, store, fake, monkeypatch):
        monkeypatch.setattr(claudron, "capabilities", lambda cwd, vault, env: frozenset())
        self.session(store, [BLOCK])
        harvest.harvest(store, env={"CLAUDNA_HARVEST": "1"}, capture=fake.capture)
        ((finding, _),) = fake.captures
        assert finding["source_type"] == "inline" and "source_url" not in finding  # 0.6 refuses `session`
        assert filing.HARVEST_TAG in finding["tags"]  # what Claudron's doctor m003 migrates on upgrade


FAKE = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
stdin = "" if "status" in argv or "resolve" in argv else sys.stdin.read()
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": argv, "stdin": stdin}) + "\\n")
verb = next(a for a in argv if not a.startswith("-") and a not in (os.environ.get("FAKE_VAULT"),))
replies = {
    "status": {"root": os.environ["FAKE_ROOT"], "capabilities": ["subjects", "amend", "runs", 7]},
    "resolve": {"name": "x", "candidates": [{"path": "k/a.md", "match_type": "title"}, "junk"]},
    "amend": {"action": os.environ.get("FAKE_AMEND", "updated"), "path": os.environ["FAKE_ROOT"] + "/k/a.md",
              "outcome": "fact_added", "fact_id": "abcdef012345"},
    "capture": {"action": "created", "path": "k/n.md"},
}
print(json.dumps({"ok": True, "command": verb, "errors": [], "warnings": [], "data": replies[verb]}))
"""


class TestDoor:
    @pytest.fixture
    def env(self, tmp_path):
        claudron._STATUS.clear()
        fake = tmp_path / "claudron"
        fake.write_text(FAKE)
        fake.chmod(0o755)
        root = tmp_path / "vault"
        root.mkdir()
        yield {"PATH": os.environ["PATH"], "CLAUDNA_CLAUDRON_BIN": str(fake), "FAKE_LOG": str(tmp_path / "log"),
               "FAKE_ROOT": str(root.resolve()), "FAKE_VAULT": "/v"}
        claudron._STATUS.clear()

    def calls(self, env) -> list[dict]:
        return [json.loads(line) for line in Path(env["FAKE_LOG"]).read_text().splitlines()]

    def test_capabilities_come_from_the_same_cached_status_as_the_root(self, env):
        assert claudron.capabilities("/w", "/v", env) == {"subjects", "amend", "runs"}  # non-strings dropped
        assert claudron.vault_root("/w", "/v", env) == Path(env["FAKE_ROOT"])
        assert len(self.calls(env)) == 1

    def test_resolve_passes_names_as_flag_values_and_keeps_object_candidates(self, env):
        found = claudron.resolve("-rf staging", aliases=["a,b", "c"], note_type="knowledge", cwd="/w", env=env,
                                 vault="/v")
        assert found == [{"path": "k/a.md", "match_type": "title"}]
        (call,) = self.calls(env)
        assert call["argv"] == ["--vault", "/v", "resolve", "--name=-rf staging", "--type=knowledge", "--json",
                                "--aliases=a b,c"]

    def test_amend_sends_the_request_and_run_id_on_stdin_and_answers_vault_relative(self, env):
        answer = claudron.amend({"note": "k/a.md", "op": "append_fact"}, "/w", env, "/v", run_id="harvest-1")
        assert answer == {"action": "updated", "outcome": "fact_added", "fact_id": "abcdef012345",
                          "path": "k/a.md", "vault": env["FAKE_ROOT"]}
        amend_call = next(c for c in self.calls(env) if "amend" in c["argv"])
        assert amend_call["argv"] == ["--vault", "/v", "amend", "--stdin", "--json"]
        assert json.loads(amend_call["stdin"]) == {"note": "k/a.md", "op": "append_fact", "run_id": "harvest-1"}

    def test_a_rejected_amend_is_a_failure(self, env):
        with pytest.raises(claudron.CaptureError, match="amend"):
            claudron.amend({"note": "k/a.md", "op": "append_fact"}, "/w", {**env, "FAKE_AMEND": "rejected"}, "/v")

    def test_capture_carries_the_run_id_only_when_given(self, env):
        claudron.capture({"type": "knowledge", "title": "t"}, "/w", env, "/v", run_id="harvest-1")
        claudron.capture({"type": "knowledge", "title": "t"}, "/w", env, "/v")
        stdins = [json.loads(c["stdin"]) for c in self.calls(env) if "capture" in c["argv"]]
        assert [s.get("run_id") for s in stdins] == ["harvest-1", None]
