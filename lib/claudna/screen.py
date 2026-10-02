"""Screening model-written text for instructions before it is remembered.

A summary can carry an instruction planted in a transcript back as a "fact".
Redaction (``claudna.redact``) masks secrets; this masks instructions. It is
deterministic and deliberately narrow: it flags the shapes an attack takes, not
every imperative, and it can't catch a well-written lie. Where it runs and why:
``documentation/plans/2026-10-01-session-store-hardening.md`` §1.
"""

from __future__ import annotations

import hashlib
import re

#: The text a withheld string is replaced with. Short enough for every schema'd field.
WITHHELD = "[withheld: instruction-like text]"

_F = re.IGNORECASE
#: ``(id, pattern)``. Each id is what a ``summary.screened`` event records; each has its own test.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Text addressed to the model reading it later.
    ("override", re.compile(r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|"
                            r"all|any|your)\b[^.\n]{0,20}\b(instructions?|prompts?|rules?|guidelines?|directions?)\b",
                            _F)),
    ("persona", re.compile(r"\b(you are now|from now on,? you|act as (an?|the) (system|administrator|developer))\b",
                           _F)),
    ("new-instructions", re.compile(r"\b(new|updated|revised|real|actual) (system )?(instructions?|prompt)\s*:", _F)),
    ("to-the-assistant", re.compile(r"\b(assistant|claude|ai|agent|model|llm)\s*[,:]\s*(you must|you should|always|"
                                    r"never|ignore|do not|don't)\b", _F)),
    # Role or prompt-format markers that only appear to impersonate a turn.
    ("role-tag", re.compile(r"<\s*/?\s*(system|assistant|user|instructions?|im_start|im_end)\s*>|<\|[a-z_]+\|>|"
                            r"\[/?INST\]", _F)),
    # Execution an attacker wants: a download piped to a shell, a remote script, decoded payloads.
    ("pipe-to-shell", re.compile(r"\b(curl|wget|iwr|invoke-webrequest)\b[^|\n]{0,200}\|\s*(sudo\s+)?"
                                 r"(ba|z|k|da)?sh\b", _F)),
    ("remote-exec", re.compile(r"\b(run|execute|eval|exec)\b[^.\n]{0,40}\bhttps?://", _F)),
    ("decode-exec", re.compile(r"\bbase64\s+(-d|--decode)\b[^|\n]{0,200}\|\s*(ba|z)?sh\b|"
                               r"\b(iex|invoke-expression)\b", _F)),
    # Moving someone's secrets somewhere (a system *description* — "the client sends the API key to the
    # gateway" — names no owner, so it passes).
    ("exfiltrate", re.compile(r"\b(send|post|upload|exfiltrate|forward|paste)\b[^.\n]{0,30}\b(your|the user'?s|all|"
                              r"every|any)\b[^.\n]{0,20}(\b(tokens?|api[ -]?keys?|secrets?|credentials?|passwords?|"
                              r"ssh keys?)\b|\.env\b)", _F)),
)


def hits(text: str) -> list[str]:
    """The ids of every pattern ``text`` trips (empty when it's clean)."""
    return [name for name, pattern in PATTERNS if pattern.search(text)]


def fingerprint(text: str) -> str:
    """A short hash naming a withheld string without keeping it."""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]


def _walk(value: object, path: str, on_string) -> object:
    """``value`` rebuilt with each string leaf replaced by ``on_string(path, text)``."""
    if isinstance(value, str):
        return on_string(path, value)
    if isinstance(value, dict):
        return {k: _walk(v, f"{path}.{k}" if path else k, on_string) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, f"{path}[{n}]", on_string) for n, v in enumerate(value)]
    return value


def _withhold(value: object, path: str) -> tuple[object, list[dict]]:
    """``value`` with every tripping string replaced by :data:`WITHHELD`, and a finding for each."""
    found: list[dict] = []

    def check(where: str, text: str) -> str:
        names = hits(text)
        if not names:
            return text
        found.append({"kind": "string", "path": where, "patterns": names, "fingerprint": fingerprint(text)})
        return WITHHELD

    return _walk(value, path, check), found


def tripped(value: object) -> list[str]:
    """Pattern ids any string under ``value`` trips (a block, a ledger line): empty when it's clean."""
    return sorted({name for f in _withhold(value, "")[1] for name in f["patterns"]})


def screen_summary(output: dict) -> tuple[dict, list[dict]]:
    """A summary's model output with instructions taken out, and what was taken.

    A block that trips is dropped whole: it is an atomic fact bound for the
    vault, and half of one is worse than none. In the journey and the
    procedures, only the tripping string is replaced. Each finding is
    ``{"kind": "block"|"string", "path", "patterns", "fingerprint"}``, never the text.
    """
    found: list[dict] = []
    blocks = []
    for n, block in enumerate(output.get("blocks") or []):
        _, inside = _withhold(block, f"blocks[{n}]")
        if inside:
            found.append({"kind": "block", "path": f"blocks[{n}]", "fingerprint": inside[0]["fingerprint"],
                          "patterns": sorted({p for f in inside for p in f["patterns"]})})
        else:
            blocks.append(block)
    screened = {**output, "blocks": blocks}
    for part in ("journey", "procedures"):
        if part in output:
            screened[part], withheld = _withhold(output[part], part)
            found += withheld
    return screened, found
