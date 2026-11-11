"""Session-owned handoffs and bounded pointer-only predecessor discovery."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .events import AGENT_CLIS
from .fsio import atomic_write_json, atomic_write_text, ensure_dir, exclusive_lock, read_json
from .paths import SCRATCH_LABEL_RE, validate_sid
from .project import latest_origin, load_lifecycle, session_facts
from .store import SessionHandle, SessionStore, owned_session

INDEX_LIMIT = 64 * 1024
REFERENCE_LIMIT = 256
HANDOFF_LIMIT = 1024 * 1024
CONTEXT_PATH = "artifacts/artifact-context.json"
_SHA256_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
_HANDOFF_TIME_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z", re.ASCII)
_CONTEXT_PROVIDERS = frozenset((*AGENT_CLIS, "cursor"))


class ContinuityError(ValueError):
    """Continuity metadata is invalid, stale, conflicting, or outside its owner."""


@dataclass(frozen=True)
class ContinuitySelection:
    status: str
    source_sid: str | None = None
    handoff_path: Path | None = None
    artifact_path: Path | None = None
    reference_hash: str | None = None
    candidate_sids: tuple[str, ...] = ()
    reason: str | None = None


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _has_control(value: str) -> bool:
    return any(unicodedata.category(char) == "Cc" for char in value)


def canonical_scope(scope: str) -> dict:
    """Canonicalize an explicit workspace path or stable runtime key."""
    if not isinstance(scope, str) or ":" not in scope:
        raise ContinuityError("scope must be workspace:<absolute-path> or runtime:<stable-key>")
    kind, value = scope.split(":", 1)
    if kind == "workspace":
        path = Path(value)
        if not path.is_absolute():
            raise ContinuityError("workspace scope must be absolute")
        try:
            canonical = path.resolve(strict=True)
        except OSError as exc:
            raise ContinuityError("workspace scope is unavailable") from exc
        if not canonical.is_dir():
            raise ContinuityError("workspace scope must resolve to a directory")
        value = str(canonical)
    elif kind == "runtime":
        if not value or len(value.encode("utf-8")) > 256 or _has_control(value):
            raise ContinuityError("runtime scope must be a nonempty stable key of at most 256 bytes")
    else:
        raise ContinuityError("scope kind must be workspace or runtime")
    return {"kind": kind, "value": value}


def _validate_scope(scope: object) -> dict:
    if not isinstance(scope, dict) or set(scope) != {"kind", "value"}:
        raise ContinuityError("scope must be a canonical tagged object")
    kind, value = scope.get("kind"), scope.get("value")
    if kind == "workspace" and isinstance(value, str):
        canonical = canonical_scope(f"workspace:{value}")
        if canonical != scope:
            raise ContinuityError("workspace scope is not canonical")
        return canonical
    if kind == "runtime" and isinstance(value, str):
        canonical = canonical_scope(f"runtime:{value}")
        if canonical != scope:
            raise ContinuityError("runtime scope is not canonical")
        return canonical
    raise ContinuityError("scope kind or value is invalid")


def scope_hash(scope: dict) -> str:
    """Hash the canonical tagged scope; workspace and runtime keys never collide by type."""
    return hashlib.sha256(_canonical_json(_validate_scope(scope))).hexdigest()


def reference_hash(reference: dict) -> str:
    """Hash the canonical JSON representation of one pointer reference."""
    if not isinstance(reference, dict):
        raise ContinuityError("reference must be an object")
    return hashlib.sha256(_canonical_json(reference)).hexdigest()


def _workflow(value: object) -> str:
    if not isinstance(value, str) or not SCRATCH_LABEL_RE.fullmatch(value):
        raise ContinuityError("workflow selector must use the ASCII label grammar")
    return value


def _index_location(store: SessionStore, scope: dict, *, create: bool = False) -> tuple[Path, Path, Path]:
    digest = scope_hash(scope)
    root = store.root / "continuity"
    directory = root / digest
    if root.is_symlink() or directory.is_symlink():
        raise ContinuityError("continuity index directory is a symlink")
    if create:
        ensure_dir(directory)
    return directory, directory / "index.json", directory / ".lock"


def _valid_relative_path(kind: str, relative: object) -> str:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ContinuityError("continuity path must be a relative POSIX path")
    path = Path(relative)
    if path.is_absolute() or any(part in ("", ".", "..") for part in relative.split("/")):
        raise ContinuityError("continuity path escapes its session")
    if kind == "handoff" and relative != "handoff.md":
        raise ContinuityError("handoff references must name handoff.md")
    if kind == "artifact" and (not relative.startswith("artifacts/") or relative == CONTEXT_PATH):
        raise ContinuityError("artifact references must name an artifact file")
    return relative


def _valid_index(index: object, scope: dict) -> dict:
    if not isinstance(index, dict) or set(index) != {"version", "scope_hash", "scope", "refs", "legacy_import_refs"}:
        raise ContinuityError("continuity index has an unknown schema")
    digest = scope_hash(scope)
    if (type(index["version"]) is not int or index["version"] != 1
            or index["scope_hash"] != digest or index["scope"] != scope
            or not isinstance(index["refs"], list) or not isinstance(index["legacy_import_refs"], list)):
        raise ContinuityError("continuity index does not match its canonical scope")
    if len(index["refs"]) + len(index["legacy_import_refs"]) > REFERENCE_LIMIT:
        raise ContinuityError("continuity index exceeds 256 references")
    identities = set()
    for ref in index["refs"]:
        if not isinstance(ref, dict) or set(ref) != {"kind", "native_sid", "relative_path", "workflow_selector"}:
            raise ContinuityError("continuity reference has an unknown schema")
        if ref["kind"] not in ("handoff", "artifact"):
            raise ContinuityError("continuity reference kind is invalid")
        try:
            validate_sid(ref["native_sid"])
        except (TypeError, ValueError) as exc:
            raise ContinuityError("continuity reference session ID is invalid") from exc
        _valid_relative_path(ref["kind"], ref["relative_path"])
        _workflow(ref["workflow_selector"])
        identity = (ref["kind"], ref["workflow_selector"])
        if identity in identities:
            raise ContinuityError("continuity index contains duplicate reference identities")
        identities.add(identity)
    import_keys = set()
    for ref in index["legacy_import_refs"]:
        if not isinstance(ref, dict) or set(ref) != {"source_key_hash", "receipt_native_sid", "receipt_relative_path"}:
            raise ContinuityError("legacy import reference has an unknown schema")
        if not isinstance(ref["source_key_hash"], str) or not _SHA256_RE.fullmatch(ref["source_key_hash"]):
            raise ContinuityError("legacy import source key is invalid")
        if ref["source_key_hash"] in import_keys:
            raise ContinuityError("continuity index contains duplicate import references")
        import_keys.add(ref["source_key_hash"])
        try:
            validate_sid(ref["receipt_native_sid"])
        except (TypeError, ValueError) as exc:
            raise ContinuityError("legacy receipt session ID is invalid") from exc
        relative = ref["receipt_relative_path"]
        if (not isinstance(relative, str) or not relative.startswith("artifacts/imports/")
                or "\\" in relative or any(part in ("", ".", "..") for part in relative.split("/"))):
            raise ContinuityError("legacy receipt path is invalid")
    if len(_index_bytes(index)) > INDEX_LIMIT:
        raise ContinuityError("continuity index exceeds 64 KiB")
    return index


def _empty_index(scope: dict) -> dict:
    return {"version": 1, "scope_hash": scope_hash(scope), "scope": scope,
            "refs": [], "legacy_import_refs": []}


def _index_bytes(index: dict) -> bytes:
    return (json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _read_index(store: SessionStore, scope: dict) -> dict:
    _, path, _ = _index_location(store, scope)
    if path.is_symlink():
        raise ContinuityError("continuity index is a symlink")
    try:
        with path.open("rb") as stream:
            raw = stream.read(INDEX_LIMIT + 1)
    except FileNotFoundError:
        return _empty_index(scope)
    except OSError as exc:
        raise ContinuityError("continuity index is unreadable") from exc
    if len(raw) > INDEX_LIMIT:
        raise ContinuityError("continuity index exceeds 64 KiB")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ContinuityError("continuity index is malformed") from exc
    if value is None:
        raise ContinuityError("continuity index is malformed")
    return _valid_index(value, scope)


def _index_transaction(store: SessionStore, scope: dict, mutate: Callable[[dict], object]) -> tuple[dict, object]:
    directory, path, lock_path = _index_location(store, scope, create=True)
    if lock_path.is_symlink():
        raise ContinuityError("continuity lock is a symlink")
    with exclusive_lock(lock_path) as taken:
        if not taken:
            raise ContinuityError("continuity index is busy")
        index = _read_index(store, scope)
        before = _index_bytes(index)
        result = mutate(index)
        _valid_index(index, scope)
        data = _index_bytes(index)
        if len(data) > INDEX_LIMIT:
            raise ContinuityError("continuity index exceeds 64 KiB")
        if data != before:
            atomic_write_text(path, data.decode("utf-8"), durable=True)
        return index, result


def _session_path(handle: SessionHandle, relative: str, *, must_exist: bool) -> Path:
    path = handle.paths.dir / relative
    session_root = _validate_session_location(handle)
    resolved = path.resolve(strict=must_exist)
    try:
        resolved.relative_to(session_root)
    except ValueError as exc:
        raise ContinuityError("continuity path resolves outside its owning session") from exc
    if must_exist and (not resolved.is_file()):
        raise ContinuityError("continuity payload is not a regular file")
    return path


def _validate_session_location(handle: SessionHandle) -> Path:
    """Allow the configured store root to resolve, but never follow a sessions/SID escape."""
    effective_root = handle.paths.root.resolve(strict=False)
    sessions_root = effective_root / "sessions"
    if (handle.paths.root / "sessions").resolve(strict=False) != sessions_root:
        raise ContinuityError("sessions directory resolves outside the configured store")
    session_root = handle.paths.dir.resolve(strict=False)
    if session_root != sessions_root / handle.sid:
        raise ContinuityError("session directory resolves outside its native owner path")
    return session_root


def _read_context(handle: SessionHandle) -> dict | None:
    path = handle.paths.dir / CONTEXT_PATH
    if path.is_symlink():
        raise ContinuityError("artifact context is a symlink")
    try:
        if path.stat().st_size > INDEX_LIMIT:
            raise ContinuityError("artifact context exceeds 64 KiB")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ContinuityError("artifact context is unreadable") from exc
    resolved = _session_path(handle, CONTEXT_PATH, must_exist=True)
    value = read_json(resolved)
    if not isinstance(value, dict) or set(value) != {"version", "native_sid", "provider", "scopes", "privacy"}:
        raise ContinuityError("artifact context has an unknown schema")
    if (type(value["version"]) is not int or value["version"] != 1 or value["native_sid"] != handle.sid
            or not isinstance(value["provider"], str) or value["provider"] not in _CONTEXT_PROVIDERS
            or value["privacy"] not in ("public", "private")
            or not isinstance(value["scopes"], list) or len(value["scopes"]) > REFERENCE_LIMIT):
        raise ContinuityError("artifact context is malformed")
    seen = set()
    for raw_scope in value["scopes"]:
        canonical = _validate_scope(raw_scope)
        key = _canonical_json(canonical)
        if key in seen:
            raise ContinuityError("artifact context contains duplicate scopes")
        seen.add(key)
    return value


def _lifecycle(handle: SessionHandle) -> tuple[str, object | None, object | None]:
    state = handle.capture_state()
    if state != "captured":
        return state, None, None
    lifecycle = load_lifecycle(handle.paths)
    if lifecycle.projected_from["skipped"]:
        return "corrupt", None, None
    return state, session_facts(lifecycle.events), latest_origin(lifecycle.events)


def _scope_in_context(context: dict | None, scope: dict) -> bool:
    return bool(context and scope in context["scopes"])


def _write_context_locked(handle: SessionHandle, host: str, scope: dict, privacy: str, *, captured: bool) -> Path:
    path = handle.paths.dir / CONTEXT_PATH
    if path.is_symlink():
        raise ContinuityError("artifact context is a symlink")
    context = _read_context(handle) or {"version": 1, "native_sid": handle.sid, "provider": host,
                                        "scopes": [], "privacy": privacy}
    if context["provider"] != host:
        raise ContinuityError("artifact context owner provider changed")
    scopes = list(context["scopes"])
    if scope not in scopes:
        scopes.append(scope)
    context = {"version": 1, "native_sid": handle.sid, "provider": host, "scopes": scopes,
               "privacy": privacy}
    if len(scopes) > REFERENCE_LIMIT or len(json.dumps(context, ensure_ascii=False).encode("utf-8")) > INDEX_LIMIT:
        raise ContinuityError("artifact context exceeds its bound")
    ensure_dir(path.parent)
    _session_path(handle, CONTEXT_PATH, must_exist=False)
    atomic_write_json(path, context, durable=True)
    return path


def _origin_binds(origin: dict | None, scope: dict) -> bool:
    if scope["kind"] != "workspace" or not isinstance(origin, dict):
        return False
    cwd = origin.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return False
    try:
        return canonical_scope(f"workspace:{cwd}") == scope
    except ContinuityError:
        return False


def _session_scope_privacy(handle: SessionHandle, scope: dict) -> str:
    state, facts, origin = _lifecycle(handle)
    if state == "captured":
        if facts.private:
            return "private"
        if _origin_binds(origin, scope):
            try:
                context = _read_context(handle)
            except ContinuityError:
                return "unavailable"
            if context and context["provider"] != facts.agent_cli:
                return "unavailable"
            return "public"
        try:
            context = _read_context(handle)
        except ContinuityError:
            return "unavailable"
        if context and context["provider"] != facts.agent_cli:
            return "unavailable"
        if _scope_in_context(context, scope):
            return "public"
        return "unbound"
    if state in ("captured", "artifact-only"):
        context = _read_context(handle)
        if not context or context["native_sid"] != handle.sid or not _scope_in_context(context, scope):
            return "unavailable"
        return context["privacy"]
    return "unavailable"


def _reference_path(store: SessionStore, ref: dict) -> Path:
    handle = store.session(ref["native_sid"])
    return _session_path(handle, ref["relative_path"], must_exist=True)


def _selection(status: str, *, ref: dict | None = None, path: Path | None = None,
               candidates: tuple[str, ...] = (), reason: str | None = None) -> ContinuitySelection:
    return ContinuitySelection(
        status=status,
        source_sid=ref["native_sid"] if ref else None,
        handoff_path=path if ref and ref["kind"] == "handoff" else None,
        artifact_path=path if ref and ref["kind"] == "artifact" else None,
        reference_hash=reference_hash(ref) if ref else None,
        candidate_sids=candidates,
        reason=reason,
    )


def resolve_predecessor(store: SessionStore, *, current_sid: str, host: str, scope: str | dict,
                        kind: str = "handoff", workflow: str | None = None,
                        from_session: str | None = None) -> ContinuitySelection:
    """Resolve one explicit scoped pointer without scanning session history."""
    if kind not in ("handoff", "artifact"):
        raise ContinuityError("kind must be handoff or artifact")
    if workflow is not None:
        workflow = _workflow(workflow)
    try:
        current, _, _, _ = _owner_locked(store, current_sid, host)
    except (OSError, ValueError, ContinuityError) as exc:
        return _selection("unavailable", reason=str(exc))
    canonical = _validate_scope(scope) if isinstance(scope, dict) else canonical_scope(scope)
    if kind == "handoff" and from_session == current_sid:
        try:
            path = _session_path(current, "handoff.md", must_exist=True)
        except FileNotFoundError:
            return _selection("none")
        except (OSError, ValueError, ContinuityError) as exc:
            return _selection("unavailable", reason=str(exc))
        return ContinuitySelection("found", source_sid=current_sid, handoff_path=path,
                                   candidate_sids=(current_sid,))
    try:
        index = _read_index(store, canonical)
        for receipt_ref in index["legacy_import_refs"]:
            _indexed_receipt(store, canonical, receipt_ref)
    except (OSError, ValueError) as exc:
        return _selection("unavailable", reason=str(exc))
    refs = [ref for ref in index["refs"] if ref["kind"] == kind
            and (workflow is None or ref["workflow_selector"] == workflow)]
    if from_session is not None:
        try:
            validate_sid(from_session)
        except ValueError as exc:
            raise ContinuityError("from-session ID is invalid") from exc
        refs = [ref for ref in refs if ref["native_sid"] == from_session]
        if not refs:
            if kind == "handoff":
                source = store.session(from_session)
                try:
                    _validate_session_location(source)
                    if _session_scope_privacy(source, canonical) == "public":
                        path = _session_path(source, "handoff.md", must_exist=True)
                        return ContinuitySelection("found", source_sid=from_session, handoff_path=path,
                                                   candidate_sids=(from_session,))
                except FileNotFoundError:
                    return _selection("unavailable", reason="explicit source handoff is missing")
                except (OSError, ValueError, ContinuityError):
                    return _selection("unavailable", reason="explicit source is private, stale, or unverifiable")
            return _selection("unavailable", reason="explicit source has no matching published reference")
    if not refs:
        return _selection("none")

    valid: list[tuple[dict, Path]] = []
    had_unavailable = False
    private_explicit = False
    for ref in refs:
        source = store.session(ref["native_sid"])
        try:
            _validate_session_location(source)
            privacy = _session_scope_privacy(source, canonical)
        except (OSError, ValueError, ContinuityError):
            had_unavailable = True
            continue
        if privacy == "private":
            had_unavailable = True
            private_explicit |= from_session == ref["native_sid"]
            continue
        if privacy != "public":
            had_unavailable = True
            continue
        try:
            path = _reference_path(store, ref)
        except (OSError, ValueError, ContinuityError):
            had_unavailable = True
            continue
        valid.append((ref, path))
    if private_explicit:
        return _selection("unavailable", reason="explicit source is private or unverifiable")
    if had_unavailable:
        return _selection("unavailable", candidates=tuple(dict.fromkeys(ref["native_sid"] for ref, _ in valid)),
                           reason="one or more published references are stale or unavailable")
    if not from_session:
        valid = [(ref, path) for ref, path in valid if ref["native_sid"] != current_sid]
    if not valid:
        return _selection("none")
    candidates = tuple(dict.fromkeys(ref["native_sid"] for ref, _ in valid))
    if len(valid) > 1:
        return _selection("ambiguous", candidates=candidates, reason="select a workflow or source session")
    ref, path = valid[0]
    return _selection("found", ref=ref, path=path, candidates=candidates)


def _owner_locked(store: SessionStore, sid: str, host: str) -> tuple[SessionHandle, str, object | None, object | None]:
    handle = store.session(sid)
    _validate_session_location(handle)
    handle = owned_session(store, sid, host)
    state, facts, origin = _lifecycle(handle)
    if state not in ("absent", "captured", "artifact-only"):
        raise ContinuityError("session lifecycle is partial, corrupt, or unavailable")
    if state == "captured" and facts.agent_cli != host:
        raise ContinuityError("provider does not match recorded session owner")
    if state == "artifact-only":
        context = _read_context(handle)
        if context and context["provider"] != host:
            raise ContinuityError("artifact context provider does not match native owner")
    return handle, state, facts, origin


def write_context(store: SessionStore, *, current_sid: str, host: str, scope: str | dict,
                  privacy: str) -> Path:
    """Record explicit owner scope/privacy metadata without creating lifecycle events."""
    if privacy not in ("public", "private"):
        raise ContinuityError("privacy must be public or private")
    canonical = _validate_scope(scope) if isinstance(scope, dict) else canonical_scope(scope)
    handle = store.session(current_sid)
    _validate_session_location(handle)
    owned_session(store, current_sid, host)
    with handle._locked():
        handle, state, facts, _ = _owner_locked(store, current_sid, host)
        expected_privacy = "private" if state == "captured" and facts.private else "public"
        if state == "captured" and privacy != expected_privacy:
            raise ContinuityError("captured lifecycle privacy is authoritative")
        path = _write_context_locked(handle, host, canonical, expected_privacy if state == "captured" else privacy,
                                     captured=state == "captured")
    return path


def _validate_handoff(content: str) -> None:
    if not isinstance(content, str) or len(content.encode("utf-8")) > HANDOFF_LIMIT or "\x00" in content:
        raise ContinuityError("handoff must be text no larger than 1 MiB")
    if not content.startswith("---\n"):
        raise ContinuityError("handoff must have a v2 YAML frontmatter header")
    end = content.find("\n---\n", 4)
    if end < 0:
        raise ContinuityError("handoff frontmatter is incomplete")
    fields = {}
    for line in content[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in fields:
            raise ContinuityError(f"handoff frontmatter repeats {key}")
        fields[key] = value.strip().strip("\"'")
    if fields.get("schema_version") != "2" or not Path(fields.get("cwd", "")).is_absolute():
        raise ContinuityError("handoff must declare schema_version 2 and an absolute cwd")
    timestamp = fields.get("last_updated", "")
    if not _HANDOFF_TIME_RE.fullmatch(timestamp):
        raise ContinuityError("handoff last_updated must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise ContinuityError("handoff last_updated is not a valid timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ContinuityError("handoff last_updated must be UTC")


def write_handoff(store: SessionStore, *, current_sid: str, host: str, content: str) -> Path:
    """Durably replace only the current native session's v2 handoff."""
    _validate_handoff(content)
    handle = store.session(current_sid)
    _validate_session_location(handle)
    owned_session(store, current_sid, host)
    with handle._locked():
        handle, _, _, _ = _owner_locked(store, current_sid, host)
        target = handle.paths.handoff
        _session_path(handle, "handoff.md", must_exist=False)
        atomic_write_text(target, content, durable=True)
    return target


def publish_reference(store: SessionStore, *, current_sid: str, host: str, scope: str | dict,
                      kind: str, workflow: str, relative_path: str,
                      expect: str | None = None) -> ContinuitySelection:
    """Publish a bounded pointer with exact-reference compare-and-swap semantics."""
    if kind not in ("handoff", "artifact"):
        raise ContinuityError("kind must be handoff or artifact")
    workflow = _workflow(workflow)
    relative_path = _valid_relative_path(kind, relative_path)
    if expect is not None and (not isinstance(expect, str) or not _SHA256_RE.fullmatch(expect)):
        raise ContinuityError("expect must be a canonical reference SHA-256")
    canonical = _validate_scope(scope) if isinstance(scope, dict) else canonical_scope(scope)
    handle = store.session(current_sid)
    _validate_session_location(handle)
    owned_session(store, current_sid, host)
    with handle._locked():
        handle, state, facts, origin = _owner_locked(store, current_sid, host)
        context = _read_context(handle)
        privacy = ("private" if facts.private else "public") if state == "captured" else (
            context["privacy"] if context else "unavailable")
        if privacy != "public":
            raise ContinuityError("private session references are never globally indexed")
        origin_bound = state == "captured" and _origin_binds(origin, canonical)
        if state == "captured" and not origin_bound and not _scope_in_context(context, canonical):
            # Publication is an explicit owner action; retain that scope binding
            # so later discovery does not infer it from cwd or timestamps.
            _write_context_locked(handle, host, canonical, "public", captured=True)
        elif state == "artifact-only" and (not _scope_in_context(context, canonical)
                                             or context["privacy"] != "public"):
            raise ContinuityError("capture-off publication requires explicit public artifact context")
        path = _session_path(handle, relative_path, must_exist=True)
        ref = {"kind": kind, "native_sid": current_sid, "relative_path": relative_path,
               "workflow_selector": workflow}

        def mutate(index):
            existing = next((item for item in index["refs"]
                             if (item["kind"], item["workflow_selector"]) == (kind, workflow)), None)
            if existing is None and expect is not None:
                raise ContinuityError("continuity reference changed; retry with a fresh reference")
            if existing is not None and (expect is None or reference_hash(existing) != expect):
                raise ContinuityError("replacing a continuity reference requires its exact current hash")
            if existing is None:
                index["refs"].append(ref)
            else:
                index["refs"][index["refs"].index(existing)] = ref
            return ref

        _, published = _index_transaction(store, canonical, mutate)
    return _selection("found", ref=published, path=path, candidates=(current_sid,))


def _legacy_source(source: Path, store: SessionStore, fingerprint: str) -> Path:
    if not source.is_absolute():
        raise ContinuityError("legacy source must be an explicitly selected absolute path")
    resolved = source.resolve(strict=True)
    if resolved.is_relative_to(store.root.resolve(strict=False)):
        raise ContinuityError("legacy import cannot bypass session privacy with a store-internal source")
    if not resolved.is_file():
        raise ContinuityError("legacy source must be a regular file")
    with resolved.open("rb") as stream:
        data = stream.read(HANDOFF_LIMIT + 1)
    if len(data) > HANDOFF_LIMIT:
        raise ContinuityError("legacy source exceeds 1 MiB")
    if hashlib.sha256(data).hexdigest() != fingerprint:
        raise ContinuityError("legacy source changed after selection; select and fingerprint it again")
    return resolved


def _import_receipt(handle: SessionHandle, relative: str, source: str) -> dict:
    path = _session_path(handle, relative, must_exist=True)
    if path.is_symlink():
        raise ContinuityError("import receipt is a symlink")
    with path.open("rb") as stream:
        raw = stream.read(INDEX_LIMIT + 1)
    try:
        receipt = json.loads(raw) if len(raw) <= INDEX_LIMIT else None
    except (ValueError, UnicodeError):
        receipt = None
    if (not isinstance(receipt, dict)
            or set(receipt) != {"version", "source_identity", "source_sha256", "imported_into", "decision"}
            or type(receipt["version"]) is not int or receipt["version"] != 1
            or receipt["source_identity"] != source
            or not isinstance(receipt["source_sha256"], str)
            or not _SHA256_RE.fullmatch(receipt["source_sha256"])
            or not isinstance(receipt["imported_into"], dict)
            or set(receipt["imported_into"]) != {"native_sid", "provider"}
            or receipt["imported_into"]["native_sid"] != handle.sid
            or not isinstance(receipt["imported_into"]["provider"], str)
            or receipt["imported_into"]["provider"] not in _CONTEXT_PROVIDERS
            or receipt["decision"] not in ("initial", "reimport")):
        raise ContinuityError("legacy receipt is malformed or does not match its source/owner")
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if relative != f"artifacts/imports/{key}/{receipt['source_sha256']}.json":
        raise ContinuityError("legacy receipt path does not match its immutable fingerprint")
    _, facts, _ = _lifecycle(handle)
    context = _read_context(handle)
    provider = facts.agent_cli if facts else context["provider"] if context else None
    if provider != receipt["imported_into"]["provider"]:
        raise ContinuityError("legacy receipt provider does not match its owner")
    return receipt


def _indexed_receipt(store: SessionStore, scope: dict, ref: dict) -> tuple[SessionHandle, dict]:
    owner = store.session(ref["receipt_native_sid"])
    _validate_session_location(owner)
    if _session_scope_privacy(owner, scope) != "public":
        raise ContinuityError("indexed receipt owner is private or unverifiable")
    path = _session_path(owner, ref["receipt_relative_path"], must_exist=True)
    if path.is_symlink():
        raise ContinuityError("indexed receipt is a symlink")
    with path.open("rb") as stream:
        raw = stream.read(INDEX_LIMIT + 1)
    try:
        value = json.loads(raw) if len(raw) <= INDEX_LIMIT else None
    except (ValueError, UnicodeError) as exc:
        raise ContinuityError("indexed receipt is malformed") from exc
    source = value.get("source_identity") if isinstance(value, dict) else None
    if (not isinstance(source, str) or not Path(source).is_absolute()
            or hashlib.sha256(source.encode("utf-8")).hexdigest() != ref["source_key_hash"]):
        raise ContinuityError("indexed receipt does not match its source key")
    receipt = _import_receipt(owner, ref["receipt_relative_path"], source)
    _session_path(owner, "handoff.md", must_exist=True)
    return owner, receipt


def import_legacy(store: SessionStore, *, current_sid: str, host: str, scope: str | dict,
                  workflow: str, source: Path, source_sha256: str, decision: str,
                  content: str, expect: str | None = None) -> dict:
    """Copy a selected legacy input once, publishing provenance only after durable output."""
    handle, _, _, _ = _owner_locked(store, current_sid, host)
    canonical = _validate_scope(scope) if isinstance(scope, dict) else canonical_scope(scope)
    workflow = _workflow(workflow)
    if not isinstance(source_sha256, str) or not _SHA256_RE.fullmatch(source_sha256):
        raise ContinuityError("source-sha256 must be the selected source's SHA-256")
    if decision not in ("initial", "reimport"):
        raise ContinuityError("import decision must be initial or reimport")
    if expect is not None and (not isinstance(expect, str) or not _SHA256_RE.fullmatch(expect)):
        raise ContinuityError("expect must be a canonical reference SHA-256")
    _validate_handoff(content)
    selected = _legacy_source(source, store, source_sha256)
    source_identity = str(selected)
    source_key = hashlib.sha256(source_identity.encode("utf-8")).hexdigest()
    relative = f"artifacts/imports/{source_key}/{source_sha256}.json"
    ref = {"kind": "handoff", "native_sid": current_sid, "relative_path": "handoff.md",
           "workflow_selector": workflow}
    receipt_ref = {"source_key_hash": source_key, "receipt_native_sid": current_sid,
                   "receipt_relative_path": relative}
    receipt = {"version": 1, "source_identity": source_identity, "source_sha256": source_sha256,
               "imported_into": {"native_sid": current_sid, "provider": host}, "decision": decision}

    def result(status, owner, receipt_relative, selected_ref=None):
        return {"status": status, "source_sid": owner.sid,
                "handoff_path": _session_path(owner, "handoff.md", must_exist=True),
                "receipt_path": _session_path(owner, receipt_relative, must_exist=True),
                "reference_hash": reference_hash(selected_ref) if selected_ref else None}

    def persist():
        # Re-read the exact selected source immediately before durable publication.
        if _legacy_source(source, store, source_sha256) != selected:
            raise ContinuityError("legacy source identity changed after selection")
        target = _session_path(handle, "handoff.md", must_exist=False)
        if target.exists() and decision == "initial":
            with target.open("rb") as stream:
                previous = stream.read(HANDOFF_LIMIT + 1)
            if previous != content.encode("utf-8"):
                raise ContinuityError("initial import would replace an existing owned handoff")
        receipt_path = _session_path(handle, relative, must_exist=False)
        if receipt_path.exists() or receipt_path.is_symlink():
            previous = _import_receipt(handle, relative, source_identity)
            if previous["source_sha256"] != source_sha256:
                raise ContinuityError("immutable import receipt conflicts with selected source")
        else:
            ensure_dir(receipt_path.parent)
            _session_path(handle, relative, must_exist=False)
            atomic_write_json(receipt_path, receipt, durable=True)
        atomic_write_text(target, content, durable=True)

    with handle._locked():
        handle, state, facts, origin = _owner_locked(store, current_sid, host)
        context = _read_context(handle)
        privacy = ("private" if facts.private else "public") if state == "captured" else (
            context["privacy"] if context and _scope_in_context(context, canonical) else "unavailable")
        if privacy == "unavailable":
            raise ContinuityError("manual import requires explicit artifact context privacy and scope")
        if privacy == "private":
            # Private provenance stays with its owner; no globally discoverable receipt.
            receipt_path = _session_path(handle, relative, must_exist=False)
            target = _session_path(handle, "handoff.md", must_exist=False)
            if receipt_path.exists() and target.exists():
                _import_receipt(handle, relative, source_identity)
                with target.open("rb") as stream:
                    if stream.read(HANDOFF_LIMIT + 1) == content.encode("utf-8"):
                        return result("already_imported", handle, relative)
            persist()
            return result("found", handle, relative)

        def mutate(index):
            if _legacy_source(source, store, source_sha256) != selected:
                raise ContinuityError("legacy source identity changed after selection")
            old_receipt = next((item for item in index["legacy_import_refs"]
                                if item["source_key_hash"] == source_key), None)
            existing = next((item for item in index["refs"]
                             if (item["kind"], item["workflow_selector"]) == ("handoff", workflow)), None)
            # Unverifiable canonical state is not permission to resurrect a legacy copy.
            for item in index["refs"]:
                owner = store.session(item["native_sid"])
                _validate_session_location(owner)
                if _session_scope_privacy(owner, canonical) != "public":
                    raise ContinuityError("canonical references are private, stale, or unverifiable")
                _reference_path(store, item)
            if old_receipt:
                owner, previous = _indexed_receipt(store, canonical, old_receipt)
                if previous["source_identity"] != source_identity:
                    raise ContinuityError("indexed legacy source identity changed")
                if previous["source_sha256"] == source_sha256:
                    return result("already_imported", owner, old_receipt["receipt_relative_path"])
                if decision != "reimport":
                    raise ContinuityError("changed legacy input requires an explicit reimport decision")
            elif index["refs"] and decision != "reimport":
                raise ContinuityError("canonical references already exist; automatic legacy import is disabled")
            if existing is None and expect is not None:
                raise ContinuityError("continuity reference changed; select it again")
            if existing and (expect is None or reference_hash(existing) != expect):
                raise ContinuityError("reimport requires the exact current reference hash")
            if existing:
                index["refs"][index["refs"].index(existing)] = ref
            else:
                index["refs"].append(ref)
            if old_receipt:
                index["legacy_import_refs"][index["legacy_import_refs"].index(old_receipt)] = receipt_ref
            else:
                index["legacy_import_refs"].append(receipt_ref)
            _valid_index(index, canonical)  # Reject full indexes before copying payloads.
            if (state == "captured" and not _origin_binds(origin, canonical)
                    and not _scope_in_context(context, canonical)):
                _write_context_locked(handle, host, canonical, "public", captured=True)
            persist()
            return result("found", handle, relative, ref)

        _, imported = _index_transaction(store, canonical, mutate)
        return imported
