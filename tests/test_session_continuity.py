"""Owner-bound handoff references and filesystem continuity contracts."""
from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import ACTOR

import claudna.session_store.continuity as continuity
from claudna.session_store.continuity import (
    CONTEXT_PATH,
    INDEX_LIMIT,
    ContinuityError,
    canonical_scope,
    import_legacy,
    publish_reference,
    resolve_predecessor,
    scope_hash,
    write_context,
    write_handoff,
)
from claudna.session_store.fsio import atomic_write_json, ensure_dir, read_json
from claudna.session_store.project import load_lifecycle


def opened(store, sid: str, workspace: Path, *, provider: str = "claude", private: bool = False):
    handle = store.session(sid)
    handle.open_session("startup", actor=ACTOR,
                        origin={"cwd": str(workspace), "repo": None, "branch": None, "head": None},
                        transcript_path=None, agent_cli=provider)
    if private:
        handle.set_private(True)
    return handle


def handoff(cwd: str = "/work", *, updated: str = "2026-11-11T12:00:00Z") -> str:
    return (f"---\ncwd: {cwd}\nlast_updated: {updated}\nschema_version: 2\n---\n\n"
            "## Activity\n- 2026-11-11T12:00:00Z — completed work\n")


def source_file(tmp_path: Path, content: str = "legacy handoff\n") -> tuple[Path, str]:
    source = tmp_path / "legacy" / "handoff.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content)
    return source, hashlib.sha256(source.read_bytes()).hexdigest()


def public_manual(store, sid: str, host: str, scope: dict, monkeypatch):
    identity(monkeypatch, sid, host)
    write_context(store, current_sid=sid, host=host, scope=scope, privacy="public")


def identity(monkeypatch, sid: str, host: str = "claude"):
    monkeypatch.setenv("CLAUDE_SESSION_ID" if host == "claude" else "CODEX_THREAD_ID", sid)


def test_scope_is_canonical_tagged_and_bounded(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(workspace, target_is_directory=True)
    canonical = canonical_scope(f"workspace:{alias}")
    assert canonical == {"kind": "workspace", "value": str(workspace.resolve())}
    assert scope_hash(canonical) != scope_hash(canonical_scope("runtime:" + str(workspace.resolve())))
    assert canonical_scope("runtime:" + "x" * 256)["value"] == "x" * 256
    with pytest.raises(ContinuityError, match="256 bytes"):
        canonical_scope("runtime:" + "x" * 257)
    with pytest.raises(ContinuityError):
        canonical_scope("runtime:bad\nkey")
    with pytest.raises(ContinuityError, match="absolute"):
        canonical_scope("workspace:relative")


def test_handoff_write_is_v2_atomic_owner_bound_and_does_not_create_events(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    opened(store, "owner", workspace)
    identity(monkeypatch, "owner")
    handle = store.session("owner")
    before = load_lifecycle(handle.paths).events

    path = write_handoff(store, current_sid="owner", host="claude", content=handoff(str(workspace)))

    assert path == handle.paths.handoff and path.read_text() == handoff(str(workspace))
    assert path.stat().st_mode & 0o777 == 0o600
    assert [e["kind"] for e in load_lifecycle(handle.paths).events] == [e["kind"] for e in before]
    with pytest.raises(ContinuityError, match="repeats cwd"):
        write_handoff(store, current_sid="owner", host="claude",
                      content=handoff().replace("cwd: /work\n", "cwd: /work\ncwd: /elsewhere\n"))
    with pytest.raises(ContinuityError, match="UTC"):
        write_handoff(store, current_sid="owner", host="claude",
                      content=handoff(updated="2026-11-11T12:00:00+03:00"))
    with pytest.raises(ValueError, match="identity"):
        write_handoff(store, current_sid="someone-else", host="claude", content=handoff())


def test_capture_off_context_publishes_only_public_scoped_artifact(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    identity(monkeypatch, "manual")
    artifact = store.session("manual").paths.artifacts / "trace.txt"
    ensure_dir(artifact.parent)
    artifact.write_text("metadata-only artifact")
    context_path = write_context(store, current_sid="manual", host="claude", scope=scope, privacy="public")
    assert context_path.relative_to(store.session("manual").paths.dir).as_posix() == CONTEXT_PATH
    assert store.session("manual").capture_state() == "artifact-only"
    assert load_lifecycle(store.session("manual").paths).events == []
    published = publish_reference(store, current_sid="manual", host="claude", scope=scope,
                                  kind="artifact", workflow="scan", relative_path="artifacts/trace.txt")
    assert published.status == "found" and published.artifact_path == artifact
    index_path = store.root / "continuity" / scope_hash(scope) / "index.json"
    index = read_json(index_path)
    assert index["scope"] == scope and len(index["refs"]) == 1
    assert index_path.stat().st_mode & 0o777 == 0o600

    opened(store, "next", workspace)
    identity(monkeypatch, "next")
    selected = resolve_predecessor(store, current_sid="next", host="claude", scope=scope,
                                   kind="artifact", workflow="scan")
    assert selected.status == "found" and selected.source_sid == "manual"
    assert selected.artifact_path == artifact

    identity(monkeypatch, "manual")
    write_context(store, current_sid="manual", host="claude", scope=scope, privacy="private")
    identity(monkeypatch, "next")
    revoked = resolve_predecessor(store, current_sid="next", host="claude", scope=scope,
                                  kind="artifact", workflow="scan")
    assert revoked.status == "unavailable" and revoked.source_sid is None and revoked.candidate_sids == ()


def test_reference_cas_ambiguity_and_explicit_workflow_selection(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    first = opened(store, "first", workspace)
    second = opened(store, "second", workspace)
    first.paths.handoff.write_text(handoff(str(workspace)))
    second.paths.handoff.write_text(handoff(str(workspace)))
    identity(monkeypatch, "first")
    ref = publish_reference(store, current_sid="first", host="claude", scope=scope,
                            kind="handoff", workflow="alpha", relative_path="handoff.md")
    assert ref.reference_hash
    with pytest.raises(ContinuityError, match="exact current hash"):
        publish_reference(store, current_sid="first", host="claude", scope=scope,
                          kind="handoff", workflow="alpha", relative_path="handoff.md")
    identity(monkeypatch, "second")
    replaced = publish_reference(store, current_sid="second", host="claude", scope=scope,
                                 kind="handoff", workflow="alpha", relative_path="handoff.md",
                                 expect=ref.reference_hash)
    assert replaced.source_sid == "second"
    identity(monkeypatch, "first")
    with pytest.raises(ContinuityError, match="exact current hash"):
        publish_reference(store, current_sid="first", host="claude", scope=scope,
                          kind="handoff", workflow="alpha", relative_path="handoff.md",
                          expect=ref.reference_hash)
    identity(monkeypatch, "first")
    publish_reference(store, current_sid="first", host="claude", scope=scope,
                      kind="handoff", workflow="beta", relative_path="handoff.md")
    current = opened(store, "current", workspace)
    identity(monkeypatch, "current")
    ambiguous = resolve_predecessor(store, current_sid="current", host="claude", scope=scope, kind="handoff")
    assert ambiguous.status == "ambiguous" and set(ambiguous.candidate_sids) == {"first", "second"}
    selected = resolve_predecessor(store, current_sid="current", host="claude", scope=scope,
                                   kind="handoff", workflow="beta")
    assert selected.status == "found" and selected.source_sid == "first"
    assert selected.handoff_path == first.paths.handoff
    assert current.capture_state() == "captured"


def test_concurrent_same_identity_publication_has_one_cas_winner(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    for sid in ("left", "right"):
        opened(store, sid, workspace).paths.handoff.write_text(handoff(str(workspace)))
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    barrier = threading.Barrier(2)

    def attempt(sid):
        barrier.wait()
        try:
            publish_reference(store, current_sid=sid, host="claude", scope=scope,
                              kind="handoff", workflow="same", relative_path="handoff.md")
            return "won"
        except ContinuityError as exc:
            assert "exact current hash" in str(exc)
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ("left", "right")))
    assert sorted(outcomes) == ["conflict", "won"]
    index = read_json(store.root / "continuity" / scope_hash(scope) / "index.json")
    assert len(index["refs"]) == 1 and index["refs"][0]["native_sid"] in ("left", "right")


def test_explicit_handoff_without_pointer_and_same_session_private_read(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    private = opened(store, "private", workspace, private=True)
    private.paths.handoff.write_text(handoff(str(workspace)))
    scope = canonical_scope(f"workspace:{workspace}")
    identity(monkeypatch, "private")
    own = resolve_predecessor(store, current_sid="private", host="claude", scope=scope,
                              kind="handoff", from_session="private")
    assert own.status == "found" and own.handoff_path == private.paths.handoff
    assert own.reference_hash is None

    public = opened(store, "public", workspace)
    public.paths.handoff.write_text(handoff(str(workspace)))
    identity(monkeypatch, "private")
    other = resolve_predecessor(store, current_sid="private", host="claude", scope=scope,
                                kind="handoff", from_session="public")
    assert other.status == "found" and other.source_sid == "public" and other.reference_hash is None


def test_stale_and_symlinked_payloads_are_unavailable_and_not_fallback(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    source = opened(store, "source", workspace)
    source.paths.handoff.write_text(handoff(str(workspace)))
    identity(monkeypatch, "source")
    published = publish_reference(store, current_sid="source", host="claude", scope=scope,
                                  kind="handoff", workflow="main", relative_path="handoff.md")
    source.paths.handoff.unlink()
    opened(store, "current", workspace)
    identity(monkeypatch, "current")
    stale = resolve_predecessor(store, current_sid="current", host="claude", scope=scope, kind="handoff")
    assert stale.status == "unavailable" and stale.source_sid is None

    outside = tmp_path / "outside.md"
    outside.write_text("must not be read")
    source.paths.handoff.symlink_to(outside)
    symlinked = resolve_predecessor(store, current_sid="current", host="claude", scope=scope,
                                    kind="handoff", workflow="main")
    assert symlinked.status == "unavailable" and symlinked.source_sid is None
    assert published.reference_hash


def test_private_captured_session_cannot_publish_and_owner_directory_escape_is_rejected(store, tmp_path,
                                                                                       monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    private = opened(store, "private", workspace, private=True)
    private.paths.handoff.write_text(handoff(str(workspace)))
    identity(monkeypatch, "private")
    with pytest.raises(ContinuityError, match="private session"):
        publish_reference(store, current_sid="private", host="claude", scope=canonical_scope(f"workspace:{workspace}"),
                          kind="handoff", workflow="main", relative_path="handoff.md")

    outside = tmp_path / "outside-session"
    outside.mkdir()
    ensure_dir(store.root / "sessions")
    (store.root / "sessions" / "escaped").symlink_to(outside, target_is_directory=True)
    identity(monkeypatch, "escaped")
    with pytest.raises(ContinuityError, match="native owner path"):
        write_handoff(store, current_sid="escaped", host="claude", content=handoff())
    assert list(outside.iterdir()) == []


def test_index_bounds_and_schema_corruption_fail_closed(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    handle = opened(store, "owner", workspace)
    handle.paths.handoff.write_text(handoff(str(workspace)))
    identity(monkeypatch, "owner")
    index_dir = ensure_dir(store.root / "continuity" / scope_hash(scope))
    refs = [{"kind": "artifact", "native_sid": "owner", "relative_path": "artifacts/x",
             "workflow_selector": f"w{i}"} for i in range(256)]
    index = {"version": 1, "scope_hash": scope_hash(scope), "scope": scope,
             "refs": refs, "legacy_import_refs": []}
    atomic_write_json(index_dir / "index.json", index)
    with pytest.raises(ContinuityError, match="256 references"):
        publish_reference(store, current_sid="owner", host="claude", scope=scope,
                          kind="handoff", workflow="last", relative_path="handoff.md")
    assert len((index_dir / "index.json").read_bytes()) <= INDEX_LIMIT

    atomic_write_json(index_dir / "index.json", {**index, "scope": {"kind": "runtime", "value": "wrong"}})
    result = resolve_predecessor(store, current_sid="owner", host="claude", scope=scope, kind="handoff")
    assert result.status == "unavailable"


def test_manual_context_provider_and_capture_off_privacy_are_authoritative(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    identity(monkeypatch, "manual")
    artifact = store.session("manual").paths.artifacts / "capture.json"
    ensure_dir(artifact.parent)
    artifact.write_text("{}")
    write_context(store, current_sid="manual", host="claude", scope=scope, privacy="private")
    with pytest.raises(ContinuityError, match="artifact context provider"):
        write_context(store, current_sid="manual", host="codex", scope=scope, privacy="private")
    index_path = store.root / "continuity" / scope_hash(scope) / "index.json"
    assert not index_path.exists()
    with pytest.raises(ContinuityError):
        publish_reference(store, current_sid="manual", host="claude", scope=scope,
                          kind="artifact", workflow="private", relative_path="artifacts/capture.json")
    assert not index_path.exists()


def test_context_and_handoff_symlink_escapes_fail_closed(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    opened(store, "owner", workspace)
    identity(monkeypatch, "owner")
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    store.session("owner").paths.handoff.symlink_to(outside)
    with pytest.raises(ContinuityError, match="outside"):
        write_handoff(store, current_sid="owner", host="claude", content=handoff())
    assert outside.read_text() == "outside"


def test_fresh_current_session_discovery_is_read_only(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sid = "fresh-current"
    identity(monkeypatch, sid)
    assert not store.session(sid).exists()

    selection = resolve_predecessor(store, current_sid=sid, host="claude",
                                    scope=canonical_scope(f"workspace:{workspace}"))

    assert selection.status == "none"
    assert not store.session(sid).exists()


def test_concurrent_handoff_writes_never_expose_torn_content(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    handle = opened(store, "writer", workspace)
    identity(monkeypatch, "writer")
    variants = [handoff(str(workspace)) + ("A" * 100_000), handoff(str(workspace)) + ("B" * 100_000)]
    barrier = threading.Barrier(2)

    def write(content):
        barrier.wait()
        return write_handoff(store, current_sid="writer", host="claude", content=content).read_text()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, variants))

    assert all(result in variants for result in results)
    assert handle.paths.handoff.read_text() in variants


def test_legacy_import_is_owner_bound_durable_and_does_not_mutate_source(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    content = handoff(str(workspace))
    legacy_v1 = f"---\ncwd: {workspace}\nschema_version: 1\n---\n\n## Old Activity\n"
    source, digest = source_file(tmp_path, legacy_v1)
    original = source.read_bytes()
    public_manual(store, "imported", "claude", scope, monkeypatch)

    result = import_legacy(store, current_sid="imported", host="claude", scope=scope,
                           workflow="legacy", source=source, source_sha256=digest,
                           decision="initial", content=content)

    handle = store.session("imported")
    assert result["status"] == "found"
    assert result["source_sid"] == "imported"
    assert result["handoff_path"] == handle.paths.handoff
    assert result["receipt_path"].is_file()
    assert result["reference_hash"]
    assert handle.paths.handoff.read_text() == content
    assert handle.paths.handoff.read_bytes() != original
    assert source.read_bytes() == original
    assert result["handoff_path"].stat().st_mode & 0o777 == 0o600
    assert result["receipt_path"].stat().st_mode & 0o777 == 0o600
    receipt = read_json(result["receipt_path"])
    assert set(receipt) == {"version", "source_identity", "source_sha256", "imported_into", "decision"}
    assert receipt["version"] == 1 and receipt["source_sha256"] == digest
    assert receipt["source_identity"] == str(source.resolve())
    assert receipt["imported_into"] == {"native_sid": "imported", "provider": "claude"}
    assert load_lifecycle(handle.paths).events == []
    index_path = store.root / "continuity" / scope_hash(scope) / "index.json"
    index = read_json(index_path)
    assert len(index["refs"]) == 1 and len(index["legacy_import_refs"]) == 1
    assert index_path.stat().st_mode & 0o777 == 0o600


def test_legacy_import_same_source_is_cross_target_idempotent(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    content = handoff(str(workspace))
    source, digest = source_file(tmp_path, content)
    public_manual(store, "first-target", "claude", scope, monkeypatch)
    first = import_legacy(store, current_sid="first-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=digest,
                          decision="initial", content=content)
    index_path = store.root / "continuity" / scope_hash(scope) / "index.json"
    before = index_path.read_bytes()
    inode = index_path.stat().st_ino

    public_manual(store, "second-target", "claude", scope, monkeypatch)
    second = import_legacy(store, current_sid="second-target", host="claude", scope=scope,
                           workflow="legacy", source=source, source_sha256=digest,
                           decision="initial", content=content)

    assert second["status"] == "already_imported"
    assert second["source_sid"] == first["source_sid"] == "first-target"
    assert second["receipt_path"] == first["receipt_path"]
    assert not store.session("second-target").paths.handoff.exists()
    assert index_path.read_bytes() == before and index_path.stat().st_ino == inode


def test_legacy_import_changed_source_requires_reimport_and_keeps_old_receipt(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    source, first_digest = source_file(tmp_path, handoff(str(workspace)))
    first_content = source.read_text()
    public_manual(store, "import-target", "claude", scope, monkeypatch)
    first = import_legacy(store, current_sid="import-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=first_digest,
                          decision="initial", content=first_content)
    old_receipt_bytes = first["receipt_path"].read_bytes()

    changed_content = handoff(str(workspace), updated="2026-11-12T12:00:00Z")
    source.write_text(changed_content)
    changed_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises((ContinuityError, ValueError)):
        import_legacy(store, current_sid="import-target", host="claude", scope=scope,
                      workflow="legacy", source=source, source_sha256=changed_digest,
                      decision="initial", content=changed_content)

    second = import_legacy(store, current_sid="import-target", host="claude", scope=scope,
                           workflow="legacy", source=source, source_sha256=changed_digest,
                           decision="reimport", content=changed_content,
                           expect=first["reference_hash"])

    assert second["status"] == "found"
    assert second["receipt_path"] != first["receipt_path"]
    assert first["receipt_path"].read_bytes() == old_receipt_bytes
    assert read_json(second["receipt_path"])["source_sha256"] == changed_digest
    assert store.session("import-target").paths.handoff.read_text() == changed_content
    opened(store, "later-session", workspace)
    identity(monkeypatch, "later-session")
    predecessor = continuity.resolve_predecessor(store, current_sid="later-session", host="claude",
                                                 scope=scope, kind="handoff", workflow="legacy")
    assert predecessor.status == "found" and predecessor.source_sid == "import-target"
    assert predecessor.handoff_path.read_text() == changed_content


def test_legacy_reimport_advances_pointer_and_symlink_alias_is_same_source(
        store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    source, first_digest = source_file(tmp_path, "legacy source version one\n")
    public_manual(store, "old-target", "claude", scope, monkeypatch)
    first_content = handoff(str(workspace), updated="2026-11-10T12:00:00Z")
    first = import_legacy(store, current_sid="old-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=first_digest,
                          decision="initial", content=first_content)
    old_receipt_bytes = first["receipt_path"].read_bytes()

    source.write_text("legacy source version two\n")
    second_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    second_content = handoff(str(workspace), updated="2026-11-12T12:00:00Z")
    public_manual(store, "new-target", "claude", scope, monkeypatch)
    second = import_legacy(store, current_sid="new-target", host="claude", scope=scope,
                           workflow="legacy", source=source, source_sha256=second_digest,
                           decision="reimport", content=second_content,
                           expect=first["reference_hash"])

    assert second["status"] == "found" and second["source_sid"] == "new-target"
    assert first["receipt_path"].read_bytes() == old_receipt_bytes
    assert store.session("old-target").paths.handoff.read_text() == first_content
    opened(store, "later-session", workspace)
    identity(monkeypatch, "later-session")
    predecessor = continuity.resolve_predecessor(store, current_sid="later-session", host="claude",
                                                 scope=scope, kind="handoff", workflow="legacy")
    assert predecessor.status == "found" and predecessor.source_sid == "new-target"
    assert predecessor.handoff_path.read_text() == second_content

    alias = tmp_path / "legacy-alias.md"
    alias.symlink_to(source)
    public_manual(store, "alias-target", "claude", scope, monkeypatch)
    alias_result = import_legacy(store, current_sid="alias-target", host="claude", scope=scope,
                                 workflow="legacy", source=alias, source_sha256=second_digest,
                                 decision="initial", content=second_content)
    assert alias_result["status"] == "already_imported"
    assert alias_result["source_sid"] == "new-target"
    assert not store.session("alias-target").paths.handoff.exists()


def test_reimport_write_failures_keep_old_authority_and_retry_without_duplicate_refs(
        store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    source, first_digest = source_file(tmp_path, "legacy source version one\n")
    public_manual(store, "stable-target", "claude", scope, monkeypatch)
    first_content = handoff(str(workspace), updated="2026-11-10T12:00:00Z")
    first = import_legacy(store, current_sid="stable-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=first_digest,
                          decision="initial", content=first_content)
    old_receipt = first["receipt_path"]
    old_receipt_bytes = old_receipt.read_bytes()
    index_path = store.root / "continuity" / scope_hash(scope) / "index.json"
    old_index_bytes = index_path.read_bytes()

    source.write_text("legacy source version two\n")
    second_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    second_content = handoff(str(workspace), updated="2026-11-12T12:00:00Z")
    original_text = continuity.atomic_write_text

    def fail_handoff(path, text, *args, **kwargs):
        if path.name == "handoff.md":
            raise OSError("injected reimport handoff failure")
        return original_text(path, text, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(continuity, "atomic_write_text", fail_handoff)
        with pytest.raises(OSError):
            import_legacy(store, current_sid="stable-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=second_digest,
                          decision="reimport", content=second_content,
                          expect=first["reference_hash"])
    orphan_receipts = list(store.session("stable-target").paths.artifacts.glob("imports/**/*.json"))
    assert len(orphan_receipts) == 2
    new_receipt = next(path for path in orphan_receipts if path != old_receipt)
    assert old_receipt.read_bytes() == old_receipt_bytes
    assert index_path.read_bytes() == old_index_bytes
    assert store.session("stable-target").paths.handoff.read_text() == first_content

    def fail_index(path, text, *args, **kwargs):
        if path.name == "index.json":
            raise OSError("injected reimport index failure")
        return original_text(path, text, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(continuity, "atomic_write_text", fail_index)
        with pytest.raises(OSError):
            import_legacy(store, current_sid="stable-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=second_digest,
                          decision="reimport", content=second_content,
                          expect=first["reference_hash"])
    assert old_receipt.read_bytes() == old_receipt_bytes
    assert new_receipt.is_file()
    assert index_path.read_bytes() == old_index_bytes
    assert store.session("stable-target").paths.handoff.read_text() == second_content

    retried = import_legacy(store, current_sid="stable-target", host="claude", scope=scope,
                            workflow="legacy", source=source, source_sha256=second_digest,
                            decision="reimport", content=second_content,
                            expect=first["reference_hash"])
    final_index = read_json(index_path)
    assert retried["status"] == "found"
    assert old_receipt.read_bytes() == old_receipt_bytes
    assert new_receipt.is_file() and retried["receipt_path"] == new_receipt
    assert len(final_index["refs"]) == 1 and len(final_index["legacy_import_refs"]) == 1


def test_legacy_import_rejects_wrong_digest_and_sources_inside_store_before_target_creation(
        store, tmp_path, monkeypatch):
    outside, digest = source_file(tmp_path, handoff())
    with pytest.raises((ContinuityError, ValueError)):
        import_legacy(store, current_sid="digest-target", host="claude", scope="runtime:build",
                      workflow="legacy", source=outside, source_sha256="0" * 64,
                      decision="initial", content=outside.read_text())
    assert not store.session("digest-target").exists()

    inside = store.root / "legacy.md"
    ensure_dir(inside.parent)
    inside.write_text(handoff())
    inside_digest = hashlib.sha256(inside.read_bytes()).hexdigest()
    with pytest.raises((ContinuityError, ValueError)):
        import_legacy(store, current_sid="inside-target", host="claude", scope="runtime:build",
                      workflow="legacy", source=inside, source_sha256=inside_digest,
                      decision="initial", content=inside.read_text())
    assert not store.session("inside-target").exists()


def test_legacy_import_fails_closed_on_missing_or_corrupt_indexed_receipt(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    source, digest = source_file(tmp_path, handoff(str(workspace)))
    content = source.read_text()
    public_manual(store, "receipt-target", "claude", scope, monkeypatch)
    first = import_legacy(store, current_sid="receipt-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=digest,
                          decision="initial", content=content)
    receipt = first["receipt_path"]
    index_path = store.root / "continuity" / scope_hash(scope) / "index.json"
    index_before = index_path.read_bytes()

    receipt.unlink()
    with pytest.raises((ContinuityError, ValueError, OSError)):
        import_legacy(store, current_sid="receipt-target", host="claude", scope=scope,
                      workflow="legacy", source=source, source_sha256=digest,
                      decision="initial", content=content)
    assert index_path.read_bytes() == index_before
    receipt.write_text("{malformed")
    with pytest.raises((ContinuityError, ValueError, OSError)):
        import_legacy(store, current_sid="receipt-target", host="claude", scope=scope,
                      workflow="legacy", source=source, source_sha256=digest,
                      decision="initial", content=content)
    assert index_path.read_bytes() == index_before


def test_legacy_import_retries_receipt_handoff_and_index_write_failures(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    source, digest = source_file(tmp_path, handoff(str(workspace)))
    content = source.read_text()
    public_manual(store, "retry-target", "claude", scope, monkeypatch)
    original_json = continuity.atomic_write_json
    original_text = continuity.atomic_write_text

    def fail_receipt(path, *args, **kwargs):
        if "imports" in path.parts:
            raise OSError("injected receipt write failure")
        return original_json(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(continuity, "atomic_write_json", fail_receipt)
        with pytest.raises(OSError):
            import_legacy(store, current_sid="retry-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=digest,
                          decision="initial", content=content)
    target = store.session("retry-target")
    assert not target.paths.handoff.exists()
    assert not list(target.paths.artifacts.glob("imports/**/*.json"))

    def fail_handoff(path, text, *args, **kwargs):
        if path.name == "handoff.md":
            raise OSError("injected handoff write failure")
        return original_text(path, text, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(continuity, "atomic_write_text", fail_handoff)
        with pytest.raises(OSError):
            import_legacy(store, current_sid="retry-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=digest,
                          decision="initial", content=content)
    receipt_files = list(target.paths.artifacts.glob("imports/**/*.json"))
    assert len(receipt_files) == 1 and not target.paths.handoff.exists()

    def fail_index(path, text, *args, **kwargs):
        if path.name == "index.json":
            raise OSError("injected index write failure")
        return original_text(path, text, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(continuity, "atomic_write_text", fail_index)
        with pytest.raises(OSError):
            import_legacy(store, current_sid="retry-target", host="claude", scope=scope,
                          workflow="legacy", source=source, source_sha256=digest,
                          decision="initial", content=content)
    assert target.paths.handoff.read_text() == content
    index_path = store.root / "continuity" / scope_hash(scope) / "index.json"
    assert not index_path.exists()

    result = import_legacy(store, current_sid="retry-target", host="claude", scope=scope,
                           workflow="legacy", source=source, source_sha256=digest,
                           decision="initial", content=content)
    assert result["status"] == "found"
    assert len(list(target.paths.artifacts.glob("imports/**/*.json"))) == 1
    assert len(read_json(index_path)["legacy_import_refs"]) == 1


def test_legacy_import_conflicts_with_canonical_pointer_without_receipt(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    source, digest = source_file(tmp_path, handoff(str(workspace)))
    owner = opened(store, "existing-owner", workspace)
    owner.paths.handoff.write_text(handoff(str(workspace)))
    identity(monkeypatch, "existing-owner")
    publish_reference(store, current_sid="existing-owner", host="claude", scope=scope,
                      kind="handoff", workflow="legacy", relative_path="handoff.md")
    public_manual(store, "new-target", "claude", scope, monkeypatch)

    with pytest.raises((ContinuityError, ValueError)):
        import_legacy(store, current_sid="new-target", host="claude", scope=scope,
                      workflow="legacy", source=source, source_sha256=digest,
                      decision="initial", content=source.read_text())
    assert not store.session("new-target").paths.handoff.exists()


def test_legacy_initial_import_preserves_a_different_owned_handoff(store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    source, digest = source_file(tmp_path, "legacy-v1 input\n")
    public_manual(store, "occupied-target", "claude", scope, monkeypatch)
    target = store.session("occupied-target")
    existing = handoff(str(workspace), updated="2026-11-10T12:00:00Z")
    target.paths.handoff.write_text(existing)

    with pytest.raises((ContinuityError, ValueError)):
        import_legacy(store, current_sid="occupied-target", host="claude", scope=scope,
                      workflow="legacy", source=source, source_sha256=digest,
                      decision="initial", content=handoff(str(workspace)))

    assert target.paths.handoff.read_text() == existing
    assert not list(target.paths.artifacts.glob("imports/**/*.json"))


def test_private_legacy_import_stays_local_and_concurrent_import_has_one_winner(
        store, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scope = canonical_scope(f"workspace:{workspace}")
    source, digest = source_file(tmp_path, handoff(str(workspace)))
    private = opened(store, "private-import", workspace, private=True)
    private.paths.handoff.unlink(missing_ok=True)
    identity(monkeypatch, "private-import")
    local = import_legacy(store, current_sid="private-import", host="claude", scope=scope,
                          workflow="private", source=source, source_sha256=digest,
                          decision="initial", content=source.read_text())
    assert local["status"] == "found" and local["handoff_path"].is_file()
    index_path = store.root / "continuity" / scope_hash(scope) / "index.json"
    assert not index_path.exists()

    for sid in ("race-one", "race-two"):
        public_manual(store, sid, "claude", scope, monkeypatch)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    barrier = threading.Barrier(2)

    def attempt(sid):
        barrier.wait()
        return import_legacy(store, current_sid=sid, host="claude", scope=scope,
                             workflow="concurrent", source=source, source_sha256=digest,
                             decision="initial", content=source.read_text())["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(attempt, ("race-one", "race-two")))
    assert sorted(statuses) == ["already_imported", "found"]
    assert sum(store.session(sid).paths.handoff.exists() for sid in ("race-one", "race-two")) == 1


def test_explicit_artifact_owner_can_read_unpublished_private_manual_plan(store, monkeypatch):
    identity(monkeypatch, "manual")
    artifact = store.session("manual").paths.artifacts / "plan.md"
    ensure_dir(artifact.parent)
    artifact.write_text("private canonical plan")
    write_context(store, current_sid="manual", host="claude", scope="runtime:task", privacy="private")
    before = {p.relative_to(store.root): p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    selected = continuity.selected_artifact(store, current_sid="manual", host="claude",
                                           scope="runtime:task", from_session="manual", path=artifact)
    assert selected.status == "found" and selected.artifact_path == artifact
    assert not store.session("manual").paths.lifecycle.exists()
    assert not (store.root / "continuity").exists()
    assert before == {p.relative_to(store.root): p.read_bytes() for p in store.root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("privacy", ["public", "private", "unknown", "wrong-scope", "corrupt", "partial"])
def test_explicit_prior_artifact_requires_public_scope_without_pointer(store, monkeypatch, privacy):
    scope = "runtime:task"
    artifact = store.session("prior").paths.artifacts / "plan.md"
    ensure_dir(artifact.parent)
    artifact.write_text("selected plan")
    if privacy != "unknown":
        identity(monkeypatch, "prior")
        write_context(store, current_sid="prior", host="claude",
                      scope="runtime:other" if privacy == "wrong-scope" else scope,
                      privacy="private" if privacy == "private" else "public")
    if privacy == "corrupt":
        (store.session("prior").paths.dir / CONTEXT_PATH).write_text("broken")
    if privacy == "partial":
        store.session("prior").paths.lifecycle.write_text("{broken\n")
    identity(monkeypatch, "current")
    selected = continuity.selected_artifact(store, current_sid="current", host="claude", scope=scope,
                                           from_session="prior", path=artifact)
    assert selected.status == ("found" if privacy == "public" else "unavailable")
    assert selected.artifact_path == (artifact if privacy == "public" else None)
    assert not (store.root / "continuity").exists()
    assert not store.session("current").paths.dir.exists()


def test_explicit_artifact_rejects_escape_conflicting_owner_and_loop(store, tmp_path, monkeypatch):
    identity(monkeypatch, "owner")
    artifacts = store.session("owner").paths.artifacts
    ensure_dir(artifacts)
    external = tmp_path / "external.md"
    external.write_text("outside")
    (artifacts / "escape.md").symlink_to(external)
    (artifacts / "loop.md").symlink_to(artifacts / "loop.md")
    (artifacts / "plan.md").write_text("canonical")
    for path in (artifacts / "escape.md", artifacts / "loop.md", Path("relative.md"), artifacts):
        result = continuity.selected_artifact(store, current_sid="owner", host="claude",
                                             scope="runtime:task", from_session="owner", path=path)
        assert result.status == "unavailable" and result.artifact_path is None
    identity(monkeypatch, "other")
    result = continuity.selected_artifact(store, current_sid="owner", host="claude",
                                         scope="runtime:task", from_session="owner", path=artifacts / "plan.md")
    assert result.status == "unavailable" and result.artifact_path is None


def test_explicit_artifact_cli_requires_source_and_rejects_workflow(store, monkeypatch, capsys):
    import json

    from claudna.session_store.cli import main

    identity(monkeypatch, "owner", "codex")
    artifact = store.session("owner").paths.artifacts / "plan.md"
    ensure_dir(artifact.parent)
    artifact.write_text("selected plan")
    args = ["continuity", "artifact-path", "--root", str(store.root), "--session", "owner",
            "--host", "codex", "--scope", "runtime:task", "--path", str(artifact), "--json"]
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["artifact_path"] is None
    assert main(args + ["--from-session", "owner", "--workflow", "plan"]) == 2
    assert json.loads(capsys.readouterr().out)["artifact_path"] is None
    assert main(args + ["--from-session", "owner"]) == 0
    assert json.loads(capsys.readouterr().out)["artifact_path"] == str(artifact)
