#!/usr/bin/env python3
"""Session-store canaries: check, on a real machine, the harness facts the store assumes.

The session store rests on Claude Code behaviour that was only observed headless,
in a cloud container (the phase 3 plan's canary table; spec §11.3–11.5). This
kit re-checks it interactively on a plain macOS or Linux machine:

- **§11.3, compact offset:** PreCompact's transcript size is where post-compact
  content begins, so the next segment can start at the seal's end.
- **§11.4, clear pid:** ``$CLAUDE_PID``, which the clear link (§4.3) is keyed
  on, is the same before and after ``/clear``. The ancestor walk the store
  falls back on is shown alongside.
- **§11.5, nested ids:** whether a nested ``claude -p`` inherits its parent's
  session id, and if so whether the store's own child guard
  (``boundaries.inherited``) would still ignore every one of its events.

Three verbs:

``setup [--dir D]``
    Writes a throwaway plugin whose hooks log every boundary and tool event,
    and prints the steps to run.
``hook --log FILE``
    What the plugin's hooks call: appends one record per hook. Records event
    names, ids, sizes and pids only, never a prompt; it always exits 0.
``report DIR``
    Reads the log (and the transcripts it names) and prints a verdict per
    canary, ready to paste back.

A maintainer tool: nothing here ships in the plugin or runs in a user's session.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from claudna.session_store.boundaries import claude_pid_of, inherited  # noqa: E402
from claudna.session_store.fsio import append_jsonl, file_size, read_jsonl  # noqa: E402
from claudna.session_store.lineage import claude_pid  # noqa: E402
from claudna.session_store.project import SessionFacts  # noqa: E402

LOG_NAME = "canary.jsonl"
EVENTS = ("SessionStart", "SessionEnd", "PreCompact", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure")
#: Payload fields worth keeping. Anything else (a prompt, tool input or output) is dropped.
KEPT = ("session_id", "source", "reason", "trigger", "transcript_path", "tool_name", "tool_use_id")
#: Transcript record types that carry conversation, which must not sit between a
#: PreCompact offset and the compact boundary.
CONVERSATION = ("user", "assistant")


# --- hook: one record per event -------------------------------------------------------------------

def record(payload: dict, env: dict, *, walked_pid: int | None, now: float) -> dict:
    """The log line for one hook payload: names, ids, sizes and pids, never conversation text."""
    return {"ts": now, "event": payload.get("hook_event_name"),
            **{k: payload[k] for k in KEPT if payload.get(k) is not None},
            "transcript_size": file_size(payload.get("transcript_path")),
            "claude_pid_env": claude_pid_of(env), "claude_pid_walked": walked_pid,
            "entrypoint": env.get("CLAUDE_CODE_ENTRYPOINT")}


def run_hook(log: Path) -> None:
    """Append the record for the payload on stdin. Never raises: a canary must not break a session."""
    try:
        line = record(json.loads(sys.stdin.read() or "{}"), os.environ, walked_pid=claude_pid(), now=time.time())
    except Exception as exc:  # noqa: BLE001 - logged, never raised
        line = {"ts": time.time(), "event": "canary-error", "error": repr(exc)}
    try:
        append_jsonl(log, line, durable=False)
    except OSError:
        pass


# --- setup: the throwaway plugin ------------------------------------------------------------------

def hooks_config(script: Path, log: Path) -> dict:
    """``hooks.json`` that sends every event in :data:`EVENTS` to ``script hook``."""
    command = f"python3 {shlex.quote(str(script))} hook --log {shlex.quote(str(log))}"
    entry = {"hooks": [{"type": "command", "command": command}]}
    return {"hooks": {event: [{**entry, "matcher": "*"} if event.startswith("PostToolUse") else entry]
                      for event in EVENTS}}


def write_plugin(target: Path, script: Path) -> Path:
    """The canary plugin under ``target``; returns its log path."""
    (target / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    log = target / LOG_NAME
    manifest = {"name": "claudna-canary", "version": "0.0.0", "description": "Logs hook payloads for the "
                "session-store canaries (scripts/session_canary.py).", "hooks": "./hooks.json"}
    (target / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (target / "hooks.json").write_text(json.dumps(hooks_config(script, log), indent=2) + "\n")
    return log


STEPS = """\
Canary plugin written to {dir}

Run this in a normal terminal on your machine (not a cloud session), from any
scratch git repo:

  claude --plugin-dir {dir}

Then, in that one interactive session, in order:

  1. say hi
  2. /compact
  3. say hi again
  4. /clear
  5. say hi
  6. !claude -p --plugin-dir {dir} "say hi"
       (the leading ! runs it as a shell command, inside this session; it is
        the nested child for §11.5, with no --session-id on purpose)
  7. /exit

Then print the verdicts, and paste them back:

  python3 {script} report {dir}

The log keeps event names, ids, sizes and pids, never your prompts.
"""


# --- report: verdicts from the log ----------------------------------------------------------------

def _next(rows: list[dict], n: int, **want) -> dict | None:
    """The first row after ``rows[n]`` whose fields equal ``want``."""
    return next((r for r in rows[n + 1:] if all(r.get(k) == v for k, v in want.items())), None)


def _before_boundary(path: Path, offset: int) -> tuple[bool, list[str] | None]:
    """Whether ``offset`` is a line start, and the record types from there to the compact boundary.

    The types are ``None`` when no boundary follows. Reading stops at the boundary.
    """
    types: list[str] = []
    with open(path, "rb") as fh:
        fh.seek(max(offset - 1, 0))
        on_line = offset == 0 or fh.read(1) == b"\n"
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("subtype") == "compact_boundary":
                return on_line, types
            types.append(str(rec.get("type")))
    return on_line, None


def check_compact(rows: list[dict]) -> list[str]:
    """§11.3: every PreCompact offset is a line start, with no conversation before the boundary."""
    out = []
    for n, row in enumerate(rows):
        if row.get("event") != "PreCompact":
            continue
        path, offset = row.get("transcript_path"), row.get("transcript_size")
        if not path or not offset or \
                not _next(rows, n, event="SessionStart", source="compact", session_id=row.get("session_id")):
            out.append("UNKNOWN: a PreCompact with no SessionStart(compact) after it, or no transcript size")
            continue
        try:
            on_line, before = _before_boundary(Path(path), offset)
        except OSError as exc:
            out.append(f"UNKNOWN: can't read the transcript ({exc.strerror})")
            continue
        if before is None:
            out.append(f"FAIL: no compact boundary after offset {offset}")
            continue
        talk = [t for t in before if t in CONVERSATION]
        out.append(f"{'PASS' if on_line and not talk else 'FAIL'}: offset {offset} "
                   f"{'is' if on_line else 'is NOT'} a line start; {len(before)} record(s) before the boundary "
                   f"({', '.join(before) or 'none'})" + (f"; {len(talk)} of them conversation" if talk else ""))
    return out or ["UNKNOWN: no PreCompact in the log (step 2 not run?)"]


def check_clear(rows: list[dict]) -> list[str]:
    """§11.4: ``$CLAUDE_PID`` (the clear link's key) is the same on both sides of each ``/clear``."""
    out = []
    for n, row in enumerate(rows):
        if row.get("event") != "SessionEnd" or row.get("reason") != "clear":
            continue
        start = _next(rows, n, event="SessionStart", source="clear")
        if start is None:
            out.append("UNKNOWN: a SessionEnd(clear) with no SessionStart(clear) after it")
            continue
        env_pid, after = row.get("claude_pid_env"), start.get("claude_pid_env")
        was, now = row.get("claude_pid_walked"), start.get("claude_pid_walked")
        walked = f"walked {was} -> {now}" if was and now else "walk unavailable"
        if env_pid or after:
            verdict, key = ("PASS" if env_pid == after else "FAIL"), f"$CLAUDE_PID {env_pid} -> {after} ({walked})"
        elif was and now:  # no $CLAUDE_PID exported: the store keys the link on the walk instead
            verdict, key = ("PASS" if was == now else "FAIL"), f"$CLAUDE_PID not exported; {walked}"
        else:
            verdict, key = "UNKNOWN", "neither $CLAUDE_PID nor the walk found a claude process"
        out.append(f"{verdict}: {key}; new session id: {start.get('session_id') != row.get('session_id')}")
    return out or ["UNKNOWN: no /clear in the log (step 4 not run?)"]


def _grouper(rows: list[dict]):
    """How to tell ``claude`` processes apart: by the walked pid, which a child can't inherit.

    Only when the walk found nothing at all (a ``claude`` whose process name
    doesn't say so) does it fall back to ``$CLAUDE_PID``; mixing the two would
    let a child carrying its parent's ``$CLAUDE_PID`` pass for the parent.
    """
    key = "claude_pid_walked" if any(r.get("claude_pid_walked") for r in rows) else "claude_pid_env"
    return lambda row: row.get(key)


def check_nested(rows: list[dict]) -> list[str]:
    """§11.5: does a nested ``claude`` reuse a parent's id, and would the store's guard ignore it?

    The guard is ``boundaries.inherited``, given the facts the store records at
    the parent's open: its ``$CLAUDE_PID`` and entrypoint.
    """
    rows = [r for r in rows if r.get("event") in EVENTS]  # a canary-error row names no process
    starts = [r for r in rows if r.get("event") == "SessionStart"]
    if not starts:
        return ["UNKNOWN: no SessionStart in the log"]
    _process = _grouper(rows)
    parent = starts[0]
    parent_ids = {r.get("session_id") for r in rows if _process(r) == _process(parent)}
    child_rows = [r for r in rows if _process(r) != _process(parent)]
    if not child_rows:
        return ["UNKNOWN: no events from a nested claude (step 6 not run?)"]
    # The facts as session.opened records them: its entrypoint (None when unset) and $CLAUDE_PID.
    facts = SessionFacts(status="open", actor={"entrypoint": parent.get("entrypoint") or None}, private=False,
                         claude_pid=parent.get("claude_pid_env"))
    out = []
    for proc in dict.fromkeys(_process(r) for r in child_rows):
        mine = [r for r in child_rows if _process(r) == proc]
        first = mine[0]
        if not any(r.get("session_id") in parent_ids for r in mine):
            out.append(f"FRESH: nested claude (pid {proc}) used a new session id; nothing to guard")
            continue
        leaks = [r.get("event") for r in mine if not inherited(
            str(r.get("event")), {"source": r.get("source")}, facts,
            {"CLAUDE_PID": str(r.get("claude_pid_env") or ""), "CLAUDE_CODE_ENTRYPOINT": r.get("entrypoint") or ""})]
        out.append(f"{'LEAKS' if leaks else 'INHERITS'}: nested claude (pid {proc}, $CLAUDE_PID "
                   f"{first.get('claude_pid_env')}, entrypoint {first.get('entrypoint')}) used its parent's session "
                   f"id; the store's guard ignores {len(mine) - len(leaks)} of its {len(mine)} event(s)"
                   + (f" and would record {', '.join(map(str, leaks))}" if leaks else ""))
    return out


def claude_version() -> str:
    import subprocess

    try:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def report(rows: list[dict], *, version: str, system: str, skipped: int = 0) -> str:
    errors = [r for r in rows if r.get("event") == "canary-error"]
    sections = [("§11.3 compact offset", check_compact(rows)), ("§11.4 $CLAUDE_PID across /clear", check_clear(rows)),
                ("§11.5 nested session id", check_nested(rows))]
    lines = [f"Session-store canaries: {version} on {system}, {len(rows)} hook records"
             + (f" ({skipped} unreadable line(s) skipped)" if skipped else "")]
    for title, results in sections:
        lines.append(f"\n{title}")
        lines += [f"  {r}" for r in results]
    if errors:
        lines.append(f"\n{len(errors)} hook error(s): {errors[0].get('error')}")
    return "\n".join(lines)


# --- CLI ------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="verb", required=True)
    setup = sub.add_parser("setup", help="write the canary plugin and print the steps")
    setup.add_argument("--dir", type=Path, help="where to write it (default: a new temp dir)")
    hook = sub.add_parser("hook", help="called by the plugin's hooks")
    hook.add_argument("--log", type=Path, required=True)
    rep = sub.add_parser("report", help="print the verdicts")
    rep.add_argument("dir", type=Path)
    args = ap.parse_args(argv)

    if args.verb == "hook":
        run_hook(args.log)
        return 0
    if args.verb == "setup":
        import tempfile

        target = (args.dir or Path(tempfile.mkdtemp(prefix="claudna-canary-"))).resolve()
        if (target / LOG_NAME).exists():  # a second run's rows would be read as the first run's children
            print(f"{target / LOG_NAME} is from an earlier run: delete it or pick another --dir", file=sys.stderr)
            return 1
        script = Path(__file__).resolve()
        write_plugin(target, script)
        print(STEPS.format(dir=shlex.quote(str(target)), script=shlex.quote(str(script))))
        return 0
    log = args.dir / LOG_NAME
    if not log.is_file():
        print(f"no log at {log}: run the steps from `setup` first", file=sys.stderr)
        return 1
    import platform

    read = read_jsonl(log)
    print(report(read.records, version=claude_version(), system=f"{platform.system()} {platform.release()}",
                 skipped=read.skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
