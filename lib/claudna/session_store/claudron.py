"""The one door to the Claudron engine (``claudron`` CLI): capture, vault resolution, promote.

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
from pathlib import Path
from typing import Mapping

CLAUDRON_ENV = "CLAUDNA_CLAUDRON_BIN"
TIMEOUT_S = 30
CAPTURE_ACTIONS = ("created", "updated", "suggest_update", "suggest_supersede", "rejected")
PROMOTE_ACTIONS = ("promoted", "unchanged")  #: ``unchanged``: the note is already at the target maturity


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


def capture(finding: dict, cwd: str | None, env: Mapping[str, str], vault: str | None = None) -> dict:
    """One ``claudron capture --stdin --json``: ``{"action", "path", "vault"}``.

    Valid answers are exit 0 + ``ok`` + a known ``data.action``; a ``rejected``
    write exits 1 with a well-formed envelope, which is an answer, not a
    failure. ``capture`` answers ``created``/``updated`` with an absolute path,
    but ``promote`` takes a vault-relative one, so the path is made relative to
    the root Claudron reports (:func:`vault_root`), and that root is returned.
    """
    code, envelope = _run(["capture", "--stdin", "--json"], env, vault=vault, stdin=json.dumps(finding), cwd=cwd,
                          error=CaptureError)
    data = _data(envelope)
    action = data.get("action")
    if envelope.get("command") != "capture" or action not in CAPTURE_ACTIONS or \
            ((code != 0 or not envelope.get("ok")) and action != "rejected"):
        raise CaptureError(f"claudron capture exited {code}: {str(envelope.get('errors') or data)[:150]}")
    path = data.get("path") if isinstance(data.get("path"), str) and data.get("path") else None
    # The root is asked for when the path needs it, or when the session recorded no vault: without one,
    # the digest item would carry vault None and `promote` would resolve against the reviewer's cwd.
    root = vault_root(cwd, vault, env) if path and (os.path.isabs(path) or not vault) else None
    if root and os.path.isabs(path):
        try:
            path = Path(os.path.realpath(path)).relative_to(root).as_posix()
        except ValueError:
            pass  # outside the vault claudron reports: keep it as given
    return {"action": action, "path": path, "vault": str(root) if root else vault}


_ROOTS: dict[tuple[str | None, str | None], Path] = {}  #: one ``status`` per vault per run (a short process)


def vault_root(cwd: str | None, vault: str | None, env: Mapping[str, str]) -> Path | None:
    """The vault root Claudron itself reports (``status --json``'s ``data.root``), or ``None``.

    Vault resolution is Claudron's contract: ask it, with the same
    ``--vault``/``cwd`` the capture used. Only a success is cached: one failed
    call (a timeout, a busy index) mustn't decide the rest of the run.
    """
    key = (cwd, vault)
    if key in _ROOTS:
        return _ROOTS[key]
    try:
        code, envelope = _run(["status", "--json"], env, vault=vault, cwd=cwd)
    except ClaudronError:
        return None
    root = _data(envelope).get("root") if code == 0 else None
    if not (isinstance(root, str) and root):
        return None
    _ROOTS[key] = Path(os.path.realpath(root))
    return _ROOTS[key]


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
