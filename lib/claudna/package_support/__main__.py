"""Directory entry point, safe from an unrelated working directory on Python 3.9.

Use ``python3 -B /absolute/package/lib/claudna/package_support doctor --host codex``.
``-B`` suppresses CPython's pre-entry cache; this flag also protects later imports.
"""

import sys

sys.dont_write_bytecode = True

from pathlib import Path  # noqa: E402

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from claudna.package_support.doctor import main  # noqa: E402

sys.exit(main())
