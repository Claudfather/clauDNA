"""Entry point: ``python3 -m claudna.session_store <verb>`` (preferred, ``lib/`` on
``PYTHONPATH``) or ``python3 lib/claudna/session_store <verb>``.

Running the package directory directly puts that directory itself on
``sys.path``, so the import root (``lib/``) is added first. This is the only
``sys.path`` manipulation in the runtime: library modules never do it.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from claudna.session_store.cli import main  # noqa: E402

sys.exit(main())
