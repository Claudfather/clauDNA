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
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True

import release_toolchain  # noqa: E402
from claudna.session_store.fsio import atomic_write_json  # noqa: E402
from package_release import (ARCHIVE, PackageError, archive_bytes, digest,  # noqa: E402
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


def filesystem_snapshot(root: Path, *, exclude: Path | None = None) -> dict:
    """Observe this fixture's paths, types, modes and bytes, including absence."""
    if not root.exists() and not root.is_symlink():
        return {}
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        if exclude is not None and (path == exclude or exclude in path.parents):
            continue
        mode = path.lstat().st_mode
        kind = "link" if stat.S_ISLNK(mode) else "dir" if stat.S_ISDIR(mode) else "file"
        value = {"type": kind, "mode": stat.S_IMODE(mode)}
        if kind == "link":
            value["sha256"] = digest(os.readlink(path).encode())
        elif kind == "file":
            require(stat.S_ISREG(mode), "fixture contains a non-regular path")
            value["sha256"] = digest(path.read_bytes())
        result[str(path.relative_to(root))] = value
    return result


def snapshot_digest(value: dict) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def fixture_environment(root: Path) -> dict[str, str]:
    """A fresh allowlist; no inherited provider credentials or Python/Git config."""
    for name in ("home", "tmp", "cwd", "bin"):
        (root / name).mkdir(mode=0o700)
    (root / "bin/python3").symlink_to(sys.executable)
    for name in ("claude", "codex", "claudron", "gh", "node", "npx"):
        sentinel = root / "bin" / name
        sentinel.write_text('#!/bin/sh\nprintf rejected > "$HOME/provider-attempt"\nexit 97\n')
        sentinel.chmod(0o700)
    for relative in ("home/.claude/settings.json", "home/.claude/auth.json",
                     "home/.claude/projects/sentinel/transcript.jsonl", "home/.claude/memory/keep.md",
                     "home/.codex/auth.json", "home/.codex/config.toml", "home/.codex/memories/keep.md",
                     "home/.cursor/settings.json", "home/.cursor/memory/keep.md", "cwd/project-sentinel"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_text("synthetic protected sentinel\n")
        target.chmod(0o600)
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
        codes: tuple[int, ...] = (0,), content: str | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, env=env, input=json.dumps(payload or {}) if content is None else content,
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
    paths = [*(state / "hooks").glob("*"), *state.glob("sessions/*/hooks/*")]
    for path in paths:
        if path.name.endswith((".stderr", ".log", ".stderr.old", ".log.old")):
            require(path.stat().st_size == 0, "packaged hook recorded errors despite exit zero")


def no_provider_work(root: Path) -> None:
    require(not list(root.rglob("provider-attempt")), "fixture attempted a provider command")
    require(not list(root.rglob("skill-events.jsonl")), "compatibility telemetry opt-out ignored")


def lifecycle(stage: Path, host: str, root: Path, version: str, *, writable: bool = False) -> dict:
    env = fixture_environment(root)
    if writable:
        env.pop("PYTHONDONTWRITEBYTECODE", None)
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

    writes = []

    def fire(event: str, **fields) -> None:
        protected = filesystem_snapshot(root, exclude=state)
        before = filesystem_snapshot(state)
        result = run(commands[event], cwd, env, payload={**payload, "hook_event_name": event, **fields})
        require(not result.stdout, "store hook produced output")
        no_hook_errors(state)
        no_provider_work(root)
        require(filesystem_snapshot(root, exclude=state) == protected, "hook changed protected host/project trees")
        after = filesystem_snapshot(state)
        writes.append({"event": event, "before": snapshot_digest(before), "after": snapshot_digest(after),
                       "protected_sha256": snapshot_digest(protected),
                       "changes": {name: {"before": before.get(name), "after": after.get(name)}
                                   for name in sorted(before.keys() | after.keys())
                                   if before.get(name) != after.get(name)}})

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
        opt.mkdir(mode=0o700)
        opt_env = fixture_environment(opt)
        opt_env[setting] = value
        if writable:
            opt_env.pop("PYTHONDONTWRITEBYTECODE", None)
        protected = filesystem_snapshot(opt)
        for event, command in commands.items():
            result = run(command, opt / "cwd", opt_env, payload={**payload, "source": "startup",
                         "hook_event_name": event, "prompt": "fixture"})
            require(not result.stdout and not (opt / "state").exists(), "store opt-out ignored")
            require(filesystem_snapshot(opt) == protected, "opt-out changed fixture files")
    return {"agent_cli": expected_host, "lifecycle_events": kinds, "prompt_events": 1, "opt_out": True,
            "writes": writes, "protected_trees": "unchanged"}


def doctor(stage: Path, host: str, root: Path, version: str) -> None:
    env = fixture_environment(root)
    before = filesystem_snapshot(root)
    result = run([sys.executable, "-S", "-B", str(stage / "lib/claudna/package_support"),
                  "doctor", "--host", host, "--json"], root / "cwd", env, codes=(0, 1))
    document = json.loads(result.stdout)
    checks = {check["id"]: check["status"] for check in document["checks"]}
    require(document["package_version"] == version and checks["package.integrity"] == "pass"
            and checks["package.selection"] == "pass" and checks["runtime.python"] == "pass"
            and checks["runtime.platform"] == "pass", "packaged doctor failed")
    require(all(checks["native." + key] == "unknown" for key in ("installed", "discovered", "trusted", "executed")),
            "doctor overclaimed native evidence")
    require(before == filesystem_snapshot(root), "doctor wrote fixture state")


def writable_and_recovery(stage: Path, root: Path, version: str) -> dict:
    """Executable candidate-as-mock-recovery fixture, not native rollback acceptance."""
    writable = root / "writable-package"
    shutil.copytree(stage, writable)
    for path in [writable, *writable.rglob("*")]:
        path.chmod(0o700 if path.is_dir() or path.stat().st_mode & 0o111 else 0o600)
    before = filesystem_snapshot(writable)
    profile = root / "writable-profile"
    profile.mkdir(mode=0o700)
    lifecycle(writable, "codex", profile, version, writable=True)
    require(filesystem_snapshot(writable) == before, "writable package changed or generated bytecode")
    detached = root / "detached-profile"
    detached.mkdir(mode=0o700)
    detached_env = fixture_environment(detached)
    detached_env.pop("PYTHONDONTWRITEBYTECODE", None)
    detached_state = Path(detached_env["CLAUDNA_STATE_DIR"])
    detached_before = filesystem_snapshot(detached_state)
    detached_protected = filesystem_snapshot(detached, exclude=detached_state)
    # Call the real packaged spawner and retain its real Popen handle only to
    # observe exit before inspecting or cleaning this fixture's exact scratch.
    code = """import os, subprocess, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from claudna.session_store import boundaries
original, children = subprocess.Popen, []
def observe(*args, **kwargs):
    child = original(*args, **kwargs)
    children.append(child)
    return child
subprocess.Popen = observe
boundaries.spawn_worker(Path(os.environ['CLAUDNA_STATE_DIR']), ['sweep'], os.environ, log='sweep.stderr')
assert len(children) == 1 and children[0].wait(timeout=20) == 0
"""
    run([sys.executable, "-I", "-B", "-c", code, str(writable / "lib")], detached / "cwd", detached_env)
    require(filesystem_snapshot(detached, exclude=detached_state) == detached_protected,
            "detached worker changed host/project sentinels")
    require((detached_state / "hooks/sweep.stderr").read_bytes() == b"", "detached worker recorded an error")
    require(filesystem_snapshot(writable) == before, "detached worker generated package caches")
    no_provider_work(detached)
    detached_after = filesystem_snapshot(detached_state)
    recovery = root / "mock-recovery"
    recovery.mkdir(mode=0o700)
    env = fixture_environment(recovery)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.update(CLAUDNA_SESSION_STORE="0", CODEX_THREAD_ID="recovery-source")
    state = Path(env["CLAUDNA_STATE_DIR"])
    protected = filesystem_snapshot(recovery, exclude=state)
    cli = [sys.executable, "-B", str(writable / "lib/claudna/session_store")]
    common = ["--session", "recovery-source", "--host", "codex"]
    content = ("---\ncwd: /synthetic/recovery\nlast_updated: 2026-11-11T00:00:00Z\n"
               "schema_version: 2\n---\nretained data\n")
    run([*cli, "handoff-write", *common], recovery / "cwd", env, content=content)
    run([*cli, "continuity", "context", *common, "--scope", "runtime:recovery", "--privacy", "public"],
        recovery / "cwd", env)
    run([*cli, "continuity", "publish", *common, "--scope", "runtime:recovery", "--kind", "handoff",
         "--workflow", "recovery", "--path", "handoff.md"], recovery / "cwd", env)
    retained = filesystem_snapshot(state)
    env["CODEX_THREAD_ID"] = "recovery-next"
    result = run([*cli, "continuity", "resolve", "--session", "recovery-next", "--host", "codex",
                  "--scope", "runtime:recovery", "--workflow", "recovery", "--json"], recovery / "cwd", env)
    selection = json.loads(result.stdout)
    require(selection["status"] == "found" and selection["source_sid"] == "recovery-source",
            "mock recovery could not read retained new-layout handoff")
    require(filesystem_snapshot(state) == retained, "mock recovery read changed retained state")
    result = run([*cli, "scratch", "--session", "recovery-next", "--host", "codex", "--label", "recovery"],
                 recovery / "cwd", env)
    scratch = Path(result.stdout.strip())
    require(scratch.parent == state / "sessions/recovery-next/scratch", "mock recovery wrote outside its owner")
    require(filesystem_snapshot(state / "sessions/recovery-source") == {
        str(Path(name).relative_to("sessions/recovery-source")): value for name, value in retained.items()
        if name == "sessions/recovery-source" or name.startswith("sessions/recovery-source/")
    }, "mock recovery changed retained source")
    require(filesystem_snapshot(recovery, exclude=state) == protected, "mock recovery changed host/project sentinels")
    require(not list(state.rglob("lifecycle.jsonl")), "manual recovery fabricated capture events")
    require(filesystem_snapshot(writable) == before, "mock recovery generated package caches")
    return {"writable_package_sha256": snapshot_digest(before), "writable_package": "unchanged",
            "detached_worker": "real packaged sweep observed exited; protected trees unchanged",
            "detached_write_set": {"before": detached_before, "after": detached_after,
                                   "protected_sha256": snapshot_digest(detached_protected)},
            "mock_recovery": "new-layout read and R-only write passed", "native_recovery_acceptance": "unknown",
            "consumer_recovery_acceptance": "unknown",
            "state_write_set_sha256": snapshot_digest(filesystem_snapshot(state))}


def qualify(output: Path, *, owner: release_toolchain.MaintainerPaths | None = None,
            session: str | None = None, host: str | None = None, standalone: bool = False) -> dict:
    output = output.resolve()
    require(not (output / "qualification.json").exists() and not (output / "qualification.json").is_symlink(),
            "qualification output already exists")
    receipt = verify_package(output)
    release_toolchain.ensure_toolchain()
    stage = output / "package"
    owner = owner or release_toolchain.maintainer_paths(
        "package-qualification", session=session, host=host, standalone=standalone)
    root = Path(tempfile.mkdtemp(prefix="fixture-", dir=owner.scratch))
    try:
        validation = root / "validation"
        validation.mkdir(mode=0o700)
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
            location.mkdir(mode=0o700)
            doctor(stage, host, location, receipt["version"])
            if host != "cursor":
                location = root / host
                location.mkdir(mode=0o700)
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
                startup_root.mkdir(mode=0o700)
                startup_env = fixture_environment(startup_root)
                protected = filesystem_snapshot(startup_root)
                result = run([str(stage / words[0][len(prefix):]), *host_args], startup_root / "cwd", startup_env)
                require(filesystem_snapshot(startup_root) == protected, "disabled startup changed fixture files")
                require(not result.stdout, "briefing opt-out ignored")
                no_hook_errors(startup_root / "state")
        filesystem_evidence = writable_and_recovery(stage, root, receipt["version"])
        no_provider_work(root)
        require(verify_package(output) == receipt, "qualification modified package artifacts")
    except Exception as exc:
        # A failed observer may leave an unconfirmed detached child. Retain
        # this exact allocation; only the successful observed-exit path cleans.
        raise PackageError(f"{exc}; retained private fixture at {root}") from exc
    shutil.rmtree(root)
    result = {"schema": "claudna.package-qualification/1", "commit": receipt["commit"],
              "version": receipt["version"], "archive_sha256": receipt["archive"]["sha256"], "status": "pass",
              "checks": ["artifact-integrity", "staged-catalog", "staged-manifests", "staged-skills",
                         "staged-integration", "host-isolation",
                         "packaged-doctor", "packaged-lifecycle", "capture-opt-outs", "read-only-package",
                         "protected-write-sets",
                         "writable-package-no-bytecode", "mock-compatible-recovery"],
              "fixtures": {host: {key: value for key, value in fixture.items() if key != "writes"}
                           for host, fixture in fixtures.items()},
              "filesystem": {key: value for key, value in filesystem_evidence.items()
                             if key not in {"state_write_set_sha256", "detached_write_set"}},
              "native_acceptance": "unknown", "consumer_acceptance": "unknown", "full_source_check": "not_run",
              "storage_cutover": "blocked: native/publication/consumer/recovery/D6 acceptance pending",
              "evidence_class": "executable fixtures; not native skill/publication acceptance"}
    write_json(output / "qualification.json", result)
    atomic_write_json(owner.artifacts / f"qualification-{uuid.uuid4().hex}.json",
                      {"schema": "claudna.maintainer-export/1", "kind": "qualification", "status": "fixtures_passed",
                       "owner_kind": owner.kind, "owner_id": owner.owner_id, "provider": owner.provider,
                       "state_root": str(owner.directory.parent.parent),
                       "state_root_mode": stat.S_IMODE(owner.directory.parent.parent.stat().st_mode),
                       "owner_mode": stat.S_IMODE(owner.directory.stat().st_mode),
                       "export": str(output), "commit": receipt["commit"],
                       "archive_sha256": receipt["archive"]["sha256"],
                       "receipt_sha256": digest((output / "qualification.json").read_bytes()),
                       "write_set_sha256": snapshot_digest(fixtures), "fixtures": fixtures,
                       "filesystem": filesystem_evidence,
                       "storage_cutover": result["storage_cutover"]}, durable=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True, help="Owned output of package_release.py")
    parser.add_argument("--session")
    parser.add_argument("--host", choices=("claude", "codex", "cursor"))
    parser.add_argument("--standalone", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = qualify(args.package, session=args.session, host=args.host, standalone=args.standalone)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"package qualification: {exc}\n")
    print(f"package qualification: fixture pass for {result['commit']}; native acceptance unknown")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
