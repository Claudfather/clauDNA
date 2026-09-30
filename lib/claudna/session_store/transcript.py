"""Read a segment's slice of a Claude Code transcript as conversation prose (spec §7.1).

A transcript is JSONL written by Claude Code; the store's segment ranges are
byte offsets into it. :func:`read_range` returns the user and assistant prose in
``[start, end)``, which is what the summarizer sees. Everything else is dropped:

* tool calls and tool results (the summarizer works from what was said, and
  tool output is where secrets and bulk live);
* thinking blocks, sidechains (subagent turns), and meta records;
* context Claude Code or a hook injected into a user turn (``<system-reminder>``
  blocks, slash-command wrappers) — it is not what the user said;
* ``!cmd`` shell input and output (``<bash-input>`` / ``<bash-stdout>`` /
  ``<bash-stderr>``), which Claude Code records as user-role text: it is tool
  output, where ``cat .env`` lands.

Partial lines at either edge of the range are skipped, and a record that isn't
understood is skipped rather than fatal: the transcript format is Claude Code's,
not ours, and it changes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_INJECTED = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|local-command-stdout|"
    r"local-command-stderr|user-prompt-submit-hook|bash-input|bash-stdout|bash-stderr)>.*?</\1>",
    re.DOTALL,
)


@dataclass(frozen=True)
class Turn:
    role: str  # "user" | "assistant"
    text: str


def _text_blocks(content: object) -> list[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [b["text"] for b in content
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)]


def turn_of(record: object) -> Turn | None:
    """The prose one transcript record contributes, or ``None``."""
    if not isinstance(record, dict) or record.get("type") not in ("user", "assistant"):
        return None
    if record.get("isSidechain") or record.get("isMeta") or record.get("isCompactSummary"):
        return None
    message = record.get("message")
    if not isinstance(message, dict) or message.get("role") != record["type"]:
        return None
    text = "\n".join(_text_blocks(message.get("content")))
    if record["type"] == "user":
        text = _INJECTED.sub("", text)
    text = text.strip()
    return Turn(record["type"], text) if text else None


def read_range(path: Path, start: int, end: int | None) -> list[Turn]:
    """The prose turns whose lines lie wholly inside ``[start, end)`` of ``path``.

    Streams line by line up to ``end`` (a segment can be many MB), and only
    parses lines that can carry prose: a user or assistant record. Raises
    ``FileNotFoundError`` when the transcript is gone (Claude Code deletes old
    ones); the caller records that as a skip.
    """
    turns = []
    with open(path, "rb") as fh:
        pos = start
        if start > 0:
            fh.seek(start - 1)
            if fh.read(1) != b"\n":  # the range starts mid-line: skip that line's tail
                pos += len(fh.readline())
        fh.seek(pos)
        for line in fh:
            pos += len(line)
            if (end is not None and pos > end) or not line.endswith(b"\n"):
                break  # a line the range cuts, or one still being written
            if b'"type":"user"' not in line and b'"type":"assistant"' not in line and \
                    b'"type": "user"' not in line and b'"type": "assistant"' not in line:
                continue
            try:
                turn = turn_of(json.loads(line))
            except (ValueError, UnicodeDecodeError):
                continue
            if turn is not None:
                turns.append(turn)
    return turns


def render(turns: list[Turn], *, limit: int) -> str:
    """Turns as a plain-text dialogue, keeping the most recent ``limit`` characters."""
    text = "\n\n".join(f"[{t.role}]\n{t.text}" for t in turns)
    return text if len(text) <= limit else "[…earlier turns cut…]\n" + text[-limit:]
