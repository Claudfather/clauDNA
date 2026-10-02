"""The one door to the Claudron engine (``claudron`` CLI): capture, resolve, amend, vault status, promote.

Every call goes through :func:`_run`, which holds the three rules the engine
contract (``skills/_shared/claudron-engine.md`` §2) and this store share:

* **argv, never a shell**: content goes on stdin as JSON, a vault path with
  spaces is one argument;
* **the session's vault, never this process's**: ``$CLAUDRON_VAULT_PATH`` is
  stripped from the child's environment, so whichever session started a run
  can't redirect another's writes (#373 review, B2) — ``--vault`` or the
  session's ``cwd`` decide;
* **the envelope decides**: a JSON object with ``ok``, ``command`` and
  ``data``, checked here, never a reading of prose.

Off the hook path: ``subprocess`` is imported only when a call is made.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

CLAUDRON_ENV = "CLAUDNA_CLAUDRON_BIN"
TIMEOUT_S = 30
CAPTURE_ACTIONS = ("created", "updated", "suggest_update", "suggest_supersede", "rejected")
PROMOTE_ACTIONS = ("promoted", "unchanged")  #: ``unchanged``: the note is already at the target maturity
AMEND_ACTIONS = ("updated", "unchanged", "rejected")


class ClaudronError(RuntimeError):
    """A ``claudron`` call failed outright (not an answer the envelope gives)."""


class CaptureError(ClaudronError):
    """``claudron capture`` failed outright (not a dedup answer)."""


class PromoteError(ClaudronError):
    """``claudron promote`` didn't promote: its error, for the person reviewing."""


def claudron_bin(env: Mapping[str, str]) -> str:
    return env.get(CLAUDRON_ENV) or "claudron"


def _run(args: list[str], env: Mapping[str, str], *, vault: str | None = None, stdin: str | None = None,
         cwd: str | None = None, error: type[ClaudronError] = ClaudronError) -> tuple[int, dict]:
    """``claudron [--vault V] <args>``: ``(exit code, envelope)``; ``error`` unless the reply is a JSON object."""
    import subprocess

    cmd = [claudron_bin(env), *(["--vault", vault] if vault else []), *args]
    child_env = {k: v for k, v in env.items() if k != "CLAUDRON_VAULT_PATH"}
    try:
        proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=TIMEOUT_S, env=child_env,
                              cwd=cwd if cwd and os.path.isdir(cwd) else None)
        envelope = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise error(f"claudron {args[0]}: {str(exc)[:150]}") from exc
    if not isinstance(envelope, dict):
        raise error(f"claudron {args[0]} exited {proc.returncode}: the output is not a JSON object")
    return proc.returncode, envelope


def _data(envelope: dict) -> dict:
    data = envelope.get("data")
    return data if isinstance(data, dict) else {}


def capture(finding: dict, cwd: str | None, env: Mapping[str, str], vault: str | None = None, *,
            run_id: str | None = None) -> dict:
    """One ``claudron capture --stdin --json``: ``{"action", "path", "vault"}``.

    Valid answers are exit 0 + ``ok`` + a known ``data.action``; a ``rejected``
    write exits 1 with a well-formed envelope, which is an answer, not a
    failure. ``capture`` answers ``created``/``updated`` with an absolute path,
    but ``promote`` takes a vault-relative one, so the path is made relative to
    the root Claudron reports (:func:`vault_root`), and that root is returned.
    ``run_id`` rides in the JSON (Claudron ≥ 0.7, ``runs``): the commit carries
    the run's trailer, so ``claudron revert-run`` can undo the whole run.
    """
    code, envelope = _run(["capture", "--stdin", "--json"], env, vault=vault,
                          stdin=json.dumps(_with_run(finding, run_id)), cwd=cwd, error=CaptureError)
    data = _data(envelope)
    action = data.get("action")
    if envelope.get("command") != "capture" or action not in CAPTURE_ACTIONS or \
            ((code != 0 or not envelope.get("ok")) and action != "rejected"):
        raise CaptureError(f"claudron capture exited {code}: {str(envelope.get('errors') or data)[:150]}")
    return {"action": action, **_located(data.get("path"), cwd, vault, env)}


def _with_run(payload: dict, run_id: str | None) -> dict:
    return {**payload, "run_id": run_id} if run_id else payload


def _located(path: object, cwd: str | None, vault: str | None, env: Mapping[str, str]) -> dict:
    """``{"path", "vault"}`` for a write's answer: the path vault-relative, as ``promote`` and ``amend`` take it.

    The root is asked for when the path needs it, or when the session recorded
    no vault: without one, the digest item would carry vault None and
    ``promote`` would resolve against the reviewer's cwd.
    """
    path = path if isinstance(path, str) and path else None
    root = vault_root(cwd, vault, env) if path and (os.path.isabs(path) or not vault) else None
    if root and os.path.isabs(path):
        try:
            path = Path(os.path.realpath(path)).relative_to(root).as_posix()
        except ValueError:
            pass  # outside the vault claudron reports: keep it as given
    return {"path": path, "vault": str(root) if root else vault}


def resolve(names: list[str], *, project: str | None, cwd: str | None, env: Mapping[str, str],
            vault: str | None = None) -> list[dict]:
    """``claudron resolve --name N --alias A ... [--project P] --json``: the candidate subjects, best first.

    Needs ``subject-filing`` (Claudron ≥ 0.7.1): each candidate carries
    ``exact`` (the note *is* one of the names), ``trust``, ``source_type``,
    ``tier`` and ``tags``. ``--project`` keeps one repo's "staging DB" apart
    from another's. Choosing among the candidates is the caller's job.
    """
    # ``--flag=value``: a name the model wrote may start with a dash, and argparse would read it as a flag;
    # ``--alias`` once per name, since ``--aliases`` splits on commas.
    args = ["resolve", f"--name={names[0]}", *(f"--alias={n}" for n in names[1:]), "--limit=10", "--json"]
    if project:
        args.append(f"--project={project}")
    code, envelope = _run(args, env, vault=vault, cwd=cwd, error=CaptureError)
    candidates = _data(envelope).get("candidates")
    if code != 0 or not envelope.get("ok") or envelope.get("command") != "resolve" or not isinstance(candidates, list):
        raise CaptureError(f"claudron resolve exited {code}: {str(envelope.get('errors') or candidates)[:150]}")
    return [c for c in candidates if isinstance(c, dict)]


def amend(request: dict, cwd: str | None, env: Mapping[str, str], vault: str | None = None, *,
          run_id: str | None = None) -> dict:
    """One ``claudron amend --stdin --json``: ``{"action", "reason", "path", "vault"}``.

    ``request`` is ``{note, op, ...}``. ``updated`` wrote; ``unchanged`` is a
    replay (the same fact and evidence). ``rejected`` is Claudron refusing this
    request (exit 2 or 1, with an envelope since 0.7.1: a note that no longer
    reads as ``expect_trust``, text the fact format can't hold), which is an
    answer about this block. Anything else raises :class:`CaptureError`, as a
    failed capture does: harvest stops and keeps the cursor.
    """
    code, envelope = _run(["amend", "--stdin", "--json"], env, vault=vault,
                          stdin=json.dumps(_with_run(request, run_id)), cwd=cwd, error=CaptureError)
    data = _data(envelope)
    action = data.get("action")
    if envelope.get("command") != "amend" or action not in AMEND_ACTIONS or \
            (action != "rejected" and (code != 0 or not envelope.get("ok"))):
        raise CaptureError(f"claudron amend exited {code}: {str(envelope.get('errors') or data)[:150]}")
    return {"action": action, "reason": str(data.get("reason") or "")[:200],
            **_located(data.get("path"), cwd, vault, env)}


@dataclass(frozen=True)
class Status:
    """What ``status --json`` says about one vault: its root and the engine's capabilities."""

    root: Path
    capabilities: frozenset


_STATUS: dict[tuple[str | None, str | None], Status] = {}  #: one ``status`` per vault per run (a short process)


def status(cwd: str | None, vault: str | None, env: Mapping[str, str]) -> Status | None:
    """The vault's :class:`Status` as Claudron itself reports it, or ``None``.

    Vault resolution is Claudron's contract: ask it, with the same
    ``--vault``/``cwd`` the capture used. Only a success is cached: one failed
    call (a timeout, a busy index) mustn't decide the rest of the run. An
    engine older than the capability list reports none, which is the right
    answer for every capability in it (claudron-engine.md §2).
    """
    key = (cwd, vault)
    if key in _STATUS:
        return _STATUS[key]
    try:
        code, envelope = _run(["status", "--json"], env, vault=vault, cwd=cwd)
    except ClaudronError:
        return None
    data = _data(envelope) if code == 0 else {}
    root, caps = data.get("root"), data.get("capabilities")
    if not (isinstance(root, str) and root):
        return None
    _STATUS[key] = Status(Path(os.path.realpath(root)),
                          frozenset(c for c in caps if isinstance(c, str)) if isinstance(caps, list) else frozenset())
    return _STATUS[key]


def vault_root(cwd: str | None, vault: str | None, env: Mapping[str, str]) -> Path | None:
    """The vault root Claudron reports (``status --json``'s ``data.root``), or ``None``."""
    found = status(cwd, vault, env)
    return found.root if found else None


def capabilities(cwd: str | None, vault: str | None, env: Mapping[str, str]) -> frozenset | None:
    """The engine's declared capabilities for this vault: empty for an engine that predates them,
    ``None`` when ``status`` failed (unknown, which is not the same as none)."""
    found = status(cwd, vault, env)
    return found.capabilities if found else None


def promote(item: str, vault: str | None, env: Mapping[str, str]) -> dict:
    """``claudron [--vault V] promote ITEM --to verified --by user --json``: the envelope's data.

    The deterministic half of ``/claudna:capture --review``: the person chose,
    and nothing here is left to a model.
    """
    code, envelope = _run(["promote", item, "--to", "verified", "--by", "user", "--json"], env, vault=vault,
                          error=PromoteError)
    data = _data(envelope)
    if code != 0 or not envelope.get("ok") or envelope.get("command") != "promote" or \
            data.get("action") not in PROMOTE_ACTIONS:
        raise PromoteError(f"claudron promote exited {code}: {str(envelope.get('errors') or data)[:200]}")
    return data
