"""Check and preserve the maintainer interpreter across private HOME/TMP work."""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from claudna.session_store.fsio import allocate_operation, ensure_dir  # noqa: E402
from claudna.session_store.paths import validate_scratch_label, validate_sid  # noqa: E402
from claudna.session_store.store import SessionStore, owned_session  # noqa: E402


class ToolchainError(ValueError):
    """Required development modules are unavailable to the isolated interpreter."""


def ensure_toolchain() -> str:
    # Preserve the venv executable path: resolving its symlink can select the
    # base interpreter and lose the very dependencies this probe verified.
    interpreter = os.path.abspath(sys.executable)
    probe = subprocess.run([interpreter, "-I", "-B", "-c", "import yaml; import ruff; import pytest"],
                           capture_output=True, text=True)
    if probe.returncode:
        raise ToolchainError(
            f"Release toolchain unavailable in isolated interpreter {interpreter}. "
            "PyYAML, ruff and pytest must be installed outside the user site/PYTHONPATH.\n"
            "Create and activate a virtual environment, then install the pinned toolchain:\n"
            "  python3.12 -m venv .venv\n  . .venv/bin/activate\n  make deps\n"
            "Re-run the release command with that environment active."
        )
    return interpreter


def isolated_python_env(directory: Path, env: dict) -> dict:
    # A shell shim preserves the selected venv; a symlink in this private bin
    # can instead change Python's pyvenv.cfg discovery. Make owns the commands.
    binary = directory / "bin"
    binary.mkdir(mode=0o700)
    launcher = binary / "python3"
    launcher.write_text(f"#!/bin/sh\nexec {shlex.quote(os.path.abspath(sys.executable))} \"$@\"\n")
    launcher.chmod(0o700)
    isolated = dict(env, PATH=str(binary) + os.pathsep + env.get("PATH", os.defpath),
                    PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    for key in ("PYTHONHOME", "PYTHONPATH"):
        isolated.pop(key, None)
    return isolated


@dataclass(frozen=True)
class MaintainerPaths:
    """A typed native or standalone owner, never an inferred replacement identity."""

    kind: str
    owner_id: str
    provider: str | None
    directory: Path

    @property
    def scratch(self) -> Path:
        return self.directory / "scratch"

    @property
    def artifacts(self) -> Path:
        return self.directory / "artifacts"


def maintainer_paths(label: str, *, session: str | None = None, host: str | None = None,
                     standalone: bool = False) -> MaintainerPaths:
    """Select explicitly authorized maintainer storage through the existing store.

    Host workflows must supply their real native context. --standalone permits
    an operation only outside native workflows; malformed available identities
    never fall through to an operation. Profile HOME/TMP overrides belong to
    children after this selection and cannot replace its effective state root.
    """
    validate_scratch_label(label)
    if (session is None) != (host is None):
        raise ValueError("native session and host must be supplied together")
    present = {}
    for provider, keys in (("claude", ("CLAUDE_SESSION_ID",)),
                           ("codex", ("CODEX_THREAD_ID", "CODEX_SESSION_ID"))):
        values = [validate_sid(os.environ[key]) for key in keys if key in os.environ]
        if values:
            if len(set(values)) != 1:
                raise ValueError("conflicting native session aliases")
            present[provider] = values[0]
    if len(present) > 1:
        raise ValueError("conflicting native providers")
    if present:
        provider, sid = next(iter(present.items()))
        if session is not None and (session != sid or host != provider):
            raise ValueError("explicit native owner conflicts with current context")
        session, host = sid, provider
    store = SessionStore()
    if session is None:
        if not standalone:
            raise ValueError("native identity required; outside host workflows explicitly pass --standalone")
        operations = store.root / "operations"
        if operations.resolve() != store.root.resolve() / "operations":
            raise ValueError("operation parent redirects outside its owned path")
        directory = allocate_operation(store.root, label=label)
        return MaintainerPaths("operation", directory.name, None, directory)
    validate_sid(session)
    directory = store.session(session).paths.dir
    if directory.resolve() != store.root.resolve() / "sessions" / session:
        raise ValueError("native directory redirects outside its owned path")
    owned_session(store, session, host)
    for name in ("scratch", "artifacts"):
        if (directory / name).resolve() != directory.resolve() / name:
            raise ValueError("native output directory redirects outside its owned path")
    ensure_dir(directory / "scratch")
    ensure_dir(directory / "artifacts")
    return MaintainerPaths("session", session, host, directory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit maintainer owner allocation")
    parser.add_argument("verb", choices=("owner-dir",))
    parser.add_argument("--label", required=True)
    parser.add_argument("--session")
    parser.add_argument("--host", choices=("claude", "codex", "cursor"))
    parser.add_argument("--standalone", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        owner = maintainer_paths(args.label, session=args.session, host=args.host, standalone=args.standalone)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"maintainer ownership unavailable: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"kind": owner.kind, "owner_id": owner.owner_id, "provider": owner.provider,
                          "directory": str(owner.directory), "scratch": str(owner.scratch),
                          "artifacts": str(owner.artifacts)}))
    else:
        print(owner.directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
