"""Exact-ref exports and packaged fixture evidence; no installed host state."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from package_release import PackageError, build, safe_path  # noqa: E402
from qualify_package import fixture_environment, qualify, verify_package  # noqa: E402


def git(root, *args):
    env = {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_AUTHOR_NAME": "Package fixture", "GIT_AUTHOR_EMAIL": "fixture@localhost",
           "GIT_COMMITTER_NAME": "Package fixture", "GIT_COMMITTER_EMAIL": "fixture@localhost"}
    return subprocess.check_output(["git", "-C", str(root), *args], env=env, text=True).strip()


@pytest.fixture
def repo(tmp_path):
    """The isolated source-check export includes the complete candidate tooling."""
    path = tmp_path / "repo"
    git(ROOT, "clone", "--quiet", "--no-hardlinks", str(ROOT), str(path))
    return path


def commit(repo):
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "-m", "package fixture")
    return git(repo, "rev-parse", "HEAD")


def test_reproducible_full_tracked_export_ignores_dirty_files_and_export_attributes(repo, tmp_path):
    (repo / "fixture-run.sh").write_text("#!/bin/sh\nexit 0\n")
    (repo / "fixture-run.sh").chmod(0o755)
    (repo / "fixture-data.txt").write_text("$Format:%H$\n")
    (repo / ".gitattributes").write_text("fixture-run.sh export-ignore\nfixture-data.txt export-subst\n")
    ref = commit(repo)
    (repo / "README.md").write_text("dirty secret excluded")
    (repo / "untracked-secret").write_text("excluded")
    first, second = tmp_path / "first output", tmp_path / "second"
    receipt = build(repo, ref, first)
    build(repo, ref, second)
    for name in ("package.tar.gz", "receipt.json", "package.sha256", "claude-marketplace.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert receipt == verify_package(first)
    assert receipt["commit"] == ref
    assert "dirty secret" not in (first / "package/README.md").read_text()
    assert not (first / "package/untracked-secret").exists()
    assert (first / "package/fixture-data.txt").read_text() == "$Format:%H$\n"
    assert (first / "package/fixture-run.sh").stat().st_mode & 0o777 == 0o555
    assert (first / "package/fixture-data.txt").stat().st_mode & 0o777 == 0o444
    with tarfile.open(first / "package.tar.gz") as archive:
        members = archive.getmembers()
        assert [entry.name for entry in members] == sorted(receipt["files"])
        assert archive.getmember("fixture-run.sh").mode == 0o755
        assert archive.getmember("fixture-data.txt").mode == 0o644
        assert all(entry.uid == entry.gid == entry.mtime == 0 and not entry.uname and not entry.gname
                   and entry.isfile() for entry in members)
    header = (first / "package.tar.gz").read_bytes()[:10]
    assert header[3] == 0 and header[4:8] == b"\0" * 4  # no filename or timestamp
    descriptor = json.loads((first / "claude-marketplace.json").read_text())
    assert descriptor["plugins"][0]["source"] == {
        "source": "github", "repo": "Claudfather/clauDNA", "sha": ref}
    assert "sha" not in json.loads((first / "package/.claude-plugin/marketplace.json").read_text())["plugins"][0]["source"]


def test_explicit_ref_resolved_once_even_when_branch_moves(repo, tmp_path, monkeypatch):
    import package_release

    before = git(repo, "rev-parse", "HEAD")
    original = package_release.tracked_files

    def move_branch(root, resolved):
        (repo / "late-file").write_text("must not ship")
        commit(repo)
        return original(root, resolved)

    monkeypatch.setattr(package_release, "tracked_files", move_branch)
    result = build(repo, "HEAD", tmp_path / "output")
    assert result["commit"] == before and "late-file" not in result["files"]


@pytest.mark.parametrize("relative", ["", ".", "../file", "/file", "a/../b", "a//b", "./file",
                                      "a\\b", ".git/config", "x/.GiT/config", "line\nbreak"])
def test_path_escape_or_nonportable_name_is_rejected(relative):
    with pytest.raises(PackageError, match="unsafe tracked path"):
        safe_path(relative)


@pytest.mark.parametrize("mode", ["symlink", "submodule"])
def test_git_links_and_submodules_are_rejected(repo, tmp_path, mode):
    if mode == "symlink":
        (repo / "escaping-link").symlink_to("../../outside")
    else:
        git(repo, "update-index", "--add", "--cacheinfo", "160000", git(repo, "rev-parse", "HEAD"), "gitlink")
    if mode == "symlink":
        ref = commit(repo)
    else:
        git(repo, "commit", "--quiet", "-m", "package gitlink fixture")
        ref = git(repo, "rev-parse", "HEAD")
    with pytest.raises(PackageError, match="unsupported tracked mode"):
        build(repo, ref, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_existing_output_is_never_clobbered(repo, tmp_path, kind):
    output = tmp_path / "existing"
    if kind == "directory":
        output.mkdir()
        (output / "keep").write_text("retained")
    else:
        output.symlink_to(tmp_path / "missing")
    with pytest.raises(FileExistsError):
        build(repo, "HEAD", output)
    assert output.is_symlink() if kind == "symlink" else (output / "keep").read_text() == "retained"


def test_qualification_toolchain_failure_precedes_output_writes(repo, tmp_path, monkeypatch):
    import release_toolchain

    def unavailable():
        raise release_toolchain.ToolchainError("isolated development toolchain unavailable")

    monkeypatch.setattr(release_toolchain, "ensure_toolchain", unavailable)
    rejected = tmp_path / "rejected"
    with pytest.raises(release_toolchain.ToolchainError, match="toolchain unavailable"):
        build(repo, "HEAD", rejected, qualify=True)
    assert not rejected.exists()

    # Pure packaging still needs only stdlib; standalone qualification also
    # fails without allocating fixture state or recording passing evidence.
    output = tmp_path / "stdlib-package"
    receipt = build(repo, "HEAD", output)
    with pytest.raises(release_toolchain.ToolchainError, match="toolchain unavailable"):
        qualify(output)
    assert verify_package(output) == receipt
    assert not (output / "qualification.json").exists() and not list(output.glob("fixture-*"))


def test_fixture_environment_does_not_inherit_secrets_or_provider_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    monkeypatch.setenv("CLAUDNA_ROOT", "hostile")
    monkeypatch.setenv("PYTHONPATH", "hostile")
    env = fixture_environment(tmp_path)
    assert "must-not-leak" not in env.values()
    assert not {"ANTHROPIC_API_KEY", "CLAUDNA_ROOT", "PYTHONPATH"} & env.keys()
    assert all(env[name] == "0" for name in ("CLAUDNA_SESSION_BRIEFING", "CLAUDNA_SESSION_SUMMARY",
                                            "CLAUDNA_HARVEST", "CLAUDNA_CAPTURE_PROMPTS", "CLAUDNA_TELEMETRY"))
    result = subprocess.run([str(tmp_path / "bin/claude")], env=env, capture_output=True)
    assert result.returncode == 97 and (tmp_path / "home/provider-attempt").read_text() == "rejected"


def test_staged_lifecycle_and_doctor_are_deterministic_fixture_only_evidence(repo, tmp_path, maintainer_toolchain):
    first, second = tmp_path / "first", tmp_path / "second"
    receipt = build(repo, "HEAD", first, qualify=True)
    build(repo, "HEAD", second, qualify=True)
    result = json.loads((first / "qualification.json").read_text())
    assert (first / "qualification.json").read_bytes() == (second / "qualification.json").read_bytes()
    assert result["commit"] == receipt["commit"] and result["archive_sha256"] == receipt["archive"]["sha256"]
    assert result["status"] == "pass" and result["native_acceptance"] == "unknown"
    assert result["full_source_check"] == "not_run"
    assert set(result["fixtures"]) == {"claude-code", "codex"}
    assert result["fixtures"]["codex"]["agent_cli"] == "codex"
    assert result["fixtures"]["claude-code"]["agent_cli"] == "claude"
    assert not list(first.glob("fixture-*"))
    assert verify_package(first) == receipt
    with pytest.raises(PackageError, match="already exists"):
        qualify(first)


@pytest.mark.parametrize("relative", ["plugin-hooks/lib/state-dir.sh", "lib/claudna/session_store/schema.py",
                                      "skills/audit/SKILL.md"])
def test_missing_tracked_runtime_or_catalog_closure_fails(repo, tmp_path, relative, maintainer_toolchain):
    (repo / relative).unlink()
    ref = commit(repo)
    with pytest.raises((PackageError, OSError)):
        build(repo, ref, tmp_path / "output", qualify=True)
    assert not (tmp_path / "output/qualification.json").exists()


@pytest.mark.parametrize("relative", ["skills/claudron/lookup.md", "skills/_shared/audit-lens-contract.md"])
def test_missing_ancillary_skill_resource_fails_even_with_ambient_ci_scoping(
    repo, tmp_path, monkeypatch, relative, maintainer_toolchain,
):
    # Neither ancillary file is a catalog hash source. The staged source
    # validators must still catch the surviving SKILL.md reference, even when
    # the caller is a CI process that could otherwise demote untouched errors.
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("PR_LABELS", "")
    (repo / relative).unlink()
    ref = commit(repo)
    output = tmp_path / "output"
    receipt = build(repo, ref, output)
    assert relative not in receipt["files"]
    assert verify_package(output) == receipt
    with pytest.raises(PackageError, match="packaged command failed"):
        qualify(output)
    assert not (output / "qualification.json").exists()


@pytest.mark.parametrize("body", ["#!/bin/bash\nexit 0\n",
                                  '#!/bin/bash\nmkdir -p "$CLAUDNA_STATE_DIR/hooks"\n'
                                  'echo failed > "$CLAUDNA_STATE_DIR/hooks/errors.log"\nexit 0\n'])
def test_fail_open_hook_is_not_passing_evidence(repo, tmp_path, body, maintainer_toolchain):
    (repo / "plugin-hooks/session-store.sh").write_text(body)
    ref = commit(repo)
    with pytest.raises((PackageError, OSError)):
        build(repo, ref, tmp_path / "output", qualify=True)
    assert not (tmp_path / "output/qualification.json").exists()


def test_ignored_optout_is_detected(repo, tmp_path, maintainer_toolchain):
    hook = repo / "plugin-hooks/session-store.sh"
    hook.write_text(hook.read_text().replace('[ "${CLAUDNA_SESSION_STORE:-1}" = "0" ] && exit 0', ""))
    ref = commit(repo)
    with pytest.raises(PackageError, match="opt-out"):
        build(repo, ref, tmp_path / "output", qualify=True)


def test_unexpected_provider_attempt_is_rejected_locally(repo, tmp_path, maintainer_toolchain):
    hook = repo / "plugin-hooks/session-store.sh"
    hook.write_text(hook.read_text().replace("#!/bin/bash", "#!/bin/bash\nclaude >/dev/null 2>&1 || true", 1))
    ref = commit(repo)
    with pytest.raises(PackageError, match="provider command"):
        build(repo, ref, tmp_path / "output", qualify=True)
    assert not (tmp_path / "output/qualification.json").exists()


@pytest.mark.parametrize("change", ["checksum", "receipt", "tree_mode", "descriptor"])
def test_tampering_fails_binding_before_execution(repo, tmp_path, change):
    output = tmp_path / "output"
    build(repo, "HEAD", output)
    if change == "tree_mode":
        (output / "package/README.md").chmod(0o644)
    elif change == "checksum":
        (output / "package.sha256").write_text("wrong")
    elif change == "descriptor":
        path = output / "claude-marketplace.json"
        document = json.loads(path.read_text())
        document["plugins"][0]["source"]["sha"] = "0" * 40
        path.write_text(json.dumps(document))
    else:
        path = output / "receipt.json"
        document = json.loads(path.read_text())
        document["archive"]["sha256"] = "0" * 64
        path.write_text(json.dumps(document))
    with pytest.raises(PackageError):
        qualify(output)
    assert not (output / "qualification.json").exists()
