"""The support projection must follow authoritative inputs without widening scope."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_package_support as support  # noqa: E402


@pytest.fixture
def package(tmp_path):
    catalog = json.loads((ROOT / support.CATALOG).read_text())
    for relative in [*catalog["sources"], support.GUIDE, support.CATALOG]:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    return tmp_path


def change_json(path, update):
    data = json.loads(path.read_text())
    update(data)
    path.write_text(json.dumps(data))


def test_current_projection_and_host_boundaries():
    assert support.generate(ROOT, check=True) == []
    catalog = support.build_catalog(ROOT)
    assert {name: host["skill_count"] for name, host in catalog["hosts"].items()} == {
        "claude-code": 40, "cursor": 35, "codex": 37,
    }
    assert catalog["hosts"]["cursor"]["hooks"]["handler_count"] == 0
    assert catalog["hosts"]["codex"]["hooks"]["handler_count"] == 6
    assert catalog["skills"]["promotion-intake"]["requires_context"] == "repo-clone"
    assert "promotion-intake" not in catalog["hosts"]["codex"]["skills"]
    for relative, digest in catalog["sources"].items():
        assert not Path(relative).is_absolute()
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_frontmatter_drift_check_does_not_write(package, capsys):
    skill = package / "skills/audit/SKILL.md"
    skill.write_text(skill.read_text().replace("Use for", "Use when reviewing", 1))
    before = {relative: (package / relative).read_bytes() for relative in (support.CATALOG, support.GUIDE)}
    assert support.main(["--root", str(package), "--check"]) == 1
    assert "drift" in capsys.readouterr().err
    assert before == {relative: (package / relative).read_bytes() for relative in before}
    assert support.generate(package)
    assert support.generate(package, check=True) == []


def test_manifest_selection_change_rejected_without_writing(package, capsys):
    change_json(package / ".codex-plugin/plugin.json", lambda data: data["skills"].pop())
    before = (package / support.CATALOG).read_bytes()
    assert support.main(["--root", str(package), "--check"]) == 1
    assert "missing eligible skill" in capsys.readouterr().err
    assert (package / support.CATALOG).read_bytes() == before


def test_consistent_selection_change_is_still_detected(package):
    # Change both owners coherently: scope validation passes, but old projection must fail.
    name = "worktree"
    skill = package / f"skills/{name}/SKILL.md"
    skill.write_text(skill.read_text().replace("---\n", "---\nhosts: [claude-code]\n", 1))
    for host in ("cursor", "codex"):
        def remove(data):
            data["skills"] = [entry for entry in data["skills"] if entry.rstrip("/").split("/")[-1] != name]
        change_json(package / f".{host}-plugin/plugin.json", remove)
    assert set(support.generate(package, check=True)) == {support.CATALOG, support.GUIDE}


@pytest.mark.parametrize("host", ["cursor", "codex"])
def test_restricted_skill_cannot_be_selected(package, host):
    change_json(package / f".{host}-plugin/plugin.json",
                lambda data: data["skills"].append("./skills/promotion-intake"))
    with pytest.raises(ValueError, match="restricted|excluded"):
        support.build_catalog(package)


@pytest.mark.parametrize("metadata", ["hosts: [unknown]\n", "requires: [invalid]\n", "requires-context: elsewhere\n"])
def test_invalid_frontmatter_is_rejected(package, metadata):
    skill = package / "skills/worktree/SKILL.md"
    skill.write_text(skill.read_text().replace("---\n", "---\n" + metadata, 1))
    with pytest.raises(ValueError, match="skills/worktree/SKILL.md"):
        support.build_catalog(package)


@pytest.mark.parametrize("payload", ["[1]", "{bad json", '{"schema": "unknown", "hosts": {}}'])
def test_invalid_policy_reports_an_error(package, payload, capsys):
    (package / support.POLICY).write_text(payload)
    assert support.main(["--root", str(package), "--check"]) == 1
    assert "package support:" in capsys.readouterr().err


def test_version_and_hook_changes_require_refresh(package):
    for host in ("claude", "cursor", "codex"):
        change_json(package / f".{host}-plugin/plugin.json", lambda data: data.update(version="0.34.99"))
    assert set(support.generate(package, check=True)) == {support.CATALOG, support.GUIDE}
    support.generate(package)
    hook = package / "plugin-hooks/codex-hooks.json"
    hook.write_text(hook.read_text() + "\n")
    assert support.generate(package, check=True) == [support.CATALOG]


def test_version_mismatch_is_rejected(package):
    change_json(package / ".codex-plugin/plugin.json", lambda data: data.update(version="0.34.99"))
    with pytest.raises(ValueError, match="versions disagree"):
        support.build_catalog(package)


@pytest.mark.parametrize("relative", ["../outside.json", "/tmp/outside.json", "..\\outside.json"])
def test_source_path_escape_is_rejected(package, relative):
    change_json(package / support.POLICY,
                lambda data: data["hosts"]["codex"].update(manifest=relative))
    with pytest.raises(ValueError, match="path"):
        support.build_catalog(package)


def test_symlink_escape_is_rejected(package, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("{}")
    manifest = package / ".claude-plugin/plugin.json"
    manifest.unlink()
    manifest.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes package root"):
        support.build_catalog(package)


def test_missing_markers_never_overwrites_guide_or_catalog(package):
    guide = package / support.GUIDE
    guide.write_text("hand-authored guide\n")
    before = (package / support.CATALOG).read_bytes()
    with pytest.raises(ValueError, match="generated markers"):
        support.generate(package)
    assert guide.read_text() == "hand-authored guide\n"
    assert (package / support.CATALOG).read_bytes() == before


def test_local_support_links_resolve():
    import re

    guide = ROOT / support.GUIDE
    for target in re.findall(r"\]\(([^)]+)\)", guide.read_text()):
        if "://" not in target:
            assert (guide.parent / target.split("#", 1)[0]).exists(), target
