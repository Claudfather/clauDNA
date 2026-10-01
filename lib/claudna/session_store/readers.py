"""Readers (spec §8, phase 6): ``list``, ``show``, ``timeline``, ``failures``.

Read-only views over the store: nothing here writes. A projection that is
missing, fails its schema, or is behind its log (its ``projected_from.bytes``
isn't the log's size: a lost refresh) is folded from its log in memory instead
(the log is the truth; ``rebuild`` is what repairs files), so a reader never
trusts a stale file and never needs the lock. The rollup is the exception:
``list`` reads it as it is, ``show`` computes a missing one.

Each function returns plain data; the CLI prints it as text or ``--json``.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .events import REGISTRY
from .fsio import read_json
from .paths import SessionPaths
from .project import load_activity, load_lifecycle, segment_docs, session_doc
from .rollup import ROLLUP_SCHEMA, current, rollup_path
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


def _rollup(paths: SessionPaths) -> dict | None:
    """``summary.json`` if it is one: one read, for ``list``'s every row."""
    doc = read_json(rollup_path(paths))
    return doc if isinstance(doc, dict) and doc.get("schema") == ROLLUP_SCHEMA else None


def list_sessions(store: SessionStore, *, since: str | None = None, repo: str | None = None,
                  bot: str | None = None, limit: int = 50, include_private: bool = False,
                  unreadable: list[str] | None = None) -> list[dict]:
    """Sessions, newest first: one row each, with status, segment count and the rollup's title.

    A cross-session view, so private sessions are left out unless
    ``include_private``: a private session's titles mustn't reach another
    session's prose (and its summary, and the vault). A session that can't be
    read (permissions: files left by ``sudo claude``) is skipped and named in
    ``unreadable`` rather than failing the whole list.
    """
    cutoff = since_cutoff(since)
    rows = []
    for sid in store.session_ids():
        paths = store.session(sid).paths
        try:
            if cutoff and _older_than(paths.lifecycle, cutoff):
                continue  # its log hasn't changed since before the cutoff, so it opened before it too
            doc = session_doc(paths)
            actor, origin = doc.get("actor") or {}, doc.get("origin") or {}
            if (doc.get("private") and not include_private) or (cutoff and (doc.get("opened_at") or "") < cutoff) \
                    or (repo and origin.get("repo") != repo) or (bot and bot not in (actor.get("bot_name"),
                                                                                       actor.get("bot_id"))):
                continue
            roll = _rollup(paths)  # only for a row that is kept
        except OSError:
            if unreadable is not None:
                unreadable.append(sid)
            continue
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
    return {"session": session_doc(paths, lifecycle), "segments": segment_docs(paths, lifecycle),
            "rollup": _rollup(paths) or current(paths, lifecycle.events)}  # missing or foreign: computed


def _lifecycle_first(life: dict, act: dict) -> bool:
    """On a millisecond tie, does the lifecycle event go before the activity one?

    What opens (a session, a segment) precedes the activity it opens; what
    ends or follows (a seal, a close, a summary job) comes after the activity
    it ends — always within segments: an opening never precedes activity
    still in an earlier segment (an async hook landing after the seal), and
    an ending never follows activity already in a later one.
    """
    if life["seg"] is None:  # a session-level event: what opens the session precedes, the rest follows
        return REGISTRY[life["kind"]].opens
    if REGISTRY[life["kind"]].opens:  # a segment opening precedes only activity in it or later
        return act["seg"] >= life["seg"]
    return act["seg"] > life["seg"]  # a seal or summary job follows its segment's activity


def timeline(store: SessionStore, sid: str) -> list[dict]:
    """Every lifecycle and activity event of one session, in time order.

    The two logs share no sequence number, so they are merged, each in its
    *file* order: appends hold the session lock, so a log's order is causal,
    and a clock step must not reorder a log against itself. Activity is taken
    segment by segment. Where both heads are comparable, the earlier
    timestamp goes first, and a tie is broken by meaning (:func:`_lifecycle_first`).
    """
    handle = store.session(sid)
    if not handle.exists():
        raise LookupError(f"no session {sid}")
    paths = handle.paths
    life = load_lifecycle(paths).events
    act = [e for index in paths.segment_indices() for e in load_activity(paths, index).events]
    merged, i, j = [], 0, 0
    while i < len(life) or j < len(act):
        if j == len(act) or (i < len(life) and (life[i]["ts"] < act[j]["ts"] or (
                life[i]["ts"] == act[j]["ts"] and _lifecycle_first(life[i], act[j])))):
            merged.append(("lifecycle", life[i]))
            i += 1
        else:
            merged.append(("activity", act[j]))
            j += 1
    return [{"ts": e["ts"], "log": log, "seg": e["seg"], "kind": e["kind"], "data": e["data"]}
            for log, e in merged]


def _failures(store: SessionStore, sids: Iterable[str], cutoff: str | None, *, skip_private: bool,
              unreadable: list[str] | None) -> list[dict]:
    out = []
    for sid in sids:
        paths = store.session(sid).paths
        try:
            indices = [i for i in paths.segment_indices()  # untouched since before the cutoff: one stat, no read
                       if not (cutoff and _older_than(paths.segment(i).events, cutoff))]
            if not indices or (skip_private and session_doc(paths).get("private")):
                continue  # signatures carry hosts, paths, repo URLs: never folded into another session's view
            for index in indices:
                out += [{"sid": sid, "seg": index, "ts": e["ts"], **e["data"]}
                        for e in load_activity(paths, index).events if e["kind"] == "tool.failed"]
        except OSError:
            if unreadable is not None:
                unreadable.append(sid)
    return out


def _older_than(path, cutoff: str) -> bool:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(path.stat().st_mtime)) < cutoff[:19]
    except OSError:
        return True


def failures(store: SessionStore, sid: str | None = None, *, group: bool = False, since: str | None = None,
             include_private: bool = False, unreadable: list[str] | None = None) -> list[dict]:
    """``tool.failed`` events for one session or all, newest first; ``group`` folds them by signature.

    A group carries its count, how many sessions saw it, the exit codes, and
    the newest occurrence's ``sid``/``tool_use_id`` (where to read the full
    error: the transcript). Across sessions (no ``sid``), private sessions are
    left out unless ``include_private``; one named by ``sid`` is always read.
    """
    if sid is not None and not store.session(sid).exists():
        raise LookupError(f"no session {sid}")
    cutoff = since_cutoff(since)
    rows = [r for r in _failures(store, [sid] if sid else store.session_ids(), cutoff,
                                 skip_private=sid is None and not include_private, unreadable=unreadable)
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


def _seg(index: int | None) -> str:
    return f"seg-{index:03d}" if index else "-      "


def _compact(data: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in data.items() if v not in (None, "", [], {}))


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def printable(text: str) -> str:
    """``text`` with control characters (newlines, ANSI escapes) turned to spaces.

    Titles, claims and signatures are model- or tool-written: a newline in one
    could forge another line (an ``item:``), an escape sequence reach the terminal.
    """
    return _CONTROL.sub(" ", text)


def render(verb: str, data, *, group: bool = False) -> list[str]:
    """Plain lines for a person at a terminal: one row per session, event or failure group."""
    if verb == "list":
        if not data:
            return ["no sessions"]
        return [f"{_short(r['opened_at'])}  {r['status'] or '-':7} {r['segments']:>3} seg  "
                f"{(r['repo'] or '-')[:24]:24}  {r['sid']}  {'[private] ' if r['private'] else ''}"
                f"{r['title'] or ''}".rstrip() for r in data]
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
        return [f"{_short(e['ts'])}  {_seg(e['seg'])}  {e['kind']:18} {_compact(e['data'])}" for e in data] \
            or ["no events"]
    if verb == "failures":
        if not data:
            return ["no failures"]
        if group:
            return [f"{g['count']:>4}x  {g['sessions']} session(s)  last {_short(g['last_ts'])}  {g['signature']}"
                    for g in data]
        return [f"{_short(r['ts'])}  {r['sid'][:8]} seg-{r['seg']:03d}  exit={r.get('exit_code')}  {r['signature']}"
                for r in data]
    raise ValueError(f"no renderer for {verb}")
