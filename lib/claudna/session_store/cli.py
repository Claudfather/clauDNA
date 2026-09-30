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
from .fsio import append_jsonl, cap_log, ensure_dir, read_json, read_jsonl
from .paths import InvalidSessionId, InvalidStateDir, state_root
from .project import SUMMARY_ENV
from .store import SessionHandle, SessionStore

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


def run_hook(event: str, raw: str | bytes, env: dict[str, str] | None = None) -> str:
    """Apply one hook event; never raise. Returns the outcome (``"error: …"`` on failure).

    ``raw`` may be the undecoded stdin bytes: decoding happens inside the guard,
    so invalid UTF-8 is logged to ``errors.log`` like any other bad payload.
    """
    env = dict(os.environ) if env is None else env
    root = None
    try:
        root = state_root(env)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if raw.strip() else None
        return boundaries.handle(event, payload, store=SessionStore(root), env=env)
    except Exception as exc:  # noqa: BLE001 — a hook must fail open, and say so
        _log_hook_error(root, event, exc)
        return f"error: {type(exc).__name__}: {exc}"


def _log_hook_error(root: Path | None, event: str, exc: BaseException) -> None:
    """One JSON line in ``<root>/hooks/errors.log``; stderr when there is no root to log to."""
    import traceback

    frame = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
    try:
        if root is None:
            raise exc
        hooks_dir = ensure_dir(root / "hooks")
        cap_log(hooks_dir / "session-store.stderr")  # the wrapper's capture; the next call starts a fresh one
        append_jsonl(cap_log(hooks_dir / "errors.log"), {
            "ts": ev.now_ts(), "component": "session_store", "event": event,
            "error": f"{type(exc).__name__}: {exc}",
            "where": f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}" if frame else None,
        }, durable=False)
    except Exception:  # noqa: BLE001 — nowhere to log to; the wrapper's stderr capture is the last resort
        print(f"session_store hook {event}: {type(exc).__name__}: {exc}", file=sys.stderr)


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
            print(json.dumps(export.export(store, args.consumer, since_seg=args.since_seg, limit=args.limit)))
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
    try:
        if args.verb == "list":
            data = readers.list_sessions(store, since=args.since, repo=args.repo, bot=args.bot, limit=args.limit)
        elif args.verb == "show":
            data = readers.show(store, args.sid)
        elif args.verb == "timeline":
            data = readers.timeline(store, args.sid)
        else:
            data = readers.failures(store, args.sid, group=args.group, since=args.since)
    except (LookupError, InvalidSessionId, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        for line in readers.render(args.verb, data, group=getattr(args, "group", False)):
            print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hook"] and len(argv) == 2:  # the hot path: no argparse
        run_hook(argv[1], sys.stdin.buffer.read())
        return 0
    if argv == ["telemetry"]:  # telemetry-emit.sh: its own entry, so it works with the store off
        from . import telemetry

        telemetry.run_hook(sys.stdin.buffer.read(), os.environ)
        return 0
    import argparse

    parser = argparse.ArgumentParser(prog="claudna.session_store", description="clauDNA session store")
    rooted = argparse.ArgumentParser(add_help=False)
    rooted.add_argument("--root", help="store root (default: $CLAUDNA_STATE_DIR or ~/.claudna)")
    sub = parser.add_subparsers(dest="verb", required=True)
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
    lst.add_argument("--since", help="7d, 12h, 2w, or an ISO date")
    lst.add_argument("--repo")
    lst.add_argument("--bot", help="a bot name or id")
    lst.add_argument("--limit", type=int, default=50)
    lst.add_argument("--json", action="store_true")
    for verb, text in (("show", "one session: its projection, segments, rollup and lineage"),
                       ("timeline", "one session's lifecycle and activity, in time order")):
        p = sub.add_parser(verb, help=text, parents=[rooted])
        p.add_argument("sid")
        p.add_argument("--json", action="store_true")
    fails = sub.add_parser("failures", help="tool.failed events, newest first; --group folds by signature",
                           parents=[rooted])
    fails.add_argument("sid", nargs="?")
    fails.add_argument("--group", action="store_true")
    fails.add_argument("--since", help="7d, 12h, 2w, or an ISO date")
    fails.add_argument("--json", action="store_true")
    exp = sub.add_parser("export", help="what a consumer hasn't taken yet (claudna.export/1), or --ack",
                         parents=[rooted])
    exp.add_argument("--consumer", required=True)
    exp.add_argument("--since-seg", type=int)
    exp.add_argument("--limit", type=int, default=100)
    exp.add_argument("--json", action="store_true", help="the envelope is always JSON; accepted for the contract")
    exp.add_argument("--ack", action="store_true", help="record that the consumer took --sid through --through")
    exp.add_argument("--sid")
    exp.add_argument("--through", type=int)
    harv = sub.add_parser("harvest", help="write summarized blocks to the vault as drafts (via claudron)",
                          parents=[rooted])
    harv.add_argument("--force", action="store_true", help="run even if the last run is recent")
    hook = sub.add_parser("hook", help="apply one Claude Code hook event (payload on stdin); always exits 0")
    hook.add_argument("event")
    args = parser.parse_args(argv)
    if args.verb == "hook":
        run_hook(args.event, sys.stdin.buffer.read())
        return 0

    if args.verb == "harvest":
        from . import harvest

        store = _store(args)
        if store is None:
            return 1
        print(json.dumps(harvest.harvest(store, force=args.force).as_dict()))
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
        # each abandoned session is summarized only by its own recorded opt-in (the #373 B2 rule).
        own = {k: v for k, v in env.items() if k != SUMMARY_ENV}
        report = unclosed.sweep(store, env, dry_run=args.dry_run,
                                close=lambda h, pid: boundaries.abandon_session(h, own, owner_pid=pid)).as_dict()
        if not args.dry_run:  # retention (spec §9) rides the same detached, debounced worker
            from . import retention

            report["retention"] = retention.sweep(store, env).as_dict()
        print(json.dumps(report))
        return 0
    if args.verb == "export":
        return _export(args)
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
        from . import summarize  # off the hook path: it pulls in hashlib, uuid and subprocess

        print(summarize.summarize(handle, args.seg))
        return 0
    if args.verb == "rebuild":
        report = handle.rebuild()
        print(json.dumps(dataclasses.asdict(report)))
        return 0
    report = check_session(handle)
    for line in report.warnings:
        print(f"warning: {line}")
    for line in report.problems:
        print(line)
    return 1 if report.problems else 0
