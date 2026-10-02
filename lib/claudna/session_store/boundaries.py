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
which case it records ``summary.skipped`` itself and starts nothing. A ``/clear``
records its lineage through :mod:`lineage` (spec §4.3). It never prints: SessionStart stdout
would land in the agent's context.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Mapping

from . import events as ev
from . import activity
from .paths import CHILD_ENV, InvalidSessionId
from .fsio import cap_log, ensure_dir, file_size
from .project import SessionFacts, load_lifecycle, session_facts, summary_gate
from .store import NotAppendable, SessionHandle, SessionStore

_SOURCES = ev.REGISTRY["session.opened"].choices["source"]
_CLOSE_REASONS = ev.HOOK_CLOSE_REASONS
#: Entrypoints a person drives. Anything else (``sdk-*``, CI actions, chat bots) is headless (#373, M5).
INTERACTIVE_ENTRYPOINTS = ("cli", "claude-vscode", "claude-desktop")


def actor_from_env(env: Mapping[str, str]) -> dict:
    """Who is running this session, from the environment Claude Code and Claudlobby set.

    A Claudlobby bot exports ``BOT_ID`` (and ``BOT_NAME``, ``FLEET_NAME``) in
    its ``bot.conf``. Interactive means an entrypoint a person drives
    (:data:`INTERACTIVE_ENTRYPOINTS`); every other entrypoint — ``sdk-cli``
    for ``claude -p``, a CI action, a chat integration — is headless. No
    entrypoint at all (a direct call) counts as interactive.
    """
    entrypoint = env.get("CLAUDE_CODE_ENTRYPOINT") or None
    if env.get("BOT_ID"):
        kind = "bot"
    elif entrypoint is None or entrypoint in INTERACTIVE_ENTRYPOINTS:
        kind = "interactive"
    else:
        kind = "headless"
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
        proc = subprocess.run(
            ["git", "-c", "core.fsmonitor=", "rev-parse", "--show-toplevel", "HEAD", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=1,
        )
        out = proc.stdout.splitlines()
        # The top level comes first and is printed even when HEAD can't resolve (a repo with no
        # commits yet): the repo is known then, its sha and branch aren't.
        if out and os.path.isabs(out[0]):
            repo = os.path.basename(out[0]) or None
        if proc.returncode == 0 and len(out) == 3:  # then the sha, then the branch (--abbrev-ref: later args)
            head = out[1]
            branch = None if out[2] == "HEAD" else out[2]  # "HEAD" means detached
    except (OSError, subprocess.SubprocessError):
        pass
    return {"cwd": cwd, "repo": repo, "branch": branch, "head": head}


# ── actions ──────────────────────────────────────────────────────────────────


def claude_pid_of(env: Mapping[str, str]) -> int | None:
    """The owning Claude Code process: ``$CLAUDE_PID``, which Claude Code exports to the commands it runs."""
    try:
        pid = int(env.get("CLAUDE_PID") or 0)
    except ValueError:
        return None
    return pid if pid > 0 else None


def harvest_choice(env: Mapping[str, str]) -> dict:
    """This session's own harvest choice, recorded at open: opted in, and the vault it would pick."""
    return {"enabled": env.get("CLAUDNA_HARVEST") == "1", "vault": env.get("CLAUDRON_VAULT_PATH") or None}


def _session_start(handle: SessionHandle, payload: dict, env: Mapping[str, str], *,
                   spawn: Callable[..., None], find_pid: Callable[[], int | None]) -> str:
    source = payload.get("source")
    transcript = payload.get("transcript_path") or None
    previous = handle.current_segment()
    if source == "compact":  # the store starts it where the last seal ended; the size is the fallback
        handle.open_segment("compact", file_size(transcript))
        # The compaction happened: summarize the segment its PreCompact sealed. Not at PreCompact
        # itself, which fires again when precompact-reflect.sh blocks the first attempt (#373, M5).
        _summarize_previous(handle, previous, env, spawn)
        return "segment opened (compact)"
    if source not in _SOURCES:
        return f"ignored: SessionStart source {source!r}"
    from . import lineage, unclosed  # opening SessionStarts only: keep them off the per-prompt path
    root = handle.paths.root
    parent = None
    if source == "clear":  # spec §4.3: the SessionEnd(clear) before us left a link under our claude's pid
        pid = find_pid()
        parent = lineage.take_link(root, pid, sid=handle.sid) if pid else None
    handle.open_session(source, actor=actor_from_env(env),
                        origin=origin_from_cwd(payload.get("cwd") or os.getcwd()),
                        transcript_path=transcript, claude_pid=claude_pid_of(env), harvest=harvest_choice(env),
                        parent_sid=parent["sid"] if parent else None,
                        chain_id=parent["chain_id"] if parent else None)
    handle.open_segment("session_open", file_size(transcript))  # before the parent's write, which can fail
    if parent:
        parent_handle = SessionStore(root).session(parent["sid"])
        if parent_handle.exists():  # never create a phantom parent; the child's lineage is already recorded
            parent_handle.link_child(handle.sid)
    _summarize_previous(handle, previous, env, spawn)
    from . import harvest  # only an opening SessionStart asks

    if harvest.is_due(handle.paths.root, env):  # spec §7.2: harvest runs at SessionStart, detached
        spawn_harvest(handle.paths.root, env)
    if unclosed.sweep_due(root):  # one stat; the walk over the store runs detached
        unclosed.mark_swept(root)
        spawn_sweep(root, env)
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


def spawn_sweep(root: Path, env: Mapping[str, str]) -> None:
    spawn_worker(root, ["sweep"], env, log="sweep.stderr")


def _summarize_segment(handle: SessionHandle, index: int, facts: SessionFacts, env: Mapping[str, str],
                       spawn: Callable[..., None]) -> None:
    """Spawn the summarizer for sealed segment ``index``, or record why not.

    A spawn that fails is recorded as a retryable ``summary.failed``, so
    harvest's retry finds it instead of a segment stuck at ``none``.
    """
    reason = summary_gate(facts, env)
    if reason:
        handle.append("summary.skipped", {"reason": reason}, seg=index)
        return
    try:
        spawn(handle, index, env)
    except OSError as exc:
        handle.append("summary.failed", {"job_id": "spawn", "error": f"spawn failed: {exc}", "retryable": True},
                      seg=index)


def abandon_session(handle: SessionHandle, env: Mapping[str, str], owner_pid: int | None = None) -> int | None:
    """Close a session whose SessionEnd never ran (``seal``, the sweep) and summarize its sealed segment.

    Returns the sealed index, or ``None`` when no segment was left open. A
    segment a PreCompact already sealed (the crash came before
    SessionStart(``compact``)) is summarized too, when it hasn't been. Raises
    ``ValueError`` for a session that isn't open, or that a resume took from
    ``owner_pid`` (the sweep's) since it was judged unclosed.
    """
    from . import unclosed

    index = unclosed.abandon(handle, owner_pid)
    if index is not None:
        _summarize_segment(handle, index, _facts(handle), env, spawn_summarizer)
    else:
        _summarize_previous(handle, handle.current_segment(), env, spawn_summarizer)
    return index


def _summarize_previous(handle: SessionHandle, previous: int | None, env: Mapping[str, str],
                        spawn: Callable[..., None]) -> None:
    """Summarize the segment before the one just opened, when its seal hasn't been summarized yet.

    That is a PreCompact seal (summarized once the compaction happened), or a
    predecessor :meth:`SessionHandle.open_segment` sealed itself after a missed
    PreCompact or a lost SessionEnd.
    """
    if previous is None:
        return
    boundary = handle.boundary(previous)
    if boundary.sealed and boundary.summary["status"] == "none":
        _summarize_segment(handle, previous, _facts(handle), env, spawn)


def _seal(handle: SessionHandle, payload: dict, *, sealed_by: str) -> int | None:
    """Seal the current segment at the transcript's size; return its index."""
    index = handle.current_segment()
    if index is None:
        return None
    handle.seal_segment(file_size(payload.get("transcript_path")), sealed_by, index=index, clamp=True)
    return index


def _record_activity(handle: SessionHandle, event: str, payload: dict, facts: SessionFacts,
                     env: Mapping[str, str]) -> str:
    """Append the activity event for an in-segment hook (``activity.py``), to the current segment.

    These hooks run async, so one can land after its session closed (SessionEnd
    raced it) or before its first segment exists. That is expected, not an
    error: nothing is recorded and nothing is logged.
    """
    mapped = activity.event_for(event, payload, env)
    if mapped is None:
        return f"ignored: nothing to record for {event}"
    if facts.status != "open":
        return "ignored: no open session"
    kind, data = mapped
    try:
        handle.append(kind, data)
    except NotAppendable as exc:  # it raced SessionEnd, or came before the first segment: expected here
        return f"ignored: {exc}"
    return f"recorded {kind}"


def _facts(handle: SessionHandle) -> SessionFacts:
    """The session's facts, folded from the lifecycle log once per hook.

    Read-only, so it is safe outside the session lock: the projection may be
    stale after a lost refresh; the log isn't.
    """
    return session_facts(load_lifecycle(handle.paths).events if handle.exists() else [])


def _inherited(event: str, payload: dict, facts: SessionFacts, env: Mapping[str, str]) -> bool:
    """Is this hook a nested ``claude`` reusing an existing session's id? (spec §11.5)

    A nested child inherits ``CLAUDE_CODE_SESSION_ID`` — and its entrypoint,
    except that a ``cli`` parent's child reports ``sdk-cli`` — so its hooks can
    look like the parent's. Three checks, any one enough, whether the parent is
    still open or already closed (a child can outlive its parent's SessionEnd):

    * **Another Claude Code process.** Claude Code exports ``CLAUDE_PID`` to
      what it runs; a hook whose ``CLAUDE_PID`` differs from the one the
      session recorded belongs to someone else.
    * **A fresh start of an existing session.** ``startup``, ``clear`` and
      ``fork`` each begin a new session id, so one naming a session the store
      already has can only be a child.
    * **Another entrypoint** (the phase 2 check; kept for sessions opened
      before ``claude_pid`` was recorded).

    A ``resume`` is always let through: ``claude --resume`` must reopen the
    session, from whatever process, whether a crash left it open or it closed.
    """
    if facts.status == "unknown" or (event == "SessionStart" and payload.get("source") == "resume"):
        return False
    pid = claude_pid_of(env)
    if facts.claude_pid and pid and pid != facts.claude_pid:
        return True
    if event == "SessionStart" and payload.get("source") in ("startup", "clear", "fork"):
        return True
    return facts.actor is not None and facts.actor["entrypoint"] != (env.get("CLAUDE_CODE_ENTRYPOINT") or None)


def handle(event: str, payload: object, *, store: SessionStore, env: Mapping[str, str],
           spawn: Callable[..., None] | None = None, find_pid: Callable[[], int | None] | None = None) -> str:
    """Apply one hook event to the store; return what happened, for tests and the error log.

    Raises only on a store failure (the caller logs it); every guard returns.
    The ``CLAUDNA_SESSION_CHILD`` check repeats the wrapper's fast exit for
    direct CLI calls.
    """
    if env.get(CHILD_ENV) == "1":
        return "ignored: clauDNA child"
    if event not in ("SessionStart", "PreCompact", "SessionEnd", *activity.EVENTS):
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
    if event in activity.EVENTS:
        return _record_activity(session, event, payload, facts, env)
    from . import lineage

    spawn = spawn or spawn_summarizer
    find_pid = find_pid or (lambda: claude_pid_of(env) or lineage.claude_pid())  # $CLAUDE_PID, else the walk
    if event == "SessionStart" and payload.get("source") != "compact":
        return _session_start(session, payload, env, spawn=spawn, find_pid=find_pid)
    # A closed session's segments are final: never re-sealed, re-closed or extended by a compaction.
    # A session the store never opened (enabled mid-session) gets no phantom segment either.
    if facts.status != "open":
        return "ignored: no open session"
    if event == "SessionStart":
        return _session_start(session, payload, env, spawn=spawn, find_pid=find_pid)
    if event == "PreCompact":  # seal only: the summary waits for SessionStart(compact) or SessionEnd
        return "segment sealed" if _seal(session, payload, sealed_by="precompact") is not None \
            else "ignored: no segment"
    index = _seal(session, payload, sealed_by="session_end")
    reason = payload.get("reason") if payload.get("reason") in _CLOSE_REASONS else "other"
    session.close_session(reason)  # closed before anything that could fail after it (#373, M2)
    if index is not None:  # before the link: a failed link write must not strand the seal unsummarized
        _summarize_segment(session, index, facts, env, spawn)
    if reason == "clear":  # spec §4.3: leave the link the next SessionStart(clear) from this claude consumes
        pid = find_pid()
        if pid:
            lineage.write_link(store.root, pid, sid=session.sid, chain_id=facts.chain_id or session.sid)
    return f"session closed ({reason})"
