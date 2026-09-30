"""Filesystem primitives: private dirs, atomic JSON writes, JSONL append/read, locks.

Everything the store writes is private to the user (dirs ``0700``, files
``0600``). Projections are written temp-then-``os.replace`` so a reader never
sees a torn file; they are rebuildable, so they are not fsynced. Logs
are the truth: appended one JSON object per line and fsynced. A reader tolerates
a torn final line (a writer killed mid-append) by skipping it, and the next
append first terminates that fragment so the torn write can't swallow a good one.

Writers never create directories: the store creates them explicitly (the
session directory on first write, a segment directory in ``open_segment``), so
a write into a directory that doesn't exist is an error, not a side effect.

``flock`` is advisory and per open file description: two ``open()`` calls in the
same process contend like two processes do, which is what the tests rely on.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DIR_MODE = 0o700
FILE_MODE = 0o600


def ensure_dir(path: Path) -> Path:
    """Create ``path`` and any missing parents, each ``0700``; return it.

    ``Path.mkdir(parents=True)`` applies ``mode`` to the leaf only, so missing
    ancestors are created one at a time. Directories that already exist are
    left untouched — never chmod something the store didn't create.
    """
    if path.is_dir():
        return path  # the common case: one stat, no ancestor walk
    missing = []
    probe = path
    while not probe.exists():
        missing.append(probe)
        probe = probe.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=DIR_MODE)
        except FileExistsError:
            pass  # created concurrently by another process
    return path


def atomic_write_json(path: Path, obj: object) -> None:
    """Write ``obj`` as pretty JSON to ``path`` atomically, mode ``0600``.

    Atomic for readers, not crash-durable (no ``fsync``) — right for
    projections, which ``rebuild`` regenerates. A file that must survive a
    crash (e.g. export acks) should add a durable variant with its first caller.
    ``path.parent`` must already exist.
    """
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def read_json(path: Path) -> object | None:
    """Parse ``path`` as JSON; ``None`` if it is missing or unparseable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def file_size(path: Path | str | None) -> int:
    """A file's size in bytes; 0 if there is no path or no file."""
    try:
        return os.stat(path).st_size if path else 0
    except OSError:
        return 0


def append_jsonl(path: Path, record: dict, *, durable: bool = True) -> None:
    """Append ``record`` as one line to ``path`` (created ``0600``); fsync it when ``durable``.

    If the file ends mid-line (a previous writer was killed), a newline is
    written first so the fragment stays one skippable line and ``record`` lands
    intact. Short writes are retried until the whole line is on disk. Callers
    that need ordering across several files (the store) serialize under their
    own lock; ``path.parent`` must already exist.

    ``durable=False`` skips the fsync: on slow storage it dominates an append
    (tens of ms on an SD card), and a caller whose records are derivable can
    trade a crash-lost line for that.
    """
    line = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, FILE_MODE)
    try:
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            line = "\n" + line
        view = memoryview(line.encode("utf-8"))
        while view:
            view = view[os.write(fd, view):]
        if durable:
            os.fsync(fd)
    finally:
        os.close(fd)


@dataclass(frozen=True)
class JsonlRead:
    """Result of reading a log: parsed records plus what was skipped."""

    records: list[dict]
    skipped: int
    bytes: int

    @property
    def lines(self) -> int:
        """Non-blank lines read: every one is either a record or a skip."""
        return len(self.records) + self.skipped


def read_jsonl(path: Path) -> JsonlRead:
    """Read every parseable object line from ``path``.

    Lines that are blank, not JSON, or not a JSON object are skipped and counted
    — a torn final line from a killed writer must not make a whole log unreadable.
    A missing file reads as empty.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return JsonlRead(records=[], skipped=0, bytes=0)
    records: list[dict] = []
    skipped = 0
    for chunk in raw.split(b"\n"):
        if not chunk.strip():
            continue
        try:
            obj = json.loads(chunk.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            skipped += 1
            continue
        if isinstance(obj, dict):
            records.append(obj)
        else:
            skipped += 1
    return JsonlRead(records=records, skipped=skipped, bytes=len(raw))


@contextlib.contextmanager
def try_exclusive_lock(path: Path) -> Iterator[bool]:
    """Try to take an exclusive ``flock`` on ``path`` without waiting; yield whether it was taken.

    For single-flight work (one summarizer per segment): a second runner sees
    ``False`` and leaves the work to the first.
    """
    fd = os.open(path, os.O_RDWR | os.O_CREAT, FILE_MODE)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


@contextlib.contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive ``flock`` on ``path`` for the ``with`` body (blocking).

    The lock file's directory must already exist: taking a lock never creates
    directories.
    """
    fd = os.open(path, os.O_RDWR | os.O_CREAT, FILE_MODE)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)
