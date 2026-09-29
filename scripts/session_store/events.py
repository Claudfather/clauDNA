"""The event envelope and the closed registry of event kinds (spec §6.2).

Every line of every log is one envelope::

    {"v": 1, "ts": "2026-09-28T17:04:05.123Z", "kind": "segment.sealed",
     "sid": "3fbb…", "seg": 2, "data": {...}}

The registry below is the single source of truth for which kinds exist, which
log each belongs to, and what its ``data`` must carry. ``event.schema.json``
mirrors the kind list; a test fails if the two drift.

Writers are strict (:func:`make_event` raises on anything malformed). Readers
are lenient (:func:`classify`): a line from a newer envelope major or an unknown
kind is *skipped*, not an error, so an older reader never breaks on a newer log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

ENVELOPE_VERSION = 1

LIFECYCLE = "lifecycle"
ACTIVITY = "activity"

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
_KIND_RE = re.compile(r"^[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*$")

_STR = (str,)
_OPT_STR = (str, type(None))
_INT = (int,)
_OPT_INT = (int, type(None))
_BOOL = (bool,)
_DICT = (dict,)


class EventError(ValueError):
    """A writer tried to build an event that violates the registry."""


@dataclass(frozen=True)
class KindSpec:
    """What one event kind requires.

    ``fields`` maps each required ``data`` key to the Python types it may hold;
    ``optional`` does the same for keys that may be absent. ``choices`` narrows
    a field to a closed vocabulary. ``seg`` says whether the envelope's ``seg``
    must be set (``True``), must be null (``False``).
    """

    log: Literal["lifecycle", "activity"]
    seg: bool
    fields: dict[str, tuple[type, ...]]
    optional: dict[str, tuple[type, ...]] = field(default_factory=dict)
    choices: dict[str, tuple[object, ...]] = field(default_factory=dict)


REGISTRY: dict[str, KindSpec] = {
    # ── lifecycle.jsonl: session scope ──────────────────────────────────────
    "session.opened": KindSpec(
        log=LIFECYCLE,
        seg=False,
        fields={
            "source": _STR,
            "parent_sid": _OPT_STR,
            "chain_id": _STR,
            "actor": _DICT,
            "origin": _DICT,
            "transcript_path": _OPT_STR,
        },
        choices={"source": ("startup", "clear", "resume")},
    ),
    "session.child_linked": KindSpec(log=LIFECYCLE, seg=False, fields={"child_sid": _STR}),
    "session.privacy_set": KindSpec(
        log=LIFECYCLE,
        seg=False,
        fields={"private": _BOOL, "by": _STR},
        choices={"by": ("user", "policy")},
    ),
    "session.closed": KindSpec(
        log=LIFECYCLE,
        seg=False,
        fields={"reason": _STR},
        choices={"reason": ("clear", "resume", "logout", "prompt_input_exit", "other")},
    ),
    # ── lifecycle.jsonl: segment boundaries and summary jobs ────────────────
    "segment.opened": KindSpec(
        log=LIFECYCLE,
        seg=True,
        fields={"opened_by": _STR, "start": _INT},
        choices={"opened_by": ("session_open", "compact")},
    ),
    "segment.sealed": KindSpec(
        log=LIFECYCLE,
        seg=True,
        fields={"end": _INT, "sealed_by": _STR, "trigger": _OPT_STR},
        optional={"sha256": _OPT_STR},
        choices={
            "sealed_by": ("precompact", "compact", "session_end"),
            "trigger": ("manual", "auto", None),
        },
    ),
    "summary.requested": KindSpec(log=LIFECYCLE, seg=True, fields={"job_id": _STR}),
    "summary.completed": KindSpec(
        log=LIFECYCLE,
        seg=True,
        fields={"job_id": _STR, "artifact": _STR, "input_sha256": _STR, "duration_ms": _INT},
    ),
    "summary.failed": KindSpec(
        log=LIFECYCLE,
        seg=True,
        fields={"job_id": _STR, "error": _STR, "retryable": _BOOL},
    ),
    "summary.skipped": KindSpec(
        log=LIFECYCLE,
        seg=True,
        fields={"reason": _STR},
        choices={"reason": ("private", "disabled", "trivial", "headless")},
    ),
    # ── seg-NNN/events.jsonl: in-segment activity ───────────────────────────
    "prompt.submitted": KindSpec(
        log=ACTIVITY,
        seg=True,
        fields={"prompt_id": _OPT_STR, "chars": _INT},
        optional={"text": _OPT_STR},
    ),
    "skill.invoked": KindSpec(log=ACTIVITY, seg=True, fields={"skill": _STR, "args_chars": _INT}),
    "tool.failed": KindSpec(
        log=ACTIVITY,
        seg=True,
        fields={
            "tool": _STR,
            "signature": _STR,
            "exit_code": _OPT_INT,
            "command": _OPT_STR,
            "error": _OPT_STR,
        },
    ),
    "checkpoint.noted": KindSpec(log=ACTIVITY, seg=True, fields={"note": _STR}),
}

#: Free-text caps (spec §6.2). Writers truncate to these before building events.
TEXT_CAPS: dict[tuple[str, str], int] = {
    ("prompt.submitted", "text"): 500,
    ("tool.failed", "command"): 300,
    ("tool.failed", "error"): 800,
    ("checkpoint.noted", "note"): 1000,
    ("summary.failed", "error"): 200,
}


def now_ts() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SS.mmmZ``."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _type_ok(value: object, types: tuple[type, ...]) -> bool:
    # bool is a subclass of int; an int field must not accept True/False.
    if isinstance(value, bool) and bool not in types:
        return False
    return isinstance(value, types)


def data_errors(kind: str, data: object) -> list[str]:
    """Problems with ``data`` for a *known* ``kind`` (empty list = valid)."""
    spec = REGISTRY[kind]
    if not isinstance(data, dict):
        return ["data must be an object"]
    errors: list[str] = []
    for key, types in spec.fields.items():
        if key not in data:
            errors.append(f"data.{key} is required")
        elif not _type_ok(data[key], types):
            errors.append(f"data.{key} has the wrong type")
    for key, types in spec.optional.items():
        if key in data and not _type_ok(data[key], types):
            errors.append(f"data.{key} has the wrong type")
    for key, allowed in spec.choices.items():
        if key in data and data[key] not in allowed:
            errors.append(f"data.{key} must be one of {list(allowed)}")
    for (cap_kind, key), cap in TEXT_CAPS.items():
        if cap_kind == kind and isinstance(data.get(key), str) and len(data[key]) > cap:
            errors.append(f"data.{key} exceeds {cap} chars")
    return errors


def envelope_errors(obj: object) -> list[str]:
    """Problems with the envelope itself, independent of kind."""
    if not isinstance(obj, dict):
        return ["event must be an object"]
    errors: list[str] = []
    if not _type_ok(obj.get("v"), _INT):
        errors.append("v must be an int")
    if not isinstance(obj.get("ts"), str) or not _TS_RE.match(obj["ts"]):
        errors.append("ts must be RFC 3339 UTC with milliseconds")
    if not isinstance(obj.get("kind"), str) or not _KIND_RE.match(obj["kind"]):
        errors.append("kind must look like noun.verb")
    if not isinstance(obj.get("sid"), str) or not obj["sid"]:
        errors.append("sid must be a non-empty string")
    seg = obj.get("seg")
    if seg is not None and (not _type_ok(seg, _INT) or seg < 1):
        errors.append("seg must be null or an int >= 1")
    if not isinstance(obj.get("data"), dict):
        errors.append("data must be an object")
    return errors


def classify(obj: object) -> Literal["ok", "unknown", "invalid"]:
    """How a reader should treat a log line.

    ``unknown`` — a newer envelope major or an unregistered kind: skip quietly.
    ``invalid`` — malformed: skip and count. ``ok`` — fold it.
    """
    if envelope_errors(obj):
        return "invalid"
    assert isinstance(obj, dict)
    if obj["v"] != ENVELOPE_VERSION or obj["kind"] not in REGISTRY:
        return "unknown"
    spec = REGISTRY[obj["kind"]]
    if spec.seg != (obj["seg"] is not None):
        return "invalid"
    return "invalid" if data_errors(obj["kind"], obj["data"]) else "ok"


def cap_text(kind: str, data: dict) -> dict:
    """Return a copy of ``data`` with free-text fields truncated to their caps."""
    out = dict(data)
    for (cap_kind, key), cap in TEXT_CAPS.items():
        if cap_kind == kind and isinstance(out.get(key), str) and len(out[key]) > cap:
            out[key] = out[key][: cap - 1] + "…"
    return out


def make_event(kind: str, sid: str, data: dict, *, seg: int | None = None, ts: str | None = None) -> dict:
    """Build a valid envelope, or raise :class:`EventError`.

    Free text is capped first (:func:`cap_text`), so callers never have to.
    """
    if kind not in REGISTRY:
        raise EventError(f"unknown event kind: {kind}")
    spec = REGISTRY[kind]
    if spec.seg and seg is None:
        raise EventError(f"{kind} requires a segment index")
    if not spec.seg and seg is not None:
        raise EventError(f"{kind} is session-scope; seg must be None")
    event = {"v": ENVELOPE_VERSION, "ts": ts or now_ts(), "kind": kind, "sid": sid, "seg": seg,
             "data": cap_text(kind, data)}
    problems = envelope_errors(event) + data_errors(kind, event["data"])
    if problems:
        raise EventError(f"{kind}: " + "; ".join(problems))
    return event
