#!/usr/bin/env python3
"""Build a deterministic full tracked-source package from one explicit Git ref.

Maintainer tooling only. Never reads working-tree file contents, applies export
attributes, installs a plugin, or modifies the source checkout.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True

import release_toolchain  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = "package.tar.gz"
MODES = {"100644": 0o644, "100755": 0o755}


class PackageError(ValueError):
    """The candidate cannot be safely packaged or qualified."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def safe_path(relative: str) -> PurePosixPath:
    path = PurePosixPath(relative)
    require(bool(relative) and bool(path.parts) and not path.is_absolute() and str(path) == relative
            and all(part not in (".", "..") and part.lower() != ".git" for part in path.parts)
            and "\\" not in relative and not any(ord(char) < 32 or ord(char) == 127 for char in relative),
            "unsafe tracked path")
    return path


def git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    # Repository object reads do not need credentials, user config or hooks.
    env = {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_NO_REPLACE_OBJECTS": "1", "LC_ALL": "C"}
    result = subprocess.run(["git", "-C", str(root), *args], input=data, env=env,
                            capture_output=True, check=False)
    require(result.returncode == 0, "Git object read failed")
    return result.stdout


def tracked_files(root: Path, commit: str) -> dict[str, tuple[str, bytes]]:
    records = []
    portable = set()
    for line in git(root, "ls-tree", "-rz", "--full-tree", commit).split(b"\0"):
        if not line:
            continue
        metadata, raw_path = line.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        relative = raw_path.decode("utf-8")
        safe_path(relative)
        require(mode in MODES and kind == "blob", "unsupported tracked mode (links/submodules forbidden)")
        require(relative.casefold() not in portable, "case-colliding tracked paths")
        portable.add(relative.casefold())
        records.append((relative, mode, oid))
    require(bool(records), "empty tracked export")
    # One batch reads raw Git blobs; export-ignore/export-subst cannot change them.
    payload = git(root, "cat-file", "--batch", data="".join(oid + "\n" for _, _, oid in records).encode())
    stream = io.BytesIO(payload)
    files = {}
    for relative, mode, oid in records:
        header = stream.readline().decode("ascii").split()
        require(len(header) == 3 and header[:2] == [oid, "blob"], "invalid Git blob response")
        data = stream.read(int(header[2]))
        require(len(data) == int(header[2]) and stream.read(1) == b"\n", "truncated Git blob response")
        files[relative] = (mode, data)
    return dict(sorted(files.items()))


def file_receipt(files: dict[str, tuple[str, bytes]]) -> dict:
    return {name: {"mode": mode, "sha256": digest(data)} for name, (mode, data) in files.items()}


def archive_bytes(files: dict[str, tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0, compresslevel=9) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, (mode, data) in sorted(files.items()):
                item = tarfile.TarInfo(name)
                item.size, item.mode = len(data), MODES[mode]
                item.uid = item.gid = item.mtime = 0
                item.uname = item.gname = ""
                archive.addfile(item, io.BytesIO(data))
    return output.getvalue()


def package_version(files: dict[str, tuple[str, bytes]]) -> str:
    versions = {json.loads(files[f".{host}-plugin/plugin.json"][1])["version"]
                for host in ("claude", "cursor", "codex")}
    require(len(versions) == 1, "manifest versions disagree")
    version = versions.pop()
    require(isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is not None,
            "invalid package version")
    return version


def pinned_descriptor(files: dict[str, tuple[str, bytes]], commit: str) -> dict:
    descriptor = json.loads(files[".claude-plugin/marketplace.json"][1])
    entries = [entry for entry in descriptor["plugins"] if entry.get("name") == "claudna"]
    require(len(entries) == 1, "expected one Claude marketplace entry")
    entries[0]["source"] = {"source": "github", "repo": "Claudfather/clauDNA", "sha": commit}
    return descriptor


def build(root: Path, ref: str, output: Path, *, qualify: bool = False) -> dict:
    require(bool(ref), "an explicit Git ref is required")
    # Resolve once; every subsequent Git object read uses this immutable value.
    commit = git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "expected a full SHA-1 commit")
    files = tracked_files(root, commit)
    version = package_version(files)
    descriptor = pinned_descriptor(files, commit)
    if qualify:
        release_toolchain.ensure_toolchain()
    # mkdir is the ownership boundary: existing directories and links fail closed.
    output.mkdir(parents=False)
    stage = output / "package"
    stage.mkdir()
    for name, (mode, data) in files.items():
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        target.chmod(MODES[mode] & ~0o222)
    for directory, _, _ in os.walk(stage, topdown=False):
        Path(directory).chmod(0o555)
    archive = archive_bytes(files)
    (output / ARCHIVE).write_bytes(archive)
    (output / "package.sha256").write_text(f"{digest(archive)}  {ARCHIVE}\n", encoding="ascii")
    write_json(output / "claude-marketplace.json", descriptor)
    receipt = {"schema": "claudna.package-release/1", "commit": commit, "version": version,
               "archive": {"name": ARCHIVE, "sha256": digest(archive)}, "files": file_receipt(files),
               "descriptor": {"name": "claude-marketplace.json",
                              "sha256": digest((output / "claude-marketplace.json").read_bytes())}}
    write_json(output / "receipt.json", receipt)
    if qualify:
        from qualify_package import qualify as qualify_output
        qualify_output(output)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True, help="Explicit ref, resolved once to a commit")
    parser.add_argument("--output", type=Path, required=True, help="New directory in an existing parent")
    parser.add_argument("--qualify", action="store_true", help="Run staged local fixture qualification")
    args = parser.parse_args(argv)
    try:
        receipt = build(ROOT, args.ref, args.output.absolute(), qualify=args.qualify)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"package release: {exc}\n")
    print(f"package release: {receipt['commit']} {receipt['archive']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
