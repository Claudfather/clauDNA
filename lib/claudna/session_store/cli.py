"""Command line for the session store.

    python3 -m claudna.session_store rebuild <sid> [--root DIR]
    python3 -m claudna.session_store check   <sid> [--root DIR]

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
from .paths import InvalidSessionId, InvalidStateDir
from .store import SessionHandle, SessionStore


def _handle(args: argparse.Namespace) -> SessionHandle | None:
    try:
        store = SessionStore(Path(args.root) if args.root else None)
        handle = store.session(args.sid)
    except (InvalidSessionId, InvalidStateDir) as exc:
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
