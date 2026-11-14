#!/usr/bin/env python3
"""Qualify one immutable candidate, then optionally tag or publish it.

No host install or marketplace promotion occurs here. Publication is explicit;
the default only produces evidence and artifacts in a new output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
from release_toolchain import ensure_toolchain, isolated_python_env, maintainer_paths  # noqa: E402
from claudna.session_store.fsio import atomic_write_json  # noqa: E402


class ReleaseError(Exception):
    """A qualification or immutable-publication boundary was not satisfied."""


def run(args, root, *, env=None, check=True):
    result = subprocess.run(args, cwd=root, env=env, text=True, capture_output=True)
    if check and result.returncode:
        raise ReleaseError(f"{' '.join(map(str, args))} failed:\n{result.stdout}{result.stderr}")
    return result


def git(root, *args, check=True):
    return run(["git", *args], root, check=check).stdout.strip()


def section(changelog, name):
    match = re.search(r"^## \[" + re.escape(name) + r"\][^\n]*\n(.*?)(?=^## \[|\Z)",
                      changelog, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def meaningful_lines(notes):
    notes = re.sub(r"<!--.*?-->", "", notes, flags=re.DOTALL)
    return {line.strip() for line in notes.splitlines()
            if re.search(r"[A-Za-z0-9]", line)
            and not re.match(r"\s*(#|\[[^\]]+\]:)", line)}


def version_at(root, ref=None):
    versions = []
    for host in ("claude", "cursor", "codex"):
        relative = f".{host}-plugin/plugin.json"
        raw = git(root, "show", f"{ref}:{relative}") if ref else (root / relative).read_text()
        versions.append(json.loads(raw)["version"])
    if len(set(versions)) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", versions[0]):
        raise ReleaseError("all three manifests must agree on a numeric release version")
    return versions[0]


def check_changelog(root):
    baseline = git(root, "rev-parse", "--verify", "origin/main", check=False)
    if baseline == git(root, "rev-parse", "HEAD"):
        return "HEAD == origin/main; nothing to gate"
    current = (root / "CHANGELOG.md").read_text()
    if not re.search(r"^## \[Unreleased\]", current, re.MULTILINE):
        raise ReleaseError("CHANGELOG.md missing [Unreleased] section")
    if not baseline:
        raise ReleaseError("origin/main is required for the changelog comparison")
    previous = git(root, "show", "origin/main:CHANGELOG.md")
    if meaningful_lines(section(current, "Unreleased")) - meaningful_lines(section(previous, "Unreleased")):
        return "Changelog has new meaningful unreleased content"
    version = version_at(root)
    if version != version_at(root, "origin/main") and (
        meaningful_lines(section(current, version)) - meaningful_lines(section(previous, version))
    ):
        return f"Changelog has new meaningful release notes for {version}"
    raise ReleaseError("CHANGELOG.md needs new meaningful [Unreleased] content "
                       "or notes for the bumped manifest version")


def remote_tag(root, remote, tag):
    """Read advertised remote identity, never a possibly stale local tag."""
    lines = git(root, "ls-remote", "--tags", remote, f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}")
    refs = dict(reversed(line.split()) for line in lines.splitlines())
    return refs.get(f"refs/tags/{tag}^{{}}", refs.get(f"refs/tags/{tag}"))


def require_tag_identity(actual, candidate, tag):
    if actual is not None and actual != candidate:
        raise ReleaseError(f"tag {tag} resolves to {actual}, expected candidate {candidate}; refusing to rewrite it")


def local_tag(root, tag, candidate):
    existing = git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}", check=False) or None
    require_tag_identity(existing, candidate, tag)
    if existing is None:
        git(root, "-c", "user.name=clauDNA release", "-c", "user.email=release@localhost",
            "tag", "-a", tag, candidate, "-m", f"Release {tag}")


def publish_tag(root, remote, tag, candidate):
    actual = remote_tag(root, remote, tag)
    require_tag_identity(actual, candidate, tag)
    if actual is None:
        local_tag(root, tag, candidate)
        pushed = run(["git", "push", remote, f"refs/tags/{tag}:refs/tags/{tag}"], root, check=False)
        # A failed push can be a same-candidate race. Only remote identity
        # proves it; the newly created local tag cannot.
        actual = remote_tag(root, remote, tag)
        require_tag_identity(actual, candidate, tag)
        if actual is None:
            raise ReleaseError(f"remote tag {tag} absent after push (exit {pushed.returncode})")


def release_info(root, repo, tag):
    result = run(["gh", "api", f"repos/{repo}/releases/tags/{tag}"], root, check=False)
    if result.returncode:
        if "HTTP 404" in result.stderr:
            return None
        raise ReleaseError(f"could not inspect release {tag}: {result.stderr}")
    return json.loads(result.stdout)


def verify_github_tag(root, repo, tag, candidate):
    """Bind the publication repository independently of the Git push remote."""
    endpoint = f"repos/{repo}/git/ref/tags/{tag}"
    seen = set()
    for _ in range(32):
        obj = json.loads(run(["gh", "api", endpoint], root).stdout)["object"]
        oid, kind = obj["sha"], obj["type"]
        if not re.fullmatch(r"[0-9a-f]{40}", oid):
            raise ReleaseError(f"invalid GitHub tag object in {repo}:{tag}")
        if kind == "commit":
            require_tag_identity(oid, candidate, f"{repo}:{tag}")
            return
        if kind != "tag" or oid in seen:
            raise ReleaseError(f"GitHub tag {repo}:{tag} does not peel to a commit")
        seen.add(oid)
        endpoint = f"repos/{repo}/git/tags/{oid}"
    raise ReleaseError(f"GitHub tag {repo}:{tag} exceeds the annotated-tag depth limit")


def owner_make_arg(owner):
    args = (['--session', owner.owner_id, '--host', owner.provider]
            if owner.kind == 'session' else ['--standalone'])
    return 'STORAGE_OWNER_ARGS=' + shlex.join(args)


def publish_assets(root, repo, tag, candidate, notes, assets, owner):
    verify_github_tag(root, repo, tag, candidate)
    work = Path(tempfile.mkdtemp(prefix="release-assets.", dir=owner.scratch))
    os.chmod(work, 0o700)
    try:
        info = release_info(root, repo, tag)
        if info is None:
            notes_file = work / "notes.md"
            write_private_file(notes_file, (notes + "\n").encode("utf-8"))
            verify_github_tag(root, repo, tag, candidate)
            result = run(["gh", "release", "create", tag, "--repo", repo, "--verify-tag",
                          "--target", candidate, "--title", tag, "--notes-file", str(notes_file)],
                         root, check=False)
            info = release_info(root, repo, tag)
            if info is None:
                raise ReleaseError(f"release creation failed: {result.stderr}")
        if info.get("tag_name") != tag:
            raise ReleaseError("release returned a different tag")
        names = [asset["name"] for asset in info["assets"]]
        if len(names) != len(set(names)):
            raise ReleaseError("release contains duplicate asset names")

        def verify_asset(asset):
            destination = work / asset.name
            if destination.exists():
                destination.unlink()
            run(["gh", "release", "download", tag, "--repo", repo,
                 "--pattern", asset.name, "--dir", str(work)], root)
            if destination.read_bytes() != asset.read_bytes():
                raise ReleaseError(f"existing release asset {asset.name} differs; overwrite forbidden")

        # Check every conflict before uploading anything. Never use --clobber.
        for asset in assets:
            if asset.name in names:
                verify_asset(asset)
        for asset in assets:
            if asset.name not in names:
                verify_github_tag(root, repo, tag, candidate)
                result = run(["gh", "release", "upload", tag, str(asset), "--repo", repo], root, check=False)
                if result.returncode:
                    # An upload race is acceptable only when bytes now agree.
                    verify_asset(asset)
        verify_github_tag(root, repo, tag, candidate)
    except Exception:
        # Retain the exact private work directory as failure evidence.
        raise
    else:
        shutil.rmtree(work)


def write_private_file(path, content):
    """Create a private file exclusively, independent of the caller's umask."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def qualify(root, candidate, output, owner):
    ensure_toolchain()
    if output.exists() or output.is_symlink():
        raise ReleaseError(f"output already exists: {output}")
    version = version_at(root, candidate)
    notes = section(git(root, "show", f"{candidate}:CHANGELOG.md"), version)
    if not meaningful_lines(notes):
        raise ReleaseError(f"candidate requires meaningful CHANGELOG.md notes for [{version}]")
    baseline = git(root, "rev-parse", "--verify", "origin/main", check=False)
    if not baseline:
        raise ReleaseError("origin/main is required for candidate source checks")
    work = Path(tempfile.mkdtemp(prefix="release-candidate.", dir=owner.scratch))
    os.chmod(work, 0o700)
    try:
        return _qualify_in_work(root, candidate, output, owner, version, notes, baseline, work)
    except Exception as error:
        raise ReleaseError(f"{error}; retained private qualification work at {work}") from error


def _qualify_in_work(root, candidate, output, owner, version, notes, baseline, work):
    home, temp, checkout = work / "home", work / "tmp", work / "source"
    home.mkdir(mode=0o700)
    temp.mkdir(mode=0o700)
    os.chmod(home, 0o700)
    os.chmod(temp, 0o700)
    env = dict(os.environ, HOME=str(home), TMPDIR=str(temp), TMP=str(temp), TEMP=str(temp),
               XDG_CACHE_HOME=str(home / ".cache"), PYTHONDONTWRITEBYTECODE="1",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               CLAUDNA_STATE_DIR=str(owner.directory.parent.parent.resolve()))
    for key in ("PYTHONPATH", "PYTHONHOME", "CLAUDNA_ROOT", "CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT"):
        env.pop(key, None)
    # The candidate's checks run as if started by hand. `make tag-release RELEASE_OUTPUT=...` exports its
    # variables and records them in MAKEFLAGS, where the nested make reads them again; a test that runs
    # release.sh would then write its fixture package into this release's real output.
    for key in [key for key in env if key.startswith(("RELEASE_", "PACKAGE_"))]:
        del env[key]
    for key in ("STORAGE_OWNER_ARGS", "MAKEFLAGS", "MFLAGS", "MAKELEVEL"):
        env.pop(key, None)
    env = isolated_python_env(work, env)
    run(["git", "clone", "--no-hardlinks", "--no-checkout", str(root), str(checkout)], root, env=env)
    run(["git", "checkout", "--detach", candidate], checkout, env=env)
    run(["git", "update-ref", "refs/remotes/origin/main", baseline], checkout, env=env)
    checked = run(["make", "check", owner_make_arg(owner)], checkout, env=env)
    print(checked.stdout, end="", flush=True)
    print(checked.stderr, end="", flush=True)
    if (git(checkout, "rev-parse", "HEAD") != candidate
            or git(checkout, "status", "--porcelain", "--untracked-files=all")):
        raise ReleaseError("source checks modified the exact candidate checkout")
    run(["make", "qualify-package", f"PACKAGE_REF={candidate}", f"PACKAGE_OUTPUT={output}",
         owner_make_arg(owner)], checkout, env=env)
    receipt = json.loads((output / "receipt.json").read_text())
    qualification = json.loads((output / "qualification.json").read_text())
    digest = hashlib.sha256((output / "package.tar.gz").read_bytes()).hexdigest()
    if (receipt["commit"] != candidate or receipt["version"] != version
            or receipt["archive"]["sha256"] != digest or qualification["commit"] != candidate
            or qualification["version"] != version or qualification["archive_sha256"] != digest
            or qualification["status"] != "pass"):
        raise ReleaseError("package qualification does not bind to this candidate and archive")
    evidence = {"schema": "claudna.release-source-check/1", "commit": candidate, "version": version,
                "source_check": "pass", "command": "make check", "archive_sha256": digest}
    evidence_bytes = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8")
    write_private_file(output / "source-check.json", evidence_bytes)
    source_check_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
    assets = [output / name for name in ("package.tar.gz", "package.sha256", "receipt.json",
              "qualification.json", "claude-marketplace.json", "source-check.json")]
    if not all(asset.is_file() for asset in assets):
        raise ReleaseError("required release assets are missing")
    receipt = {
        "schema": "claudna.release-source-check-receipt/1",
        "owner": {"kind": owner.kind, "id": owner.owner_id, "provider": owner.provider},
        "status": "pass",
        "commit": candidate,
        "version": version,
        "archive_sha256": digest,
        "source_check_sha256": source_check_sha256,
        "export_path": str(output.resolve()),
        "evidence": ("isolated source check and package qualification; "
                     "no native, consumer, publication, or recovery acceptance"),
    }
    receipt_path = owner.artifacts / f"release-source-check-{candidate}-{uuid.uuid4().hex}.json"
    atomic_write_json(receipt_path, receipt, durable=True)
    shutil.rmtree(work)
    return version, notes, assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref")
    parser.add_argument("--output", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--tag", action="store_true")
    action.add_argument("--publish", action="store_true")
    action.add_argument("--check-changelog", action="store_true")
    action.add_argument("--unreleased-notes", action="store_true")
    action.add_argument("--preflight", action="store_true")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--repo")
    owner_group = parser.add_mutually_exclusive_group()
    owner_group.add_argument("--session")
    owner_group.add_argument("--standalone", action="store_true")
    parser.add_argument("--host", choices=("claude", "codex", "cursor"))
    args = parser.parse_args()
    try:
        if args.preflight:
            print(ensure_toolchain())
            return
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
        if args.check_changelog:
            print(check_changelog(root))
            return
        if args.unreleased_notes:
            notes = section((root / "CHANGELOG.md").read_text(), "Unreleased")
            if not meaningful_lines(notes):
                raise ReleaseError("CHANGELOG has no meaningful entries under [Unreleased]")
            print(notes)
            return
        if not args.ref or not args.output:
            parser.error("--ref and --output are required")
        if args.publish and (not args.repo or not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo)):
            parser.error("--publish requires --repo OWNER/REPO")
        candidate = git(root, "rev-parse", "--verify", "--end-of-options", f"{args.ref}^{{commit}}")
        if args.output.exists() or args.output.is_symlink():
            raise ReleaseError(f"output already exists: {args.output}")
        output = args.output.resolve()
        ensure_toolchain()
        try:
            owner = maintainer_paths("release-candidate", session=args.session, host=args.host,
                                     standalone=args.standalone)
        except (OSError, ValueError, RuntimeError) as error:
            raise ReleaseError(f"maintainer ownership unavailable: {error}") from error
        version, notes, assets = qualify(root, candidate, output, owner)
        tag = f"v{version}"
        if args.publish:
            publish_tag(root, args.remote, tag, candidate)
            publish_assets(root, args.repo, tag, candidate, notes, assets, owner)
            actual = remote_tag(root, args.remote, tag)
            require_tag_identity(actual, candidate, tag)
            if actual is None:
                raise ReleaseError(f"remote tag {tag} disappeared during publication")
        elif args.tag:
            local_tag(root, tag, candidate)
        print(f"Qualified {candidate} ({version}): {output}")
    except (ReleaseError, OSError, ValueError, KeyError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
