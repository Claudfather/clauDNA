#!/usr/bin/env python3
"""Move clauDNA to a new Claudron release: the logic behind ``.github/workflows/claudron-release.yml``.

The workflow runs daily (and on demand). It asks this script whether Claudron
has a release newer than ``contracts/claudron.ref``. If so, it installs that
release, runs ``scripts/sync_claudron_contract.py --ref <tag>``, runs the
check-set, and opens a PR with the results. This script holds the parts worth
testing:

    python3 scripts/claudron_bump.py detect               # tag=… / newer=true|false, for $GITHUB_OUTPUT
    python3 scripts/claudron_bump.py changelog <tag>      # add the [Unreleased] line
    python3 scripts/claudron_bump.py body <tag> <pinned> <check> <contract>   # the PR body (pass|fail)

Releases come from the public GitHub API (``$GH_TOKEN`` is sent when set,
for its rate limit). A draft or prerelease is never the latest release.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDRON_REPO = "Claudfather/Claudron"
REF = REPO_ROOT / "contracts" / "claudron.ref"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
TAG_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def version(tag: str) -> tuple[int, int, int]:
    m = TAG_RE.fullmatch(tag.strip())
    if not m:
        raise ValueError(f"not a release tag: {tag!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def latest_release(token: str | None = None) -> str:
    """The tag of Claudron's latest release."""
    req = urllib.request.Request(f"https://api.github.com/repos/{CLAUDRON_REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "claudna-claudron-bump",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)["tag_name"]


def detect(pinned: str, latest: str) -> dict:
    """``{"tag", "newer"}``: is ``latest`` a release after ``pinned``?"""
    return {"tag": latest, "newer": version(latest) > version(pinned)}


def add_changelog_line(text: str, tag: str) -> str:
    """``text`` with the move recorded under ``[Unreleased]`` → ``### Changed`` (created when missing)."""
    line = (f"- **Moves to Claudron {tag}.** `contracts/claudron.json` and `contracts/claudron.ref` now come "
            f"from {tag}, and output-guide §3's status table is re-rendered from it. Opened by the "
            "`claudron-release` workflow.\n")
    head = "## [Unreleased]\n"
    start = text.index(head) + len(head)
    end = text.find("\n## [", start)
    end = len(text) if end == -1 else end + 1
    section = text[start:end]
    if "### Changed\n" in section:
        at = start + section.index("### Changed\n") + len("### Changed\n")
        return text[:at] + line + text[at:]
    # A new subsection goes in Keep a Changelog's order: after Added, ahead of Deprecated/Removed/Fixed/Security.
    later = re.search(r"^### (?:Deprecated|Removed|Fixed|Security)\n", section, re.M)
    if later:
        at = start + later.start()
        return text[:at] + "### Changed\n" + line + "\n" + text[at:]
    return text[:end].rstrip("\n") + "\n### Changed\n" + line + "\n" + text[end:]


def pr_body(tag: str, pinned: str, check: str, contract: str) -> str:
    def mark(result: str) -> str:
        return "passed" if result == "pass" else "**failed**: see the workflow run"

    follow = ("" if check == contract == "pass" else
              "\n\nSomething failed, so this PR needs a person: `make check` names each mirror that has to "
              "follow the new contract (`HOME_SECTIONS`, the capabilities harvest gates on, the summary "
              "schema's homes), and the live suite says whether harvest still works through the engine. "
              "Push the fixes to this branch.")
    moves = (f"Moves clauDNA from Claudron {pinned} to {tag}: `contracts/claudron.json` is {tag}'s "
             f"`claudron contract --json`, `contracts/claudron.ref` names {tag}, and output-guide §3's status "
             "table is re-rendered from it.")
    ci = ("A PR opened with the workflow's own token doesn't start CI. Push any commit to this branch (or close "
          "and reopen it as a person) to run CI here.")
    return f"""## What changed

{moves}

## Testing done

The `claudron-release` workflow ran these against {tag} before opening this PR:

- `make check`: {mark(check)}
- `make test-contract` (the live suite, exact mode): {mark(contract)}

{ci}{follow}

## Checklist

- [x] CHANGELOG.md updated under `[Unreleased]`
- [ ] Version bump: none here; the next release carries it
"""


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "detect":
        found = detect(REF.read_text(encoding="utf-8").strip(), latest_release(os.environ.get("GH_TOKEN")))
        print(f"tag={found['tag']}\nnewer={'true' if found['newer'] else 'false'}")
        return 0
    if cmd == "changelog" and len(args) == 1:
        version(args[0])
        CHANGELOG.write_text(add_changelog_line(CHANGELOG.read_text(encoding="utf-8"), args[0]), encoding="utf-8")
        return 0
    if cmd == "body" and len(args) == 4:
        print(pr_body(*args))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
