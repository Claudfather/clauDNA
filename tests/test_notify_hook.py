"""Security invariants for the Notification hook (`notify.sh`).

The hook turns a Claude Code Notification event into a macOS notification via
`osascript`. #259: it read raw stdin and interpolated it, unescaped, into the
AppleScript *code* string — so a `message` containing `"` and a newline could
close the string literal and inject `do shell script`, i.e. arbitrary command
execution. Interpolating the whole raw JSON payload also broke the notification
for ordinary input, since JSON always contains `"`.

These tests never invoke the real `osascript`; a shim on PATH records its argv.
The invariant asserted is the security boundary itself: attacker-controlled
text must reach `osascript` only as a run *argument* (data bound to an AppleScript
variable), never inside an `-e` code fragment.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "plugin-hooks" / "notify.sh"

# A distinctive AppleScript/shell payload. If any of this lands in an `-e`
# code fragment, the string boundary was breached.
INJECTION = 'pwn" \ndo shell script "touch /tmp/claudna_pwned_259"\ndisplay notification "x'


def run_notify(tmp_path: Path, stdin: str) -> list[str]:
    """Run notify.sh with a recording `osascript` shim; return the argv it saw."""
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir(exist_ok=True)
    log = tmp_path / "osascript-argv.txt"
    shim = shim_dir / "osascript"
    # Record each argument NUL-delimited, so an argument that itself contains
    # newlines (the injection payload does) stays a single element.
    shim.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\000" "$a"; done > "$OSA_LOG"\n')
    shim.chmod(0o755)
    env = {"PATH": f"{shim_dir}:/usr/bin:/bin", "OSA_LOG": str(log)}
    subprocess.run(
        ["bash", str(HOOK)], input=stdin, capture_output=True, text=True,
        cwd=tmp_path, env=env, timeout=10,
    )
    if not log.exists():
        return []
    raw = log.read_bytes().decode()
    return raw.split("\0")[:-1]  # trailing empty after the final delimiter


def code_fragments(argv: list[str]) -> list[str]:
    """The strings passed as AppleScript code — the value after each `-e`."""
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-e" and i + 1 < len(argv)]


class TestNotifyDoesNotInjectAppleScript:
    def test_injection_payload_never_reaches_a_code_fragment(self, tmp_path):
        argv = run_notify(tmp_path, json.dumps({"message": INJECTION}))
        joined = "\n".join(code_fragments(argv))
        assert "do shell script" not in joined
        assert "claudna_pwned_259" not in joined

    def test_message_is_passed_as_an_argument_not_code(self, tmp_path):
        argv = run_notify(tmp_path, json.dumps({"message": INJECTION}))
        # The payload must appear somewhere (it is still displayed) — but only
        # in the run-arguments after `--`, never in an `-e` fragment.
        assert INJECTION in argv, "message was dropped entirely"
        assert INJECTION not in code_fragments(argv)


class TestNotifyExtractsTheMessageField:
    def test_only_the_message_field_is_shown_not_raw_json(self, tmp_path):
        argv = run_notify(
            tmp_path,
            json.dumps({"message": "build finished", "session_id": "abc123"}),
        )
        assert "build finished" in argv
        # The raw envelope (session_id, braces) must not be what we display.
        assert not any("session_id" in a for a in argv)

    def test_missing_message_falls_back_to_default(self, tmp_path):
        argv = run_notify(tmp_path, json.dumps({"session_id": "abc123"}))
        assert any("Claude needs your attention" in a for a in argv)

    def test_empty_stdin_falls_back_to_default(self, tmp_path):
        argv = run_notify(tmp_path, "")
        assert any("Claude needs your attention" in a for a in argv)
