"""clauDNA session store — local, session-id-keyed capture of what a session did.

Design: ``documentation/specs/2026-09-28-session-store-design.md``. The short
version, as it shapes this package:

* **Logs are truth; JSON files are projections.** Every ``.json`` under a
  session directory is rebuildable from the ``.jsonl`` logs beside it
  (:func:`session_store.project.rebuild`).
* **One writer per file.** Callers append events through
  :class:`session_store.store.SessionHandle`; the handle re-projects under the
  session lock right after the append.
* **The directory is the holder.** Segment indexes are derived from the
  ``seg-NNN`` directories on disk, never stored in a counter.

Module map (one concern each):

``paths``    where things live; session-id validation
``fsio``     atomic writes, JSONL append/read, file locks
``events``   the event envelope and the closed kind registry
``project``  pure log → projection folds, plus ``rebuild``
``store``    the write API hooks and readers use
``schema``   a small stdlib JSON Schema subset validator (tests, ``--check``)
``cli``      ``python3 scripts/session_store <verb>``

The core is host-agnostic: nothing here knows about Claude Code hook payloads.
Mapping a host's hook events onto store events is an adapter's job.
"""

STORE_SCHEMA_MAJOR = 1
