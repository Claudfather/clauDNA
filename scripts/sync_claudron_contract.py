#!/usr/bin/env python3
"""Refresh (or check) clauDNA's copy of Claudron's machine-readable contract.

``contracts/claudron.json`` is ``claudron contract --json``'s payload, kept
here so clauDNA's mirrors of it (each memory home's sections, the
capabilities harvest gates on, the summary schema's home enum) are checked on
every run of the suite, with no engine installed
(``tests/test_claudron_contract.py``). ``contracts/claudron.ref`` names the
Claudron release the copy was taken from, which clauDNA's contract CI leg
installs (``make deps-contract``) and checks the copy against.

    python3 scripts/sync_claudron_contract.py           # write the installed engine's contract
    python3 scripts/sync_claudron_contract.py --check   # exit 1 if the copy differs from it

Run it after installing the Claudron release you are moving to, set
``contracts/claudron.ref`` to that release's tag, and commit both with
whatever the move changes on this side.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO_ROOT / "contracts" / "claudron.json"


def installed_contract(claudron: str) -> dict:
    """The installed engine's ``contract --json`` payload. Raises ``RuntimeError`` with the reason."""
    try:
        proc = subprocess.run([claudron, "contract", "--json"], capture_output=True, text=True, timeout=30)
        envelope = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError(f"`{claudron} contract --json` failed: {exc}") from exc
    if not (isinstance(envelope, dict) and envelope.get("ok") and envelope.get("command") == "contract"
            and isinstance(envelope.get("data"), dict)):
        raise RuntimeError(f"`{claudron} contract --json` gave no contract (exit {proc.returncode}); "
                           "it needs Claudron 0.9 or later")
    return envelope["data"]


def render(contract: dict) -> str:
    return json.dumps(contract, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare only; exit 1 on a difference")
    parser.add_argument("--claudron", default=os.environ.get("CLAUDNA_CLAUDRON_BIN") or "claudron",
                        help="the claudron binary (default: $CLAUDNA_CLAUDRON_BIN, else claudron on PATH)")
    args = parser.parse_args(argv)
    try:
        text = render(installed_contract(args.claudron))
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.check:
        if SNAPSHOT.is_file() and SNAPSHOT.read_text(encoding="utf-8") == text:
            print(f"ok: {SNAPSHOT.relative_to(REPO_ROOT)} matches the installed engine")
            return 0
        print(f"{SNAPSHOT.relative_to(REPO_ROOT)} differs from the installed engine's contract; "
              "run scripts/sync_claudron_contract.py", file=sys.stderr)
        return 1
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(text, encoding="utf-8")
    print(f"wrote {SNAPSHOT.relative_to(REPO_ROOT)}; set contracts/claudron.ref to the installed release's tag")
    return 0


if __name__ == "__main__":
    sys.exit(main())
