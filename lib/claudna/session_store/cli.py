"""Command line for the session store.

    python3 -m claudna.session_store rebuild <sid> [--root DIR]
    python3 -m claudna.session_store check   <sid> [--root DIR]
    python3 lib/claudna/session_store hook <event>     (hook payload on stdin)
    python3 lib/claudna/session_store summarize <sid> <seg> [--root DIR]
    python3 lib/claudna/session_store harvest [--force] [--root DIR]
    python3 lib/claudna/session_store private <sid> [--off] [--root DIR]

(with ``lib/`` on ``PYTHONPATH``; ``python3 lib/claudna/session_store …`` also works)

``rebuild`` regenerates a session's projections from its logs. ``check``
validates the current projections and every log line against the schemas, the
kind registry, and placement (right session, log, and segment), without writing
anything. Lines from a newer envelope version or an unknown kind are skipped,
exactly as readers skip them — an older ``check`` never fails on a newer log.

``check`` fails on what a writer can prevent or a reader must not ignore:
schema, registry, and placement violations, bad or missing projections, and
corrupt lines. The one exception is a torn write — an unterminated fragment of
a JSON object, which the store deliberately keeps as one skippable line and
no ``rebuild`` can remove. That is crash debris, reported as a warning.

``summarize`` is the detached worker a seal starts (:mod:`summarize`); it prints
what it did and exits 0 unless the session or segment doesn't exist.

``harvest`` writes summarized segments' knowledge blocks to the vault as
drafts, through ``claudron capture`` (:mod:`harvest`); it prints the run report
as JSON. SessionStart starts it detached when one is due.

``private`` marks a session private (``--off`` clears it): it is never
summarized or harvested from then on.

``hook`` is what the hook wrappers call: it applies one Claude Code hook event
to the store (:mod:`boundaries`) and always exits 0, because a failing hook must
never break the session. Failures go to ``<root>/hooks/errors.log``, one JSON
line each, without the payload (it can hold prompt text).

Exit codes: 0 ok (warnings allowed) · 1 not found or check failed · 2 usage.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from . import boundaries
from . import events as ev
from . import schema
from .fsio import (allocate_operation, append_jsonl, cap_log, ensure_dir,
                   make_scratch, read_json, read_jsonl)
from .paths import (InvalidSessionId, InvalidStateDir, SessionPaths, operation_path, owned_path, state_root,
                    validate_scratch_label, validate_sid)
from .project import OLDER_PROJECTIONS, SUMMARY_ENV
from .store import SessionHandle, SessionStore, owned_session

# readers.SINCE_HELP, kept literal: the parser must not import readers (loaded lazily, per verb).
_SINCE_HELP = "30m, 12h, 7d, 2w, or an ISO date/time"

if TYPE_CHECKING:
    import argparse


def _store(args: argparse.Namespace) -> SessionStore | None:
    try:
        return SessionStore(Path(args.root) if args.root else None)
    except InvalidStateDir as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _handle(args: argparse.Namespace) -> SessionHandle | None:
    store = _store(args)
    if store is None:
        return None
    try:
        handle = store.session(args.sid)
    except InvalidSessionId as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
    if not handle.exists():
        print(f"error: no session {args.sid} under {store.root}", file=sys.stderr)
        return None
    return handle


def _owned_path_command(args) -> int:
    """Thin manual allocation door; never opens a captured session."""
    try:
        store = SessionStore(Path(args.root) if args.root else None)
        if args.verb == "operation-dir":
            if args.label is not None and not args.create:
                raise ValueError("--label requires --create")
            target = (allocate_operation(store.root, label=args.label, operation_id=args.operation_id)
                      if args.create else operation_path(store.root, args.operation_id))
        else:
            if args.verb == "scratch":
                validate_scratch_label(args.label)
            handle = owned_session(store, args.session, args.host)
            if args.verb == "scratch":
                target = make_scratch(handle.paths.scratch, args.label)
            else:
                target = owned_path(handle.paths, args.kind)
                if args.create:
                    ensure_dir(target.parent if args.kind == "handoff" else target)
        print(target)
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _continuity_command(args) -> int:
    """Explicit owner-scoped persistence and pointer discovery; never starts capture."""
    from . import continuity

    try:
        store = SessionStore(Path(args.root) if args.root else None)
        owner = {"current_sid": args.session, "host": args.host}
        if args.verb == "handoff-write":
            if args.background and os.environ.get("CLAUDNA_SESSION_STORE") == "0":
                raise ValueError("background checkpoint disabled with session capture")
            target = continuity.write_handoff(store, **owner, content=sys.stdin.read(1048577))
            result = {"status": "found", "source_sid": args.session, "handoff_path": str(target)}
        elif args.action == "context":
            target = continuity.write_context(store, **owner, scope=args.scope, privacy=args.privacy)
            result = {"status": "found", "source_sid": args.session, "context_path": str(target)}
        elif args.action == "import":
            result = continuity.import_legacy(
                store, **owner, scope=args.scope, workflow=args.workflow, source=Path(args.source),
                source_sha256=args.source_sha256, decision=args.decision,
                content=sys.stdin.read(1048577), expect=args.expect)
        elif args.action == "artifact-path" and args.path:
            if not args.from_session or args.workflow:
                raise ValueError("explicit artifact path requires from-session and cannot select a workflow")
            result = dataclasses.asdict(continuity.selected_artifact(
                store, **owner, scope=args.scope, from_session=args.from_session, path=Path(args.path)))
        else:
            selection = {**owner, "scope": args.scope, "kind": args.kind, "workflow": args.workflow}
            if args.action == "publish":
                selected = continuity.publish_reference(store, **selection,
                                                        relative_path=args.path, expect=args.expect)
            else:
                selected = continuity.resolve_predecessor(store, **selection, from_session=args.from_session)
            result = dataclasses.asdict(selected)
        if args.json:
            print(json.dumps(result, default=str))
        elif result.get("status") == "found":
            print(result.get("handoff_path") or result.get("artifact_path") or result.get("context_path"))
        elif result.get("reason"):
            print(result["reason"], file=sys.stderr)
        return {"found": 0, "already_imported": 0, "none": 1}.get(result.get("status"), 3)
    except (ValueError, OSError, RuntimeError) as exc:
        if args.json:
            print(json.dumps({"status": "unavailable", "handoff_path": None,
                              "artifact_path": None, "reason": str(exc)}))
        else:
            print(f"continuity unavailable: {exc}", file=sys.stderr)
        return 2


@dataclasses.dataclass(frozen=True)
class CheckReport:
    """``problems`` fail a check; ``warnings`` (crash debris, a lost refresh) are reported but don't."""

    problems: list[str]
    warnings: list[str]


def check_session(handle: SessionHandle) -> CheckReport:
    """Every schema, registry, or placement violation in one session's files."""
    problems: list[str] = []
    warnings: list[str] = []
    session_schema, segment_schema = schema.load("session"), schema.load("segment")
    indices = handle.paths.segment_indices()
    logs = [(handle.paths.lifecycle, ev.LIFECYCLE, None)] + [
        (handle.paths.segment(i).events, ev.ACTIVITY, i) for i in indices
    ]
    sizes: dict[Path, int] = {}
    for log, log_kind, seg in logs:
        read = read_jsonl(log)
        sizes[log] = read.bytes
        torn, corrupt = _unparseable_lines(log)
        if torn:
            warnings.append(f"{log}: {torn} torn line(s) (crash debris; readers skip them)")
        if corrupt:
            problems.append(f"{log}: {corrupt} corrupt line(s) (not a JSON object, not a torn write)")
        for n, record in enumerate(read.records, 1):
            verdict = ev.classify(record)
            if verdict == "unknown":
                continue  # newer envelope or kind: not ours to judge
            envelope = ev.envelope_errors(record)
            problems.extend(f"{log} record {n}: {err}" for err in envelope)
            if envelope:
                continue
            if verdict == "invalid":
                problems.append(f"{log} record {n}: violates the kind registry")
                continue
            problems.extend(f"{log} record {n}: {err}"
                            for err in ev.placement_errors(record, sid=handle.sid, log=log_kind, seg=seg))
    targets = [(handle.paths.session_json, session_schema, handle.paths.lifecycle)] + [
        (handle.paths.segment(i).segment_json, segment_schema, handle.paths.segment(i).events) for i in indices
    ]
    for path, target_schema, source in targets:
        obj = read_json(path)
        if obj is None:
            problems.append(f"{path}: missing or unparseable (run rebuild)")
            continue
        if isinstance(obj, dict) and obj.get("schema") in OLDER_PROJECTIONS:
            # written by an older release: readers re-fold it; the sweep or the next write rewrites it
            warnings.append(f"{path}: an older projection ({obj['schema']}); readers re-fold it, and the "
                            "background sweep, the next write or a rebuild rewrites it")
            continue
        errors = schema.validate(obj, target_schema)
        problems.extend(f"{path}: {err}" for err in errors)
        # A projection behind its log means a refresh was lost (a killed hook): the
        # next write heals it, so it's a warning, not a failure.
        if not errors and obj["projected_from"]["bytes"] != sizes[source]:
            warnings.append(f"{path}: covers {obj['projected_from']['bytes']} of {sizes[source]} bytes of "
                            f"{source.name} (a refresh was lost; the next write or a rebuild heals it)")
    return CheckReport(problems=problems, warnings=warnings)


def _unparseable_lines(log: Path) -> tuple[int, int]:
    """``(torn, corrupt)`` counts of lines readers skip as unparseable.

    Torn: a fragment that starts like a JSON object but doesn't parse — what a
    writer killed mid-append leaves. Corrupt: anything else that isn't a JSON
    object (garbage, invalid UTF-8, ``[]``, ``5``) — no store writer produces those.
    """
    torn = corrupt = 0
    try:
        raw = log.read_bytes()
    except FileNotFoundError:
        return 0, 0
    for line in raw.split(b"\n"):
        if not line.strip():
            continue
        try:
            if isinstance(json.loads(line.decode("utf-8")), dict):
                continue
            corrupt += 1
        except UnicodeDecodeError:
            corrupt += 1
        except json.JSONDecodeError:
            if line.lstrip().startswith(b"{"):
                torn += 1
            else:
                corrupt += 1
    return torn, corrupt


def run_hook(event: str, raw: str | bytes, env: dict[str, str] | None = None, *, host: str = "claude") -> str:
    """Apply one hook event; never raise. Returns the outcome (``"error: …"`` on failure).

    ``raw`` may be the undecoded stdin bytes: decoding happens inside the guard,
    so invalid UTF-8 is logged to ``errors.log`` like any other bad payload.
    """
    env = dict(os.environ) if env is None else env
    root = None
    sid = None
    try:
        root = state_root(env)
        selected = boundaries.HOSTS.get(host)
        if selected is None:
            _log_hook_error(root, event, ValueError(f"unknown host {host!r}"))
            return f"ignored: unknown host {host!r}"
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if raw.strip() else None
        if isinstance(payload, dict):
            try:
                sid = validate_sid(payload.get("session_id"))
            except ValueError:
                pass
        return boundaries.handle(event, payload, store=SessionStore(root), env=env, host=selected)
    except Exception as exc:  # noqa: BLE001 — a hook must fail open, and say so
        _log_hook_error(root, event, exc, sid=sid)
        return f"error: {type(exc).__name__}: {exc}"


def _log_hook_error(root: Path | None, event: str, exc: BaseException, *, sid: str | None = None) -> None:
    """Payload diagnostics belong to a known session; bootstrap records carry only fixed codes."""
    import traceback

    frame = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
    event = event if any(event in h.events for h in boundaries.HOSTS.values()) else "unknown"
    if root is not None and sid is not None:
        try:
            hooks_dir = ensure_dir(SessionPaths(root, validate_sid(sid)).hooks)
            cap_log(hooks_dir / "session-store.stderr")
            append_jsonl(cap_log(hooks_dir / "errors.log"), {
                "ts": ev.now_ts(), "component": "session_store", "event": event,
                "error": f"{type(exc).__name__}: {exc}",
                "where": f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}" if frame else None,
            }, durable=False)
            return
        except (OSError, ValueError):
            pass  # a failed owned allocation must not send its payload to global state
    code = "decode" if isinstance(exc, (UnicodeError, json.JSONDecodeError)) else (
        "io" if isinstance(exc, OSError) else "runtime")
    try:
        if root is None:
            raise OSError("no root")
        hooks_dir = ensure_dir(root / "hooks")
        append_jsonl(cap_log(hooks_dir / "errors.log"), {
            "ts": ev.now_ts(), "component": "session_store", "event": event, "code": code, "count": 1,
        }, durable=False)
    except OSError:
        print(f"session_store hook: {code}", file=sys.stderr)


def _review(store, digest, item: str, vault: str | None, revision: int | None, *, outcome: str,
            promote: bool) -> int:
    """``digest --promote`` / ``--done``: one person's decision on one item, as they saw it.

    Under harvest's own lock, so no fact lands in a note between the check and
    the decision. A draft's decision covers the note at ``revision`` (the
    item's, as shown): promoting it promotes every fact in it, and a review
    covers what was seen, so a note written to since is shown again first. A
    promotion runs ``claudron promote`` and is marked done only on its yes.
    """
    from . import claudron
    from .fsio import ensure_dir, exclusive_lock

    with exclusive_lock(ensure_dir(store.root / "harvest") / "lock", blocking=False) as taken:
        if not taken:
            print("error: a harvest is running; try again in a minute", file=sys.stderr)
            return 1
        try:
            match = digest.find(store.root, item, vault)
        except LookupError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if promote and match.kind != "draft":
            print("error: only a draft is promoted; a person fact is captured, then --done", file=sys.stderr)
            return 1
        if match.kind == "draft":
            if revision is None:
                print("error: a draft needs --revision, the item's revision as shown", file=sys.stderr)
                return 2
            if match.revision != revision:
                print(f"error: the note has changed since revision {revision} (now {match.revision}); show it "
                      "again first", file=sys.stderr)
                return 1
        if promote:
            try:
                claudron.promote(item, vault, os.environ)
            except claudron.PromoteError as exc:
                print(f"error: {exc}", file=sys.stderr)  # not marked reviewed: it stays in the digest
                return 1
        digest.mark_reviewed(store.root, item, outcome=outcome, vault=vault,
                             revision=match.revision if match.kind == "draft" else None)
    print(json.dumps({"item": item, "vault": vault, "outcome": outcome}))
    return 0


def _export(args) -> int:
    """The export door (spec §8): the envelope, or an ack."""
    from . import export

    store = _store(args)
    if store is None:
        return 1
    try:
        if args.ack:
            if args.sid is None or args.through is None:
                raise ValueError("--ack needs --sid and --through")
            cursor = export.ack(store, args.consumer, args.sid, args.through)
            print(json.dumps({"consumer": args.consumer, "sid": args.sid, "through_seg": cursor}))
        else:
            print(json.dumps(export.export(store, args.consumer, since_seg=args.since_seg, limit=args.limit,
                                           include_skipped=args.include_skipped)))
    except (LookupError, InvalidSessionId, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _read(args) -> int:
    """The reader verbs (spec §8): data from readers.py, printed as text or JSON."""
    from . import readers

    store = _store(args)
    if store is None:
        return 1
    unreadable: list[str] = []
    try:
        if args.verb == "list":
            data = readers.list_sessions(store, since=args.since, repo=args.repo, bot=args.bot, limit=args.limit,
                                         include_private=args.include_private, unreadable=unreadable)
        elif args.verb == "show":
            data = readers.show(store, args.sid)
        elif args.verb == "timeline":
            data = readers.timeline(store, args.sid)
        else:
            data = readers.failures(store, args.sid, group=args.group, since=args.since,
                                    include_private=args.include_private, unreadable=unreadable)
    except (LookupError, InvalidSessionId, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if unreadable:
        print(f"warning: {len(unreadable)} session(s) could not be read (permissions?): {', '.join(unreadable[:5])}",
              file=sys.stderr)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        for line in readers.render(args.verb, data, group=getattr(args, "group", False)):
            print(readers.printable(line))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["native-session-id"]:
        try:
            payload = json.loads(sys.stdin.buffer.read())
            print(validate_sid(payload.get("session_id") if isinstance(payload, dict) else None))
            return 0
        except (ValueError, UnicodeError):
            return 2
    if argv[:1] == ["hook"] and len(argv) in (2, 4):  # the hot path: no argparse
        if len(argv) == 2:
            run_hook(argv[1], sys.stdin.buffer.read())
        elif argv[1] == "--host":
            run_hook(argv[3], sys.stdin.buffer.read(), host=argv[2])
        return 0
    if argv == ["telemetry-path"]:
        from .telemetry import telemetry_path

        try:
            print(telemetry_path(os.environ))
            return 0
        except (OSError, ValueError):
            print("telemetry configuration invalid: require an absolute destination inside the clauDNA root",
                  file=sys.stderr)
            return 2
    if argv == ["telemetry"]:  # telemetry-emit.sh: its own entry, so it works with the store off
        from . import telemetry

        telemetry.run_hook(sys.stdin.buffer.read(), os.environ)
        return 0
    import argparse

    parser = argparse.ArgumentParser(prog="claudna.session_store", description="clauDNA session store")
    rooted = argparse.ArgumentParser(add_help=False)
    rooted.add_argument("--root", help="store root (default: $CLAUDNA_STATE_DIR or ~/.claudna)")
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb in ("paths", "scratch"):
        allocation = sub.add_parser(verb, help="explicit native-session artifact paths", parents=[rooted])
        allocation.add_argument("--session", required=True)
        allocation.add_argument("--host", required=True, choices=("claude", "codex", "cursor"))
        if verb == "paths":
            allocation.add_argument("--kind", required=True,
                                    choices=("scratch", "artifacts", "handoff", "hooks", "delegation"))
            allocation.add_argument("--create", action="store_true")
        else:
            allocation.add_argument("--label", required=True)
    operation = sub.add_parser("operation-dir", help="explicit standalone maintainer allocation", parents=[rooted])
    identity = operation.add_mutually_exclusive_group(required=True)
    identity.add_argument("--label")
    identity.add_argument("--operation-id")
    operation.add_argument("--create", action="store_true")
    handoff = sub.add_parser("handoff-write", help="atomically persist the current owner's v2 handoff",
                             parents=[rooted])
    handoff.add_argument("--session", required=True)
    handoff.add_argument("--host", required=True, choices=("claude", "codex", "cursor"))
    handoff.add_argument("--background", action="store_true", help="honor disabled capture for background checkpoints")
    handoff.add_argument("--json", action="store_true")
    continuity = sub.add_parser("continuity", help="explicit scoped handoff and artifact pointers")
    actions = continuity.add_subparsers(dest="action", required=True)
    for action in ("resolve", "artifact-path", "publish", "context", "import"):
        entry = actions.add_parser(action, parents=[rooted])
        entry.add_argument("--session", required=True)
        entry.add_argument("--host", required=True, choices=("claude", "codex", "cursor"))
        entry.add_argument("--scope", required=True)
        entry.add_argument("--json", action="store_true")
        if action == "context":
            entry.add_argument("--privacy", choices=("public", "private"), required=True)
            continue
        entry.add_argument("--workflow", required=action in ("publish", "import"))
        if action == "artifact-path":
            entry.set_defaults(kind="artifact")
            entry.add_argument("--path", help="explicit absolute artifact; requires from-session, no workflow")
        elif action != "import":
            entry.add_argument("--kind", choices=("handoff", "artifact"), default="handoff")
        if action in ("resolve", "artifact-path"):
            entry.add_argument("--from-session")
        if action in ("publish", "import"):
            entry.add_argument("--expect", help="exact prior reference SHA-256, required for replacement")
        if action == "publish":
            entry.add_argument("--path", required=True, help="path relative to the producing session")
        if action == "import":
            entry.add_argument("--source", required=True, help="explicit absolute legacy file, read-only")
            entry.add_argument("--source-sha256", required=True, help="fingerprint bound to the selected source read")
            entry.add_argument("--decision", choices=("initial", "reimport"), required=True)
    skill = sub.add_parser("skill-start", help="best-effort Codex agent procedure entry; not task success",
                           parents=[rooted])
    skill.add_argument("skill", help="selected claudna skill slug; no task arguments")
    for verb, text in (("rebuild", "regenerate projections from logs"),
                       ("check", "validate logs and projections; writes nothing"),
                       ("summarize", "summarize one sealed segment (the detached worker)"),
                       ("seal", "close a session whose SessionEnd never ran, as abandoned")):
        p = sub.add_parser(verb, help=text, parents=[rooted])
        p.add_argument("sid")
        if verb == "summarize":
            p.add_argument("seg", type=int)
    priv = sub.add_parser("private", help="mark a session private: never summarized or harvested", parents=[rooted])
    priv.add_argument("sid")
    priv.add_argument("--off", action="store_true", help="clear the mark")
    swp = sub.add_parser("sweep", help="close unclosed sessions (open, idle, claude gone), oldest first",
                         parents=[rooted])
    swp.add_argument("--dry-run", action="store_true", help="list what would be closed; write nothing")
    lst = sub.add_parser("list", help="sessions, newest first", parents=[rooted])
    lst.add_argument("--since", help=_SINCE_HELP)
    lst.add_argument("--repo")
    lst.add_argument("--bot", help="a bot name or id")
    lst.add_argument("--limit", type=int, default=50)
    lst.add_argument("--json", action="store_true")
    lst.add_argument("--include-private", action="store_true", help="also list private sessions (marked)")
    for verb, text in (("show", "one session: its projection, segments, rollup and lineage"),
                       ("timeline", "one session's lifecycle and activity, in time order")):
        p = sub.add_parser(verb, help=text, parents=[rooted])
        p.add_argument("sid")
        p.add_argument("--json", action="store_true")
    fails = sub.add_parser("failures", help="tool.failed events, newest first; --group folds by signature",
                           parents=[rooted])
    fails.add_argument("sid", nargs="?")
    fails.add_argument("--group", action="store_true")
    fails.add_argument("--since", help=_SINCE_HELP)
    fails.add_argument("--json", action="store_true")
    fails.add_argument("--include-private", action="store_true",
                       help="across sessions, also fold in private ones (a named sid is always read)")
    exp = sub.add_parser("export", help="what a consumer hasn't taken yet (claudna.export/1), or --ack",
                         parents=[rooted])
    exp.add_argument("--consumer", required=True)
    exp.add_argument("--since-seg", type=int)
    exp.add_argument("--limit", type=int, default=100)
    exp.add_argument("--include-skipped", action="store_true",
                     help="also emit a status item {summary: null, skipped: {reason}} for unsummarized segments")
    exp.add_argument("--json", action="store_true", help="the envelope is always JSON; accepted for the contract")
    exp.add_argument("--ack", action="store_true", help="record that the consumer took --sid through --through")
    exp.add_argument("--sid")
    exp.add_argument("--through", type=int)
    dig = sub.add_parser("digest", help="drafts and held person facts awaiting a person's review",
                         parents=[rooted])
    dig.add_argument("--limit", type=int, default=5)
    dig.add_argument("--json", action="store_true")
    act = dig.add_mutually_exclusive_group()
    act.add_argument("--promote", metavar="ITEM", help="promote a draft to verified (runs claudron), then take it off")
    act.add_argument("--done", metavar="ITEM", help="take an item (a note path or a held fact's person: id) off")
    dig.add_argument("--vault", help="with --promote/--done: the item's vault, as the digest gave it")
    dig.add_argument("--revision", type=int, help="with --promote/--done on a draft: its revision, as shown")
    dig.add_argument("--outcome", choices=("promoted", "discarded", "kept"), help="with --done: what the person did")
    rns = sub.add_parser("runs", help="the ops log: the store's background runs, newest first", parents=[rooted])
    rns.add_argument("--kind", choices=("summarize", "harvest", "sweep"))
    rns.add_argument("--since", help=_SINCE_HELP)
    rns.add_argument("--limit", type=int, default=50)
    rns.add_argument("--json", action="store_true")
    health = sub.add_parser("health", help="read-only pipeline coverage, backlog and review decisions",
                            parents=[rooted])
    health.add_argument("--json", action="store_true")
    harv = sub.add_parser("harvest", help="write summarized blocks to the vault as drafts (via claudron)",
                          parents=[rooted])
    harv.add_argument("--force", action="store_true", help="run even if the last run is recent")
    hook = sub.add_parser("hook", help="apply one host hook event (payload on stdin); always exits 0")
    hook.add_argument("--host", default="claude")
    hook.add_argument("event")
    args = parser.parse_args(argv)
    if args.verb in ("paths", "scratch", "operation-dir"):
        return _owned_path_command(args)
    if args.verb in ("continuity", "handoff-write"):
        return _continuity_command(args)
    if args.verb == "skill-start":
        from .host_codex import record_skill_start

        try:
            print(record_skill_start(args.skill, os.environ, Path(args.root) if args.root else None))
        except Exception as exc:  # noqa: BLE001 — logging must not break the skill
            # A diagnostic without task content, paths or exception payloads.
            print(f"skill logging unavailable: {type(exc).__name__}", file=sys.stderr)
        return 0
    if args.verb == "hook":
        run_hook(args.event, sys.stdin.buffer.read(), host=args.host)
        return 0

    if args.verb == "harvest":
        from . import harvest

        store = _store(args)
        if store is None:
            return 1
        from . import ops

        with ops.run(store.root, "harvest") as rec:
            report = harvest.harvest(store, force=args.force).as_dict()
            rec["outcome"], rec["sessions"] = report.get("status") or "done", report.get("sessions") or []
            rec["detail"] = {k: report.get(k) for k in ("created", "known", "held_back", "rejected", "retried",
                                                        "gave_up", "segments", "errors")}
        print(json.dumps(report))
        return 0
    if args.verb in ("list", "show", "timeline", "failures"):
        return _read(args)
    if args.verb == "sweep":
        from . import unclosed

        store = _store(args)
        if store is None:
            return 1
        env = dict(os.environ)
        # The sweep acts for every session, so no session's summary override applies to the others:
        # each abandoned session is summarized only by its own recorded policy (the #373 B2 rule).
        own = {k: v for k, v in env.items() if k != SUMMARY_ENV}
        from . import ops

        def close(h, pid):
            return boundaries.abandon_session(h, own, owner_pid=pid)

        if args.dry_run:
            report = unclosed.sweep(store, env, dry_run=True, close=close).as_dict()
        else:
            from . import retention

            with unclosed.sweep_lock(store.root) as taken:
                if not taken:  # another sweep is running: neither half runs twice (#387 review S1)
                    print(json.dumps({"status": "skipped", "reason": "another sweep is running"}))
                    return 0
                with ops.run(store.root, "sweep") as rec:
                    report = unclosed.sweep(store, env, close=close, locked=True).as_dict()
                    # retention (spec §9) rides the same detached, debounced worker, under the same lock
                    report["retention"] = retention.sweep(store, env).as_dict()
                    retired = report["retention"]["retired"]
                    errors = report["errors"] + report["retention"]["errors"]
                    rec.update(outcome="error" if errors else "done",
                               sessions=report["closed"] + [r.split("/", 1)[0] for r in retired],
                               detail={"closed": len(report["closed"]), "retired": len(retired),
                                       "repaired": len(report["retention"]["repaired"]), "errors": errors[:5]})
        print(json.dumps(report))
        return 0
    if args.verb == "health":
        from .health import report

        store = _store(args)
        if store is None:
            return 1
        found = report(store)
        if args.json:
            print(json.dumps(found, indent=2))
        else:
            print(f"Pipeline: {found['status']} (retained evidence only)")
            print(f"Sessions by host: {found['sessions_by_host']}")
            print(f"Final summaries: {found['final_segment_summaries']}")
            print(f"Harvest: {found['harvest']}")
            print(f"Draft reviews: {found['draft_reviews']}")
            for warning in found["warnings"]:
                print(f"WARN: {warning}")
            for limit in found["limits"]:
                print(f"INFO: {limit}")
        return 0
    if args.verb == "runs":
        store = _store(args)
        if store is None:
            return 1
        from . import ops, readers

        try:
            since = readers.since_cutoff(args.since)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        found = ops.runs(store.root, kind=args.kind, since=since, limit=args.limit)
        if args.json:
            print(json.dumps(found, indent=2))
        else:
            for r in found:
                who = f"  {len(r['sessions'])} session(s)" if r["sessions"] else ""
                print(f"{r['started_at']}  {r['kind']:9} {r['duration_ms']:>7} ms  {r['outcome']}{who}")
            if not found:
                print("no runs")
        return 0
    if args.verb == "export":
        return _export(args)
    if args.verb == "digest":
        from . import digest, readers

        store = _store(args)
        if store is None:
            return 1
        item = args.promote or args.done
        if args.vault and not item:
            print("error: --vault only goes with --promote or --done", file=sys.stderr)
            return 2
        if args.done and not args.outcome:
            print("error: --done needs --outcome (promoted, discarded or kept)", file=sys.stderr)
            return 2
        if item:
            return _review(store, digest, item, args.vault, args.revision,
                           outcome="promoted" if args.promote else args.outcome, promote=bool(args.promote))
        found = [i.as_dict() for i in digest.items(store.root, limit=args.limit)]
        if args.json:
            print(json.dumps(found, indent=2))
        else:
            for n, i in enumerate(found, 1):
                seen = f"{i['sessions']} session(s)" + (", user-asserted" if i["asserted_by"] == "user" else "")
                title = readers.printable(i["title"])
                claims = "".join(f"\n   - {readers.printable(c or '')}" for c in (i["claims"] or [i["claim"]]))
                print(f"{n}. [{i['kind']}] {title}  ({seen}){claims}\n   item: {i['item']}"
                      + (f"  vault: {i['vault']}" if i["vault"] else "") + f"  revision: {i['revision']}")
            if not found:
                print("nothing to review")
        return 0
    handle = _handle(args)
    if handle is None:
        return 1
    if args.verb == "seal":
        try:
            index = boundaries.abandon_session(handle, dict(os.environ))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"{args.sid}: closed (abandoned)" + (f", seg-{index:03d} sealed" if index is not None else ""))
        return 0
    if args.verb == "private":
        handle.set_private(not args.off)
        print(f"{args.sid}: {'not ' if args.off else ''}private")
        return 0
    if args.verb == "summarize":
        from . import ops, summarize  # off the hook path: summarize pulls in hashlib, uuid and subprocess

        with ops.run(handle.paths.root, "summarize") as rec:
            rec.update(sessions=[handle.sid], detail={"seg": args.seg})
            outcome = rec["outcome"] = summarize.summarize(handle, args.seg)
        print(outcome)
        return 0
    if args.verb == "rebuild":
        from . import rollup  # the rollup is derived from summaries, not logs: rebuild regenerates it too

        report = handle.rebuild()
        rollup.refresh(handle.paths)
        print(json.dumps(dataclasses.asdict(report)))
        return 0
    report = check_session(handle)
    for line in report.warnings:
        print(f"warning: {line}")
    for line in report.problems:
        print(line)
    return 1 if report.problems else 0
