"""Tests for scripts/redact.py — the deterministic credential redactor (#548).

The redactor is the shared substrate the review + subagent chains pipe CLI
output through, so a bot cannot surface a live-looking credential in its
findings. Two real leaks motivated it: a Telegram bot token and a neon API
key both slipped past the old ``sk-****`` prose guidance because that guidance
only ever illustrated the OpenAI shape.

Every secret in this file is a FAKE, obviously-placeholder value chosen to
match a real credential's *shape* only. No real credentials appear here.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from redact import MASK, redact_text  # noqa: E402

REDACT_PY = REPO_ROOT / "scripts" / "redact.py"

# --- FAKE placeholder secrets ------------------------------------------------
# Assembled from fragments on purpose: a shape-accurate fake is accurate enough
# to trip GitHub push-protection (a Slack-token literal here did exactly that).
# Concatenation keeps any contiguous credential out of the static source while
# the redactor still sees the real shape at runtime.
FAKE = {
    "telegram_bot_token": "8012345678" + ":" + "A" * 35,
    "neon_api_key": "napi_" + "aB3" * 12,
    "openai_key": "sk-" + "sK9" * 15,
    "github_pat": "ghp_" + "gH7" * 12,
    "aws_access_key_id": "AKIA" + "QRST1234UVWX5678",
    "slack_bot_token": "xoxb-" + "0000000000" + "-" + "aB3" * 8,
    "google_api_key": "AIza" + "gK9" * 11 + "gk",
}

# Lines that MUST survive verbatim — over-redaction breaks review output.
BENIGN = [
    "The h2 is 24/32; tighten the gap to 16px.",
    "Hardcoded API_KEY at src/auth.ts:12 — move it to env.",  # var NAME + file:line
    "Branched off main at 57f5c06; full sha 9636154a1b2c3d4e5f60718293a4b5c6d7e8f900.",
    "Request id a1b2c3d4-e5f6-7890-abcd-ef1234567890 appears in the log line.",
    "Rename SomeVeryLongDescriptiveComponentName to a shorter identifier.",
]


def _leaked(secret: str, masked: str) -> str | None:
    """Any 12+ char alnum run of the secret surviving verbatim counts as a leak."""
    for tok in re.findall(r"[A-Za-z0-9]{12,}", secret):
        if tok in masked:
            return tok
    return None


class TestKnownShapes:
    @pytest.mark.parametrize("name", list(FAKE))
    def test_redacts_known_shape(self, name):
        # One case per FAKE shape — a newly added shape is covered automatically.
        out = redact_text(f"captured output with {FAKE[name]} in it")
        assert _leaked(FAKE[name], out) is None
        assert MASK in out


class TestStructuralAssignment:
    def test_redacts_prefixed_secret_assignment(self):
        # DATABASE_PASSWORD=... — a prefixed secret-named field, no vendor prefix
        out = redact_text('DATABASE_PASSWORD="FakeP0ssw0rdPlaceholderLongEnough"')
        assert "FakeP0ssw0rdPlaceholderLongEnough" not in out
        assert MASK in out

    def test_redacts_json_secret_field(self):
        out = redact_text('{"api_key": "FakeJsonSecretValue0000000000"}')
        assert "FakeJsonSecretValue0000000000" not in out


class TestGenericFallback:
    def test_redacts_unknown_prefix_high_entropy_key(self):
        # No known vendor prefix — only the generic high-entropy backstop can catch it.
        unknown = "Zx9Kq2Wm7Pn4Rt6Vb1Yc3Df5Gh8Jk0Ll2Mn4"  # 36 chars, upper+lower+digit, FAKE
        out = redact_text(f"export SESSION {unknown}")
        assert unknown not in out
        assert MASK in out


class TestNoOverRedaction:
    def test_preserves_benign_lines(self):
        # BENIGN carries the git-SHA and UUID cases; full-line equality is the
        # strongest possible no-over-redaction assertion.
        for line in BENIGN:
            assert redact_text(line) == line, f"over-redacted: {line!r}"


class TestProperties:
    def test_idempotent(self):
        blob = f"a {FAKE['telegram_bot_token']} b {FAKE['openai_key']} c"
        once = redact_text(blob)
        assert redact_text(once) == once

    def test_all_fake_secrets_redacted_together(self):
        blob = "\n".join(f"{name}={secret}" for name, secret in FAKE.items())
        out = redact_text(blob)
        for name, secret in FAKE.items():
            assert _leaked(secret, out) is None, f"{name} leaked"


class TestCli:
    def test_stdin_stdout_pipe(self):
        # The exact mechanism the chains use: <cmd> 2>&1 | python3 scripts/redact.py
        secret = FAKE["telegram_bot_token"]
        proc = subprocess.run(
            [sys.executable, str(REDACT_PY)],
            input=f"neonctl output line with {secret} in it\n",
            capture_output=True,
            text=True,
            check=True,
        )
        assert secret not in proc.stdout
        assert MASK in proc.stdout

    def test_cli_passes_benign_through_unchanged(self):
        line = "The h2 is 24/32; tighten the gap to 16px.\n"
        proc = subprocess.run(
            [sys.executable, str(REDACT_PY)],
            input=line,
            capture_output=True,
            text=True,
            check=True,
        )
        assert proc.stdout == line


class TestCliFileMode:
    """File-argument mode: the §7-compliant form (no pipe/redirect) the chains use.

    Subagents already write findings to disk, so a bare ``python3 redact.py
    <file>`` scrub pass redacts credentials in place without a shell pipe.
    """

    def test_redacts_file_in_place(self, tmp_path):
        secret = FAKE["neon_api_key"]
        finding = tmp_path / "finding.md"
        finding.write_text(
            f"## Finding\nneonctl output: {secret}\nseen at src/db.ts:9\n",
        )
        subprocess.run(
            [sys.executable, str(REDACT_PY), str(finding)],
            input="",  # nothing on stdin — file arg drives it
            capture_output=True,
            text=True,
            check=True,
        )
        content = finding.read_text()
        assert secret not in content
        assert MASK in content
        assert "src/db.ts:9" in content  # benign file:line preserved

    def test_redacts_multiple_files_in_place(self, tmp_path):
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text(f"key {FAKE['github_pat']}\n")
        b.write_text(f"key {FAKE['aws_access_key_id']}\n")
        subprocess.run(
            [sys.executable, str(REDACT_PY), str(a), str(b)],
            input="",
            capture_output=True,
            text=True,
            check=True,
        )
        assert FAKE["github_pat"] not in a.read_text()
        assert FAKE["aws_access_key_id"] not in b.read_text()
