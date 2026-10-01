"""Tests for the promotion digest (digest.py, and its ledger in harvest.py) — phase 5.

What these guard:

* **The ledger.** Every capture harvest makes is recorded with its note path
  and claim key; held person facts carry the key too.
* **Evidence** counts distinct sessions per claim key.
* **The digest** lists unreviewed drafts, most-reinforced first (user-asserted
  ahead on a tie), then held person facts, capped; a reviewed item leaves it.
* **SessionStart's line** reflects the digest after a harvest and after a review.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_session_store_harvest import BLOCK, ON, PERSON, FakeCapture, summarized_session

from claudna.session_store import digest, harvest, rollup
from claudna.session_store.cli import main

REPO_ROOT = Path(__file__).resolve().parent.parent
OTHER = {**BLOCK, "claim": "Deploys freeze on Fridays.", "asserted_by": "agent"}


def run(store, capture=None):
    return harvest.harvest(store, env=ON, capture=capture or FakeCapture(), force=True)


class TestLedgerAndEvidence:
    def test_every_capture_is_recorded_with_its_path_and_key(self, store):
        summarized_session(store, "s1", [[BLOCK, PERSON]])
        run(store)
        (rec,) = [json.loads(line) for line in (store.root / "harvest" / "ledger.jsonl").read_text().splitlines()]
        assert (rec["sid"], rec["seg"], rec["action"], rec["path"]) == ("s1", 1, "created", "knowledge/note-1.md")
        assert rec["key"] == rollup.dedup_key("blocks", BLOCK) and rec["vault"] == "/vaults/default"
        held = json.loads((store.root / "harvest" / "held.jsonl").read_text().splitlines()[0])
        assert held["key"] == rollup.dedup_key("blocks", PERSON)

    def test_evidence_counts_distinct_sessions(self, store):
        summarized_session(store, "s1", [[BLOCK]])
        summarized_session(store, "s2", [[BLOCK, OTHER]])
        run(store)
        seen = digest.evidence(store.root)
        assert seen[rollup.dedup_key("blocks", BLOCK)] == {"s1", "s2"}
        assert seen[rollup.dedup_key("blocks", OTHER)] == {"s2"}


class TestDigest:
    def test_most_reinforced_first_then_people(self, store):
        summarized_session(store, "s1", [[OTHER]])
        summarized_session(store, "s2", [[BLOCK, PERSON]])
        summarized_session(store, "s3", [[BLOCK]])
        # every capture creates its own note in the fake; give BLOCK one shared path
        answers = iter(["knowledge/other.md", "knowledge/staging.md", "knowledge/staging.md"])

        class SharedPath(FakeCapture):
            def __call__(self, finding, cwd, env, vault=None):
                super().__call__(finding, cwd, env, vault)
                return {"action": "created", "path": next(answers)}

        run(store, SharedPath())
        found = digest.items(store.root)
        assert [(i.kind, i.item, i.sessions) for i in found] == [
            ("draft", "knowledge/staging.md", 2), ("draft", "knowledge/other.md", 1),
            ("person", digest.person_item(rollup.dedup_key("blocks", PERSON)), 1)]

    def test_a_user_assertion_wins_a_tie(self, store):
        summarized_session(store, "s1", [[OTHER, {**BLOCK, "claim": "Users asked for dark mode."}]])
        run(store)
        assert digest.items(store.root)[0].asserted_by == "user"

    def test_only_created_or_updated_drafts_are_listed(self, store):
        summarized_session(store, "s1", [[BLOCK, OTHER]])
        run(store, FakeCapture(answers=["suggest_update", "rejected"]))
        assert digest.items(store.root) == []

    def test_a_reviewed_item_leaves_and_the_cap_holds(self, store):
        summarized_session(store, "s1", [[BLOCK, OTHER]])
        run(store)
        first = digest.items(store.root)[0]
        digest.mark_reviewed(store.root, first.item, outcome="promoted")
        assert first.item not in [i.item for i in digest.items(store.root)]
        assert len(digest.items(store.root, limit=1)) == 1
        with pytest.raises(ValueError):
            digest.mark_reviewed(store.root, "x", outcome="deleted")

    def test_the_review_line_follows_the_digest(self, store):
        summarized_session(store, "s1", [[BLOCK, PERSON]])
        run(store)
        line = (store.root / "harvest" / "review.txt").read_text()
        assert "1 draft(s)" in line and "1 person fact(s)" in line and "/claudna:capture --review" in line
        for item in digest.items(store.root):
            digest.mark_reviewed(store.root, item.item, outcome="kept")
        assert (store.root / "harvest" / "review.txt").read_text() == ""


class TestCliAndBriefing:
    def test_the_digest_verb(self, store, capsys):
        summarized_session(store, "s1", [[BLOCK]])
        run(store)
        root = ["--root", str(store.root)]
        assert main(["digest", "--json", *root]) == 0
        (item,) = json.loads(capsys.readouterr().out)
        assert main(["digest", "--done", item["item"], "--outcome", "promoted", *root]) == 0
        capsys.readouterr()
        assert main(["digest", *root]) == 0 and "nothing to review" in capsys.readouterr().out

    def test_session_start_shows_the_review_line(self, tmp_path):
        state = tmp_path / "home" / ".claudna"
        (state / "harvest").mkdir(parents=True)
        (state / "harvest" / "review.txt").write_text("to review: 2 draft(s) (/claudna:capture --review)\n")
        proc = subprocess.run(["bash", str(REPO_ROOT / "plugin-hooks" / "session-start.sh")], input="{}",
                              capture_output=True, text=True, cwd=tmp_path, timeout=20,
                              env={"HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin"})
        assert "Memory, to review: 2 draft(s)" in proc.stdout


class TestVaultRelativeItems:
    """``capture`` answers with an absolute path; ``claudron promote`` takes a vault-relative one."""

    def test_a_path_under_the_recorded_vault(self, tmp_path):
        vault = tmp_path / "vault"
        assert digest.vault_note(str(vault / "projects" / "w" / "n.md"), str(vault)) == (str(vault), "projects/w/n.md")

    def test_the_vault_is_found_by_its_marker_when_none_was_recorded(self, tmp_path):
        vault = tmp_path / "vault"
        (vault / "projects").mkdir(parents=True)
        (vault / digest.VAULT_MARKER).write_text("")
        assert digest.vault_note(str(vault / "projects" / "n.md"), None) == (str(vault), "projects/n.md")

    def test_a_relative_or_unplaceable_path_is_kept(self, tmp_path):
        assert digest.vault_note("knowledge/n.md", None) == (None, "knowledge/n.md")
        assert digest.vault_note(str(tmp_path / "n.md"), None) == (None, str(tmp_path / "n.md"))

    def test_the_ledger_and_digest_carry_the_relative_path(self, store, tmp_path):
        vault = tmp_path / "vault"
        digest.record_capture(store.root, sid="s1", seg=1, block=BLOCK, title="t", action="created",
                              path=str(vault / "projects" / "n.md"), vault=str(vault))
        (item,) = digest.items(store.root)
        assert (item.item, item.vault) == ("projects/n.md", str(vault))
