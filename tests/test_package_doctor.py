"""Exercise the shipped directory CLI in isolation, including its failure boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from claudna.package_support.catalog import CATALOG
from claudna.package_support.doctor import diagnose

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "relocated package with spaces"
    for name in ("lib", "skills", "plugin-hooks", "agents", "assets", ".claude-plugin",
                 ".codex-plugin", ".cursor-plugin", ".agents"):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return root


def change_json(path, update):
    data = json.loads(path.read_text())
    update(data)
    path.write_text(json.dumps(data))


def snapshot(root):
    return {str(path.relative_to(root)): ("directory" if path.is_dir() else
            "link:" + str(path.readlink()) if path.is_symlink() else path.read_bytes())
            for path in root.rglob("*")}


def run(package, tmp_path, *args, env=None):
    cwd, home, temp = [tmp_path / part for part in ("hostile cwd", "home", "tmp")]
    for directory in (cwd, home, temp):
        directory.mkdir(exist_ok=True)
    for module in ("json", "pathlib", "hashlib", "shutil", "argparse", "typing"):
        (cwd / f"{module}.py").write_text("raise RuntimeError('HOSTILE_MODULE_IMPORTED')\n")
    variables = {"HOME": str(home), "TMPDIR": str(temp), "TMP": str(temp), "TEMP": str(temp),
                 "PATH": "", "CLAUDNA_ROOT": str(cwd), "CLAUDE_PLUGIN_ROOT": str(cwd),
                 "PLUGIN_ROOT": str(cwd), "CLAUDNA_STORE_ROOT": str(home / "private-store")}
    variables.update(env or {})
    before = snapshot(tmp_path)
    proc = subprocess.run([sys.executable, "-S", "-B", str(package / "lib/claudna/package_support"),
                           "doctor", *args], cwd=cwd, env=variables, text=True, capture_output=True)
    assert snapshot(tmp_path) == before, "doctor changed package, HOME, TMP or working directory"
    assert not proc.stderr, proc.stderr
    assert "HOSTILE_MODULE_IMPORTED" not in proc.stdout
    return proc


def rows(result):
    return {entry["id"]: entry for entry in result["checks"]}


def test_real_directory_cli_defaults_to_loaded_package_not_cwd_or_env(package, tmp_path):
    proc = run(package, tmp_path, "--host", "cursor", "--json")
    result = json.loads(proc.stdout)
    assert proc.returncode == result["exit_code"] == 0
    assert result["status"] == "observed"
    assert result["schema"] == "claudna.package-doctor/1"
    assert result["package_version"] == json.loads((package / CATALOG).read_text())["package_version"]
    assert rows(result)["package.integrity"]["status"] == "pass"
    assert "35 skills and 0 hook handlers" in rows(result)["package.selection"]["summary"]
    assert result["pipeline_health"] is None
    for state in ("installed", "discovered", "trusted", "executed"):
        assert rows(result)[f"native.{state}"]["status"] == "unknown"


def test_absent_tools_are_scoped_attention_not_global_failure(package, tmp_path):
    proc = run(package, tmp_path, "--host", "claude-code", "--json")
    result = json.loads(proc.stdout)
    assert proc.returncode == result["exit_code"] == 1
    assert result["status"] == "attention"
    checks = rows(result)
    assert checks["runtime.python"]["status"] == "pass"
    assert checks["baseline.cli.python3"]["status"] == "warn"
    for name in ("bash", "jq", "gh", "git", "node", "npx"):
        assert checks[f"baseline.cli.{name}"]["status"] == "warn"
        assert "only workflows" in checks[f"baseline.cli.{name}"]["summary"]
    assert "silently does nothing" in checks["baseline.cli.jq"]["summary"]


def test_versioned_binary_is_never_executed_or_certified(package, tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    executable = tools / "claudron"
    executable.write_text("#!/bin/sh\nprintf secret-tool-output\ntouch executed\n")
    executable.chmod(0o755)
    proc = run(package, tmp_path, "--host", "cursor", "--skill", "capture", "--json", env={"PATH": str(tools)})
    result = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert rows(result)["skill.cli.claudron"]["status"] == "unknown"
    assert "0.2 unverified" in rows(result)["skill.cli.claudron"]["summary"]
    assert "secret-tool-output" not in proc.stdout


@pytest.mark.parametrize("value,present", [("ENV_SECRET_TOKEN", True), ("", False)])
def test_environment_checks_return_presence_only(package, tmp_path, value, present):
    change_json(package / CATALOG, lambda data: data["skills"]["audit"].update(
        requires=[{"env": "DOCTOR_TEST_TOKEN"}]))
    proc = run(package, tmp_path, "--host", "cursor", "--skill", "audit", "--json",
               env={"DOCTOR_TEST_TOKEN": value})
    result = json.loads(proc.stdout)
    assert rows(result)["skill.env.DOCTOR_TEST_TOKEN"]["status"] == ("pass" if present else "warn")
    assert "ENV_SECRET_TOKEN" not in proc.stdout


@pytest.mark.parametrize("arguments", [[], ["--host", "secret-invalid-host"],
                                      ["--host", "cursor", "--skill", "secret-invalid-skill"],
                                      ["--host", "cursor", "--skill", "using-claudna"],
                                      ["--host", "cursor", "--invalid-secret-flag"]])
def test_invalid_requests_are_structured_without_echoing_values(package, tmp_path, arguments):
    proc = run(package, tmp_path, *arguments, "--json")
    result = json.loads(proc.stdout)
    assert proc.returncode == result["exit_code"] == 2
    assert result["status"] == "invalid"
    assert "secret" not in proc.stdout


@pytest.mark.parametrize("relative", [CATALOG, "skills/audit/SKILL.md", ".codex-plugin/plugin.json",
                                      "plugin-hooks/session-store.sh", "lib/claudna/session_store/__main__.py"])
def test_missing_bundled_files_fail_diagnosis(package, tmp_path, relative):
    (package / relative).unlink()
    proc = run(package, tmp_path, "--host", "cursor", "--json")
    assert proc.returncode == 2
    assert rows(json.loads(proc.stdout))["package.integrity"]["status"] == "fail"


@pytest.mark.parametrize("payload", ["{secret-invalid-json", "[]", "{}", '{"schema": 42}',
                                     '{"schema":"a","schema":"b"}', '{"secret":"\ud800"}'])
def test_malformed_metadata_never_leaks_parser_input(package, tmp_path, payload):
    (package / CATALOG).write_text(payload, errors="surrogatepass")
    proc = run(package, tmp_path, "--host", "codex", "--json")
    assert proc.returncode == 2
    assert "secret" not in proc.stdout


@pytest.mark.parametrize("relative", ["skills/audit/SKILL.md", ".codex-plugin/plugin.json",
                                      "lib/claudna/package_support/host-policy.json"])
def test_stale_source_hash_fails(package, tmp_path, relative):
    with (package / relative).open("a") as stream:
        stream.write("\n")
    proc = run(package, tmp_path, "--host", "codex", "--json")
    assert proc.returncode == 2
    assert "source_hash" in proc.stdout


@pytest.mark.parametrize("mutation", [
    lambda data: data["sources"].pop("skills/audit/SKILL.md"),
    lambda data: data["sources"].update({"../secret-outside": "0" * 64}),
    lambda data: data["skills"]["audit"].update(path="/secret-outside"),
    lambda data: data["skills"].pop("audit"),
    lambda data: data["hosts"]["cursor"]["skills"].pop(),
    lambda data: data["hosts"]["cursor"].update(runtime_prerequisites=[], skill_count=False),
    lambda data: data["hosts"]["codex"]["hooks"].update(handler_count=7),
    lambda data: data["skills"]["audit"].update(requires=[{"cli": "../secret-tool"}]),
])
def test_invalid_projection_or_membership_fails_closed(package, tmp_path, mutation):
    change_json(package / CATALOG, mutation)
    proc = run(package, tmp_path, "--host", "cursor", "--json")
    assert proc.returncode == 2
    assert "secret" not in proc.stdout


def test_new_skill_directory_requires_projection_refresh(package, tmp_path):
    directory = package / "skills/added-skill"
    directory.mkdir()
    (directory / "SKILL.md").write_text("new skill")
    proc = run(package, tmp_path, "--host", "codex", "--json")
    assert proc.returncode == 2
    assert "skill_membership" in proc.stdout


def test_manifest_change_detected_even_if_source_hash_refreshed(package, tmp_path):
    relative = ".codex-plugin/plugin.json"
    change_json(package / relative, lambda data: data["skills"].pop())
    change_json(package / CATALOG, lambda data: data["sources"].update(
        {relative: hashlib.sha256((package / relative).read_bytes()).hexdigest()}))
    proc = run(package, tmp_path, "--host", "codex", "--json")
    assert proc.returncode == 2
    assert "manifest_membership" in proc.stdout


@pytest.mark.parametrize("relative", [CATALOG, "skills/audit/SKILL.md", "plugin-hooks/session-store.sh"])
def test_symlink_escape_is_rejected_without_reading_target(package, tmp_path, relative):
    target = tmp_path / "outside-secret"
    target.write_text("NEVER_PRINT_THIS_SECRET")
    path = package / relative
    path.unlink()
    path.symlink_to(target)
    proc = run(package, tmp_path, "--host", "cursor", "--json")
    assert proc.returncode == 2
    assert "bundled_symlink" in proc.stdout
    assert "SECRET" not in proc.stdout


def test_explicit_root_missing_is_not_replaced_by_loaded_root(package, tmp_path):
    proc = run(package, tmp_path, "--host", "cursor", "--root", str(tmp_path / "secret-missing"), "--json")
    assert proc.returncode == 2
    assert "package_root" in proc.stdout
    assert "secret-missing" not in proc.stdout


def test_explicit_missing_store_is_unknown_and_never_created(package, tmp_path):
    proc = run(package, tmp_path, "--host", "cursor", "--store-root", str(tmp_path / "empty-store"), "--json")
    result = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert result["pipeline_health"]["status"] == "no_evidence"
    assert result["pipeline_health"]["draft_reviews"]["acceptance_fraction"] is None
    assert not (tmp_path / "empty-store").exists()


def test_optional_existing_health_reuses_store_boundary(package, tmp_path, store):
    from test_session_store_harvest import BLOCK, summarized_session

    summarized_session(store, "private-secret-session", [[BLOCK]]).set_private(True)
    summarized_session(store, "public-session", [[BLOCK]], agent_cli="codex")
    proc = run(package, tmp_path, "--host", "cursor", "--store-root", str(store.root), "--json")
    result = json.loads(proc.stdout)
    assert result["pipeline_health"]["private_sessions_excluded"] == 1
    assert result["pipeline_health"]["sessions_by_host"] == {"codex": 1}
    assert "private-secret-session" not in proc.stdout
    assert "public-session" not in proc.stdout
    assert "Always run" not in proc.stdout


def test_platform_support_and_interpreter_are_measured(package, monkeypatch):
    monkeypatch.setattr(sys, "platform", "unsupported")
    monkeypatch.setattr(sys, "version_info", (3, 8, 9))
    result = diagnose(root=package, host="codex", env={"PATH": ""})
    assert rows(result)["runtime.platform"]["status"] == "fail"
    assert rows(result)["runtime.python"]["status"] == "fail"
    assert rows(result)["baseline.cli.python3"]["status"] == "warn"
    assert result["exit_code"] == 1


def test_text_uses_same_status_contract(package, tmp_path):
    proc = run(package, tmp_path, "--host", "cursor")
    assert proc.returncode == 0
    assert "Package doctor: observed (exit 0)" in proc.stdout
    assert "UNKNOWN native.executed" in proc.stdout
    assert "not publisher authenticity" in proc.stdout


def test_help_documents_pre_entry_cache_suppression(package, tmp_path):
    proc = run(package, tmp_path, "--help")
    assert proc.returncode == 0
    assert "python3 -B <loaded-root>/lib/claudna/package_support" in proc.stdout
    assert "Keep -B" in proc.stdout


def test_ancillary_directory_and_claude_discovery_match_generator(package, tmp_path):
    (package / "skills/ancillary-files").mkdir()
    # Claude's directory discovery includes restricted host content by contract.
    change_json(package / CATALOG, lambda data: data["skills"]["cleanup-legacy-install"].update(hosts=["codex"]))
    proc = run(package, tmp_path, "--host", "cursor", "--json")
    assert proc.returncode == 0


def test_path_python_version_is_unknown_even_with_supported_running_python(package, tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("python3", "bash", "git"):
        binary = tools / name
        binary.write_text("#!/bin/sh\nprintf secret-output\ntouch executed\n")
        binary.chmod(0o755)
    proc = run(package, tmp_path, "--host", "codex", "--json", env={"PATH": str(tools)})
    checks = rows(json.loads(proc.stdout))
    assert proc.returncode == 0
    assert checks["runtime.python"]["status"] == "pass"
    assert checks["baseline.cli.python3"]["status"] == "unknown"
    assert "secret-output" not in proc.stdout
