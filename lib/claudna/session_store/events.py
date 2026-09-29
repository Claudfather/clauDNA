"""The event envelope and the closed registry of event kinds (spec §6.2).

Every line of every log is one envelope::

    {"v": 1, "ts": "2026-09-28T17:04:05.123Z", "kind": "segment.sealed",
     "sid": "3fbb…", "seg": 2, "data": {...}}

Two sources of truth, each for one thing: ``schemas/event.schema.json`` owns
the *envelope* (``v``, ``ts``, ``sid``, ``seg``, the shape of ``kind``), and the
registry below owns the *kinds* — which exist, which log each belongs to, what
its ``data`` must carry, and how long its free text may be. Where a ``data``
value ends up in a projection (``actor``, ``origin``, offsets, hashes), the
registry constrains it with the projection schema's own fragment, so an event
``make_event`` accepts always projects to something ``check`` accepts.

Writers are strict (:func:`make_event` raises on anything malformed). Readers
are lenient (:func:`classify`): a line from a newer envelope major or an unknown
kind is *skipped*, not an error, so an older reader never breaks on a newer log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from . import schema

ENVELOPE_VERSION = 1

LIFECYCLE = "lifecycle"
ACTIVITY = "activity"

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
    a field to a closed vocabulary; ``caps`` bounds free-text fields (writers
    truncate, readers reject); ``constraints`` maps a field to a JSON Schema
    fragment its value must satisfy. ``seg`` says whether the envelope's ``seg``
    must be set (``True``) or null (``False``).
    """

    log: Literal["lifecycle", "activity"]
    seg: bool
    fields: dict[str, tuple[type, ...]]
    optional: dict[str, tuple[type, ...]] = field(default_factory=dict)
    choices: dict[str, tuple[object, ...]] = field(default_factory=dict)
    caps: dict[str, int] = field(default_factory=dict)
    constraints: dict[str, dict] = field(default_factory=dict)


_SESSION_DEFS = schema.load("session")["$defs"]
_NON_NEGATIVE = {"minimum": 0}
_SHA256 = {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}

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
        constraints={"actor": _SESSION_DEFS["actor_or_null"], "origin": _SESSION_DEFS["origin_or_null"]},
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
        constraints={"start": _NON_NEGATIVE},
    ),
    "segment.sealed": KindSpec(
        log=LIFECYCLE,
        seg=True,
        fields={"end": _INT, "sealed_by": _STR, "trigger": _OPT_STR},
        optional={"sha256": _OPT_STR},
        choices={
            # "compact"/"resume": open_segment sealing an unsealed predecessor (missed PreCompact / lost SessionEnd)
            "sealed_by": ("precompact", "compact", "session_end", "resume"),
            "trigger": ("manual", "auto", None),
        },
        constraints={"end": _NON_NEGATIVE, "sha256": _SHA256},
    ),
    "summary.requested": KindSpec(log=LIFECYCLE, seg=True, fields={"job_id": _STR}),
    "summary.completed": KindSpec(
        log=LIFECYCLE,
        seg=True,
        fields={"job_id": _STR, "artifact": _STR, "input_sha256": _STR, "duration_ms": _INT},
        constraints={"input_sha256": _SHA256, "duration_ms": _NON_NEGATIVE},
    ),
    "summary.failed": KindSpec(
        log=LIFECYCLE,
        seg=True,
        fields={"job_id": _STR, "error": _STR, "retryable": _BOOL},
        caps={"error": 200},
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
        caps={"text": 500},
        constraints={"chars": _NON_NEGATIVE},
    ),
    "skill.invoked": KindSpec(log=ACTIVITY, seg=True, fields={"skill": _STR, "args_chars": _INT},
                              constraints={"args_chars": _NON_NEGATIVE}),
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
        caps={"command": 300, "error": 800},
    ),
    "checkpoint.noted": KindSpec(log=ACTIVITY, seg=True, fields={"note": _STR}, caps={"note": 1000}),
}

def now_ts() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SS.mmmZ``."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


_EVENT_SCHEMA = schema.load("event")


def data_errors(kind: str, data: object) -> list[str]:
    """Problems with ``data`` for a *known* ``kind`` (empty list = valid)."""
    spec = REGISTRY[kind]
    if not isinstance(data, dict):
        return ["data must be an object"]
    errors: list[str] = []
    for key, types in spec.fields.items():
        if key not in data:
            errors.append(f"data.{key} is required")
        elif not schema.is_instance(data[key], types):
            errors.append(f"data.{key} has the wrong type")
    for key, types in spec.optional.items():
        if key in data and not schema.is_instance(data[key], types):
            errors.append(f"data.{key} has the wrong type")
    for key, allowed in spec.choices.items():
        if key in data and data[key] not in allowed:
            errors.append(f"data.{key} must be one of {list(allowed)}")
    for key, cap in spec.caps.items():
        if isinstance(data.get(key), str) and len(data[key]) > cap:
            errors.append(f"data.{key} exceeds {cap} chars")
    for key, fragment in spec.constraints.items():
        if key in data:
            errors.extend(schema.validate(data[key], fragment, path=f"data.{key}"))
    return errors


def envelope_errors(obj: object) -> list[str]:
    """Problems with the envelope itself, independent of kind (``event.schema.json``)."""
    return schema.validate(obj, _EVENT_SCHEMA)


def classify(obj: object) -> Literal["ok", "unknown", "invalid"]:
    """How a reader should treat a log line.

    ``unknown`` — a newer envelope major or an unregistered kind: skip quietly.
    ``invalid`` — malformed: skip and count. ``ok`` — fold it.
    """
    # A newer envelope major is someone else's format: skip it before judging it by ours.
    if isinstance(obj, dict) and schema.is_instance(obj.get("v"), _INT) and obj["v"] != ENVELOPE_VERSION:
        return "unknown"
    if envelope_errors(obj):
        return "invalid"
    assert isinstance(obj, dict)
    if obj["kind"] not in REGISTRY:
        return "unknown"
    spec = REGISTRY[obj["kind"]]
    if spec.seg != (obj["seg"] is not None):
        return "invalid"
    return "invalid" if data_errors(obj["kind"], obj["data"]) else "ok"


def placement_errors(obj: dict, *, sid: str, log: str, seg: int | None) -> list[str]:
    """Problems with *where* an ``ok`` event sits: its log, session, and segment.

    ``log`` is the log the event was read from; ``seg`` is the segment directory
    for an activity log (``None`` for ``lifecycle.jsonl``). A well-formed event
    in the wrong place is still wrong — it must not fold into this projection.
    """
    errors: list[str] = []
    if obj["sid"] != sid:
        errors.append(f"sid {obj['sid']!r} belongs to another session")
    if REGISTRY[obj["kind"]].log != log:
        errors.append(f"{obj['kind']} belongs in the {REGISTRY[obj['kind']].log} log")
    elif log == ACTIVITY and obj["seg"] != seg:
        errors.append(f"seg {obj['seg']} read from segment {seg}'s log")
    return errors


def cap_text(kind: str, data: dict) -> dict:
    """Return a copy of ``data`` with free-text fields truncated to their caps."""
    out = dict(data)
    for key, cap in REGISTRY[kind].caps.items():
        if isinstance(out.get(key), str) and len(out[key]) > cap:
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
