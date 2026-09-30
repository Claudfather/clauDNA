"""Readers (spec §8, phase 6): ``list``, ``show``, ``timeline``, ``failures``.

Read-only views over the store: nothing here writes. A projection that is
missing or fails its schema is folded from its log in memory instead (the log
is the truth; ``rebuild`` is what repairs files), so a reader never trusts a
stale file and never needs the lock.

Each function returns plain data; the CLI prints it as text or ``--json``.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .fsio import read_json, read_jsonl
from .paths import SessionPaths
from .project import (
    SEGMENT_SCHEMA,
    SESSION_SCHEMA,
    by_segment,
    load_activity,
    load_lifecycle,
    project_segment,
    project_session,
    read_projection,
    segment_transcript_paths,
    transcript_path_of,
)
from .rollup import rollup_path
from .store import SessionStore

_SINCE = re.compile(r"^(\d+)([hdw])$")


def since_cutoff(since: str | None, *, now: float | None = None) -> str | None:
    """``--since``: ``7d``, ``12h``, ``2w`` or an ISO date/time, as an event timestamp to compare against."""
    if not since:
        return None
    match = _SINCE.match(since.strip())
    if match:
        hours = int(match.group(1)) * {"h": 1, "d": 24, "w": 24 * 7}[match.group(2)]
        moment = datetime.fromtimestamp(time.time() if now is None else now, tz=timezone.utc) - timedelta(hours=hours)
    else:
        moment = datetime.fromisoformat(since.strip().replace("Z", "+00:00"))
        moment = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _segments(paths: SessionPaths, lifecycle) -> list[dict]:
    buckets, transcripts = by_segment(lifecycle.events), segment_transcript_paths(lifecycle.events)
    out = []
    for index in paths.segment_indices():
        doc = read_projection(paths.segment(index).segment_json, SEGMENT_SCHEMA)
        if doc is None:
            doc = project_segment(paths.sid, index, buckets.get(index, []), load_activity(paths, index),
                                  transcript_path=transcripts[index])
        out.append(doc)
    return out


def session_doc(paths: SessionPaths) -> dict:
    """``session.json``, or the same document folded from the log when the file can't be trusted."""
    doc = read_projection(paths.session_json, SESSION_SCHEMA)
    if doc is not None:
        return doc
    lifecycle = load_lifecycle(paths)
    return project_session(paths.sid, lifecycle, _segments(paths, lifecycle),
                           transcript_path=transcript_path_of(lifecycle.events))


def _rollup(paths: SessionPaths) -> dict | None:
    doc = read_json(rollup_path(paths))
    return doc if isinstance(doc, dict) and doc.get("schema") == "claudna.session-summary/2" else None


def list_sessions(store: SessionStore, *, since: str | None = None, repo: str | None = None,
                  bot: str | None = None, limit: int = 50) -> list[dict]:
    """Sessions, newest first: one row each, with status, segment count and the rollup's title."""
    cutoff = since_cutoff(since)
    rows = []
    for sid in store.session_ids():
        paths = store.session(sid).paths
        doc = session_doc(paths)
        actor, origin = doc.get("actor") or {}, doc.get("origin") or {}
        if cutoff and (doc.get("opened_at") or "") < cutoff:
            continue
        if repo and origin.get("repo") != repo:
            continue
        if bot and bot not in (actor.get("bot_name"), actor.get("bot_id")):
            continue
        roll = _rollup(paths)
        rows.append({
            "sid": sid, "opened_at": doc.get("opened_at"), "status": doc.get("status"),
            "close_reason": doc.get("close_reason"), "private": doc.get("private"),
            "kind": actor.get("kind"), "bot": actor.get("bot_name") or actor.get("bot_id"),
            "repo": origin.get("repo"), "branch": origin.get("branch"),
            "segments": doc["segments"]["count"], "chain_id": doc.get("chain_id"),
            "parent_sid": doc.get("parent_sid"),
            "title": ((roll or {}).get("fields") or {}).get("title"),
        })
    rows.sort(key=lambda r: r["opened_at"] or "", reverse=True)
    return rows[:limit]


def show(store: SessionStore, sid: str) -> dict:
    """One session: ``session.json``, its segments, the rollup and its lineage."""
    handle = store.session(sid)
    if not handle.exists():
        raise LookupError(f"no session {sid}")
    paths = handle.paths
    lifecycle = load_lifecycle(paths)
    return {"session": session_doc(paths), "segments": _segments(paths, lifecycle), "rollup": _rollup(paths)}


def timeline(store: SessionStore, sid: str) -> list[dict]:
    """Every lifecycle and activity event of one session, in time order (a lifecycle event first on a tie)."""
    handle = store.session(sid)
    if not handle.exists():
        raise LookupError(f"no session {sid}")
    paths = handle.paths
    merged = [(e["ts"], 0, n, "lifecycle", e) for n, e in enumerate(load_lifecycle(paths).events)]
    for index in paths.segment_indices():
        merged += [(e["ts"], 1, n, "activity", e) for n, e in enumerate(load_activity(paths, index).events)]
    merged.sort(key=lambda row: row[:3])
    return [{"ts": e["ts"], "log": log, "seg": e["seg"], "kind": e["kind"], "data": e["data"]}
            for _, _, _, log, e in merged]


def _failures(store: SessionStore, sids: Iterable[str]) -> list[dict]:
    out = []
    for sid in sids:
        paths = store.session(sid).paths
        for index in paths.segment_indices():
            for e in read_jsonl(paths.segment(index).events).records:
                if isinstance(e, dict) and e.get("kind") == "tool.failed" and isinstance(e.get("data"), dict):
                    out.append({"sid": sid, "seg": index, "ts": e.get("ts"), **e["data"]})
    return out


def failures(store: SessionStore, sid: str | None = None, *, group: bool = False,
             since: str | None = None) -> list[dict]:
    """``tool.failed`` events for one session or all, newest first; ``group`` folds them by signature.

    A group carries its count, how many sessions saw it, the exit codes, and
    the newest occurrence's ``sid``/``tool_use_id`` (where to read the full
    error: the transcript).
    """
    if sid is not None and not store.session(sid).exists():
        raise LookupError(f"no session {sid}")
    cutoff = since_cutoff(since)
    rows = [r for r in _failures(store, [sid] if sid else store.session_ids())
            if not cutoff or (r["ts"] or "") >= cutoff]
    rows.sort(key=lambda r: r["ts"] or "", reverse=True)
    if not group:
        return rows
    groups: dict[str, dict] = {}
    for r in rows:  # newest first, so the first row of a group is its latest
        g = groups.setdefault(r["signature"], {"signature": r["signature"], "tool": r["tool"], "count": 0,
                                               "sessions": set(), "exit_codes": set(), "last_ts": r["ts"],
                                               "last": {"sid": r["sid"], "seg": r["seg"],
                                                        "tool_use_id": r.get("tool_use_id")}})
        g["count"] += 1
        g["sessions"].add(r["sid"])
        if r.get("exit_code") is not None:
            g["exit_codes"].add(r["exit_code"])
    out = [{**g, "sessions": len(g["sessions"]), "exit_codes": sorted(g["exit_codes"])} for g in groups.values()]
    out.sort(key=lambda g: (-g["count"], g["signature"]))
    return out


# ── text output (the CLI's default; --json prints the data as is) ─────────────


def _short(ts: str | None) -> str:
    return (ts or "")[:16].replace("T", " ") or "-"


def _compact(data: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in data.items() if v not in (None, "", [], {}))


def render(verb: str, data, *, group: bool = False) -> list[str]:
    """Plain lines for a person at a terminal: one row per session, event or failure group."""
    if verb == "list":
        if not data:
            return ["no sessions"]
        return [f"{_short(r['opened_at'])}  {r['status'] or '-':7} {r['segments']:>3} seg  "
                f"{(r['repo'] or '-')[:24]:24}  {r['sid']}  {r['title'] or ''}".rstrip() for r in data]
    if verb == "show":
        s, roll = data["session"], data["rollup"]
        lines = [f"session {s['sid']}  {s['status']}" + (f" ({s['close_reason']})" if s.get("close_reason") else ""),
                 f"  opened {_short(s['opened_at'])} by {s['opened_by']}  closed {_short(s['closed_at'])}",
                 f"  chain {s['chain_id']}  parent {s['parent_sid'] or '-'}  "
                 f"children {', '.join(s['children']) or '-'}"]
        for seg in data["segments"]:
            c = seg["counts"]
            lines.append(f"  seg-{seg['index']:03d} {seg['status']:6} summary={seg['summary']['status']:7} "
                         f"prompts={c['prompts']} skills={c['skills']} failures={c['failures']} "
                         f"interrupts={c.get('interrupts', 0)}")
        if roll:
            f = roll["fields"]
            lines += [f"  {f.get('title') or ''}".rstrip(), f"  outcome: {f.get('outcome') or '-'}"]
            lines += [f"  - {b.get('claim')}" for b in f.get("blocks", [])[:10]]
        return lines
    if verb == "timeline":
        return [f"{_short(e['ts'])}  seg-{e['seg']:03d}  {e['kind']:18} {_compact(e['data'])}" if e["seg"] else
                f"{_short(e['ts'])}  -        {e['kind']:18} {_compact(e['data'])}" for e in data] or ["no events"]
    if verb == "failures":
        if not data:
            return ["no failures"]
        if group:
            return [f"{g['count']:>4}x  {g['sessions']} session(s)  last {_short(g['last_ts'])}  {g['signature']}"
                    for g in data]
        return [f"{_short(r['ts'])}  {r['sid'][:8]} seg-{r['seg']:03d}  exit={r.get('exit_code')}  {r['signature']}"
                for r in data]
    raise ValueError(f"no renderer for {verb}")
