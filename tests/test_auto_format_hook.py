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

The payload tests never invoke the real `ruff`; a shim on PATH records its argv.
PATH is hermetic — the tools the hook needs are symlinked in — so the no-`jq` arm
can drop `jq` alone rather than dropping `/usr/bin` and taking `grep` and `sed`
with it. The #419 tests at the end run the real `ruff` where it is installed,
because that defect is what ruff itself does to a file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "plugin-hooks" / "auto-format.sh"

# Everything the hook needs that is not a bash builtin and not `jq`: the
# resolution ladder, then `git` for the style check, then the before-and-after
# comparison behind the change notice. `bash` is included because a hermetic
# PATH is also the PATH the interpreter is looked up on.
_BASE_TOOLS = ("bash", "cat", "grep", "head", "cut", "git", "mktemp", "rm", "cp", "diff", "awk")

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


def _bin_dir(tmp_path: Path, *, with_jq: bool, extra: tuple[str, ...] = ()) -> Path:
    d = tmp_path / ("bin-jq" if with_jq else "bin-nojq")
    d.mkdir(exist_ok=True)
    for name in (*_BASE_TOOLS, *(("jq",) if with_jq else ()), *extra):
        real = shutil.which(name)
        if real is None:
            pytest.skip(f"{name} is not available on this host")
        link = d / name
        if not link.exists():
            link.symlink_to(real)
    return d


def _shim(d: Path, name: str, body: str) -> None:
    """Install an executable `name` in `d`. A symlink already there is
    replaced, never written through into the real tool."""
    shim = d / name
    shim.unlink(missing_ok=True)
    shim.write_text(body)
    shim.chmod(0o755)


def _run(tmp_path: Path, d: Path, stdin: str, **env: str) -> subprocess.CompletedProcess:
    """Run the real hook with `d` as its whole PATH."""
    return subprocess.run(
        [str(d / "bash"), str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": str(d), **env},
        timeout=30,
    )


def run_hook(tmp_path: Path, stdin: str, *, with_jq: bool = True):
    """Run the real hook with a recording `ruff` shim.

    Returns `(returncode, stderr, calls)` where `calls` is one argv list per
    `ruff` invocation.
    """
    d = _bin_dir(tmp_path, with_jq=with_jq)
    log = tmp_path / "ruff-argv.txt"
    # NUL-delimit each argument so a path containing whitespace stays one
    # element; RS-delimit each invocation so two calls stay two calls.
    _shim(
        d,
        "ruff",
        "#!/bin/sh\n"
        'for a in "$@"; do printf "%s\\000" "$a"; done >> "$RUFF_LOG"\n'
        'printf "\\036" >> "$RUFF_LOG"\n',
    )
    proc = _run(tmp_path, d, stdin, RUFF_LOG=str(log))
    calls = []
    if log.exists():
        for record in log.read_text().split(_RECORD_SEP):
            if record:
                calls.append(record.split("\0")[:-1])
    return proc.returncode, proc.stderr, calls


def targets(calls: list[list[str]]) -> list[str]:
    """The file each `ruff` invocation was pointed at.

    `ruff format -- <file>` names it after `--`. The style check reads the
    committed copy on stdin, so it names the file with `--stdin-filename=`.
    """
    named = []
    for c in calls:
        if not c:
            continue
        stdin_names = [a.split("=", 1)[1] for a in c if a.startswith("--stdin-filename=")]
        named.append(stdin_names[0] if stdin_names else c[-1])
    return named


# Git with no user or system config, so a fixture repo is the same on any host.
_GIT_ENV = {"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """A git repo at `tmp_path/repo` with `files` committed.

    The hook formats Python only where the file's committed version is already
    in ruff's style, so a test that needs ruff to run commits its target first.
    """
    repo = tmp_path / "repo"
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "fixture"]):
        subprocess.run([*git, *args], check=True, capture_output=True, env=_GIT_ENV)
    return repo


def _committed(tmp_path: Path, *rels: str) -> list[str]:
    """Commit a one-line Python file at each of `rels` and return their paths.

    The recording shim passes the style check, so each of these files that the
    hook resolves is then formatted.
    """
    repo = _repo(tmp_path, {rel: "x = 1\n" for rel in rels})
    return [str(repo / rel) for rel in rels]


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
        (target,) = _committed(tmp_path, rel)
        rc, err, calls = run_hook(
            tmp_path, serialize(_payload(target, tool=tool)), with_jq=with_jq
        )
        assert rc == 0, f"hook failed: {err}"
        assert targets(calls) == [target, target], (
            f"expected the style check and `ruff format` on {target}, got {calls}"
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
        (target,) = _committed(tmp_path, "fixture.py")
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
        # Both are committed, so a wrong pick would reach ruff and show.
        target, echoed = _committed(tmp_path, "mod.py", "echoed.py")
        payload = _payload(target)
        payload["tool_response"]["file_path"] = echoed
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

    def test_empty_stdin_is_silent_and_successful(self, tmp_path):
        # No event is not a parse failure — the hook has nothing to act on.
        # Not run across the jq arms: the hook exits before jq is consulted, so
        # both arms are byte-identical executions (bash, cat — nothing else).
        rc, err, calls = run_hook(tmp_path, "")
        assert rc == 0
        assert err == ""
        assert calls == []


class TestExtensionDispatch:
    @SERIALIZERS
    def test_a_non_python_target_does_not_reach_ruff(self, tmp_path, serialize):
        rc, err, calls = run_hook(tmp_path, serialize(_payload(str(tmp_path / "notes.txt"))))
        assert rc == 0, f"hook failed: {err}"
        assert calls == []


class TestJqResolvesToolInputRegardlessOfKeyOrder:
    """Why `jq` is rung 1 and not a fallback, despite being the expensive rung.

    A text pattern takes the *first* `file_path` in the payload, so it is correct
    only while `tool_input` happens to precede `tool_response`. That is one more
    uncontracted property of the same external producer this fix exists to stop
    depending on — trading whitespace-order for key-order is not a fix. Measured:
    with the keys swapped, the text rung returns the echoed path and `jq` returns
    the real one.

    The text rung keeps that limitation; it is the degraded path for a host with
    no `jq`, and its bound is stated rather than papered over. This test pins the
    `jq` rung's freedom from it, so a later change that reorders the rungs for
    speed fails here rather than silently re-acquiring the dependency.
    """

    def test_a_reordered_payload_still_resolves_tool_input(self, tmp_path):
        real, echoed = _committed(tmp_path, "real.py", "echoed.py")
        # tool_response BEFORE tool_input — a key order no contract forbids.
        payload = {
            "tool_name": "Write",
            "tool_response": {"file_path": echoed},
            "tool_input": {"file_path": real, "content": "x = 1\n"},
        }
        rc, err, calls = run_hook(tmp_path, compact(payload), with_jq=True)
        assert rc == 0, f"hook failed: {err}"
        assert targets(calls) == [real, real], (
            f"jq must resolve tool_input.file_path, not the first match; got {calls}"
        )


# ─── formatters must not load repo config / run repo code ───────────────────

class TestFormattersIsolateConfigAndTerminateOptions:
    """A formatter that loads repo config can run repo code (prettier plugins,
    sqlfluff templater). Each is run isolated from repo config, and the path is
    passed after `--` so it is never read as an option."""

    def test_ruff_calls_are_isolated_with_dashdash(self, tmp_path):
        (target,) = _committed(tmp_path, "mod.py")
        rc, err, calls = run_hook(tmp_path, compact(_payload(target)), with_jq=True)
        assert rc == 0, err
        assert len(calls) == 2, calls  # the style check, then ruff format
        for c in calls:
            assert "--isolated" in c, f"ruff call not isolated: {c}"
            assert "--" in c, f"ruff call missing --: {c}"
        check, fmt = calls
        # The check reads the committed copy on stdin; the `=` form keeps a
        # path that starts with `-` from being read as an option.
        assert check[check.index("--") + 1] == "-", f"the check must read stdin: {check}"
        assert f"--stdin-filename={target}" in check, check
        # the file is the argument right after `--`
        assert fmt[fmt.index("--") + 1] == target, f"path not after --: {fmt}"

    def test_source_isolates_every_formatter(self):
        src = HOOK.read_text()
        # ruff (the style check and the format), prettier, sqlfluff
        assert "ruff format --isolated --check --stdin-filename=" in src
        assert "ruff format --isolated -- " in src
        assert "prettier --write --no-config -- " in src
        assert "sqlfluff fix --templater raw -- " in src
        # the bare, config-loading forms are gone
        assert "prettier --write \"$FILE_PATH\"" not in src
        assert "sqlfluff fix \"$FILE_PATH\"" not in src


# ─── #419: never delete code, never change a file silently ──────────────────

# #419's reproduction, verbatim: `fixtures_mod.py` defines a fixture and
# `test_example.py` imports it. The import is used only as a parameter name, so
# F401 reads it as unused. Neither file is in ruff's default style.
_FIXTURES_MOD = "import pytest\n\n\n@pytest.fixture\ndef profile():\n    return {'kind': 'example'}\n"
_TEST_EXAMPLE = (
    "from fixtures_mod import profile\n"
    "\n"
    "\n"
    "def test_uses_profile(profile):\n"
    "    assert profile['kind'] == 'example'\n"
    "\n"
    "\n"
    "def test_other():\n"
    "    assert {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q'} >= {'a'}\n"
)
_IMPORT = "from fixtures_mod import profile\n"
# The same fixture user in ruff's default style, as a repo that uses it holds it.
_TEST_FORMATTED = _IMPORT + '\n\ndef test_uses_profile(profile):\n    assert profile["kind"] == "example"\n'
# A line to add that ruff format changes: no space after the colon.
_ADDED_LINE = '    assert profile == {"kind":"example"}\n'


def run_real_hook(tmp_path: Path, stdin: str) -> subprocess.CompletedProcess:
    """Run the hook with the real `ruff`: #419 is about what ruff itself does
    to a file, which a shim cannot show."""
    return _run(tmp_path, _bin_dir(tmp_path, with_jq=True, extra=("ruff",)), stdin)


def run_changing_shim(tmp_path: Path, stdin: str, name: str) -> subprocess.CompletedProcess:
    """Run the hook with a `name` shim that appends a line to the file it is
    given and prints a line of its own, as a real formatter reports its work."""
    d = _bin_dir(tmp_path, with_jq=True)
    _shim(d, name, '#!/bin/sh\nfor a in "$@"; do f=$a; done\nprintf "added\\n" >> "$f"\necho "$f 12ms"\n')
    return _run(tmp_path, d, stdin)


def notice(proc: subprocess.CompletedProcess) -> str:
    """The hook's change notice, once it is shown to be PostToolUse JSON."""
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse", out
    return out["hookSpecificOutput"]["additionalContext"]


class TestAPostEditHookNeverDeletesCode:
    """#419: the hook ran `ruff check --fix` after every edit. ruff's default
    rules include F401, whose fix deletes an import that looks unused, and a
    fixture imported from another module is used only as a parameter name, so
    every test that requested it then errored at setup. Formatting changes
    layout; a lint fix changes code, which this hook must never do to Python.
    `test_a_file_in_ruff_style_gets_only_its_edit_formatted` shows the import
    surviving where ruff format does run."""

    def test_the_reproduction_comes_back_as_written(self, tmp_path):
        # #419's one-line edit on its two files. Neither is in ruff's style, so
        # the file stays exactly as the edit left it.
        repo = _repo(tmp_path, {"fixtures_mod.py": _FIXTURES_MOD, "test_example.py": _TEST_EXAMPLE})
        target = repo / "test_example.py"
        edited = _TEST_EXAMPLE.replace("def test_other():", "def test_letters():")
        target.write_text(edited)
        proc = run_real_hook(tmp_path, compact(_payload(str(target), tool="Edit")))
        assert proc.returncode == 0, proc.stderr
        after = target.read_text()
        fate = "kept" if _IMPORT in after else "deleted"
        assert after == edited, (
            f"a one-line edit came back {len(after.splitlines())} lines long, from"
            f" {len(edited.splitlines())}, and its fixture import was {fate}"
        )
        assert proc.stdout == "", "the file is unchanged, so there is nothing to report"

    def test_only_ruff_format_ever_runs(self, tmp_path):
        # Recorded by the shim, so this holds on a host without ruff as well.
        (target,) = _committed(tmp_path, "mod.py")
        rc, err, calls = run_hook(tmp_path, compact(_payload(target)))
        assert rc == 0, err
        assert [c[0] for c in calls] == ["format", "format"], f"a lint fix ran: {calls}"


class TestOnlyAFileAlreadyInRuffStyleIsFormatted:
    """#419: `--isolated` formats with ruff's defaults, so in a repo whose
    Python is not in that style a one-line edit came back as a whole-file
    rewrite. A file is now formatted only when its committed version has content
    and `ruff format --isolated` would leave that version unchanged. In such a
    file, formatting reaches only what the edit changed; anywhere else the file
    stays as the session wrote it. `--isolated` stays, for the reason
    `TestFormattersIsolateConfigAndTerminateOptions` gives."""

    def test_a_file_in_ruff_style_gets_only_its_edit_formatted(self, tmp_path):
        # The style check passes here, so ruff format runs: what keeps the
        # import is that nothing else does. The notice names the one line.
        repo = _repo(tmp_path, {"fixtures_mod.py": _FIXTURES_MOD, "test_example.py": _TEST_FORMATTED})
        target = repo / "test_example.py"
        target.write_text(_TEST_FORMATTED + _ADDED_LINE)
        proc = run_real_hook(tmp_path, compact(_payload(str(target), tool="Edit")))
        after = target.read_text()
        assert _IMPORT in after, "the hook deleted the fixture import"
        assert after == _TEST_FORMATTED + '    assert profile == {"kind": "example"}\n'
        assert notice(proc).startswith(
            f"auto-format: ruff format changed line 6 of {target} after your edit (+1/-1 lines)."
        )

    @pytest.mark.parametrize(
        "committed",
        [{"other.py": "y = 1\n"}, None, {"mod.py": ""}, {"mod.py": "def f(:\n"}],
        ids=["new-file", "outside-a-repo", "empty-at-head", "unparseable-at-head"],
    )
    def test_a_file_with_no_style_evidence_is_left_as_written(self, tmp_path, committed):
        # None of these gives a committed version that shows the file is kept
        # in ruff's style.
        root = tmp_path / "loose" if committed is None else _repo(tmp_path, committed)
        root.mkdir(exist_ok=True)
        target = root / "mod.py"
        written = "x = {'a':1}\n"
        target.write_text(written)
        proc = run_real_hook(tmp_path, compact(_payload(str(target), content=written)))
        assert proc.returncode == 0, proc.stderr
        assert target.read_text() == written
        assert proc.stdout == ""


class TestTheSessionIsToldWhatTheHookChanged:
    """#419: the hook exited 0 whatever it changed, so a rewrite was found only
    by reading the diff. A change now comes back as PostToolUse
    `additionalContext`, which reaches the model as context rather than as an
    error, naming the formatter, the lines it touched and how many. The
    session's next Edit has to match what is on disk. The ruff case is checked
    in `test_a_file_in_ruff_style_gets_only_its_edit_formatted`."""

    def test_an_edit_already_in_style_prints_nothing(self, tmp_path):
        # Nothing changed, so no notice. This also pins that ruff's own "1 file
        # left unchanged" never reaches stdout, where the notice is read as JSON.
        repo = _repo(tmp_path, {"fixtures_mod.py": _FIXTURES_MOD, "test_example.py": _TEST_FORMATTED})
        target = repo / "test_example.py"
        edited = _TEST_FORMATTED + "    assert profile\n"
        target.write_text(edited)
        proc = run_real_hook(tmp_path, compact(_payload(str(target), tool="Edit")))
        assert proc.returncode == 0, proc.stderr
        assert target.read_text() == edited
        assert proc.stdout == ""

    @pytest.mark.parametrize(("name", "rel"), [("prettier", "notes.md"), ("sqlfluff", "query.sql")])
    def test_every_formatters_change_is_reported(self, tmp_path, name, rel):
        target = tmp_path / rel
        target.write_text("one\ntwo\n")
        text = notice(run_changing_shim(tmp_path, compact(_payload(str(target))), name))
        assert f" changed line 3 of {target} after your edit (+1/-0 lines)." in text, text

    def test_the_notice_is_json_whatever_the_path_holds(self, tmp_path):
        # A quote or a backslash in the path would break the JSON, and the
        # notice with it, so each comes back as `?`.
        target = tmp_path / 'a "quoted" \\ dir' / "notes.md"
        target.parent.mkdir()
        target.write_text("one\n")
        text = notice(run_changing_shim(tmp_path, compact(_payload(str(target))), "prettier"))
        assert "a ?quoted? ? dir/notes.md" in text, text
