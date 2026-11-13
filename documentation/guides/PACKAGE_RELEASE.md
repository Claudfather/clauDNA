---
title: "Exact-commit package qualification"
type: knowledge
status: current
owner: claudna
created: 2026-11-04
updated: 2026-11-04
---

# Exact-commit package qualification

The maintainer package is a full tracked Git export. It is an artifact for review
and release qualification; generating it does not install, publish, promote or
update a user's plugin. The runtime and pure package export remain stdlib-only.
Qualification uses the pinned development toolchain in `requirements-dev.txt`.

The export includes contributor tooling and optional setup resources such as
`project-template/`, `shell/` and `snowflake/`. Packaging those files does not
register or execute them. Host manifests select plugin components; the
[setup guide](../../SETUP_GUIDE.md#optional-setup-resources) explains which
resources a user applies manually.

## Qualification toolchain

Use Python 3.12, matching the development CI baseline, to create and select a
virtual environment before qualification or release checks. Then install the
repository's pinned development dependencies:

```sh
python3.12 -m venv /absolute/claudna-release-venv
source /absolute/claudna-release-venv/bin/activate
make deps
```

With that environment active, the Makefile's `python3` and each subprocess use
its interpreter. Direct script invocations can instead use
`/absolute/claudna-release-venv/bin/python3`. A prior user-site `make deps` install
does not satisfy qualification: its private HOME and disabled user site
deliberately exclude ambient packages. The shared preflight checks that the
selected interpreter can import YAML, Ruff and pytest under `-I -B`, and fails
with setup instructions before creating qualified-build output. It never
installs dependencies or accesses the network. Standalone qualification uses
the same preflight; pure `make package` does not need development packages.
The plugin runtime's Python 3.9 floor is separate from this development setup.

## Build and inspect

Run from the source checkout with an explicit ref and a new absolute output
directory whose parent already exists:

```sh
make package PACKAGE_REF=<commit-or-ref> PACKAGE_OUTPUT=/absolute/new-output
make qualify-package PACKAGE_REF=<commit-or-ref> PACKAGE_OUTPUT=/absolute/another-new-output
```

`qualify-package` builds and qualifies in one call. To qualify an existing,
previously unqualified output:

```sh
python3 scripts/qualify_package.py --package /absolute/new-output
```

The ref resolves once to a full commit SHA. Every byte comes from that commit's
Git blobs, including development files and auxiliary resources. Untracked files,
dirty working files, and Git export attributes cannot alter the package. There
is no distribution allowlist. Symlinks, submodules, non-regular Git modes,
escaping paths and case-colliding file names are rejected. Tracked executable
bits are preserved.

Standalone commands execute the maintainer tooling in the caller's checkout;
the ref identifies exported content, not necessarily that tooling's revision.
The release controller runs the tooling from its exact candidate checkout so
the checked source, exporter and staged runtime share the candidate commit.

The output contains:

| File | Purpose |
|---|---|
| `package/` | Relocated source tree, made read-only before qualification |
| `package.tar.gz` | Source archive with sorted paths, Git file modes, zero uid/gid/mtime, empty owner names and deterministic gzip header |
| `package.sha256` | SHA-256 of the archive |
| `receipt.json` | Commit, version, archive hash, every tracked file hash and Git mode, and descriptor hash |
| `claude-marketplace.json` | Reviewable SHA-pinned Claude descriptor; live registration is unchanged |
| `qualification.json` | Written only after all staged checks pass; binds the same commit, version and archive hash |

Building the same commit with the same toolchain produces identical archive and
receipt bytes. Existing output directories and existing qualification receipts
are never overwritten. Failed qualification leaves its artifact for inspection
without a passing qualification receipt; use a fresh output for another attempt.
The source archive retains Git's `0644`/`0755` modes; its staged tree uses
`0444`/`0555` so checks cannot casually modify the candidate. Checksums establish
consistency, not publisher authenticity.

## What staged qualification proves

Qualification verifies that the archive, read-only tree, descriptor and receipt
agree before executing packaged code, then repeats that verification afterward.
It runs the staged support generator in check mode, the existing manifest and
skill validators, the integration checks and the actual packaged doctor. Those
existing owners validate host selection, catalog hashes and bundled resources,
including referenced skill depth files and shared guidance. The fresh environment
does not inherit CI touched-file scoping, so all skills receive blocking
validation. Existing advisory warnings and exclusions for external project files
and runtime output paths keep their source-validator meaning. Cursor remains
hook-free; Codex retains six handlers and its inert agent directory.

Both Claude and Codex store fixtures invoke the actual declared packaged shell
commands from an unrelated directory. They drive start, prompt, synthetic Skill
activity, pre-compact, compact start and end. Qualification checks the recorded
package path/version, selected host, closed session, two sealed segments, activity
records, the store's own schema check and empty error logs. A fail-open shell hook
returning zero without its records fails qualification. The synthetic Skill
envelope does not establish a native Codex Skill callback or task execution.

Each fixture gets a fresh allowlisted environment, private HOME/TMP/state and
rejecting provider-command sentinels. Summary, harvest, briefing, prompt-text
capture and compatibility telemetry are explicitly disabled. Separate stores
exercise the session-store and child-process opt-outs. The startup hook runs
with briefing disabled. A fresh sweep marker prevents detached housekeeping in
the synthetic store; the synchronous lifecycle remains real packaged code.
No global settings, credentials, installed caches or real session history are
read or changed by these fixtures.

`qualification.json` deliberately reports `native_acceptance: "unknown"` and
`full_source_check: "not_run"`. A passing fixture is not evidence of native
installation, discovery, trust, context delivery, upgrade, rollback or removal.

## Source and publication gates

Before releasing, the release controller must run the complete `make check` in
a clean private checkout of the exact candidate, using the pinned development
toolchain, then run `make qualify-package` for that same commit. Keep its
source-check evidence external and bind it to the package receipt. Full source
checking does not run recursively inside package qualification. The contributor
and versioned release-note gates remain part of `make check`.

```sh
make qualify-release RELEASE_REF=<full-commit-sha> RELEASE_OUTPUT=/absolute/new-release-output
```

This controller target performs both gates without tagging. `make tag-release`
uses the same variables and creates the local tag after the gates pass.
`make publish-release` additionally requires `RELEASE_REPO=Claudfather/clauDNA`
and optionally `RELEASE_REMOTE=origin`; it pushes the exact tag and attaches the
package artifacts plus `source-check.json`. Tagging and publishing are separate
owner-authorized actions. Existing tags and attached artifacts must match the
candidate; the controller does not rewrite or clobber them.

### The `release-tag` workflow

`.github/workflows/release-tag.yml` runs on a push to `main` that touches
`.claude-plugin/plugin.json`. Its first step does two things before anything is
built:

- It pins `origin/main` in the runner's checkout to the tip that push replaced
  (`github.event.before`, or the pushed commit's parent when that commit is not in
  the fetched history, with a warning in the log: a version bump earlier in a force-pushed
  range is then not seen). The changelog gate in `make check` compares the candidate
  with `origin/main`, and the moving tip of a `main` that has since advanced would
  reject a correct release commit: its own `[Unreleased]` section no longer adds
  anything to the newer one.
- It compares the manifest `version` before and after the push. An edit that left
  it alone (to `hooks`, `description` or `keywords`) stops there with "nothing to
  release": no source check, qualification, tag or publication.

Otherwise it runs `make publish-release` for the pushed commit. The workflow has
no manual trigger. To publish a commit it did not, run the `make publish-release`
target above from a checkout of that commit whose local `origin/main` is the tip the
commit replaced, which is the relation the workflow pins.

What follows from that, so it is not rediscovered:

- The changelog gate and skill validation in the release run's `make check` now see the
  push's own changes. The release notes must land in the same push as the version bump
  (as `scripts/release.sh` does), and errors in skills that push touches block it.
- Only a change to the manifest `version` starts a release, including a revert or a
  downgrade, which fails at the tag-identity check once qualification runs. A later push
  that leaves the version alone does not retry a failed release: re-run the failed
  workflow run for the release commit (a re-run reuses the same push event, so the same
  pin) or use the manual route above.

The generated Claude descriptor uses the documented plugin source shape:

```json
{
  "source": "github",
  "repo": "Claudfather/clauDNA",
  "sha": "<full-40-character-lowercase-commit-sha>"
}
```

Claude's [marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference#plugin-sources)
documents `sha` for GitHub plugin entries. The commit must remain reachable from
the upstream repository. Keep the release tag pointing to the qualified commit;
an existing or raced tag that peels to another commit is a hard failure, never a
reason to rewrite it. Review and promote the descriptor separately through the
owner-controlled marketplace process. Cursor and Codex receive no invented pin
fields. The live manifest's version is not proof of the installed source bytes.

## Native acceptance and owner queue

After source checks and fixture qualification pass, the owner still controls
merge, tag/release publication, descriptor promotion and any authenticated native
acceptance. Retain archive/checksum/receipt/qualification and source-check
artifacts with the exact release. CI platform results establish their tested
platform only; they do not establish delivery to a user's machine.

For each authorized host acceptance run, retain host/version, exact package
commit and hashes, source registration, discovered skills, agent policy, hook
trust decision, actual hook/context receipt and observed state path. Use private
test identities and state so synthetic events cannot become user-history claims.

- **Upgrade:** install through the supported marketplace, reload the host, verify
  the selected package path and hashes against the target receipt, and observe
  discovery plus the supported lifecycle on that host. Preserve existing state.
- **Rollback:** select the prior supported release through the host's marketplace
  controls, reload, compare against that prior receipt and repeat the same
  acceptance checks. Do not infer rollback from a displayed version alone.
- **Uninstall:** remove through the host's plugin controls, reload and verify
  registration, discovery and hook inactivity. Retained session history is
  separate from plugin removal; deleting it requires separate authority.

Record unsupported or unavailable native steps as unknown and keep them in the
owner queue. Fixture evidence cannot discharge those acceptance steps.
