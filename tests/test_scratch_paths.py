"""Scratch files and directories are private to the user who made them.

Native workflows allocate scratch through the existing session-store primitive
beneath their verified native owner. Static Markdown routing checks are separate
from executable allocator/concurrency/failure fixtures below; neither claims
native-host acceptance. Internal writes never fall back to OS temporary paths.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from claudna.session_store.fsio import (  # noqa: E402
    OperationAllocationError,
    allocate_operation,
    ensure_dir,
    make_scratch,
)
from claudna.session_store.paths import (  # noqa: E402
    SessionPaths,
    operation_path,
    owned_path,
    validate_operation_id,
    validate_scratch_label,
)
from claudna.session_store.store import SessionStore  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from release_toolchain import maintainer_paths  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FILES = sorted(
    p for d in ("skills", "agents", "plugin-hooks") for p in (REPO / d).rglob("*") if p.suffix in (".md", ".sh")
)
PROSE = [p for p in FILES if p.suffix == ".md"]

# A path in the shared temp directory: anything beneath /tmp/ or $TMPDIR/ (`/tmp/<skill>-<ts>/`,
# `${TMPDIR:-/tmp}/name`, `/tmp/` itself as a place to write), or /tmp or $TMPDIR as a working
# directory (`cd /tmp && ...`). A mention of the directory, such as "never under `/tmp`", is not one.
_TEMP_PATH = re.compile(
    r"(?<![\w$}.~])/tmp(?:/|(?=[\s&;|)]|$))"
    r"|\$\{?TMPDIR\b(?:\}|:?[-=?+][^}\s]*\})?(?=[/\s&;|)]|$)"
)
# A permission declaration is not an executed output path. Unlike the previous
# policy, mktemp under an OS-temp root is an active ownership violation too.
_PRIVATE = re.compile(r"\bBash\([^)]*\)")


def _flags(line: str) -> bool:
    return bool(_TEMP_PATH.search(_PRIVATE.sub("", line)))


# Orchestration guide §1 (never §10), where the private directory is made and this rule is stated.
_SECTION_1 = r"orchestration[- ]guide(?:\.md`?\)?)? §\s?1(?!\d)"
# A line that has the model write a file it names only by a placeholder, or not at all.
_WRITES_A_FILE = re.compile(r"\b(?:with|by|via) the Write tool\b")
_UNNAMED_FILE = re.compile(r"<[a-z0-9-]*file>|\b(?:a|two|three|its own|those three) files?\b|\btemp(?:orary)? file\b")
_SAYS_WHERE = re.compile(r"<scratch>|<artifacts>|" + _SECTION_1)
# Output written "to a scratch directory" or "in scratch": the file must make one or point at §1.
_WRITES_TO_SCRATCH = re.compile(
    r"\b(?:to|in|into) (?:a |the )?scratch\b|\ba scratch (?:file|directory|dir)\b|\btemporary or ignored directory\b",
    re.I,
)
_MAKES_OR_POINTS = re.compile(r"<scratch>|" + _SECTION_1)


def _leaves_the_file_unplaced(line: str) -> bool:
    return bool(_WRITES_A_FILE.search(line) and _UNNAMED_FILE.search(line) and not _SAYS_WHERE.search(line))


def _leaves_scratch_unmade(text: str) -> bool:
    return bool(_WRITES_TO_SCRATCH.search(text) and not _MAKES_OR_POINTS.search(text))


def test_files_are_found():
    # Positive control: an empty scan would pass the tests below.
    assert len(FILES) > 40
    assert sum(1 for p in PROSE for line in p.read_text().splitlines() if _WRITES_A_FILE.search(line)) > 20


def test_no_file_names_a_path_in_the_shared_temp_dir():
    hits = []
    for path in FILES:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if _flags(line):
                hits.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:120]}")
    assert not hits, "use the native session allocator and owned state paths:\n" + "\n".join(hits)


@pytest.mark.parametrize(
    "line, rejected",
    [
        ('psql -f "<scratch>/query.sql" > output.csv', True),
        ('snowsql -f "<scratch>/query.sql" > "output.csv"', True),
        ('Report: ~/Downloads/activity.html', True),
        ('psql -f "<scratch>/query.sql" > "<artifacts>/output.csv"', False),
        ('Explicit export: > "<user-selected-export>/output.csv"', False),
        ('Edit the project README.md when explicitly requested.', False),
    ],
)
def test_report_placement_source_fixtures(line, rejected):
    # Narrow static examples for the audited CSV and Downloads defaults.
    assert bool(re.search(r'>\s*["\']?output\.csv\b|~/Downloads/', line)) is rejected


def test_analyst_and_activity_defaults_do_not_write_cwd_or_downloads():
    for relative in ('agents/neon-analyst.md', 'agents/snowflake-analyst.md',
                     'skills/github-activity-report/SKILL.md'):
        assert not re.search(r'>\s*["\']?output\.csv\b|~/Downloads/', (REPO / relative).read_text())


def test_each_file_a_skill_writes_says_where():
    # A command's text file, a finding, a message: the line that writes it places it in <scratch>.
    hits = [
        f"{p.relative_to(REPO)}:{n}: {line.strip()[:120]}"
        for p in PROSE
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if _leaves_the_file_unplaced(line)
    ]
    assert not hits, "write it in <scratch> (orchestration guide §1):\n" + "\n".join(hits)


def test_a_file_that_writes_to_scratch_makes_it_or_points_at_section_1():
    hits = [str(p.relative_to(REPO)) for p in PROSE if _leaves_scratch_unmade(p.read_text())]
    assert not hits, "allocate <scratch> through the native session store, per orchestration guide §1:\n" + "\n".join(hits)


def test_section_1_states_the_rule_and_the_refusal():
    guide = (REPO / "skills" / "_shared" / "orchestration-guide.md").read_text()
    section_1 = guide.split("\n## 1.", 1)[1].split("\n## 2.", 1)[0]
    assert "Working files go in `<scratch>`; durable deliverables go in `<artifacts>`" in section_1
    assert "If the native allocation is refused, stop that write and say so" in section_1
    assert "--session \"<verified-native-sid>\" --host \"<provider>\"" in section_1


@pytest.mark.parametrize(
    "line",
    [
        'D=$(mktemp -d "${TMPDIR:-/tmp}/audit-x.XXXXXX")',
        "Scratch dir: `/tmp/audit-<YYYY-MM-DD_HHMMSS>/`",
        'OUT="${OUT:-/tmp/gh-activity-stats}"',
        'MARKER="${TMPDIR:-/tmp}/claudna-reflected-${SESSION_ID}"',
        "write it to `$TMPDIR/out.json`",
        'LOG="/tmp/claude-permissions.log"',
        # A mktemp call on the line does not excuse the rest of it.
        'made once with `mktemp -d "${TMPDIR:-/tmp}/audit.XXXXXX"`, so the maps are `/tmp/audit-<TS>/system/map.md`',
        "cd /tmp && git clone <url>",
        'OUT="/tmp/"',
        "rm -rf /tmp/*",
        "write it to ${TMPDIR-/tmp}/out.json",
        "writing research to `/tmp/`",
    ],
)
def test_the_lint_flags_each_form(line):
    assert _flags(line)


@pytest.mark.parametrize(
    "line",
    [
        "  - Bash(rm -rf /tmp/heist-*)",
        "Scratch directory: `<scratch>/research/`",
        "Never name a scratch path yourself under `/tmp` or `$TMPDIR`.",
        'if path in ("/", "/tmp", os.path.expanduser("~")):',
        "state lives in the Issue's comments, not `/tmp`, which stays ephemeral.",
    ],
)
def test_the_lint_passes_the_private_forms(line):
    assert not _flags(line)


@pytest.mark.parametrize(
    "line",
    [
        "Write the keywords to `<keywords-file>` with the Write tool, then:",
        "Write the title and the description to two files with the Write tool, then run `gh pr create`.",
        "write the markdown body to a temp file (with the Write tool) and post it with `-F body=@<file>`",
        "Write it to `<out-file>` with the Write tool (orchestration guide §10).",
    ],
)
def test_an_unplaced_file_is_flagged(line):
    assert _leaves_the_file_unplaced(line)


@pytest.mark.parametrize(
    "line",
    [
        "Write the keywords to `<keywords-file>` in `<scratch>` (`../_shared/orchestration-guide.md` §1) with the Write tool",
        "write the title and the body to two files with the Write tool, inside `<scratch>` from the native session allocator",
        "Create `CLAUDE.md` in the project root with the Write tool.",
    ],
)
def test_a_placed_or_named_file_passes(line):
    assert not _leaves_the_file_unplaced(line)


def test_a_doc_written_in_scratch_needs_scratch_made_or_pointed_at():
    line = "author the retro as a publishable doc in scratch named `00_RETRO.md`, then publish it"
    assert _leaves_scratch_unmade(line)
    assert _leaves_scratch_unmade(line + " (see `../_shared/orchestration-guide.md` §10)")
    assert not _leaves_scratch_unmade(line.replace("in scratch", "in `<scratch>`"))
    assert not _leaves_scratch_unmade(line + " (`../_shared/orchestration-guide.md` §1)")


def test_the_activity_crawl_needs_its_output_dir_named(tmp_path):
    crawl = REPO / "skills" / "github-activity-report" / "crawl.sh"
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "SCOPE": "fake-org",
        "SINCE_DATE": "2026-01-01",
        "UNTIL_DATE": "2026-01-31",
    }
    run = subprocess.run(["bash", str(crawl)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert run.returncode != 0 and "OUT" in run.stderr, run.stdout + run.stderr


@pytest.mark.parametrize("label", ["a", "A0._-", "z" * 64])
def test_scratch_labels_use_the_exact_ascii_grammar(label):
    assert validate_scratch_label(label) == label


@pytest.mark.parametrize("label", ["", ".hidden", "../escape", "a/b", "a\n", "é", "z" * 65])
def test_scratch_labels_reject_traversal_unicode_and_newlines(label):
    with pytest.raises(ValueError):
        validate_scratch_label(label)


def test_scratch_creation_is_unique_private_and_scoped_to_parent(tmp_path):
    parent = tmp_path / "state" / "sessions" / "sid" / "scratch"
    with ThreadPoolExecutor(max_workers=8) as pool:
        created = list(pool.map(lambda _: make_scratch(parent, "audit"), range(24)))
    assert len(set(created)) == 24
    assert all(path.parent == parent and path.name.startswith("audit.") for path in created)
    assert parent.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o700 for path in created)


def test_operation_lookup_is_pure_and_keeps_its_own_namespace(tmp_path):
    operation_id = "op-" + "a" * 32
    root = tmp_path / "state"
    target = operation_path(root, operation_id)
    assert target == root / "operations" / operation_id
    assert not root.exists()
    with pytest.raises(ValueError):
        operation_path(root, "a" * 32)
    with pytest.raises(ValueError):
        validate_operation_id(operation_id + "\n")


def test_session_owned_path_lookup_is_whitelisted_and_pure(tmp_path):
    root = tmp_path / "state"
    paths = SessionPaths(root=root, sid="native-session")
    assert owned_path(paths, "handoff") == root / "sessions/native-session/handoff.md"
    assert owned_path(paths, "artifacts") == root / "sessions/native-session/artifacts"
    assert not root.exists()
    with pytest.raises(ValueError):
        owned_path(paths, "../../outside")


def test_generated_operation_allocation_has_private_layout_and_owner_record(tmp_path):
    import json

    allocation = allocate_operation(tmp_path, label="review")
    assert allocation.parent == tmp_path / "operations"
    assert allocation.name.startswith("op-") and len(allocation.name) == 35
    assert allocation.stat().st_mode & 0o777 == 0o700
    for directory in (allocation / "scratch", allocation / "artifacts"):
        assert directory.is_dir() and directory.stat().st_mode & 0o777 == 0o700
    marker = allocation / "operation.json"
    assert marker.stat().st_mode & 0o777 == 0o600
    assert json.loads(marker.read_text()) == {"version": 1, "operation_id": allocation.name, "label": "review"}


def test_explicit_operation_allocation_records_null_label(tmp_path):
    import json

    operation_id = "op-" + "e" * 32
    allocation = allocate_operation(tmp_path / "state", operation_id=operation_id)
    assert json.loads((allocation / "operation.json").read_text()) == {
        "version": 1, "operation_id": operation_id, "label": None
    }


def test_explicit_operation_collision_fails_without_adopting_existing_data(tmp_path):
    operation_id = "op-" + "b" * 32
    existing = operation_path(tmp_path, operation_id)
    existing.mkdir(parents=True)
    sentinel = existing / "keep"
    sentinel.write_text("untouched")
    with pytest.raises(FileExistsError, match=str(existing)):
        allocate_operation(tmp_path, operation_id=operation_id)
    assert sentinel.read_text() == "untouched"
    assert not (existing / "operation.json").exists()


def test_generated_operation_retries_only_an_id_collision(tmp_path, monkeypatch):
    from claudna.session_store import fsio

    collision_id = "op-" + "f" * 32
    occupied = operation_path(tmp_path, collision_id)
    occupied.mkdir(parents=True)
    generated_ids = iter((collision_id[3:], "1" * 32))
    monkeypatch.setattr(fsio.uuid, "uuid4", lambda: type("UUID", (), {"hex": next(generated_ids)})())
    allocation = allocate_operation(tmp_path, label="retry")
    assert allocation.name == "op-" + "1" * 32
    assert occupied.is_dir()


def test_relative_operation_root_is_rejected_before_any_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        allocate_operation(Path("relative-state"), operation_id="op-" + "2" * 32)
    assert not (tmp_path / "relative-state").exists()


def test_operation_partial_failure_names_and_preserves_exact_allocation(tmp_path, monkeypatch):
    from claudna.session_store import fsio

    def fail(*args, **kwargs):
        raise OSError("injected marker failure")

    monkeypatch.setattr(fsio, "atomic_write_json", fail)
    with pytest.raises(OperationAllocationError) as caught:
        allocate_operation(tmp_path, operation_id="op-" + "c" * 32)
    assert caught.value.path == tmp_path / "operations" / ("op-" + "c" * 32)
    assert (caught.value.path / "scratch").is_dir()
    assert (caught.value.path / "artifacts").is_dir()


def _run_store_cli(root: Path, *arguments: str, extra_env: dict[str, str] | None = None):
    env = {"PATH": os.environ["PATH"], "HOME": str(root.parent / "home")}
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-B", str(REPO / "lib/claudna/session_store"), *arguments, "--root", str(root)],
        env=env, capture_output=True, text=True, timeout=10,
    )


def test_paths_cli_lookup_is_read_only_and_create_handoff_makes_only_session_parent(tmp_path):
    root = tmp_path / "state"
    sid = "native-cli-session"
    lookup = _run_store_cli(root, "paths", "--session", sid, "--host", "cursor", "--kind", "handoff")
    assert lookup.returncode == 0 and lookup.stdout.strip() == str(root / "sessions" / sid / "handoff.md")
    assert not root.exists()

    created = _run_store_cli(root, "paths", "--session", sid, "--host", "cursor", "--kind", "handoff", "--create")
    session_dir = root / "sessions" / sid
    assert created.returncode == 0, created.stderr
    assert session_dir.is_dir() and not (session_dir / "handoff.md").exists()
    assert sorted(path.name for path in session_dir.iterdir()) == []


def test_paths_cli_rejects_missing_and_placeholder_session_ids(tmp_path):
    root = tmp_path / "state"
    missing = _run_store_cli(root, "paths", "--host", "claude", "--kind", "artifacts")
    placeholder = _run_store_cli(
        root, "paths", "--session", "SESSION_ID", "--host", "claude", "--kind", "artifacts"
    )
    assert missing.returncode == 2
    assert placeholder.returncode == 2 and "verified native session ID" in placeholder.stderr
    assert not root.exists()


def test_paths_cli_rejects_conflicting_codex_environment_identity(tmp_path):
    root = tmp_path / "state"
    sid = "codex-thread-native-1"
    result = _run_store_cli(
        root, "paths", "--session", sid, "--host", "codex", "--kind", "artifacts",
        extra_env={"CODEX_THREAD_ID": sid, "CODEX_SESSION_ID": "other-thread"},
    )
    assert result.returncode == 2 and "conflicting native session identity" in result.stderr
    assert not root.exists()


def test_paths_cli_rejects_a_provider_mismatch_in_recorded_session(tmp_path):
    root = tmp_path / "state"
    sid = "recorded-claude-session"
    handle = SessionStore(root).session(sid)
    handle.open_session(
        "startup",
        actor={"kind": "interactive", "fleet": None, "bot_id": None, "bot_name": None,
               "model": None, "entrypoint": "cli"},
        origin={"cwd": str(tmp_path), "repo": None, "branch": None, "head": None},
        transcript_path=None,
        agent_cli="claude",
    )
    result = _run_store_cli(root, "paths", "--session", sid, "--host", "codex", "--kind", "artifacts")
    assert result.returncode == 2 and "provider does not match recorded session owner" in result.stderr


def test_operation_dir_cli_lookup_is_read_only_and_create_records_generated_owner(tmp_path):
    root = tmp_path / "state"
    operation_id = "op-" + "d" * 32
    lookup = _run_store_cli(root, "operation-dir", "--operation-id", operation_id)
    assert lookup.returncode == 0 and lookup.stdout.strip() == str(root / "operations" / operation_id)
    assert not root.exists()

    created = _run_store_cli(root, "operation-dir", "--label", "manual-review", "--create")
    assert created.returncode == 0, created.stderr
    allocation = Path(created.stdout.strip())
    assert allocation.parent == root / "operations" and allocation.name.startswith("op-")
    assert (allocation / "scratch").is_dir() and (allocation / "artifacts").is_dir()
    assert json.loads((allocation / "operation.json").read_text()) == {
        "version": 1, "operation_id": allocation.name, "label": "manual-review"
    }


def test_native_id_spelling_does_not_alias_the_operation_namespace(tmp_path):
    root = tmp_path / "state"
    sid = "op-" + "e" * 32
    result = _run_store_cli(root, "paths", "--session", sid, "--host", "codex", "--kind", "artifacts",
                            extra_env={"CODEX_THREAD_ID": sid})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(root / "sessions" / sid / "artifacts")
    assert operation_path(root, sid) == root / "operations" / sid
    assert not root.exists()


def test_observed_child_exit_allows_only_its_exact_scratch_cleanup(tmp_path):
    root = tmp_path / "state"
    home = tmp_path / "home"
    temp = tmp_path / "tmp"
    home.mkdir()
    temp.mkdir()
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(temp),
           "PYTHONPATH": str(REPO / "lib")}
    owner = SessionStore(root).session("native-child-owner")
    sibling = SessionStore(root).session("sibling-owner")
    ensure_dir(owner.paths.artifacts)
    ensure_dir(sibling.paths.artifacts)
    canonical = owner.paths.artifacts / "keep.md"
    canonical.write_text("canonical deliverable survives cleanup")
    canonical.chmod(0o600)
    sibling_artifact = sibling.paths.artifacts / "keep.md"
    sibling_artifact.write_text("sibling deliverable survives cleanup")
    sibling_artifact.chmod(0o600)
    sibling_scratch = make_scratch(sibling.paths.scratch, "sibling")
    (sibling_scratch / "keep.txt").write_text("sibling private scratch")
    (sibling_scratch / "keep.txt").chmod(0o600)

    dead_child = subprocess.Popen(
        [sys.executable, "-B", "-c", (
            "import os, sys; from pathlib import Path; os.umask(0o077); "
            "from claudna.session_store.fsio import make_scratch; "
            "from claudna.session_store.paths import session_paths; "
            "paths = session_paths(sys.argv[2], Path(sys.argv[1])); "
            "scratch = make_scratch(paths.scratch, 'abrupt'); "
            "(scratch / 'private.txt').write_text('private interrupted work'); "
            "print(scratch, flush=True); os._exit(23)"
        ), str(root), "native-child-owner"],
        env=env, cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    stdout, stderr = dead_child.communicate(timeout=10)
    assert dead_child.returncode == 23, stderr
    dead_scratch = Path(stdout.strip())
    assert dead_scratch.parent == owner.paths.scratch and dead_scratch.is_dir()
    assert dead_scratch.stat().st_mode & 0o777 == 0o700
    assert (dead_scratch / "private.txt").stat().st_mode & 0o777 == 0o600

    live_child = subprocess.Popen(
        [sys.executable, "-B", "-c", (
            "import os, sys, time; from pathlib import Path; os.umask(0o077); "
            "from claudna.session_store.fsio import make_scratch; "
            "scratch = make_scratch(Path(sys.argv[1]), 'live'); "
            "(scratch / 'private.txt').write_text('running child work'); "
            "print(scratch, flush=True); time.sleep(30)"
        ), str(owner.paths.scratch)],
        env=env, cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        live_scratch = Path(live_child.stdout.readline().strip())
        assert live_scratch.parent == owner.paths.scratch and live_child.poll() is None
        assert (live_scratch / "private.txt").stat().st_mode & 0o777 == 0o600
        # Observe the abrupt child exit above before removing only its exact allocation.
        shutil.rmtree(dead_scratch)
        assert not dead_scratch.exists()
        assert live_scratch.is_dir()
        assert canonical.read_text() == "canonical deliverable survives cleanup"
        assert sibling_artifact.read_text() == "sibling deliverable survives cleanup"
        assert (sibling_scratch / "keep.txt").read_text() == "sibling private scratch"
    finally:
        if live_child.poll() is None:
            live_child.terminate()
        live_child.communicate(timeout=10)
        if "live_scratch" in locals() and live_scratch.exists():
            # The owner observes this second child's exit before its own exact cleanup.
            shutil.rmtree(live_scratch)


@pytest.fixture
def maintainer_state(tmp_path, monkeypatch):
    home = tmp_path / "private home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    root = tmp_path / "relocated state"
    monkeypatch.setenv("CLAUDNA_STATE_DIR", str(root))
    return root


def test_maintainer_owner_requires_explicit_standalone_and_is_not_a_session(maintainer_state):
    with pytest.raises(ValueError, match="native identity required"):
        maintainer_paths("qualification")
    assert not maintainer_state.exists()
    with ThreadPoolExecutor(max_workers=3) as pool:
        owners = list(pool.map(lambda _: maintainer_paths("qualification", standalone=True), range(3)))
    assert len({owner.owner_id for owner in owners}) == 3
    for owner in owners:
        assert owner.kind == "operation" and owner.provider is None
        assert owner.directory.parent == maintainer_state / "operations"
        assert owner.scratch.stat().st_mode & 0o777 == 0o700
        assert owner.artifacts.stat().st_mode & 0o777 == 0o700
        assert json.loads((owner.directory / "operation.json").read_text())["operation_id"] == owner.owner_id
    assert not (maintainer_state / "sessions").exists()


@pytest.mark.parametrize("default_root", [False, True])
def test_maintainer_native_context_wins_and_capture_off_creates_no_events(maintainer_state, monkeypatch, default_root):
    if default_root:
        monkeypatch.delenv("CLAUDNA_STATE_DIR")
        root = Path(os.environ["HOME"]) / ".claudna"
    else:
        root = maintainer_state
    monkeypatch.setenv("CODEX_THREAD_ID", "actual-fixture-owner")
    monkeypatch.setenv("CODEX_SESSION_ID", "actual-fixture-owner")
    monkeypatch.setenv("CLAUDNA_SESSION_STORE", "0")
    owner = maintainer_paths("qualification", standalone=True)
    assert owner.kind == "session" and owner.provider == "codex"
    assert owner.directory == root / "sessions/actual-fixture-owner"
    assert owner.scratch.is_dir() and owner.artifacts.is_dir()
    assert not (root / "operations").exists()
    assert not list(root.rglob("lifecycle.jsonl"))


@pytest.mark.parametrize("values", [{"CODEX_THREAD_ID": ""}, {"CODEX_THREAD_ID": "bad/owner"},
                                    {"CODEX_THREAD_ID": "one", "CODEX_SESSION_ID": "two"},
                                    {"CODEX_THREAD_ID": "one", "CLAUDE_SESSION_ID": "one"}])
def test_maintainer_invalid_native_context_never_falls_back(maintainer_state, monkeypatch, values):
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        maintainer_paths("qualification", standalone=True)
    assert not maintainer_state.exists()


def test_maintainer_explicit_native_owner_and_conflicts(maintainer_state, monkeypatch):
    with pytest.raises(ValueError, match="together"):
        maintainer_paths("qualification", session="fixture", standalone=True)
    assert not maintainer_state.exists()
    owner = maintainer_paths("qualification", session="cursor-fixture", host="cursor")
    assert owner.provider == "cursor" and owner.kind == "session"
    monkeypatch.setenv("CODEX_THREAD_ID", "actual-fixture")
    with pytest.raises(ValueError, match="conflicts"):
        maintainer_paths("qualification", session="cursor-fixture", host="cursor", standalone=True)
    assert not (maintainer_state / "operations").exists()


def test_maintainer_denied_allocation_retains_exact_partial_owner(maintainer_state, monkeypatch):
    import release_toolchain

    monkeypatch.setenv("CODEX_THREAD_ID", "denied-fixture")
    original = release_toolchain.ensure_dir

    def deny_artifacts(path):
        if path.name == "artifacts":
            raise PermissionError("fixture denied")
        return original(path)

    monkeypatch.setattr(release_toolchain, "ensure_dir", deny_artifacts)
    with pytest.raises(PermissionError, match="fixture denied"):
        maintainer_paths("qualification", standalone=True)
    assert (maintainer_state / "sessions/denied-fixture/scratch").is_dir()
    assert not (maintainer_state / "operations").exists()


def test_maintainer_rejects_redirected_owner_without_touching_sentinel(maintainer_state, tmp_path, monkeypatch):
    sentinel = tmp_path / "host-owned"
    sentinel.mkdir()
    (sentinel / "keep").write_text("unchanged")
    maintainer_state.mkdir()
    (maintainer_state / "sessions").symlink_to(sentinel, target_is_directory=True)
    monkeypatch.setenv("CODEX_THREAD_ID", "redirected-fixture")
    with pytest.raises(ValueError, match="redirects"):
        maintainer_paths("qualification", standalone=True)
    assert list(sentinel.iterdir()) == [sentinel / "keep"]
    assert (sentinel / "keep").read_text() == "unchanged"
