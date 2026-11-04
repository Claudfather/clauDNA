"""Check and preserve the maintainer interpreter across private HOME/TMP work."""

import os
from pathlib import Path
import shlex
import subprocess
import sys


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
    binary.mkdir()
    launcher = binary / "python3"
    launcher.write_text(f"#!/bin/sh\nexec {shlex.quote(os.path.abspath(sys.executable))} \"$@\"\n")
    launcher.chmod(0o755)
    isolated = dict(env, PATH=str(binary) + os.pathsep + env.get("PATH", os.defpath),
                    PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    for key in ("PYTHONHOME", "PYTHONPATH"):
        isolated.pop(key, None)
    return isolated
