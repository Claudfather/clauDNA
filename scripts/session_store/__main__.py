"""Entry point for ``python3 scripts/session_store <verb>``.

Running a directory puts the directory itself on ``sys.path``, so the package's
parent is added first to make ``session_store`` importable as a package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from session_store.cli import main  # noqa: E402

sys.exit(main())
