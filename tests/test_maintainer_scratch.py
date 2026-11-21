"""Maintainer operations use scratch beneath an explicit, verified owner."""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from release_toolchain import maintainer_paths  # noqa: E402


@pytest.fixture
def maintainer_state(tmp_path, monkeypatch):
    home = tmp_path / "private home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    root = tmp_path / "relocated state"
    monkeypatch.setenv("CLAUDNA_STATE_DIR", str(root))
    return root


def test_maintainer_owner_requires_explicit_standalone_and_is_not_a_session(maintainer_state):
    with pytest.raises(ValueError, match="native identity required"):
        maintainer_paths("qualification")
    assert not maintainer_state.exists()
    with ThreadPoolExecutor(max_workers=3) as pool:
        owners = list(pool.map(lambda _: maintainer_paths("qualification", standalone=True), range(3)))
    assert len({owner.owner_id for owner in owners}) == 3
    for owner in owners:
        assert owner.kind == "operation" and owner.provider is None
        assert owner.directory.parent == maintainer_state / "operations"
        assert owner.scratch.stat().st_mode & 0o777 == 0o700
        assert owner.artifacts.stat().st_mode & 0o777 == 0o700
        assert json.loads((owner.directory / "operation.json").read_text())["operation_id"] == owner.owner_id
    assert not (maintainer_state / "sessions").exists()


@pytest.mark.parametrize("default_root", [False, True])
def test_maintainer_native_context_wins_and_capture_off_creates_no_events(maintainer_state, monkeypatch, default_root):
    if default_root:
        monkeypatch.delenv("CLAUDNA_STATE_DIR")
        root = Path(os.environ["HOME"]) / ".claudna"
    else:
        root = maintainer_state
    monkeypatch.setenv("CODEX_THREAD_ID", "actual-fixture-owner")
    monkeypatch.setenv("CODEX_SESSION_ID", "actual-fixture-owner")
    monkeypatch.setenv("CLAUDNA_SESSION_STORE", "0")
    owner = maintainer_paths("qualification", standalone=True)
    assert owner.kind == "session" and owner.provider == "codex"
    assert owner.directory == root / "sessions/actual-fixture-owner"
    assert owner.scratch.is_dir() and owner.artifacts.is_dir()
    assert not (root / "operations").exists()
    assert not list(root.rglob("lifecycle.jsonl"))


@pytest.mark.parametrize("values", [{"CODEX_THREAD_ID": ""}, {"CODEX_THREAD_ID": "bad/owner"},
                                    {"CODEX_THREAD_ID": "one", "CODEX_SESSION_ID": "two"},
                                    {"CODEX_THREAD_ID": "one", "CLAUDE_SESSION_ID": "one"}])
def test_maintainer_invalid_native_context_never_falls_back(maintainer_state, monkeypatch, values):
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        maintainer_paths("qualification", standalone=True)
    assert not maintainer_state.exists()


def test_maintainer_explicit_native_owner_and_conflicts(maintainer_state, monkeypatch):
    with pytest.raises(ValueError, match="together"):
        maintainer_paths("qualification", session="fixture", standalone=True)
    assert not maintainer_state.exists()
    owner = maintainer_paths("qualification", session="cursor-fixture", host="cursor")
    assert owner.provider == "cursor" and owner.kind == "session"
    monkeypatch.setenv("CODEX_THREAD_ID", "actual-fixture")
    with pytest.raises(ValueError, match="conflicts"):
        maintainer_paths("qualification", session="cursor-fixture", host="cursor", standalone=True)
    assert not (maintainer_state / "operations").exists()


def test_maintainer_denied_allocation_retains_exact_partial_owner(maintainer_state, monkeypatch):
    import release_toolchain

    monkeypatch.setenv("CODEX_THREAD_ID", "denied-fixture")
    original = release_toolchain.ensure_dir

    def deny_artifacts(path):
        if path.name == "artifacts":
            raise PermissionError("fixture denied")
        return original(path)

    monkeypatch.setattr(release_toolchain, "ensure_dir", deny_artifacts)
    with pytest.raises(PermissionError, match="fixture denied"):
        maintainer_paths("qualification", standalone=True)
    assert (maintainer_state / "sessions/denied-fixture/scratch").is_dir()
    assert not (maintainer_state / "operations").exists()


def test_maintainer_rejects_redirected_owner_without_touching_sentinel(maintainer_state, tmp_path, monkeypatch):
    sentinel = tmp_path / "host-owned"
    sentinel.mkdir()
    (sentinel / "keep").write_text("unchanged")
    maintainer_state.mkdir()
    (maintainer_state / "sessions").symlink_to(sentinel, target_is_directory=True)
    monkeypatch.setenv("CODEX_THREAD_ID", "redirected-fixture")
    with pytest.raises(ValueError, match="redirects"):
        maintainer_paths("qualification", standalone=True)
    assert list(sentinel.iterdir()) == [sentinel / "keep"]
    assert (sentinel / "keep").read_text() == "unchanged"
