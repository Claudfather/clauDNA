"""Command line for the session store.

    python3 -m claudna.session_store rebuild <sid> [--root DIR]
    python3 -m claudna.session_store check   <sid> [--root DIR]

(with ``lib/`` on ``PYTHONPATH``; ``python3 lib/claudna/session_store …`` also works)

``rebuild`` regenerates a session's projections from its logs. ``check``
validates the current projections and every log line against the schemas, the
kind registry, and placement (right session, log, and segment), without writing
anything. Lines from a newer envelope version or an unknown kind are skipped,
exactly as readers skip them — an older ``check`` never fails on a newer log.

``check`` fails only on what a writer can prevent: schema, registry, and
placement violations, and bad or missing projections. Unparseable lines are
crash debris — a torn write the store deliberately keeps as one skippable
line, and that no ``rebuild`` can remove — so they are reported as warnings.

Exit codes: 0 ok (warnings allowed) · 1 not found or check failed · 2 usage.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from . import events as ev
from . import schema
from .fsio import read_json, read_jsonl
from .paths import InvalidSessionId
from .store import SessionHandle, SessionStore


def _handle(args: argparse.Namespace) -> SessionHandle | None:
    store = SessionStore(Path(args.root) if args.root else None)
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
    """``problems`` fail a check; ``warnings`` (crash debris) are reported but don't."""

    problems: list[str]
    warnings: list[str]


def check_session(handle: SessionHandle) -> CheckReport:
    """Every schema, registry, or placement violation in one session's files."""
    problems: list[str] = []
    warnings: list[str] = []
    event_schema, session_schema, segment_schema = (schema.load(n) for n in ("event", "session", "segment"))
    indices = handle.paths.segment_indices()
    logs = [(handle.paths.lifecycle, ev.LIFECYCLE, None)] + [
        (handle.paths.segment(i).events, ev.ACTIVITY, i) for i in indices
    ]
    for log, log_kind, seg in logs:
        read = read_jsonl(log)
        if read.skipped:
            warnings.append(f"{log}: {read.skipped} unparseable line(s) (crash debris; readers skip them)")
        for n, record in enumerate(read.records, 1):
            verdict = ev.classify(record)
            if verdict == "unknown":
                continue  # newer envelope or kind: not ours to judge
            envelope = schema.validate(record, event_schema)
            problems.extend(f"{log} record {n}: {err}" for err in envelope)
            if envelope:
                continue
            if verdict == "invalid":
                problems.append(f"{log} record {n}: violates the kind registry")
                continue
            problems.extend(f"{log} record {n}: {err}"
                            for err in ev.placement_errors(record, sid=handle.sid, log=log_kind, seg=seg))
    targets = [(handle.paths.session_json, session_schema)] + [
        (handle.paths.segment(i).segment_json, segment_schema) for i in indices
    ]
    for path, target_schema in targets:
        obj = read_json(path)
        if obj is None:
            problems.append(f"{path}: missing or unparseable (run rebuild)")
            continue
        problems.extend(f"{path}: {err}" for err in schema.validate(obj, target_schema))
    return CheckReport(problems=problems, warnings=warnings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claudna.session_store", description="clauDNA session store")
    sub = parser.add_subparsers(dest="verb", required=True)
    for verb, text in (("rebuild", "regenerate projections from logs"),
                       ("check", "validate logs and projections; writes nothing")):
        p = sub.add_parser(verb, help=text)
        p.add_argument("sid")
        p.add_argument("--root", help="store root (default: $CLAUDNA_STATE_DIR or ~/.claudna)")
    args = parser.parse_args(argv)

    handle = _handle(args)
    if handle is None:
        return 1
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
