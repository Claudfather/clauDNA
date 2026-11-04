"""Release boundaries exercised with real Git repositories and fixture remotes."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.usefixtures("maintainer_toolchain")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("release_candidate", ROOT / "scripts/release_candidate.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()


def commit(root, message="fixture"):
    git(root, "add", ".")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def fixture_targets(root):
    """Bounded make recipes prevent recursive full-suite calls in subprocess tests.

    The controller still runs real make and Git with private HOME/TMP. The
    package fixture refuses to run before the candidate source check succeeds.
    Separate package tests exercise the real archive and lifecycle machinery.
    """
    (root / "scripts").mkdir(exist_ok=True)
    for name in ("release_candidate.py", "release_toolchain.py", "check-changelog.sh"):
        shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
    (root / "Makefile").write_text(
        "check:\n\tpython3 scripts/fixture_check.py\n\tbash scripts/check-changelog.sh\n"
        "qualify-package:\n\tpython3 scripts/fixture_package.py '$(PACKAGE_REF)' '$(PACKAGE_OUTPUT)'\n"
        "tag-release:\n\tpython3 scripts/release_candidate.py --tag --ref '$(RELEASE_REF)' --output '$(RELEASE_OUTPUT)'\n"
    )
    (root / "scripts/fixture_check.py").write_text(
        "from pathlib import Path\nimport os\n"
        "assert Path.home().name == 'home'\n"
        "assert Path(os.environ['TMPDIR']).name == 'tmp'\n"
        "assert Path('payload').read_text() == 'committed'\n"
        "(Path.home() / 'source-passed').write_text('yes')\n"
    )
    (root / "scripts/fixture_package.py").write_text('''\
import hashlib
import json
from pathlib import Path
import subprocess
import sys

candidate, destination = sys.argv[1:]
assert (Path.home() / 'source-passed').read_text() == 'yes'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == candidate
version = json.loads(Path('.claude-plugin/plugin.json').read_text())['version']
out = Path(destination)
out.mkdir()
archive = b'fixture archive'
digest = hashlib.sha256(archive).hexdigest()
(out / 'package.tar.gz').write_bytes(archive)
(out / 'package.sha256').write_text(digest + '  package.tar.gz\\n')
(out / 'claude-marketplace.json').write_text(json.dumps({'commit': candidate}))
(out / 'receipt.json').write_text(json.dumps({'commit': candidate, 'version': version, 'archive': {'sha256': digest}}))
(out / 'qualification.json').write_text(json.dumps({'commit': candidate, 'version': version, 'archive_sha256': digest, 'status': 'pass'}))
''')
    (root / "payload").write_text("committed")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    fixture_targets(root)
    for host in ("claude", "cursor", "codex"):
        path = root / f".{host}-plugin"
        path.mkdir()
        (path / "plugin.json").write_text(json.dumps({"version": "1.0.0"}))
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n## [1.0.0]\n- Existing release.\n")
    baseline = commit(root)
    git(root, "update-ref", "refs/remotes/origin/main", baseline)
    for host in ("claude", "cursor", "codex"):
        (root / f".{host}-plugin/plugin.json").write_text(json.dumps({"version": "1.0.1"}))
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n## [1.0.1]\n- New release.\n\n## [1.0.0]\n- Existing release.\n")
    commit(root)
    remote = tmp_path / "remote.git"
    git(root, "clone", "--bare", str(root), str(remote))
    git(root, "remote", "add", "publish", str(remote))
    return root


def controller(root, output, *args):
    return subprocess.run([sys.executable, "scripts/release_candidate.py", "--ref", "HEAD",
                           "--output", str(output), *args], cwd=root, capture_output=True, text=True)


def test_exact_committed_candidate_checked_before_package_and_default_does_not_tag(repo, tmp_path):
    candidate = git(repo, "rev-parse", "HEAD")
    (repo / "payload").write_text("dirty source must not leak")
    result = controller(repo, tmp_path / "artifacts")
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads((tmp_path / "artifacts/source-check.json").read_text())
    assert evidence["commit"] == candidate and evidence["source_check"] == "pass"
    assert git(repo, "tag") == ""
    assert (repo / "payload").read_text() == "dirty source must not leak"


@pytest.fixture
def missing_toolchain_python(tmp_path, monkeypatch):
    environment = tmp_path / "without-toolchain"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(environment)], check=True)
    injected = tmp_path / "ambient-modules"
    injected.mkdir()
    for name in ("yaml", "ruff", "pytest"):
        (injected / f"{name}.py").write_text("# Only available through ambient PYTHONPATH.\n")
    monkeypatch.setenv("PYTHONPATH", str(injected))
    interpreter = environment / "bin/python3"
    # The ordinary caller can import all three; isolated qualification cannot.
    subprocess.run([str(interpreter), "-c", "import yaml; import ruff; import pytest"], check=True)
    return interpreter


def test_toolchain_preflight_rejects_ambient_only_dependencies_before_qualification(
        repo, tmp_path, missing_toolchain_python):
    original = git(repo, "rev-parse", "HEAD")
    output = tmp_path / "artifacts"
    env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"}
    result = subprocess.run([str(missing_toolchain_python), "scripts/release_candidate.py", "--ref", "HEAD",
                             "--output", str(output), "--tag"], cwd=repo, env=env, text=True, capture_output=True)
    assert result.returncode != 0 and "Release toolchain unavailable" in result.stderr
    assert "make deps" in result.stderr and ".venv/bin/activate" in result.stderr
    assert not output.exists()
    assert not (repo / "scripts/__pycache__").exists()
    assert git(repo, "rev-parse", "HEAD") == original
    assert git(repo, "status", "--porcelain") == "" and git(repo, "tag") == ""


def test_release_helper_toolchain_failure_precedes_every_file_commit_and_tag_mutation(
        repo, missing_toolchain_python, monkeypatch):
    shutil.copy2(ROOT / "scripts/release.sh", repo / "scripts/release.sh")
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n- Ready for a release.\n")
    original = commit(repo)
    original_files = {relative: (repo / relative).read_bytes() for relative in
                      ("CHANGELOG.md", ".claude-plugin/plugin.json", ".cursor-plugin/plugin.json",
                       ".codex-plugin/plugin.json")}
    monkeypatch.setenv("PATH", str(missing_toolchain_python.parent) + os.pathsep + os.environ["PATH"])
    result = subprocess.run(["bash", "scripts/release.sh", "patch"], cwd=repo, text=True, capture_output=True)
    assert result.returncode != 0 and "Release toolchain unavailable" in result.stderr
    assert git(repo, "rev-parse", "HEAD") == original
    assert git(repo, "status", "--porcelain") == "" and git(repo, "tag") == ""
    for relative, contents in original_files.items():
        assert (repo / relative).read_bytes() == contents


def test_absolute_interpreter_is_preserved_when_outer_path_has_another_python(repo, tmp_path, monkeypatch):
    binary = tmp_path / "wrong-python"
    binary.mkdir()
    wrong_python = binary / "python3"
    wrong_python.write_text("#!/bin/sh\necho unexpected outer PATH interpreter >&2\nexit 87\n")
    wrong_python.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    check = repo / "scripts/fixture_check.py"
    check.write_text(check.read_text() + "assert os.environ['PYTHONNOUSERSITE'] == '1'\n"
                     "assert 'PYTHONPATH' not in os.environ\nimport yaml, ruff, pytest\n")
    commit(repo)
    result = controller(repo, tmp_path / "artifacts")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("failure", ["source", "package", "notes", "moves-head"])
def test_qualification_failure_prevents_local_tag(repo, tmp_path, failure):
    if failure == "source":
        (repo / "payload").write_text("bad source")
    elif failure == "package":
        (repo / "scripts/fixture_package.py").write_text("raise SystemExit('package failed')\n")
    elif failure == "notes":
        (repo / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [1.0.1]\n### Fixed\n<!-- no notes -->\n")
    else:
        (repo / "scripts/fixture_check.py").write_text(
            "import subprocess\nsubprocess.run(['git', 'checkout', '--detach', 'origin/main'], check=True)\n"
        )
    commit(repo)
    result = controller(repo, tmp_path / "artifacts", "--tag")
    assert result.returncode != 0
    assert git(repo, "tag") == ""


def test_local_tag_is_only_created_after_successful_qualification(repo, tmp_path):
    result = controller(repo, tmp_path / "artifacts", "--tag")
    assert result.returncode == 0, result.stdout + result.stderr
    assert git(repo, "rev-parse", "v1.0.1^{commit}") == git(repo, "rev-parse", "HEAD")
    assert release.remote_tag(repo, "publish", "v1.0.1") is None


@pytest.mark.parametrize("annotated", [False, True])
def test_wrong_remote_tag_is_rejected_even_with_correct_local_tag(repo, annotated):
    candidate = git(repo, "rev-parse", "HEAD")
    if annotated:
        git(repo, "tag", "-a", "v1.0.1", "HEAD~", "-m", "wrong")
    else:
        git(repo, "tag", "v1.0.1", "HEAD~")
    git(repo, "push", "publish", "refs/tags/v1.0.1")
    git(repo, "tag", "-d", "v1.0.1")
    git(repo, "tag", "v1.0.1", candidate)
    with pytest.raises(release.ReleaseError, match="refusing to rewrite"):
        release.publish_tag(repo, "publish", "v1.0.1", candidate)


def test_remote_tag_idempotence_checks_peeled_annotated_commit(repo):
    candidate = git(repo, "rev-parse", "HEAD")
    release.publish_tag(repo, "publish", "v1.0.1", candidate)
    original = git(repo, "ls-remote", "publish", "refs/tags/v1.0.1")
    release.publish_tag(repo, "publish", "v1.0.1", candidate)
    assert git(repo, "ls-remote", "publish", "refs/tags/v1.0.1") == original
    assert release.remote_tag(repo, "publish", "v1.0.1") == candidate


@pytest.mark.parametrize("race", ["same", "wrong", "absent"])
def test_failed_push_uses_fresh_remote_identity_not_stale_local_tag(repo, monkeypatch, race):
    candidate = git(repo, "rev-parse", "HEAD")
    remote = Path(git(repo, "remote", "get-url", "publish"))
    real_run = release.run

    def raced_run(args, root, **kwargs):
        if args[:2] == ["git", "push"]:
            if race != "absent":
                git(remote, "update-ref", "refs/tags/v1.0.1",
                    candidate if race == "same" else git(repo, "rev-parse", "HEAD~"))
            return subprocess.CompletedProcess(args, 1, "", "fixture rejected push")
        return real_run(args, root, **kwargs)

    monkeypatch.setattr(release, "run", raced_run)
    if race == "same":
        release.publish_tag(repo, "publish", "v1.0.1", candidate)
    else:
        with pytest.raises(release.ReleaseError, match="absent after push" if race == "absent" else "refusing to rewrite"):
            release.publish_tag(repo, "publish", "v1.0.1", candidate)
    # This local tag exists in every case and is never accepted as remote proof.
    assert git(repo, "rev-parse", "v1.0.1^{commit}") == candidate


@pytest.fixture
def fake_gh(tmp_path, monkeypatch, repo):
    binary = tmp_path / "bin"
    state = tmp_path / "github-fixture"
    binary.mkdir()
    state.mkdir()
    (state / "repositories.json").write_text(json.dumps({"fixture/repo": git(repo, "remote", "get-url", "publish")}))
    executable = binary / "gh"
    executable.write_text(f"#!{sys.executable}\n" + '''\
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(os.environ['FAKE_GH_STATE'])
args = sys.argv[1:]
with (root / 'commands').open('a') as stream:
    stream.write(json.dumps(args) + '\\n')
assets = root / 'assets'
if args[0] == 'api':
    parts = args[1].split('/')
    repository = json.loads((root / 'repositories.json').read_text())['/'.join(parts[1:3])]
    if parts[3:6] == ['git', 'ref', 'tags']:
        oid = subprocess.check_output(['git', '--git-dir', repository, 'rev-parse', 'refs/tags/' + parts[6]], text=True).strip()
        kind = subprocess.check_output(['git', '--git-dir', repository, 'cat-file', '-t', oid], text=True).strip()
        print(json.dumps({'object': {'type': kind, 'sha': oid}}))
    elif parts[3:5] == ['git', 'tags']:
        tag = subprocess.check_output(['git', '--git-dir', repository, 'cat-file', '-p', parts[5]], text=True).splitlines()
        print(json.dumps({'object': {'sha': tag[0].split()[1], 'type': tag[1].split()[1]}}))
    elif parts[3:5] != ['releases', 'tags']:
        raise SystemExit('unexpected fixture API')
    elif not assets.exists():
        print('HTTP 404', file=sys.stderr)
        raise SystemExit(1)
    else:
        print(json.dumps({'tag_name': 'v1.0.1', 'assets': [{'name': p.name} for p in assets.iterdir()]}))
elif args[:2] == ['release', 'create']:
    assert '--verify-tag' in args
    assets.mkdir()
elif args[:2] == ['release', 'download']:
    name = args[args.index('--pattern') + 1]
    destination = Path(args[args.index('--dir') + 1]) / name
    destination.write_bytes((assets / name).read_bytes())
elif args[:2] == ['release', 'upload']:
    assert '--clobber' not in args
    source = Path(args[3])
    destination = assets / source.name
    assert not destination.exists()
    destination.write_bytes(source.read_bytes())
else:
    raise SystemExit('unexpected fixture gh command')
''')
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_GH_STATE", str(state))
    return state


@pytest.mark.parametrize("annotated", [False, True])
def test_publish_attaches_all_evidence_and_accepts_only_identical_existing_assets(repo, tmp_path, fake_gh, annotated):
    if annotated:
        git(repo, "tag", "-a", "v1.0.1", "-m", "candidate")
    else:
        git(repo, "tag", "v1.0.1")
    git(repo, "push", "publish", "refs/tags/v1.0.1")
    first = controller(repo, tmp_path / "first", "--publish", "--remote", "publish", "--repo", "fixture/repo")
    assert first.returncode == 0, first.stdout + first.stderr
    expected = {"package.tar.gz", "package.sha256", "receipt.json", "qualification.json",
                "claude-marketplace.json", "source-check.json"}
    assert {path.name for path in (fake_gh / "assets").iterdir()} == expected
    second = controller(repo, tmp_path / "second", "--publish", "--remote", "publish", "--repo", "fixture/repo")
    assert second.returncode == 0, second.stdout + second.stderr
    commands = [json.loads(line) for line in (fake_gh / "commands").read_text().splitlines()]
    assert sum(command[:2] == ["release", "upload"] for command in commands) == len(expected)
    assert sum(command[:2] == ["release", "download"] for command in commands) == len(expected)
    (fake_gh / "assets/package.tar.gz").write_bytes(b"conflicting existing asset")
    third = controller(repo, tmp_path / "third", "--publish", "--remote", "publish", "--repo", "fixture/repo")
    assert third.returncode != 0 and "overwrite forbidden" in third.stderr
    assert (fake_gh / "assets/package.tar.gz").read_bytes() == b"conflicting existing asset"


@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("existing_release", [False, True])
def test_correct_push_remote_cannot_authorize_wrong_publication_repository(
        repo, tmp_path, fake_gh, annotated, existing_release):
    candidate = git(repo, "rev-parse", "HEAD")
    release.publish_tag(repo, "publish", "v1.0.1", candidate)
    wrong = tmp_path / "wrong-publication.git"
    git(repo, "clone", "--bare", str(repo), str(wrong))
    git(wrong, "tag", "-d", "v1.0.1")
    if annotated:
        git(wrong, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "tag", "-a", "v1.0.1", "HEAD~", "-m", "wrong candidate")
    else:
        git(wrong, "tag", "v1.0.1", "HEAD~")
    mapping = fake_gh / "repositories.json"
    repositories = json.loads(mapping.read_text())
    repositories["fixture/wrong"] = str(wrong)
    mapping.write_text(json.dumps(repositories))
    if existing_release:
        (fake_gh / "assets").mkdir()
        (fake_gh / "assets/package.tar.gz").write_bytes(b"existing wrong-candidate asset")
    result = controller(repo, tmp_path / "artifacts", "--publish", "--remote", "publish", "--repo", "fixture/wrong")
    assert result.returncode != 0 and "fixture/wrong:v1.0.1 resolves to" in result.stderr
    assert release.remote_tag(repo, "publish", "v1.0.1") == candidate
    commands = [json.loads(line) for line in (fake_gh / "commands").read_text().splitlines()]
    assert all(command[0] == "api" for command in commands)
    if existing_release:
        assert (fake_gh / "assets/package.tar.gz").read_bytes() == b"existing wrong-candidate asset"
    else:
        assert not (fake_gh / "assets").exists()


def test_publication_tag_must_peel_to_a_commit(repo, fake_gh):
    git(repo, "tag", "v1.0.1", "HEAD^{tree}")
    git(repo, "push", "publish", "refs/tags/v1.0.1")
    with pytest.raises(release.ReleaseError, match="does not peel to a commit"):
        release.publish_assets(repo, "fixture/repo", "v1.0.1", git(repo, "rev-parse", "HEAD"), "notes", [])
    assert not (fake_gh / "assets").exists()


def test_nested_annotated_publication_tag_is_peeled(repo, fake_gh):
    git(repo, "tag", "-a", "inner", "-m", "inner tag")
    git(repo, "tag", "-a", "v1.0.1", "inner", "-m", "outer tag")
    git(repo, "push", "publish", "refs/tags/v1.0.1")
    release.verify_github_tag(repo, "fixture/repo", "v1.0.1", git(repo, "rev-parse", "HEAD"))


def test_publication_tag_changed_during_final_upload_is_not_reported_successful(repo, tmp_path, fake_gh, monkeypatch):
    candidate = git(repo, "rev-parse", "HEAD")
    release.publish_tag(repo, "publish", "v1.0.1", candidate)
    remote = Path(git(repo, "remote", "get-url", "publish"))
    asset = tmp_path / "asset.txt"
    asset.write_text("qualified evidence")
    real_run = release.run

    def raced_run(args, root, **kwargs):
        result = real_run(args, root, **kwargs)
        if args[:3] == ["gh", "release", "upload"]:
            git(remote, "update-ref", "refs/tags/v1.0.1", git(repo, "rev-parse", "HEAD~"))
        return result

    monkeypatch.setattr(release, "run", raced_run)
    with pytest.raises(release.ReleaseError, match="fixture/repo:v1.0.1 resolves to"):
        release.publish_assets(repo, "fixture/repo", "v1.0.1", candidate, "notes", [asset])


def test_release_lookup_error_is_not_treated_as_absent(repo, monkeypatch):
    monkeypatch.setattr(release, "run", lambda args, root, **kwargs:
                        subprocess.CompletedProcess(args, 1, "", "HTTP 503 service unavailable"))
    with pytest.raises(release.ReleaseError, match="could not inspect release"):
        release.release_info(repo, "fixture/repo", "v1.0.1")
