"""Command line for the session store.

    python3 -m claudna.session_store rebuild <sid> [--root DIR]
    python3 -m claudna.session_store check   <sid> [--root DIR]
    python3 lib/claudna/session_store hook <event>     (hook payload on stdin)
    python3 lib/claudna/session_store summarize <sid> <seg> [--root DIR]
    python3 lib/claudna/session_store harvest [--force] [--root DIR]

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


def run_hook(event: str, raw: str, env: dict[str, str] | None = None) -> str:
    """Apply one hook event; never raise. Returns the outcome (``"error: …"`` on failure)."""
    env = dict(os.environ) if env is None else env
    root = None
    try:
        root = state_root(env)
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hook"] and len(argv) == 2:  # the hot path: no argparse
        run_hook(argv[1], sys.stdin.read())
        return 0
    import argparse

    parser = argparse.ArgumentParser(prog="claudna.session_store", description="clauDNA session store")
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb, text in (("rebuild", "regenerate projections from logs"),
                       ("check", "validate logs and projections; writes nothing"),
                       ("summarize", "summarize one sealed segment (the detached worker)")):
        p = sub.add_parser(verb, help=text)
        p.add_argument("sid")
        if verb == "summarize":
            p.add_argument("seg", type=int)
        p.add_argument("--root", help="store root (default: $CLAUDNA_STATE_DIR or ~/.claudna)")
    harv = sub.add_parser("harvest", help="write summarized blocks to the vault as drafts (via claudron)")
    harv.add_argument("--force", action="store_true", help="run even if the last run is recent")
    harv.add_argument("--root", help="store root (default: $CLAUDNA_STATE_DIR or ~/.claudna)")
    hook = sub.add_parser("hook", help="apply one Claude Code hook event (payload on stdin); always exits 0")
    hook.add_argument("event")
    args = parser.parse_args(argv)
    if args.verb == "hook":
        run_hook(args.event, sys.stdin.read())
        return 0

    if args.verb == "harvest":
        from . import harvest

        store = _store(args)
        if store is None:
            return 1
        print(json.dumps(harvest.harvest(store, force=args.force).as_dict()))
        return 0
    handle = _handle(args)
    if handle is None:
        return 1
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
