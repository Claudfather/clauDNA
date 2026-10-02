#!/usr/bin/env python3
"""Session-store canaries: check, on a real machine, the harness facts the store assumes.

The session store rests on Claude Code behaviour that was only observed headless,
in a cloud container (spec §2, §11; the phase 3 plan's canary table). This kit
re-checks it interactively on a plain macOS or Linux machine:

- **§11.3, compact offset:** PreCompact's transcript size is where post-compact
  content begins, so the next segment can start at the seal's end.
- **§11.4, clear pid:** the ``claude`` process (``$CLAUDE_PID`` and the ancestor
  walk the store falls back on) is the same before and after ``/clear``, which
  the clear link (§4.3) is keyed on.
- **§11.5, nested ids:** whether a nested ``claude -p`` inherits its parent's
  session id when it isn't given ``--session-id``.
- **PostToolUseFailure for a Skill:** what a failed Skill call's payload looks
  like (the phase 4 plan's open canary).

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

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from claudna.session_store.lineage import claude_pid  # noqa: E402

LOG_NAME = "canary.jsonl"
EVENTS = ("SessionStart", "SessionEnd", "PreCompact", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure")
#: Payload fields worth keeping. Anything else (a prompt, tool input or output) is dropped.
KEPT = ("session_id", "source", "reason", "trigger", "transcript_path", "tool_name", "tool_use_id")
#: Transcript record types that carry conversation, which must not sit between a
#: PreCompact offset and the compact boundary.
CONVERSATION = ("user", "assistant")
ERROR_HEAD = 300


# --- hook: one record per event -------------------------------------------------------------------

def _size(path: object) -> int | None:
    try:
        return os.stat(str(path)).st_size if path else None
    except OSError:
        return None


def record(payload: dict, env: dict, *, walked_pid: int | None, now: float) -> dict:
    """The log line for one hook payload: names, ids, sizes and pids, never conversation text."""
    rec = {"ts": now, "event": payload.get("hook_event_name")}
    rec.update({k: payload[k] for k in KEPT if payload.get(k) is not None})
    rec["transcript_size"] = _size(payload.get("transcript_path"))
    rec["claude_pid_env"] = env.get("CLAUDE_PID")
    rec["claude_pid_walked"] = walked_pid
    rec["entrypoint"] = env.get("CLAUDE_CODE_ENTRYPOINT")
    rec["payload_keys"] = sorted(payload)
    if rec["event"] == "PostToolUseFailure":
        error = payload.get("error")
        rec["error_head"] = (error if isinstance(error, str) else json.dumps(error))[:ERROR_HEAD]
    return rec


def run_hook(log: Path) -> None:
    """Append the record for the payload on stdin. Never raises: a canary must not break a session."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        line = record(payload, dict(os.environ), walked_pid=claude_pid(), now=time.time())
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
    except Exception as exc:  # noqa: BLE001 - logged, never raised
        try:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": time.time(), "event": "canary-error", "error": repr(exc)}) + "\n")
        except OSError:
            pass


# --- setup: the throwaway plugin ------------------------------------------------------------------

def hooks_config(script: Path, log: Path) -> dict:
    """``hooks.json`` that sends every event in :data:`EVENTS` to ``script hook``."""
    command = f'python3 "{script}" hook --log "{log}"'
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

  claude --plugin-dir "{dir}"

Then, in that one interactive session, in order:

  1. say hi
  2. /compact
  3. say hi again
  4. /clear
  5. say hi
  6. !claude -p --plugin-dir "{dir}" "say hi"
       (the leading ! runs it as a shell command, inside this session; it is
        the nested child for §11.5, with no --session-id on purpose)
  7. Use the Skill tool to invoke the skill canary:does-not-exist
  8. /exit

Then print the verdicts, and paste them back:

  python3 scripts/session_canary.py report "{dir}"

The log keeps event names, ids, sizes and pids, never your prompts. A failed
tool's error text is kept to its first {head} characters; read the report
before pasting it.
"""


# --- report: verdicts from the log ----------------------------------------------------------------

def load(log: Path) -> list[dict]:
    rows = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _pid(row: dict) -> str | None:
    """The ``claude`` process a row ran under: the walked pid, else ``$CLAUDE_PID``.

    The walk comes first because it can't be inherited: a nested ``claude``
    that saw its parent's ``$CLAUDE_PID`` would otherwise pass for the parent.
    """
    value = row.get("claude_pid_walked") or row.get("claude_pid_env")
    return str(value) if value else None


def _records_from(path: Path, offset: int) -> tuple[bool, list[dict]]:
    """Whether ``offset`` falls on a line start in ``path``, and the records from there on."""
    with open(path, "rb") as fh:
        if offset:
            fh.seek(offset - 1)
            on_line = fh.read(1) == b"\n"
        else:
            on_line = True
        tail = fh.read()
    records = []
    for line in tail.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return on_line, records


def _is_boundary(rec: dict) -> bool:
    return rec.get("subtype") == "compact_boundary" or rec.get("type") == "compact_boundary"


def check_compact(rows: list[dict]) -> list[str]:
    """§11.3: every PreCompact offset is a line start, with no conversation before the boundary."""
    out = []
    for n, row in enumerate(rows):
        if row.get("event") != "PreCompact":
            continue
        after = next((r for r in rows[n + 1:] if r.get("event") == "SessionStart" and r.get("source") == "compact"
                      and r.get("session_id") == row.get("session_id")), None)
        path, offset = row.get("transcript_path"), row.get("transcript_size")
        if after is None or not path or offset is None:
            out.append("UNKNOWN: a PreCompact with no SessionStart(compact) after it, or no transcript size")
            continue
        try:
            on_line, records = _records_from(Path(path), offset)
        except OSError as exc:
            out.append(f"UNKNOWN: can't read the transcript ({exc.strerror})")
            continue
        boundary = next((i for i, r in enumerate(records) if _is_boundary(r)), None)
        if boundary is None:
            out.append(f"FAIL: no compact boundary after offset {offset}")
            continue
        before = [r.get("type") for r in records[:boundary]]
        talk = [t for t in before if t in CONVERSATION]
        verdict = "PASS" if on_line and not talk else "FAIL"
        out.append(f"{verdict}: offset {offset} {'is' if on_line else 'is NOT'} a line start; "
                   f"{len(before)} record(s) before the boundary ({', '.join(map(str, before)) or 'none'})"
                   + (f"; {len(talk)} of them conversation" if talk else ""))
    return out or ["UNKNOWN: no PreCompact in the log (step 2 not run?)"]


def check_clear(rows: list[dict]) -> list[str]:
    """§11.4: each SessionEnd(clear) and the SessionStart(clear) after it ran under one ``claude``."""
    out = []
    for n, row in enumerate(rows):
        if row.get("event") != "SessionEnd" or row.get("reason") != "clear":
            continue
        start = next((r for r in rows[n + 1:] if r.get("event") == "SessionStart" and r.get("source") == "clear"),
                     None)
        if start is None:
            out.append("UNKNOWN: a SessionEnd(clear) with no SessionStart(clear) after it")
            continue
        env_same = row.get("claude_pid_env") == start.get("claude_pid_env")
        walked_same = row.get("claude_pid_walked") == start.get("claude_pid_walked")
        verdict = "PASS" if env_same and walked_same and _pid(row) else "FAIL"
        out.append(f"{verdict}: $CLAUDE_PID {row.get('claude_pid_env')} -> {start.get('claude_pid_env')}, "
                   f"walked {row.get('claude_pid_walked')} -> {start.get('claude_pid_walked')}; "
                   f"new session id: {start.get('session_id') != row.get('session_id')}")
    return out or ["UNKNOWN: no /clear in the log (step 4 not run?)"]


def check_nested(rows: list[dict]) -> list[str]:
    """§11.5: a SessionStart from another ``claude`` process; did it reuse a live parent's id?"""
    starts = [r for r in rows if r.get("event") == "SessionStart"]
    if not starts:
        return ["UNKNOWN: no SessionStart in the log"]
    parent_pid = _pid(starts[0])
    parent_ids = {r.get("session_id") for r in rows if _pid(r) == parent_pid}
    children = [r for r in starts if _pid(r) != parent_pid]
    if not children:
        return ["UNKNOWN: no SessionStart from a nested claude (step 6 not run?)"]
    out = []
    for r in children:
        inherits = r.get("session_id") in parent_ids
        verdict, which = ("INHERITS", "its parent's") if inherits else ("FRESH", "a new")
        env = r.get("claude_pid_env")
        guard = ("its $CLAUDE_PID is the parent's, so the store's child guard can't tell them apart"
                 if env and str(env) == str(starts[0].get("claude_pid_env")) else f"its $CLAUDE_PID is {env}")
        out.append(f"{verdict}: nested claude (pid {_pid(r)}, entrypoint {r.get('entrypoint')}) "
                   f"started with {which} session id; {guard}")
    return out


def check_skill_failure(rows: list[dict]) -> list[str]:
    """What PostToolUseFailure carries for a Skill: its payload keys and the error's first characters."""
    hits = [r for r in rows if r.get("event") == "PostToolUseFailure" and r.get("tool_name") == "Skill"]
    if not hits:
        posted = any(r.get("event") == "PostToolUse" and r.get("tool_name") == "Skill" for r in rows)
        if posted:
            return ["NONE: no PostToolUseFailure for Skill; the call came back as PostToolUse instead"]
        return ["NONE: no Skill hook fired at all. If step 7 ran, the unknown skill was rejected before the tool "
                "ran, which fires neither PostToolUse nor PostToolUseFailure (seen headless on 2.1.287)"]
    return [f"SEEN: keys {r.get('payload_keys')}; error: {r.get('error_head')!r}" for r in hits]


def claude_version() -> str:
    try:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def report(rows: list[dict], *, version: str, system: str) -> str:
    errors = [r for r in rows if r.get("event") == "canary-error"]
    sections = [("§11.3 compact offset", check_compact(rows)), ("§11.4 claude pid across /clear", check_clear(rows)),
                ("§11.5 nested session id", check_nested(rows)), ("Skill failure payload", check_skill_failure(rows))]
    lines = [f"Session-store canaries: {version} on {system}, {len(rows)} hook records"]
    for title, results in sections:
        lines.append(f"\n{title}")
        lines += [f"  {r}" for r in results]
    if errors:
        lines.append(f"\n{len(errors)} hook error(s): {errors[0].get('error')}")
    return "\n".join(lines)


# --- CLI ------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
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
        target = (args.dir or Path(tempfile.mkdtemp(prefix="claudna-canary-"))).resolve()
        write_plugin(target, Path(__file__).resolve())
        print(STEPS.format(dir=target, head=ERROR_HEAD))
        return 0
    log = args.dir / LOG_NAME
    if not log.is_file():
        print(f"no log at {log}: run the steps from `setup` first", file=sys.stderr)
        return 1
    print(report(load(log), version=claude_version(), system=f"{platform.system()} {platform.release()}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
