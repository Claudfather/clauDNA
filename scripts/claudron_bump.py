#!/usr/bin/env python3
"""Move clauDNA to a new Claudron release: the logic behind ``.github/workflows/claudron-release.yml``.

The workflow runs daily (and on demand). It asks this script whether Claudron
has a release newer than ``contracts/claudron.ref``. If so, it installs that
release, runs ``scripts/sync_claudron_contract.py --ref <tag>``, runs the
check-set, pushes the result to ``claudron/<tag>`` and tries to open a PR with
the results. GitHub Actions may not create PRs in this repo (#432), so it then
leaves one issue for the release, asking a person or the fleet to open the PR
from that branch; later runs find that issue again. This script holds the parts
worth testing:

    python3 scripts/claudron_bump.py detect               # tag=… / newer=true|false, for $GITHUB_OUTPUT
    python3 scripts/claudron_bump.py changelog <tag>      # add the [Unreleased] line
    python3 scripts/claudron_bump.py body <tag> <pinned> <check> <contract>   # the PR body (pass|fail)
    python3 scripts/claudron_bump.py issue <tag> <pinned> [<check> <contract>]   # find or open the release's issue

Releases come from the public GitHub API (``$GH_TOKEN`` is sent when set,
for its rate limit). A draft or prerelease is never the latest release.
``issue`` reads and opens ``$GITHUB_REPOSITORY``'s issues through ``gh``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
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
            f"from {tag}, and output-guide §3's status table is re-rendered from it. Made by the "
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
    ci = ("A PR the workflow opens with its own token doesn't start CI: if it opened this one, push any commit to "
          "this branch (or close and reopen it as a person) to run CI here.")
    return f"""## What changed

{moves}

## Testing done

These ran against {tag} on this branch:

- `make check`: {mark(check)}
- `make test-contract` (the live suite, exact mode): {mark(contract)}

{ci}{follow}

## Checklist

- [x] CHANGELOG.md updated under `[Unreleased]`
- [ ] Version bump: none here; the next release carries it
"""


def run_gh(args: list[str], input: str | None = None) -> str:
    """``gh ARGS``'s stdout. Raises ``subprocess.CalledProcessError``, carrying gh's stderr, when it fails."""
    return subprocess.run(["gh", *args], input=input, capture_output=True, text=True, check=True).stdout


def issue_title(tag: str) -> str:
    """The title of the release's issue. It is matched exactly, so no release takes another's issue."""
    return f"Move to Claudron {tag}: open the PR from claudron/{tag}"


def issue_body(tag: str, pinned: str, check: str | None = None, contract: str | None = None,
               run_url: str | None = None) -> str:
    """What the fleet does to land the move, with the checks' results when the run that pushed the branch has them."""
    branch = f"claudron/{tag}"
    why = (f"Claudron {tag} is released, and the `claudron-release` workflow has moved clauDNA to it on the branch "
           f"`{branch}`. GitHub Actions may not create pull requests in this repository (#432), so the PR is left "
           "to a person or the fleet.")
    if check and contract:
        why += (" The run that pushed the branch ran the checks on it: `make check` "
                f"{'passed' if check == 'pass' else '**failed**'}, `make test-contract` "
                f"{'passed' if contract == 'pass' else '**failed**'}.")
    steps = (f"To land the move, open a PR from `{branch}` itself, titled `Move to Claudron {tag}`:\n\n"
             "1. If main has moved since the branch was made, bring it in with a merge commit. Where main changed a "
             "file the move rewrites, take main's copy and run the move's commands again (the workflow's \"Move to "
             "the release\" step) rather than merge it by hand.\n"
             "2. Run `make check` and `make test-contract` on the result.\n"
             f"3. Write the PR's body with `python3 scripts/claudron_bump.py body {tag} {pinned} <check> <contract>` "
             "(each `pass` or `fail`), and add `Closes #` with this issue's number.")
    after = f"Until a PR from `{branch}` exists, each daily run finds this issue again and opens no other."
    if run_url:
        after += f" Opened by {run_url}."
    return f"{why}\n\n{steps}\n\n{after}\n"


ISSUES_QUERY = """query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, after: $after, states: [OPEN, CLOSED]) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes { number title state url }
    }
  }
}"""


def list_issues(repo: str, gh=None) -> list[dict]:
    """Every issue in ``repo`` (``owner/name``), open or closed, read a page at a time through GraphQL.

    Raises ``RuntimeError`` unless the pages add up to the connection's ``totalCount``: a short read must never
    pass for "this release has no issue". (On 2026-10-22 REST's issue listing answered one query with an empty
    page on 5 of 8 calls, where this connection returned the same first 100 of 228 issues on all 4.)
    """
    gh = gh or run_gh
    owner, name = repo.split("/", 1)
    rows: list[dict] = []
    after, total = None, None
    while True:
        args = ["api", "graphql", "-f", f"query={ISSUES_QUERY}", "-f", f"owner={owner}", "-f", f"name={name}"]
        if after:
            args += ["-f", f"after={after}"]
        try:
            doc = json.loads(gh(args))
            if doc.get("errors"):
                raise RuntimeError(f"the issues query failed: {doc['errors']}")
            page = doc["data"]["repository"]["issues"]
            count, info = page["totalCount"], page["pageInfo"]
            rows += [node for node in page["nodes"] if node]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise RuntimeError(f"an issues page could not be read: {exc!r}") from exc
        if total is None:
            total = count
        elif count != total:
            raise RuntimeError(f"the issue count moved from {total} to {count} during the read")
        if not info.get("hasNextPage"):
            break
        if not info.get("endCursor") or info["endCursor"] == after:
            raise RuntimeError("the issues query gave no next cursor")
        after = info["endCursor"]
    if len(rows) != total:
        raise RuntimeError(f"read {len(rows)} of {total} issues")
    return rows


def find_issue(issues: list[dict], tag: str) -> dict | None:
    """The release's issue among ``issues``, open or closed: the first one opened with its exact title."""
    title = issue_title(tag)
    found = [row for row in issues if row.get("title") == title]
    return min(found, key=lambda row: row["number"]) if found else None


def ensure_issue(repo: str, tag: str, pinned: str, check: str | None = None, contract: str | None = None,
                 run_url: str | None = None, gh=None) -> tuple[str, dict]:
    """``("found", issue)`` when the release has its issue, else ``("opened", {"url": ...})`` once it opens it.

    The whole listing comes first (``list_issues``), so a failed read raises before anything is opened.
    """
    gh = gh or run_gh
    issue = find_issue(list_issues(repo, gh=gh), tag)
    if issue:
        return "found", issue
    out = gh(["issue", "create", "--repo", repo, "--title", issue_title(tag), "--body-file", "-"],
             input=issue_body(tag, pinned, check, contract, run_url)).split()
    if not out:
        raise RuntimeError("gh issue create printed no URL")
    return "opened", {"url": out[-1]}


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
    if cmd == "issue" and len(args) in (2, 4):
        tag = args[0]
        for each in args[:2]:
            version(each)
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if not set(args[2:]) <= {"pass", "fail"} or "/" not in repo:
            print("issue: the results are pass or fail, and GITHUB_REPOSITORY names owner/repo", file=sys.stderr)
            return 2
        run_url = None
        if os.environ.get("GITHUB_RUN_ID"):
            server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
            run_url = f"{server}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        try:
            state, issue = ensure_issue(repo, *args, run_url=run_url)
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            detail = (getattr(exc, "stderr", None) or "").strip()
            print(f"issue: no issue found or opened for {tag}: {exc}" + (f": {detail}" if detail else ""),
                  file=sys.stderr)
            return 1
        if state == "opened":
            print(f"claudron/{tag} waits for its PR: opened {issue['url']}")
            return 0
        print(f"claudron/{tag} waits for its PR: issue #{issue['number']} ({issue['state'].lower()}) {issue['url']}")
        if issue["state"] != "OPEN":
            print(f"::warning::claudron/{tag} has no PR, and its issue #{issue['number']} is closed: {issue['url']}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
