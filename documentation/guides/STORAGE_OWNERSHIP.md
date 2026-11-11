---
title: clauDNA storage ownership
type: knowledge
status: current
owner: claudna
created: 2026-11-11
updated: 2026-11-11
---

# Storage ownership

`R` is the absolute effective clauDNA root: `CLAUDNA_STATE_DIR` when set,
otherwise `$HOME/.claudna`. An explicit CLI `--root` selects the same contract
for that invocation. A missing home without an absolute root is an error.
Configuration chooses the root; it is not a promise of hostile-symlink isolation.
Existing ancestor directories remain trusted and are never chmodded by allocation.

## Owners and exceptions

| Owner | Location |
|---|---|
| Native session | `R/sessions/<exact-native-id>/` |
| Global preferences, coordination, compatibility observations | Named paths directly beneath `R` |
| Explicit standalone maintainer/CI operation | `R/operations/op-<32 lowercase hex digits>/` |
| Native host logs, transcripts, authentication, settings, memory and installations | Host-owned location, unchanged |
| Intentional source/configuration edits and Git worktrees | Selected project/workspace |
| Explicit artifact export/publication | Requested destination; preserve the canonical owned artifact |

No timestamp, cwd, latest-session selection, invented ID, OS-temp fallback or
operation-ID fallback supplies missing native ownership. Global coordination
may point to a session but cannot become its full payload store. This contract
extends the existing session store; it adds no analytics store or lifecycle kind.

## Manual allocation

Invoke the directory entry point from the actual loaded package, with `-B`:

```sh
python3 -B "<loaded-package>/lib/claudna/session_store" paths --host codex --session "<verified-native-id>" --kind artifacts --create
python3 -B "<loaded-package>/lib/claudna/session_store" scratch --host codex --session "<verified-native-id>" --label review
```

The examples require actual resolved values. `paths` is a pure lookup unless
`--create` is supplied. Kinds are `scratch`, `artifacts`, `handoff`, `hooks`, and
`delegation`. Creating the handoff path creates only its parent, never an empty
handoff. Scratch is uniquely allocated beneath the session's `scratch/` with
an ASCII label `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. New directories are 0700 and
owned files are 0600. Allocation failure returns nonzero without a fallback.

`--host` binds the provider. A caller must first obtain its real native session
identity through the host surface. Known environment identities and retained
lifecycle provider must agree with the supplied owner. CLI syntax validation
alone does not establish that a host delivered its ID. Missing/conflicting or
unresolved identity means no persistence; interactive workflows explain the
limit and automatic writers fail open. Cursor remains hook-free.

Explicit manual artifacts work with capture disabled and never enable capture
or synthesize lifecycle records. Artifact-only directories (including interrupted
empty allocations) differ from captured sessions. Existing lifecycle, event or
projection remnants without a valid opening remain partial/corrupt and visible
to diagnostics. A later genuine session opening can preserve and adopt the
artifact directory. `exists()` and session enumeration retain their physical
meaning; readers requiring lifecycle evidence use `capture_state` explicitly.
Unknown privacy never authorizes cross-session artifact discovery. Captured
lifecycle privacy remains authoritative, as do `consumers.json` acknowledgments.
Segment retention does not delete arbitrary artifacts or handoffs.

## Standalone maintainer operations

```sh
python3 -B "<loaded-package>/lib/claudna/session_store" operation-dir --label qualification --create
python3 -B "<loaded-package>/lib/claudna/session_store" operation-dir --operation-id "<allocated-operation-id>"
```

The label form requires `--create` and generates an exclusive operation ID.
The explicit-ID form is read-only unless `--create` is supplied; creation fails
on an existing directory. Allocation returns the absolute root containing
`scratch/`, `artifacts/` and `operation.json` with version, operation ID and label
(null for explicit-ID allocation). Partial failures identify the exact retained
allocation; a retry never adopts an existing directory. No session index or
lifecycle event is created. This interface is only for explicitly invoked
standalone work, never a host workflow missing its native identity.

After the exact writer has been observed exited, its owner may remove only its
exact scratch allocation. Unknown/running writers retain their scratch.
Abrupt termination can leave private residue: no age sweep or broad deletion is
authorized. Durable artifacts and operation markers survive scratch cleanup.

## Capability and cutover gates

| Surface | Native identity source to qualify | Evidence requirement |
|---|---|---|
| Claude hook | Native event `session_id`, provider claude | Actual hook plus ordinary scratch/artifact write receipt |
| Claude local/plugin skill | Rendered `${CLAUDE_SESSION_ID}` | Actual invocation; a raw file read or shell variable is insufficient |
| Codex hook | Native event `session_id`, provider codex | Actual hook receipt, separate from Desktop skill execution |
| Codex skill | Surface-provided native thread/session ID; present aliases agree | Qualify each actual execution surface separately |
| Cursor hook-free skill | Native identity transport remains to be established | Actual hook-free invocation and write receipt; no added hooks |

Each receipt binds loaded revision, host version/surface, identity source,
ordinary write outcome, capture-off behavior and observed filesystem effects.
Missing evidence is unverified, not unsupported. A hook-only transport cannot
qualify a hook-free workflow. No global grants or authentication changes are
part of qualification. Broad workflow defaults wait for these prerequisites.

The first two phases supply allocation/classification and runtime ownership.
Continuity, broad workflow defaults and maintainer callers remain pending their
owning phases. Existing tests passing
does not establish package-wide root compliance. The integration stack remains
unmerged and unreleased pending native and consumer acceptance, a compatible
recovery candidate or approved forward recovery, and the owner's breaking-release
decision. An arbitrary old package is not a qualified rollback.

## Runtime writers

### Session continuity (phase03 source contract)

Continuity payloads belong to the verified native session at
`R/sessions/<native-sid>/handoff.md`. The qualified host surface supplies the
real native SID/provider; no cwd, timestamp, operation ID, or reconstructed
identifier may fill a missing value. The CLI returns the absolute handoff path.
That current artifact location is distinct from the source session identity in
a resolved predecessor or artifact reference.

`handoff-write --session <sid> --host <host> [--background] --json` accepts a
complete v2 document on stdin. The runtime validates its v2 schema, absolute
cwd, UTC timestamp, and 1 MiB bound, then persists it atomically. It does not
create lifecycle records. Capture-off suppresses background writes; an explicit
manual user request may still write when native identity is verified. No writer
manages `.gitignore`.

Scoped continuity pointers are indexed under
`R/continuity/<sha256-canonical-scope>/index.json`. Scope is an absolute realpath
workspace or an explicit stable runtime key. Resolution matches kind and scope;
ambiguous matches require a workflow selector or explicit source SID. There is
no latest selection or session-directory scan. Publishing uses compare-and-swap
when replacing an existing reference. A stale, ambiguous, or corrupt pointer
stops resolution and does not trigger legacy fallback. Payloads remain in their
owning session and are not copied into the index. `continuity context --privacy
public|private --scope <scope>` writes artifact-only discovery metadata under
the current native session; public permits local cross-session discovery, while
captured private lifecycle privacy remains authoritative. Context publication
does not open a session or emit lifecycle events. `continuity artifact-path`
resolves artifact references separately from handoff references.

Legacy import reads only an explicitly selected source. The caller binds the
selected bytes with `--source-sha256 <hex>`; import verifies that digest before
mutating state. The source remains read-only. The importer converts a copy to
v2, writes an immutable receipt under the destination session's
`artifacts/imports/<source-key-hash>/<source-sha256>.json`, durably writes the
handoff, then publishes the pointer. The same fingerprint is idempotent across
targets; changed content needs an explicit `reimport`. A failed import does not
publish a pointer. These are staged source contracts; native-host and external
consumer acceptance remain pending.

The compatibility feed is global at `R/telemetry/skill-events.jsonl`, with its
prune lock/marker and sanitized file-level diagnostic sidecars. An override must
be absolute and inside R; invalid configured destinations produce a bounded
notice without feed writes or silent redirection. Existing schema, population,
null-SID rows, privacy locks, child suppression and opt-outs are preserved.
Explicit telemetry-on with capture off is a standalone observation. A canonical
skill event and its compatibility row describe the same invocation, not two uses.

Automatic startup/formatter scratch uses the native event owner. Missing identity
or allocation skips the scratch-dependent part and never falls back to OS temp.
Only the invocation's allocated directory is removed after its writers exit.
Permissions/reflection/attributable diagnostics and summary stderr live in the
session's `hooks/`; global bootstrap/whole-store diagnostics retain fixed codes
and counts. Health exposes aggregate counts without payload/private identity.

Delegation keeps one global lock and a version-1 `active.json` containing only
`version`, `job_id`, `parent_sid`, `parent_provider`. It derives the durable 32 KiB
payload path from those validated identities under the parent session, writes it
before publishing the pointer, and preserves the payload after terminal cleanup.
Legacy full records are recognized read-only without migration. Unresolved or
unknown legacy slots are retained; known-terminal legacy coordination keeps its
existing exact-match cleanup, including absent parent history. Unknown execution,
missing payload, identity/provider mismatch, corrupt parent history and orphans
retain evidence and never cause a relaunch. An older reader treats a
new pointer as unknown. A known-terminal payload permits pointer cleanup without
recreating absent parent lifecycle history; payload/artifacts remain.

Runtime entrypoints suppress bytecode; existing caches are not deleted. Authorized
repo-list saves use `R/repo-health-repos.txt`; authorized legacy-install cleanup
backs up under `R/backups/legacy-install/<run>/`. Old saved lists/backups are
read-only inputs for explicit discovery/restore, never silently migrated.
