"""Payload-parse invariants for the auto-format hook (`auto-format.sh`).

The hook is wired `PostToolUse` on `Write|Edit` and mutates the file Claude just
wrote. #324: it resolved its target with `grep -o '"file_path":"[^"]*"'`, a
pattern that requires *compact* JSON. Against a pretty-printed payload the match
fails, `FILE_PATH` is empty, and the hook exits 0 having formatted nothing — no
error, no log, no exit code.

The payload comes from an external producer. Its whitespace was measured compact
on `claude 2.1.240` (Linux, interactive and headless arms, literal captured
stdin), which is why the defect was latent rather than live — but nothing
contracts that shape, and a producer that starts pretty-printing switches this
hook off silently. **That measurement expires with the binary**; these tests
exist so the hook does not depend on it either way.

The invariant asserted is therefore: *the target path resolves from the payload
regardless of its whitespace, and a payload the hook cannot parse is loud.*

These tests never invoke the real `ruff`; a shim on PATH records its argv. PATH
is hermetic — the tools the hook needs are symlinked in — so the no-`jq` arm can
drop `jq` alone rather than dropping `/usr/bin` and taking `grep` and `sed` with
it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "plugin-hooks" / "auto-format.sh"

# Everything the hook's resolution ladder needs that is not a bash builtin and
# not `jq`. `bash` is included because a hermetic PATH is also the PATH the
# interpreter is looked up on.
_BASE_TOOLS = ("bash", "cat", "grep", "head", "cut")

_RECORD_SEP = "\x1e"


def _payload(file_path: str, *, tool: str = "Write", content: str = "x = 1\n") -> dict:
    """A PostToolUse payload with the top-level keys the real one carries.

    Key set captured from `claude 2.1.240`. The extra keys are not decoration:
    they are what makes an unanchored pattern able to match more than once.
    """
    tool_input = {"file_path": file_path}
    if tool == "Write":
        tool_input["content"] = content
    else:
        tool_input.update({"old_string": "a", "new_string": content, "replace_all": False})
    return {
        "session_id": "s-1",
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/tmp",
        "permission_mode": "acceptEdits",
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_use_id": "tu-1",
        "tool_input": tool_input,
        "tool_response": {"filePath": file_path, "type": "create"},
        "duration_ms": 3,
    }


def compact(payload: dict) -> str:
    """The measured production shape: no whitespace between tokens."""
    return json.dumps(payload, separators=(",", ":"))


def pretty(payload: dict) -> str:
    """Pretty-printed — `"file_path": "..."`. The shape that killed the old parse."""
    return json.dumps(payload, indent=2)


def spaced_separator(payload: dict) -> str:
    """`"file_path" : "..."` — whitespace BEFORE the colon as well as after.

    Not a shape any producer here has been observed to emit. It is here because
    the fallback pattern claims to tolerate whitespace on *both* sides, and a
    pattern anchored as `'"file_path":[[:space:]]*"'` — the obvious half-fix,
    and the one proposed on #262 — passes every `pretty` case above while
    failing this one. Without this arm that distinction is unpinned.
    """
    return json.dumps(payload, separators=(", ", " : "))


SERIALIZERS = pytest.mark.parametrize(
    "serialize",
    [compact, pretty, spaced_separator],
    ids=["compact", "pretty", "spaced-separator"],
)
JQ_ARMS = pytest.mark.parametrize("with_jq", [True, False], ids=["with-jq", "without-jq"])


def _bin_dir(tmp_path: Path, *, with_jq: bool) -> Path:
    d = tmp_path / ("bin-jq" if with_jq else "bin-nojq")
    d.mkdir(exist_ok=True)
    for name in (*_BASE_TOOLS, *(("jq",) if with_jq else ())):
        real = shutil.which(name)
        if real is None:
            pytest.skip(f"{name} is not available on this host")
        link = d / name
        if not link.exists():
            link.symlink_to(real)
    return d


def run_hook(tmp_path: Path, stdin: str, *, with_jq: bool = True):
    """Run the real hook with a recording `ruff` shim.

    Returns `(returncode, stderr, calls)` where `calls` is one argv list per
    `ruff` invocation.
    """
    d = _bin_dir(tmp_path, with_jq=with_jq)
    log = tmp_path / "ruff-argv.txt"
    shim = d / "ruff"
    # NUL-delimit each argument so a path containing whitespace stays one
    # element; RS-delimit each invocation so two calls stay two calls.
    shim.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do printf "%s\\000" "$a"; done >> "$RUFF_LOG"\n'
        'printf "\\036" >> "$RUFF_LOG"\n'
    )
    shim.chmod(0o755)
    proc = subprocess.run(
        [str(d / "bash"), str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": str(d), "RUFF_LOG": str(log)},
        timeout=30,
    )
    calls = []
    if log.exists():
        for record in log.read_text().split(_RECORD_SEP):
            if record:
                calls.append(record.split("\0")[:-1])
    return proc.returncode, proc.stderr, calls


def targets(calls: list[list[str]]) -> list[str]:
    """The final argument of each `ruff` invocation — the file it was pointed at."""
    return [c[-1] for c in calls if c]


class TestPathResolvesRegardlessOfPayloadWhitespace:
    """#324: the target must not depend on the producer's formatting choices."""

    @SERIALIZERS
    @JQ_ARMS
    @pytest.mark.parametrize(
        ("tool", "rel"),
        [("Write", "mod.py"), ("Edit", "mod.py"), ("Write", "a dir/my mod.py")],
        ids=["write", "edit", "path-with-spaces"],
    )
    def test_the_target_resolves(self, tmp_path, serialize, with_jq, tool, rel):
        # The third case is not decoration: a pattern made whitespace-tolerant
        # around the colon must still tolerate whitespace inside the VALUE.
        target = str(tmp_path / rel)
        rc, err, calls = run_hook(
            tmp_path, serialize(_payload(target, tool=tool)), with_jq=with_jq
        )
        assert rc == 0, f"hook failed: {err}"
        assert targets(calls) == [target, target], (
            f"expected `ruff format` and `ruff check --fix` on {target}, got {calls}"
        )


class TestTheTargetIsTheToolInputPathNeverFileContent:
    """The pattern is unanchored, so `tool_input.content` is adjacent to it.

    JSON escaping is what closes the content route: content reaches the payload
    as `\\"file_path\\":\\"`, which the pattern cannot match. Pinned because that
    protection is incidental to the escaping rather than stated by the pattern.

    A second `file_path` *key* is the route escaping does not close, and it is
    the same class of producer change this whole fix is about — `tool_response`
    echoes the path today as camelCase `filePath`, which is not a contract
    either. `head -1` is what keeps the fallback rung single-valued there.
    """

    @SERIALIZERS
    @JQ_ARMS
    def test_a_decoy_in_the_written_content_is_not_formatted(self, tmp_path, serialize, with_jq):
        target = str(tmp_path / "fixture.py")
        decoy = "/tmp/decoy-324.py"
        rc, err, calls = run_hook(
            tmp_path,
            serialize(_payload(target, content='FIXTURE = \'{"file_path":"%s"}\'\n' % decoy)),
            with_jq=with_jq,
        )
        assert rc == 0, f"hook failed: {err}"
        assert targets(calls) == [target, target]
        assert decoy not in "".join(sum(calls, [])), "content chose the formatter's target"

    @SERIALIZERS
    @JQ_ARMS
    def test_a_second_file_path_key_does_not_produce_a_two_line_target(
        self, tmp_path, serialize, with_jq
    ):
        # Simulates the producer renaming `tool_response.filePath` to snake_case.
        # Unanchored matching then finds two keys, and without `head -1` the
        # fallback rung yields a two-line value that points at no file at all.
        target = str(tmp_path / "mod.py")
        payload = _payload(target)
        payload["tool_response"]["file_path"] = str(tmp_path / "echoed.py")
        rc, err, calls = run_hook(tmp_path, serialize(payload), with_jq=with_jq)
        assert rc == 0, f"hook failed: {err}"
        assert targets(calls) == [target, target], (
            f"expected a single-valued target from tool_input, got {calls}"
        )


class TestAnUnparseablePayloadIsLoud:
    """The defect was silence. A payload that yields no path must say so."""

    @JQ_ARMS
    @pytest.mark.parametrize(
        "stdin",
        [json.dumps({"hook_event_name": "PostToolUse"}), "{not json at all"],
        ids=["no-file-path-key", "malformed-json"],
    )
    def test_a_payload_that_yields_no_path_is_loud(self, tmp_path, stdin, with_jq):
        rc, err, calls = run_hook(tmp_path, stdin, with_jq=with_jq)
        assert rc != 0, "a payload the hook cannot parse must not exit 0"
        assert "file_path" in err
        assert calls == [], "nothing should have been formatted"

    @JQ_ARMS
    def test_empty_stdin_is_silent_and_successful(self, tmp_path, with_jq):
        # No event is not a parse failure — the hook has nothing to act on.
        rc, err, calls = run_hook(tmp_path, "", with_jq=with_jq)
        assert rc == 0
        assert err == ""
        assert calls == []


class TestExtensionDispatch:
    @SERIALIZERS
    def test_a_non_python_target_does_not_reach_ruff(self, tmp_path, serialize):
        rc, err, calls = run_hook(tmp_path, serialize(_payload(str(tmp_path / "notes.txt"))))
        assert rc == 0, f"hook failed: {err}"
        assert calls == []
