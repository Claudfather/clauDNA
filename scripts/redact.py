#!/usr/bin/env python3
"""Deterministic credential redactor — the CLI (#548).

The patterns and ``redact_text`` live in ``lib/claudna/redact.py``, the runtime
home the session store imports; this script keeps the path skills call:

    python3 scripts/redact.py <findings-file>    # redact in place
    python3 scripts/redact.py < in > out         # stdin → stdout
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from claudna.redact import MASK, PATTERNS, redact_text  # noqa: E402

__all__ = ["MASK", "PATTERNS", "main", "redact_text"]


def main() -> int:
    """Redact file arguments in place, or stdin → stdout when none are given.

    The in-place file form is the pipe-free invocation the review + subagent
    chains use: they already write findings to disk, so ``python3 redact.py
    <file>`` scrubs credentials without a shell pipe (orchestration-guide §7).
    """
    paths = sys.argv[1:]
    if paths:
        for path in paths:
            target = Path(path)
            target.write_text(redact_text(target.read_text()))
        return 0
    sys.stdout.write(redact_text(sys.stdin.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
