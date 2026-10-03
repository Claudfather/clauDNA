"""The live contract suite: clauDNA's Claudron door and harvest against a real ``claudron``.

``tests/test_claudron_contract.py`` checks clauDNA's mirrors against the
vendored copy of Claudron's contract; this checks the copy and the door
against a real engine. It is off unless ``CLAUDNA_CONTRACT`` says how to run,
so ``make check`` never depends on whichever engine a machine has installed:

* ``CLAUDNA_CONTRACT=exact``: this repo's contract CI leg (``make
  test-contract``), with the release ``contracts/claudron.ref`` names
  installed. The vendored copy must be exactly that engine's contract.
* ``CLAUDNA_CONTRACT=compat``: Claudron's CI, on every Claudron change. The
  engine may add to the contract but must keep everything the copy promises.

Either way, harvest must work end to end through the engine. And with the
mode set, a missing engine fails the run rather than skipping it: a contract
leg that skips is a gate that never closes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ACTOR, ORIGIN, complete_segment, segment_summary

from claudna.session_store import claudron, filing, harvest
from claudna.session_store.store import SessionStore

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sync_claudron_contract as sync  # noqa: E402

MODES = ("exact", "compat")
MODE = os.environ.get("CLAUDNA_CONTRACT", "")
COPY = json.loads(sync.SNAPSHOT.read_text(encoding="utf-8"))

pytestmark = pytest.mark.skipif(
    MODE not in MODES,
    reason=f"CLAUDNA_CONTRACT={MODE!r} is not one of {MODES}" if MODE
    else "the live contract suite runs with CLAUDNA_CONTRACT=exact|compat (make test-contract)")

#: A block the summarizer could write: one fact about a service, with a section the home doesn't have.
BLOCK = {"home": "entity", "subject_hint": {"name": "staging DB", "kind": "service", "aliases": []},
         "claim": "The staging DB is reset nightly at 02:00 UTC.", "asserted_by": "user", "tags": [],
         "section_hint": "Operations"}
SUBJECT = "projects/webapp/unverified-staging-db.md"


@pytest.fixture(autouse=True)
def _no_real_claudron_status():
    """Overrides the suite-wide stub (tests/conftest.py): here the real engine answers."""
    claudron._STATUS.clear()
    yield
    claudron._STATUS.clear()


@pytest.fixture(scope="module")
def claudron_bin() -> str:
    found = shutil.which(os.environ.get(claudron.CLAUDRON_ENV) or "claudron")
    if not found:
        pytest.fail(f"CLAUDNA_CONTRACT={MODE} but no claudron is installed (make deps-contract)")
    return found


@pytest.fixture
def env(claudron_bin) -> dict:
    return {**os.environ, claudron.CLAUDRON_ENV: claudron_bin, "CLAUDNA_HARVEST": "1"}


@pytest.fixture
def vault(tmp_path: Path, claudron_bin: str) -> Path:
    """A fresh git vault with its own identity (a CI runner has none), as `claudron init` makes it."""
    root = tmp_path / "vault"
    subprocess.run([claudron_bin, "init", str(root)], check=True, capture_output=True, text=True)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "contract@example.invalid"],
                 ["config", "user.name", "contract"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return root


@pytest.fixture
def work(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


def _session(store: SessionStore, sid: str, blocks: list[dict], *, vault: Path, work: Path) -> None:
    """A closed session in ``webapp`` whose one segment's summary carries ``blocks``, harvest-enabled."""
    handle = store.session(sid)
    handle.open_session("startup", actor=ACTOR, origin={**ORIGIN, "repo": "webapp", "cwd": str(work)},
                        transcript_path="/t.jsonl", harvest={"enabled": True, "vault": str(vault)})
    handle.open_segment("session_open", 10)
    handle.seal_segment(15, "precompact")
    complete_segment(handle, 1, segment_summary(sid, 1, blocks, start=10, end=15))
    handle.close_session("other")


def _harvest(store: SessionStore, env: dict) -> harvest.RunReport:
    claudron._STATUS.clear()
    report = harvest.harvest(store, env=env, force=True)
    assert report.status == "ok" and report.errors == [], report
    return report


def _frontmatter(note: Path) -> dict:
    import yaml

    return yaml.safe_load(note.read_text(encoding="utf-8").split("---", 2)[1])


def _section(note: Path, heading: str) -> str:
    text = note.read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, f"{note.name} has no ## {heading}"
    return match.group(1)


class TestTheContract:
    @pytest.mark.skipif(MODE != "exact", reason="exact mode only: a newer engine may add to the contract")
    def test_the_copy_is_the_installed_engines_contract(self, claudron_bin):
        assert sync.render(sync.installed_contract(claudron_bin)) == sync.SNAPSHOT.read_text(encoding="utf-8"), \
            "contracts/claudron.json is not this engine's contract: run scripts/sync_claudron_contract.py"

    def test_the_engine_keeps_everything_the_copy_promises(self, claudron_bin):
        """Additions are fine; a removal or rename breaks clauDNA, so it fails here, in the engine's own CI."""
        live = sync.installed_contract(claudron_bin)
        assert live["contract_version"] == COPY["contract_version"]
        for key in ("capabilities", "types", "relations", "maturity", "source_types", "trust_classes"):
            assert set(COPY[key]) <= set(live[key]), f"{key}: the engine dropped {set(COPY[key]) - set(live[key])}"
        for home, sections in COPY["homes"].items():
            assert home in live["homes"], f"the engine dropped the {home} home"
            assert set(sections) <= set(live["homes"][home]), f"{home}: the engine dropped a section"
        assert {t: d for t, d in live["type_dirs"].items() if t in COPY["type_dirs"]} == COPY["type_dirs"]
        assert live["person_dir"] == COPY["person_dir"]


class TestTheDoor:
    def test_status_reports_the_root_and_every_capability_harvest_gates_on(self, vault, work, env):
        found = claudron.status(str(work), str(vault), env)
        assert found is not None and found.root == Path(os.path.realpath(vault))
        assert {*filing.FILING_CAPS, filing.HOMES_CAP} <= found.capabilities


class TestHarvest:
    def test_a_block_files_under_its_home_and_a_replay_adds_nothing(self, tmp_path, vault, work, env):
        store = SessionStore(tmp_path / "store")
        second = {**BLOCK, "claim": "Staging restores from Monday's prod snapshot."}
        _session(store, "s1", [BLOCK, second], vault=vault, work=work)
        _harvest(store, env)

        note = vault / SUBJECT
        meta = _frontmatter(note)
        assert (meta["type"], meta["kind"], meta["maturity"], meta["source_type"]) == \
            ("entity", "service", "draft", "session")
        facts = _section(note, filing.HOME_DEFAULT_SECTION["entity"])  # "Operations" is no entity section
        assert BLOCK["claim"] in facts and second["claim"] in facts

        _session(store, "s2", [BLOCK], vault=vault, work=work)  # the same fact, from another session
        _harvest(store, env)
        assert _section(note, "Facts").count(BLOCK["claim"]) == 1

    def test_every_write_carries_the_run_and_revert_run_undoes_it(self, tmp_path, vault, work, env, claudron_bin):
        store = SessionStore(tmp_path / "store")
        _session(store, "s1", [BLOCK], vault=vault, work=work)
        report = _harvest(store, env)
        log = subprocess.run(["git", "log", "--format=%(trailers:key=Claudron-Run,valueonly,separator=)"],
                             cwd=vault, capture_output=True, text=True, check=True).stdout.split()
        assert log and set(log) == {report.run_id}

        subprocess.run([claudron_bin, "--vault", str(vault), "revert-run", report.run_id], check=True,
                       capture_output=True, text=True)
        assert not (vault / SUBJECT).exists()

    def test_once_a_person_promotes_the_subject_harvest_stops_writing_into_it(self, tmp_path, vault, work, env):
        store = SessionStore(tmp_path / "store")
        _session(store, "s1", [BLOCK], vault=vault, work=work)
        _harvest(store, env)
        assert claudron.promote(SUBJECT, str(vault), env)["action"] == "promoted"

        later = {**BLOCK, "claim": "Staging gets a fresh dump weekly."}
        _session(store, "s2", [later], vault=vault, work=work)
        report = _harvest(store, env)
        assert later["claim"] not in (vault / SUBJECT).read_text(encoding="utf-8")
        assert report.created == 1  # a per-claim draft instead
