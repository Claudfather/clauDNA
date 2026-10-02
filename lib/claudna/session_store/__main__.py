"""Entry point: ``python3 lib/claudna/session_store <verb>`` (the directory form,
which hooks must use), or ``python3 -m claudna.session_store <verb>`` with ``lib/``
on ``PYTHONPATH`` from this repo only: ``-m`` puts the working directory first on
``sys.path``, so in a user's project a local ``json.py`` would shadow the stdlib
(``lib/CLAUDE.md``).

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
