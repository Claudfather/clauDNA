#!/usr/bin/env python3
"""Qualify an exported package with local fixtures, never native installation.

This is a focused distribution gate, not the full source check-set. The release
controller must separately bind a fresh `make check` to the same commit.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

import release_toolchain  # noqa: E402
from package_release import (ARCHIVE, archive_bytes, digest,  # noqa: E402
                             file_receipt, package_version, pinned_descriptor,
                             require, safe_path, write_json)


def read_tree(stage: Path) -> dict[str, tuple[str, bytes]]:
    require(stage.is_dir() and not stage.is_symlink(), "missing staged package")
    files = {}
    for directory, folders, names in os.walk(stage):
        current = Path(directory)
        require(current.stat().st_mode & 0o7777 == 0o555, "staged directory is not read-only")
        for name in folders:
            require(not (current / name).is_symlink(), "staged symlink")
        for name in names:
            path = current / name
            relative = path.relative_to(stage).as_posix()
            safe_path(relative)
            require(path.is_file() and not path.is_symlink(), "staged non-regular file")
            mode = path.stat().st_mode & 0o7777
            require(mode in (0o444, 0o555), "unsafe or writable staged mode")
            files[relative] = ("100755" if mode == 0o555 else "100644", path.read_bytes())
    return dict(sorted(files.items()))


def verify_package(output: Path) -> dict:
    for name in ("receipt.json", ARCHIVE, "package.sha256", "claude-marketplace.json"):
        path = output / name
        require(path.is_file() and not path.is_symlink(), "missing or linked package artifact")
    receipt = json.loads((output / "receipt.json").read_text())
    require(receipt["schema"] == "claudna.package-release/1", "unsupported receipt schema")
    require(re.fullmatch(r"[0-9a-f]{40}", receipt["commit"]) is not None, "invalid receipt commit")
    files = read_tree(output / "package")
    require(receipt["files"] == file_receipt(files), "staged files differ from receipt")
    require(receipt["version"] == package_version(files), "receipt version mismatch")
    archive = (output / ARCHIVE).read_bytes()
    require(archive == archive_bytes(files), "archive differs from staged tracked files")
    expected_archive = {"name": ARCHIVE, "sha256": digest(archive)}
    require(receipt["archive"] == expected_archive, "archive checksum mismatch")
    require((output / "package.sha256").read_text() == f"{digest(archive)}  {ARCHIVE}\n",
            "checksum file mismatch")
    descriptor = (output / "claude-marketplace.json").read_bytes()
    require(receipt["descriptor"] == {"name": "claude-marketplace.json", "sha256": digest(descriptor)},
            "descriptor checksum mismatch")
    require(json.loads(descriptor) == pinned_descriptor(files, receipt["commit"]), "descriptor commit mismatch")
    return receipt


def fixture_environment(root: Path) -> dict[str, str]:
    """A fresh allowlist; no inherited provider credentials or Python/Git config."""
    for name in ("home", "tmp", "cwd", "bin"):
        (root / name).mkdir(mode=0o700)
    (root / "bin/python3").symlink_to(sys.executable)
    for name in ("claude", "codex", "claudron", "gh", "node", "npx"):
        sentinel = root / "bin" / name
        sentinel.write_text('#!/bin/sh\nprintf rejected > "$HOME/provider-attempt"\nexit 97\n')
        sentinel.chmod(0o700)
    # A project named like a stdlib module must not shadow packaged execution.
    (root / "cwd/json.py").write_text("raise RuntimeError('unrelated cwd imported')\n")
    return {"HOME": str(root / "home"), "TMPDIR": str(root / "tmp"), "TMP": str(root / "tmp"),
            "TEMP": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "home/.cache"),
            "PATH": str(root / "bin") + os.pathsep + os.defpath, "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "CLAUDNA_STATE_DIR": str(root / "state"), "CLAUDNA_SESSION_BRIEFING": "0",
            "CLAUDNA_SESSION_SUMMARY": "0", "CLAUDNA_HARVEST": "0", "CLAUDNA_CAPTURE_PROMPTS": "0",
            "CLAUDNA_SESSION_STORE": "1", "CLAUDNA_TELEMETRY": "0", "CLAUDE_CODE_ENTRYPOINT": "cli"}


def run(command: list[str], cwd: Path, env: dict[str, str], *, payload: dict | None = None,
        codes: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, env=env, input=json.dumps(payload or {}),
                            text=True, capture_output=True, timeout=30)
    require(result.returncode in codes and not result.stderr,
            f"packaged command failed: {Path(command[0]).name}")
    return result


def hook_commands(stage: Path, host: str) -> dict[str, list[str]]:
    filename = "codex-hooks.json" if host == "codex" else "hooks.json"
    config = json.loads((stage / "plugin-hooks" / filename).read_text())["hooks"]
    prefix = "${PLUGIN_ROOT}/" if host == "codex" else "${CLAUDE_PLUGIN_ROOT}/"
    selected = {}
    for event, groups in config.items():
        for group in groups:
            for handler in group["hooks"]:
                words = shlex.split(handler["command"])
                if words[0] != prefix + "plugin-hooks/session-store.sh":
                    continue
                require(event not in selected, "duplicate store handler")
                expected = ["--host", "codex", event] if host == "codex" else [event]
                require(words[1:] == expected, "store handler host isolation mismatch")
                selected[event] = [str(stage / words[0][len(prefix):]), *words[1:]]
    require(set(selected) == {"SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact", "SessionEnd"}
            | ({"PostToolUseFailure"} if host == "claude-code" else set()), "store handler membership mismatch")
    return selected


def no_hook_errors(state: Path) -> None:
    for path in (state / "hooks").glob("*"):
        if path.name.endswith((".stderr", ".log")):
            require(path.stat().st_size == 0, "packaged hook recorded errors despite exit zero")


def no_provider_work(root: Path) -> None:
    require(not list(root.rglob("provider-attempt")), "fixture attempted a provider command")
    require(not list(root.rglob("skill-events.jsonl")), "compatibility telemetry opt-out ignored")


def lifecycle(stage: Path, host: str, root: Path, version: str) -> dict:
    env = fixture_environment(root)
    state, cwd = root / "state", root / "cwd"
    commands = hook_commands(stage, host)
    # Avoid a detached maintenance sweep in this fresh synthetic store; exercise
    # the synchronous hooks, with summary/harvest/briefing explicitly disabled.
    (state / "hooks").mkdir(parents=True, mode=0o700)
    (state / "hooks/unclosed-sweep.last").touch(mode=0o600)
    sid = "package-fixture-" + host
    transcript = root / "fixture.jsonl"
    transcript.write_bytes(b"")
    payload = {"session_id": sid, "transcript_path": str(transcript), "cwd": str(cwd)}

    def fire(event: str, **fields) -> None:
        result = run(commands[event], cwd, env, payload={**payload, "hook_event_name": event, **fields})
        require(not result.stdout, "store hook produced output")
        no_hook_errors(state)

    fire("SessionStart", source="startup")
    fire("UserPromptSubmit", prompt="synthetic package fixture", prompt_id="fixture-prompt")
    # This tests the configured adapter with a fixture, not a claim that Codex
    # exposes a native Skill callback or that a workflow was executed.
    fire("PostToolUse", tool_name="Skill", tool_input={"skill": "claudna:audit"})
    transcript.write_bytes(b"fixture\n")
    fire("PreCompact", trigger="manual")
    fire("SessionStart", source="compact")
    fire("SessionEnd", reason="other")
    session_dir = state / "sessions" / sid
    session = json.loads((session_dir / "session.json").read_text())
    expected_host = "codex" if host == "codex" else "claude"
    require(session["status"] == "closed" and session["agent_cli"] == expected_host,
            "packaged lifecycle did not close for selected host")
    entry = json.loads((state / "entrypoint.json").read_text())
    require(entry["plugin_root"] == str(stage) and entry["plugin_version"] == version
            and entry["agent_cli"] == expected_host, "hook executed a different package")
    events = [json.loads(line) for line in (session_dir / "lifecycle.jsonl").read_text().splitlines()]
    kinds = [event["kind"] for event in events]
    require(kinds.count("session.opened") == 1 and kinds.count("session.closed") == 1
            and kinds.count("segment.opened") == 2 and kinds.count("segment.sealed") == 2,
            "incomplete persisted lifecycle")
    for number in (1, 2):
        segment = json.loads((session_dir / f"seg-{number:03d}/segment.json").read_text())
        require(segment["status"] == "sealed", "segment did not seal")
    activity = [json.loads(line) for line in (session_dir / "seg-001/events.jsonl").read_text().splitlines()]
    require([event["kind"] for event in activity] == ["prompt.submitted", "skill.invoked"],
            "packaged hook activity missing")
    require("text" not in activity[0]["data"], "prompt capture opt-out ignored")
    run([sys.executable, "-S", "-B", str(stage / "lib/claudna/session_store"), "check", sid,
         "--root", str(state)], cwd, env)
    no_hook_errors(state)
    no_provider_work(root)
    require(not any((state / "hooks" / name).exists() for name in
                    ("summarizer.stderr", "harvest.stderr", "sweep.stderr")),
            "fixture started disabled detached work")
    require(not (state / "harvest").exists() and not list(state.glob("sessions/*/seg-*/summary.json")),
            "disabled provider work produced state")
    # Each opt-out gets its own environment and entirely absent store.
    for setting, value in (("CLAUDNA_SESSION_STORE", "0"), ("CLAUDNA_SESSION_CHILD", "1")):
        opt = root / setting
        opt.mkdir()
        opt_env = fixture_environment(opt)
        opt_env[setting] = value
        for event, command in commands.items():
            result = run(command, opt / "cwd", opt_env, payload={**payload, "source": "startup",
                         "hook_event_name": event, "prompt": "fixture"})
            require(not result.stdout and not (opt / "state").exists(), "store opt-out ignored")
    return {"agent_cli": expected_host, "lifecycle_events": kinds, "prompt_events": 1, "opt_out": True}


def doctor(stage: Path, host: str, root: Path, version: str) -> None:
    env = fixture_environment(root)
    before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    result = run([sys.executable, "-S", "-B", str(stage / "lib/claudna/package_support"),
                  "doctor", "--host", host, "--json"], root / "cwd", env, codes=(0, 1))
    document = json.loads(result.stdout)
    checks = {check["id"]: check["status"] for check in document["checks"]}
    require(document["package_version"] == version and checks["package.integrity"] == "pass"
            and checks["package.selection"] == "pass" and checks["runtime.python"] == "pass"
            and checks["runtime.platform"] == "pass", "packaged doctor failed")
    require(all(checks["native." + key] == "unknown" for key in ("installed", "discovered", "trusted", "executed")),
            "doctor overclaimed native evidence")
    require(before == sorted(str(path.relative_to(root)) for path in root.rglob("*")), "doctor wrote fixture state")


def qualify(output: Path) -> dict:
    output = output.resolve()
    require(not (output / "qualification.json").exists() and not (output / "qualification.json").is_symlink(),
            "qualification output already exists")
    receipt = verify_package(output)
    release_toolchain.ensure_toolchain()
    stage = output / "package"
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=output) as temp:
        root = Path(temp)
        validation = root / "validation"
        validation.mkdir()
        env = fixture_environment(validation)
        for script, flags in (("generate_package_support.py", ["--check"]), ("validate-manifest.py", []),
                              ("validate-skills.py", []), ("integration-test.py", [])):
            run([sys.executable, "-B", str(stage / "scripts" / script), *flags], validation / "cwd", env)
        catalog = json.loads((stage / "lib/claudna/package_support/catalog.json").read_text())
        require(catalog["hosts"]["cursor"]["hooks"]["handler_count"] == 0
                and catalog["hosts"]["codex"]["hooks"]["handler_count"] == 6,
                "host hook scope changed")
        manifest = json.loads((stage / ".codex-plugin/plugin.json").read_text())
        require(manifest["agents"] == "./.codex-plugin/store-only"
                and sorted(path.name for path in (stage / ".codex-plugin/store-only").iterdir()) == [".gitkeep"],
                "Codex agents are not inert")
        fixtures = {}
        for host in ("claude-code", "codex", "cursor"):
            location = root / ("doctor-" + host)
            location.mkdir()
            doctor(stage, host, location, receipt["version"])
            if host != "cursor":
                location = root / host
                location.mkdir()
                fixtures[host] = lifecycle(stage, host, location, receipt["version"])
                # Exercise the packaged startup opt-out without live context or provider reads.
                config = json.loads((stage / "plugin-hooks" / ("codex-hooks.json" if host == "codex"
                                                             else "hooks.json")).read_text())
                startup = [handler["command"] for group in config["hooks"]["SessionStart"]
                           for handler in group["hooks"] if "session-start.sh" in handler["command"]]
                require(len(startup) == 1, "missing startup briefing handler")
                prefix = "${PLUGIN_ROOT}/" if host == "codex" else "${CLAUDE_PLUGIN_ROOT}/"
                words = shlex.split(startup[0])
                host_args = ["--host", "codex"] if host == "codex" else []
                require(words == [prefix + "plugin-hooks/session-start.sh", *host_args],
                        "unexpected startup handler")
                startup_root = root / ("startup-" + host)
                startup_root.mkdir()
                result = run([str(stage / words[0][len(prefix):]), *host_args], startup_root / "cwd",
                             fixture_environment(startup_root))
                require(not result.stdout, "briefing opt-out ignored")
                no_hook_errors(startup_root / "state")
        no_provider_work(root)
        require(verify_package(output) == receipt, "qualification modified package artifacts")
    result = {"schema": "claudna.package-qualification/1", "commit": receipt["commit"],
              "version": receipt["version"], "archive_sha256": receipt["archive"]["sha256"], "status": "pass",
              "checks": ["artifact-integrity", "staged-catalog", "staged-manifests", "staged-skills",
                         "staged-integration", "host-isolation",
                         "packaged-doctor", "packaged-lifecycle", "capture-opt-outs", "read-only-package"],
              "fixtures": fixtures, "native_acceptance": "unknown", "full_source_check": "not_run"}
    write_json(output / "qualification.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True, help="Owned output of package_release.py")
    args = parser.parse_args(argv)
    try:
        result = qualify(args.package)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"package qualification: {exc}\n")
    print(f"package qualification: fixture pass for {result['commit']}; native acceptance unknown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
