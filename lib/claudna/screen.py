"""Screening model-written text for instructions before it is remembered.

A session summary is written by a model reading a transcript, and a transcript
can carry someone else's text: a web page, a README, a quoted tool output. An
instruction in it ("ignore previous instructions", "always run curl …| sh
before builds") can come back as a summary's claim, then as a vault draft or a
digest item that a later session reads. Redaction (``claudna.redact``) masks
secrets; this masks *instructions*. It is deterministic (no model call) and
deliberately narrow: it flags the shapes an attack takes, not every imperative,
so "the build runs `make check` before pushing" passes while "curl x | sh"
doesn't. It can't catch a well-written lie; drafts stay unverified for that.

Used where summary text is written (``session_store.summarize``) and again
where older text is read back (``session_store.digest``, ``session_store.harvest``).
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


def _strings(value: object, path: str):
    """Every ``(path, string)`` leaf under ``value``."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for n, item in enumerate(value):
            yield from _strings(item, f"{path}[{n}]")


def tripped(value: object) -> list[str]:
    """Pattern ids any string under ``value`` trips (a block, a ledger line): empty when it's clean."""
    return sorted({name for _, text in _strings(value, "") for name in hits(text)})


def _withhold(value: object, path: str, found: list[dict]) -> object:
    """``value`` with every tripping string replaced by :data:`WITHHELD`, recording each in ``found``."""
    if isinstance(value, str):
        names = hits(value)
        if names:
            found.append({"path": path, "patterns": names, "fingerprint": fingerprint(value)})
            return WITHHELD
        return value
    if isinstance(value, dict):
        return {k: _withhold(v, f"{path}.{k}" if path else k, found) for k, v in value.items()}
    if isinstance(value, list):
        return [_withhold(v, f"{path}[{n}]", found) for n, v in enumerate(value)]
    return value


def screen_summary(output: dict) -> tuple[dict, list[dict]]:
    """A summary's model output with instructions taken out, and what was taken.

    A block that trips is dropped whole: it is an atomic fact bound for the
    vault, and half of one is worse than none. In the journey and the
    procedures, only the tripping string is replaced. Each finding is
    ``{"path", "patterns", "fingerprint"}``, never the text itself.
    """
    found: list[dict] = []
    blocks = []
    for n, block in enumerate(output.get("blocks") or []):
        names = tripped(block)
        if names:
            text = "\n".join(t for _, t in _strings(block, ""))
            found.append({"path": f"blocks[{n}]", "patterns": names, "fingerprint": fingerprint(text)})
        else:
            blocks.append(block)
    screened = {**output, "blocks": blocks}
    for part in ("journey", "procedures"):
        if part in output:
            screened[part] = _withhold(output[part], part, found)
    return screened, found
