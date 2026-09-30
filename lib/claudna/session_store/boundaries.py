"""Hook adapter: Claude Code hook payloads → store actions (spec §4.2).

The one Claude Code-specific module. A hook wrapper pipes the hook's JSON
payload to ``session_store hook <event>``; :func:`handle` maps it onto the
store's lifecycle verbs:

========================  =====================================================
SessionStart (startup,    ``session.opened``, then a new segment starting at the
resume, clear, fork)      transcript's current size
SessionStart (compact)    a new segment starting where the last seal ended
PreCompact                seal the current segment at the transcript's size
SessionEnd                seal the current segment, then ``session.closed``
========================  =====================================================

Guards, in order (each makes the hook record nothing):

* ``CLAUDNA_SESSION_CHILD=1`` — a ``claude -p`` child clauDNA spawned itself.
* An inherited session id — a nested ``claude -p`` can reuse its parent's
  session id (canary, spec §11.5) and must not seal, close, or otherwise write
  into the parent (see :func:`_inherited`).
* An event or payload this adapter doesn't know.

After a seal, the adapter starts the summarizer for that segment as a detached
process (:func:`spawn_summarizer`) and returns at once — unless the summary
gate is closed for the session (private, headless, a bot, switched off), in
which case it records ``summary.skipped`` itself and starts nothing; clear lineage
(``parent_sid``) arrives in a later phase. It never prints: SessionStart stdout
would land in the agent's context.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Mapping

from . import events as ev
from .paths import CHILD_ENV, InvalidSessionId
from .fsio import cap_log, ensure_dir, file_size
from .project import SessionFacts, load_lifecycle, session_facts, summary_gate
from .store import SessionHandle, SessionStore

_SOURCES = ev.REGISTRY["session.opened"].choices["source"]
_CLOSE_REASONS = ev.REGISTRY["session.closed"].choices["reason"]
_TRIGGERS = ev.REGISTRY["segment.sealed"].choices["trigger"]


def actor_from_env(env: Mapping[str, str]) -> dict:
    """Who is running this session, from the environment Claude Code and Claudlobby set.

    A Claudlobby bot exports ``BOT_ID`` (and ``BOT_NAME``, ``FLEET_NAME``) in
    its ``bot.conf``. ``claude -p`` runs with ``CLAUDE_CODE_ENTRYPOINT=sdk-cli``;
    an interactive session with ``cli``.
    """
    entrypoint = env.get("CLAUDE_CODE_ENTRYPOINT") or None
    if env.get("BOT_ID"):
        kind = "bot"
    elif entrypoint and entrypoint.startswith("sdk"):
        kind = "headless"
    else:
        kind = "interactive"
    return {
        "kind": kind,
        "fleet": env.get("FLEET_NAME") or env.get("CLAUDLOBBY_FLEET") or None,
        "bot_id": env.get("BOT_ID") or None,
        "bot_name": env.get("BOT_NAME") or None,
        "model": None,
        "entrypoint": entrypoint,
    }


def origin_from_cwd(cwd: str) -> dict:
    """Where the session runs: its cwd, plus the repo's root name, branch and HEAD when there is one.

    ``repo`` is the name of the repository's top-level directory — what
    ``/claudna:capture`` scopes repo-specific findings to (``--project``).

    One bounded ``git`` call; fsmonitor is disabled because a repository's own
    config could otherwise name a command for git to run.
    """
    import subprocess  # only an opening SessionStart needs it; the other hooks skip the import

    repo = branch = head = None
    try:
        out = subprocess.run(
            ["git", "-c", "core.fsmonitor=", "rev-parse", "--show-toplevel", "HEAD", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=1, check=True,
        ).stdout.splitlines()
        if len(out) == 3:  # the top level, the sha, then the branch (--abbrev-ref applies to later args only)
            repo = os.path.basename(out[0]) or None
            head = out[1]
            branch = None if out[2] == "HEAD" else out[2]  # "HEAD" means detached
    except (OSError, subprocess.SubprocessError):
        pass
    return {"cwd": cwd, "repo": repo, "branch": branch, "head": head}


# ── actions ──────────────────────────────────────────────────────────────────


def _session_start(handle: SessionHandle, payload: dict, env: Mapping[str, str], *,
                   spawn: Callable[..., None]) -> str:
    source = payload.get("source")
    transcript = payload.get("transcript_path") or None
    previous = handle.current_segment()
    if source == "compact":  # the store starts it where the last seal ended; the size is the fallback
        handle.open_segment("compact", file_size(transcript))
        _summarize_implicit_seal(handle, previous, env, spawn)
        return "segment opened (compact)"
    if source not in _SOURCES:
        return f"ignored: SessionStart source {source!r}"
    handle.open_session(source, actor=actor_from_env(env),
                        origin=origin_from_cwd(payload.get("cwd") or os.getcwd()),
                        transcript_path=transcript)
    handle.open_segment("session_open", file_size(transcript))
    _summarize_implicit_seal(handle, previous, env, spawn)
    from . import harvest  # only an opening SessionStart asks

    if harvest.is_due(handle.paths.root, env):  # spec §7.2: harvest runs at SessionStart, detached
        spawn_harvest(handle.paths.root, env)
    return f"session opened ({source})"


def spawn_worker(root: Path, args: list[str], env: Mapping[str, str], *, log: str) -> None:
    """Start ``session_store <args> --root <root>`` detached, and return at once.

    Its own session (``start_new_session``), so a group kill of the hook's tree
    doesn't reap it; ``CLAUDNA_SESSION_CHILD=1``, so nothing it starts records
    into the store; its stderr goes to ``<root>/hooks/<log>``.
    """
    import subprocess

    package = Path(__file__).resolve().parent
    with open(cap_log(ensure_dir(root / "hooks") / log), "ab") as err:
        subprocess.Popen(
            [sys.executable, "-S", str(package), *args, "--root", str(root)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
            env={**env, CHILD_ENV: "1"}, start_new_session=True, close_fds=True,
        )


def spawn_summarizer(handle: SessionHandle, index: int, env: Mapping[str, str]) -> None:
    spawn_worker(handle.paths.root, ["summarize", handle.sid, str(index)], env, log="summarizer.stderr")


def spawn_harvest(root: Path, env: Mapping[str, str]) -> None:
    spawn_worker(root, ["harvest"], env, log="harvest.stderr")


def _summarize_segment(handle: SessionHandle, index: int, facts: SessionFacts, env: Mapping[str, str],
                       spawn: Callable[..., None]) -> None:
    """Spawn the summarizer for sealed segment ``index``, or record why not."""
    reason = summary_gate(facts, env)
    if reason:
        handle.append("summary.skipped", {"reason": reason}, seg=index)
    else:
        spawn(handle, index, env)


def _summarize_implicit_seal(handle: SessionHandle, previous: int | None, env: Mapping[str, str],
                             spawn: Callable[..., None]) -> None:
    """Summarize a predecessor :meth:`SessionHandle.open_segment` just sealed itself.

    A missed PreCompact or a lost SessionEnd (a crash, then a resume) leaves
    the predecessor to be sealed by ``open_segment`` (``sealed_by`` ``compact``
    or ``resume``); no hook seal ran, so nothing else would ever summarize it,
    and harvest's cursor would hold at it forever.
    """
    if previous is None:
        return
    boundary = handle.boundary(previous)
    if boundary.sealed and boundary.summary["status"] == "none" and \
            boundary.last_seal["data"]["sealed_by"] in ("compact", "resume"):
        _summarize_segment(handle, previous, _facts(handle), env, spawn)


def _seal(handle: SessionHandle, payload: dict, facts: SessionFacts, env: Mapping[str, str], *,
          sealed_by: str, trigger: str | None, spawn: Callable[..., None]) -> bool:
    """Seal the current segment, then summarize it: spawn the worker, or record why not."""
    index = handle.current_segment()
    if index is None:
        return False
    handle.seal_segment(file_size(payload.get("transcript_path")), sealed_by, index=index, trigger=trigger,
                        clamp=True)
    _summarize_segment(handle, index, facts, env, spawn)
    return True


def _facts(handle: SessionHandle) -> SessionFacts:
    """The session's facts, folded from the lifecycle log once per hook.

    Read-only, so it is safe outside the session lock: the projection may be
    stale after a lost refresh; the log isn't.
    """
    return session_facts(load_lifecycle(handle.paths).events if handle.exists() else [])


def _inherited(event: str, payload: dict, facts: SessionFacts, env: Mapping[str, str]) -> bool:
    """Is this hook a nested ``claude -p`` reusing an open session's id?

    A stopgap until every child carries a marker (spec §11.5): a hook whose
    entrypoint differs from the one the open session recorded. A resume is let
    through — ``claude -p --resume`` of a session a crash left open must reopen
    it — and the canary shows an inheriting child reports ``startup``.
    """
    if facts.status != "open" or facts.actor is None or (event == "SessionStart" and payload.get("source") == "resume"):
        return False
    return facts.actor["entrypoint"] != (env.get("CLAUDE_CODE_ENTRYPOINT") or None)


def handle(event: str, payload: object, *, store: SessionStore, env: Mapping[str, str],
           spawn: Callable[..., None] | None = None) -> str:
    """Apply one hook event to the store; return what happened, for tests and the error log.

    Raises only on a store failure (the caller logs it); every guard returns.
    The ``CLAUDNA_SESSION_CHILD`` check repeats the wrapper's fast exit for
    direct CLI calls.
    """
    if env.get(CHILD_ENV) == "1":
        return "ignored: clauDNA child"
    if event not in ("SessionStart", "PreCompact", "SessionEnd"):
        return f"ignored: event {event!r}"
    if not isinstance(payload, dict):
        return "ignored: payload is not an object"
    try:
        session = store.session(payload.get("session_id"))
    except InvalidSessionId:
        return "ignored: no valid session id"
    facts = _facts(session)
    if _inherited(event, payload, facts, env):
        return "ignored: nested child with an inherited session id"
    spawn = spawn or spawn_summarizer
    if event == "SessionStart":
        return _session_start(session, payload, env, spawn=spawn)
    if event == "PreCompact":
        trigger = payload.get("trigger") if payload.get("trigger") in _TRIGGERS else None
        sealed = _seal(session, payload, facts, env, sealed_by="precompact", trigger=trigger, spawn=spawn)
        return "segment sealed" if sealed else "ignored: no segment"
    if facts.status != "open":
        return "ignored: no open session"
    _seal(session, payload, facts, env, sealed_by="session_end", trigger=None, spawn=spawn)
    reason = payload.get("reason") if payload.get("reason") in _CLOSE_REASONS else "other"
    session.close_session(reason)
    return f"session closed ({reason})"
