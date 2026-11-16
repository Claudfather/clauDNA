"""A handoff write moves its own session's scoped pointer (#496).

``session-store handoff-write`` publishes the save it writes for the session's
own workspace, so a handoff no longer needs a second ``continuity publish`` that
the model can skip. The compare-and-swap expects the reference that workspace
named as the session opened, which the store's SessionStart records.
"""
from __future__ import annotations

import io
import json
import sys

import pytest
from conftest import ACTOR, fire

import claudna.session_store.continuity as continuity
from claudna.session_store.cli import main
from claudna.session_store.continuity import (canonical_scope, publish_reference, reference_hash,
                                              resolve_predecessor, scope_hash)
from claudna.session_store.fsio import ensure_dir, read_json

pytestmark = pytest.mark.usefixtures("quiet_hooks")


def handoff(cwd, note: str) -> str:
    return (f"---\ncwd: {cwd}\nlast_updated: 2026-11-16T12:00:00Z\nschema_version: 2\n---\n\n"
            f"## Next Steps\n- 2026-11-16T12:00:00Z — {note}\n")


def own_ref(sid: str) -> dict:
    return {"kind": "handoff", "native_sid": sid, "relative_path": "handoff.md", "workflow_selector": "session"}


def opened(store, sid: str, workspace, *, source: str = "startup"):
    """A session opened the way Claude Code opens one: through the store's SessionStart hook."""
    assert fire(store, "SessionStart", sid, workspace, source=source) == f"session opened ({source})"
    return store.session(sid)


def write(store, monkeypatch, capsys, sid: str, workspace, note: str, *extra):
    """One handoff-write through the CLI, as the session skill runs it. No continuity publish follows it."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", sid)
    monkeypatch.setattr(sys, "stdin", io.StringIO(handoff(workspace, note)))
    code = main(["handoff-write", "--session", sid, "--host", "claude", "--root", str(store.root),
                 "--json", *extra])
    return code, json.loads(capsys.readouterr().out)


def resolve(store, monkeypatch, sid: str, workspace):
    """What a fresh session's resume, and its SessionStart briefing, resolve in that workspace."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", sid)
    return resolve_predecessor(store, current_sid=sid, host="claude", scope=f"workspace:{workspace}",
                               kind="handoff")


def index_refs(store, workspace) -> list:
    scope = canonical_scope(f"workspace:{workspace}")
    return read_json(store.root / "continuity" / scope_hash(scope) / "index.json")["refs"]


def published_predecessor(store, monkeypatch, workspace, sid: str = "previous"):
    """A predecessor whose save the pointer names, published the way step 7 did before #496."""
    handle = opened(store, sid, workspace)
    handle.paths.handoff.write_text(handoff(workspace, "from the predecessor"))
    monkeypatch.setenv("CLAUDE_SESSION_ID", sid)
    return publish_reference(store, current_sid=sid, host="claude", scope=f"workspace:{workspace}",
                             kind="handoff", workflow="session", relative_path="handoff.md")


@pytest.fixture
def workspace(tmp_path):
    path = tmp_path / "workspace"
    path.mkdir()
    return path


def test_a_handoff_write_moves_the_pointer_off_its_predecessor(store, workspace, monkeypatch, capsys):
    """#496: no continuity publish runs after the write, and the next fresh session still resumes it."""
    published_predecessor(store, monkeypatch, workspace)
    current = opened(store, "current", workspace)

    code, _ = write(store, monkeypatch, capsys, "current", workspace, "from the current session")
    assert code == 0
    opened(store, "next", workspace)
    selected = resolve(store, monkeypatch, "next", workspace)

    assert (selected.status, selected.source_sid) == ("found", "current")  # before #496: ("found", "previous")
    assert selected.handoff_path == current.paths.handoff


def test_the_write_reports_its_publication_and_keeps_its_own_pointer(store, workspace, monkeypatch, capsys):
    predecessor = published_predecessor(store, monkeypatch, workspace)
    current = opened(store, "current", workspace)
    assert read_json(current.paths.dir / continuity.START_PATH) == {
        "version": 1, "native_sid": "current", "scope": canonical_scope(f"workspace:{workspace}"),
        "workflow_selector": "session", "reference_hash": predecessor.reference_hash}

    code, result = write(store, monkeypatch, capsys, "current", workspace, "from the current session")

    assert code == 0 and result["status"] == "found" and result["handoff_path"] == str(current.paths.handoff)
    assert result["publish"] == {"status": "published", "scope": f"workspace:{workspace.resolve()}",
                                 "source_sid": "current", "reference_hash": reference_hash(own_ref("current")),
                                 "reason": None}
    assert index_refs(store, workspace) == [own_ref("current")]
    code, again = write(store, monkeypatch, capsys, "current", workspace, "later in the same session")
    assert code == 0 and again["publish"]["status"] == "published"
    assert index_refs(store, workspace) == [own_ref("current")]


def test_a_pointer_another_session_published_after_this_one_opened_is_left_in_place(store, workspace,
                                                                                    monkeypatch, capsys):
    published_predecessor(store, monkeypatch, workspace)
    opened(store, "left", workspace)
    right = opened(store, "right", workspace)  # both open while the pointer names the predecessor

    assert write(store, monkeypatch, capsys, "left", workspace, "left's work")[1]["publish"]["status"] == "published"
    code, result = write(store, monkeypatch, capsys, "right", workspace, "right's work")

    assert code == 0 and result["handoff_path"] == str(right.paths.handoff)  # the save itself stands
    assert result["publish"]["status"] == "conflict" and result["publish"]["source_sid"] == "left"
    assert "after this session opened" in result["publish"]["reason"]
    assert index_refs(store, workspace) == [own_ref("left")]
    opened(store, "next", workspace)
    assert resolve(store, monkeypatch, "next", workspace).source_sid == "left"


def test_without_a_start_record_only_an_empty_slot_or_its_own_pointer_is_published(store, workspace, tmp_path,
                                                                                   monkeypatch, capsys):
    """A session opened without the store's SessionStart (one resumed across this change) has no record."""
    published_predecessor(store, monkeypatch, workspace)
    origin = {"cwd": str(workspace), "repo": None, "branch": None, "head": None}
    store.session("unrecorded").open_session("startup", actor=ACTOR, origin=origin, transcript_path=None,
                                             agent_cli="claude")

    code, result = write(store, monkeypatch, capsys, "unrecorded", workspace, "unrecorded work")

    assert code == 0 and result["publish"]["status"] == "conflict"
    assert result["publish"]["source_sid"] == "previous" and "no record" in result["publish"]["reason"]
    assert index_refs(store, workspace) == [own_ref("previous")]
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    store.session("alone").open_session("startup", actor=ACTOR, origin={**origin, "cwd": str(elsewhere)},
                                        transcript_path=None, agent_cli="claude")
    code, result = write(store, monkeypatch, capsys, "alone", elsewhere, "the first save here")
    assert code == 0 and result["publish"]["status"] == "published"
    assert index_refs(store, elsewhere) == [own_ref("alone")]


def test_private_and_capture_off_sessions_stay_local(store, workspace, monkeypatch, capsys):
    published_predecessor(store, monkeypatch, workspace)
    opened(store, "private", workspace).set_private(True)

    code, private = write(store, monkeypatch, capsys, "private", workspace, "private work")
    code_off, capture_off = write(store, monkeypatch, capsys, "manual", workspace, "capture-off work")

    assert code == 0 and private["publish"]["status"] == "local" and "private" in private["publish"]["reason"]
    assert code_off == 0 and capture_off["publish"]["status"] == "local"
    assert "capture-off" in capture_off["publish"]["reason"]
    assert store.session("manual").capture_state() == "artifact-only"
    assert index_refs(store, workspace) == [own_ref("previous")]
    opened(store, "next", workspace)
    assert resolve(store, monkeypatch, "next", workspace).source_sid == "previous"


def test_a_checkpoint_keeps_the_pointer_where_it_is(store, workspace, monkeypatch, capsys):
    published_predecessor(store, monkeypatch, workspace)
    opened(store, "current", workspace)
    opened(store, "next", workspace)

    code, checkpoint = write(store, monkeypatch, capsys, "current", workspace, "checkpointed", "--no-publish")

    assert code == 0 and checkpoint["publish"] == {"status": "kept", "scope": None, "source_sid": None,
                                                   "reference_hash": None,
                                                   "reason": "--no-publish leaves the pointer where it is"}
    assert resolve(store, monkeypatch, "next", workspace).source_sid == "previous"
    code, handed_off = write(store, monkeypatch, capsys, "current", workspace, "handed off")
    assert code == 0 and handed_off["publish"]["status"] == "published"
    assert resolve(store, monkeypatch, "next", workspace).source_sid == "current"


def test_the_start_record_is_the_pointer_as_a_new_session_first_opens(store, workspace, monkeypatch, capsys):
    first = opened(store, "first", workspace)
    record = first.paths.dir / continuity.START_PATH
    assert read_json(record)["reference_hash"] is None  # no pointer yet: the slot was empty

    assert write(store, monkeypatch, capsys, "first", workspace, "the first save")[1]["publish"]["status"] \
        == "published"
    opened(store, "first", workspace, source="resume")  # the same session again: its record is kept
    fire(store, "PreCompact", "first", workspace, trigger="auto")
    fire(store, "SessionStart", "first", workspace, source="compact")
    assert read_json(record)["reference_hash"] is None
    cleared = opened(store, "after-clear", workspace, source="clear")
    assert read_json(cleared.paths.dir / continuity.START_PATH)["reference_hash"] == reference_hash(own_ref("first"))


def test_a_pointer_to_a_session_now_private_is_replaced(store, workspace, monkeypatch, capsys):
    """Resolvers answer unavailable for it, so the next save heals the workspace instead of leaving it blocked."""
    published_predecessor(store, monkeypatch, workspace)
    store.session("previous").set_private(True)
    opened(store, "current", workspace)
    opened(store, "next", workspace)
    assert resolve(store, monkeypatch, "next", workspace).status == "unavailable"

    code, result = write(store, monkeypatch, capsys, "current", workspace, "after the private one")

    assert code == 0 and result["publish"]["status"] == "published"
    assert resolve(store, monkeypatch, "next", workspace).source_sid == "current"


def test_an_unreadable_index_records_nothing_and_never_fails_the_session_start(store, workspace, monkeypatch,
                                                                               capsys):
    scope = canonical_scope(f"workspace:{workspace}")
    index_dir = ensure_dir(store.root / "continuity" / scope_hash(scope))
    (index_dir / "index.json").write_text("not json\n")

    current = opened(store, "current", workspace)
    code, result = write(store, monkeypatch, capsys, "current", workspace, "work")

    assert not (current.paths.dir / continuity.START_PATH).exists()
    assert code == 0 and result["publish"]["status"] == "unavailable"
    assert (index_dir / "index.json").read_text() == "not json\n"
