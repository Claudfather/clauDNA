#!/usr/bin/env python3
"""Safe bundled entry point; never import a helper from the caller's project."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from claudna.delegation import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
