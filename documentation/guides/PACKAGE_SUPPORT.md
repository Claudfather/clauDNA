---
title: "Package support and lifecycle"
type: knowledge
status: current
owner: claudna
created: 2026-11-04
updated: 2026-11-04
---

# Package support and lifecycle

clauDNA is a marketplace plugin, with no server to start. The table below is a
projection of the package manifests and skill frontmatter. Selection means the
package declares a skill; it does not prove native discovery, execution or task
success on any particular host/version. Native certification remains unknown
until a separate acceptance receipt identifies the host, version and package bytes.

## Local package doctor

Use the absolute root of the package that the host actually loaded. The directory
entrypoint works with Python 3.9+ and its standard library, including `python3 -S -B`,
from any working directory (including paths with spaces):

```sh
python3 -B "/absolute/loaded/package/lib/claudna/package_support" doctor --host codex --json
python3 -B "/absolute/loaded/package/lib/claudna/package_support" doctor --host cursor --skill capture
```

Keep `-B` to suppress CPython's entrypoint bytecode cache, which can be written
before the doctor's own no-bytecode setting runs. `--host` is required:
`claude-code`, `cursor` or `codex`. `--skill` checks only that
manifest-selected workflow's declared prerequisites. Cursor can call this CLI
directly; its excluded `using-claudna` skill remains excluded. `--root` selects an
explicit alternate package to inspect; without it the root comes from the loaded
doctor code, never cwd, environment overrides or a cache search. An older package
without this entrypoint needs the supported update workflow, not a doctor borrowed
silently from another checkout.

The doctor validates the generated JSON schema, its source inventory and hashes,
manifest membership, declared hook paths and required bundled files. It does not
parse YAML at runtime. Hashes establish consistency with the generator's recorded
sources, not publisher authenticity or a signature. Missing/stale/malformed
metadata, missing files, traversal and symlinked metadata fail diagnosis.

Dependency checks inspect PATH presence and environment-variable presence only.
Values, resolved executable paths, parser input and raw errors are not printed.
No PATH command is launched, so a found versioned binary remains **unknown** until
separately checked. `runtime.python` measures the running interpreter; a different
`python3` on PATH is only presence-checked. Missing baseline commands affect their
consumers, not all workflows. In particular, absent `jq` disables the Claude
permission hook. Native installed/discovered, trusted and executed states remain
separate unknowns.

Text and `--json` share the following exit contract. JSON schema
`claudna.package-doctor/1` includes `package_version`, `host`, `skill`, `status`,
`exit_code`, stable `checks` rows (`id`, `status`, `summary`), `pipeline_health`
and `limits`. Row statuses are `pass`, `warn`, `fail` and `unknown`; unknown alone
does not make the exit nonzero.

| Exit | Report status | Meaning |
|---:|---|---|
| 0 | `observed` | No concrete local issue found; unknowns still require separate evidence. |
| 1 | `attention` | A scoped dependency/runtime issue or pipeline evidence needs attention. |
| 2 | `invalid` | The request or package cannot be diagnosed; do not treat partial checks as acceptance. |

By default no store or other user cache is scanned. To include retained pipeline
evidence, select its root explicitly:

```sh
python3 -B "/absolute/loaded/package/lib/claudna/package_support" doctor --host codex --store-root "/absolute/selected/store" --json
```

This reuses `session_store.health.report`; it adds no records, workers or ledger.
An absent store stays absent and reports `no_evidence`, not healthy coverage.
Private-session content is excluded by that existing health boundary. Neither
mode writes bytecode, repairs files, installs dependencies, probes a provider,
launches a native host nor changes auth/trust/settings. The snapshot can become
stale while another process changes package or store files.

## Declared support

<!-- BEGIN GENERATED PACKAGE SUPPORT -->

Source package version: **0.34.10**. Generated declarations; native certification is **unknown**.

| Host | Selected skills | Agent policy | Declared hook handlers | Baseline checks |
|---|---:|---|---|---|
| claude-code | 40 | Native agent definitions | 13 — Claude lifecycle, permission, formatting and notification hooks | `python3>=3.9`, `bash`, `jq`, `git`, `gh`, `node`, `npx` |
| codex | 37 | Read-and-dispatch prompts only; no native agent registration | 6 — Session store and startup briefing only; operator hook trust required | `python3>=3.9`, `bash`, `git` |
| cursor | 35 | Native agent definitions | 0 — No hooks | Workflow-specific only |

| Skill | Claude Code | Cursor | Codex | Context restriction |
|---|:---:|:---:|:---:|---|
| [adversarial-review](../../skills/adversarial-review/SKILL.md) | Selected | Selected | Selected | None declared |
| [audit](../../skills/audit/SKILL.md) | Selected | Selected | Selected | None declared |
| [build](../../skills/build/SKILL.md) | Selected | Selected | Selected | None declared |
| [build-all](../../skills/build-all/SKILL.md) | Selected | Selected | Selected | None declared |
| [capture](../../skills/capture/SKILL.md) | Selected | Selected | Selected | None declared |
| [claudron](../../skills/claudron/SKILL.md) | Selected | Selected | Selected | None declared |
| [cleanup-legacy-install](../../skills/cleanup-legacy-install/SKILL.md) | Selected | Excluded | Excluded | None declared |
| [dbt](../../skills/dbt/SKILL.md) | Selected | Selected | Selected | None declared |
| [delegate](../../skills/delegate/SKILL.md) | Selected | Excluded | Selected | None declared |
| [development-retro](../../skills/development-retro/SKILL.md) | Selected | Selected | Selected | None declared |
| [extract-system-spec](../../skills/extract-system-spec/SKILL.md) | Selected | Selected | Selected | None declared |
| [file-github-issue](../../skills/file-github-issue/SKILL.md) | Selected | Selected | Selected | None declared |
| [find-skills](../../skills/find-skills/SKILL.md) | Selected | Selected | Selected | None declared |
| [forge](../../skills/forge/SKILL.md) | Selected | Selected | Selected | None declared |
| [github-activity-report](../../skills/github-activity-report/SKILL.md) | Selected | Selected | Selected | None declared |
| [heist](../../skills/heist/SKILL.md) | Selected | Selected | Selected | None declared |
| [index](../../skills/index/SKILL.md) | Selected | Selected | Selected | None declared |
| [init-project](../../skills/init-project/SKILL.md) | Selected | Selected | Selected | None declared |
| [investigate-app](../../skills/investigate-app/SKILL.md) | Selected | Selected | Selected | None declared |
| [ironclad](../../skills/ironclad/SKILL.md) | Selected | Selected | Selected | None declared |
| [kindle](../../skills/kindle/SKILL.md) | Selected | Selected | Selected | None declared |
| [modal](../../skills/modal/SKILL.md) | Selected | Selected | Selected | None declared |
| [neon](../../skills/neon/SKILL.md) | Selected | Selected | Selected | None declared |
| [product-enhance](../../skills/product-enhance/SKILL.md) | Selected | Selected | Selected | None declared |
| [product-vision](../../skills/product-vision/SKILL.md) | Selected | Selected | Selected | None declared |
| [promotion-intake](../../skills/promotion-intake/SKILL.md) | Selected | Excluded | Excluded | repo-clone |
| [publish](../../skills/publish/SKILL.md) | Selected | Selected | Selected | None declared |
| [qa](../../skills/qa/SKILL.md) | Selected | Selected | Selected | None declared |
| [railway](../../skills/railway/SKILL.md) | Selected | Selected | Selected | None declared |
| [recall](../../skills/recall/SKILL.md) | Selected | Selected | Selected | None declared |
| [review-work](../../skills/review-work/SKILL.md) | Selected | Selected | Selected | None declared |
| [session](../../skills/session/SKILL.md) | Selected | Selected | Selected | None declared |
| [ship](../../skills/ship/SKILL.md) | Selected | Selected | Selected | None declared |
| [skill-scaffold](../../skills/skill-scaffold/SKILL.md) | Selected | Excluded | Excluded | repo-clone |
| [sync-branches](../../skills/sync-branches/SKILL.md) | Selected | Selected | Selected | None declared |
| [using-claudna](../../skills/using-claudna/SKILL.md) | Selected | Excluded | Selected | None declared |
| [vercel](../../skills/vercel/SKILL.md) | Selected | Selected | Selected | None declared |
| [verify-completion](../../skills/verify-completion/SKILL.md) | Selected | Selected | Selected | None declared |
| [weigh-development-paths](../../skills/weigh-development-paths/SKILL.md) | Selected | Selected | Selected | None declared |
| [worktree](../../skills/worktree/SKILL.md) | Selected | Selected | Selected | None declared |

Baseline checks have different consequences; they are not a universal execution gate. Per-tool reasons and skill-specific prerequisites are in the [generated catalog](../../lib/claudna/package_support/catalog.json).

- **claude-code:** Declared packaging only. Native discovery, hook execution and context delivery require separate evidence. Notifications are macOS-specific.
- **codex:** Declared packaging only. Native install/discovery, trust, execution and stdout delivery are separate unknowns. Desktop delegation does not certify native CLI support; procedure-entry records do not prove task completion.
- **cursor:** Declared packaging only. Native discovery and execution are unverified by this catalog. Hook capture is unsupported; workflow-specific prerequisites still apply.

<!-- END GENERATED PACKAGE SUPPORT -->

Claude Code's default skill discovery includes context-restricted contribution
skills; they still need their declared source checkout. Cursor and Codex exclude
those skills through their manifests. Runtime hooks use the Python standard
library on macOS/Linux with Python 3.9 or newer; Windows runtime support is not
claimed. Cursor has no clauDNA hooks or automatic local session capture. Optional
formatters and service CLIs apply only to the workflows that use them. The host
application and its authentication are managed separately by the operator.

## Install, update, pin and remove

Use one native marketplace installation per host and scope. The package contains
host-specific marketplace manifests and the existing [Cursor logo](../../assets/logo.svg).
A repository URL or submission-ready asset does not establish public marketplace
approval. Inspect the native installed version and selected content after each
change, then start a fresh session; loaded instructions can outlive removal.

### Claude Code

Install through the interactive marketplace interface:

```text
/plugin marketplace add Claudfather/clauDNA
/plugin install claudna@Claudfather
```

Update with `claude plugin update claudna@Claudfather`. Disable with
`claude plugin disable claudna@Claudfather`, or uninstall with
`claude plugin uninstall claudna@Claudfather --scope user`; use the scope where
you installed it (`user`, `project` or `local`). These are native interfaces in
the [Claude Code command reference](https://code.claude.com/docs/en/plugins/cli-reference).
Headless provisioning is in [SETUP_GUIDE §4](../../SETUP_GUIDE.md#4-headless--ci--docker-provisioning).

The shipped GitHub marketplace entry follows the default branch: it has no
`ref`/`sha` pin. A maintainer-controlled marketplace can use native Git source
pinning, as described in the [marketplace documentation](https://code.claude.com/docs/en/plugin-marketplaces).
There is no clauDNA consumer rollback command or certified version-selection
workflow. Do not edit an installed cache to simulate a rollback.

### Cursor

Open **Customize**, find the plugin in an available marketplace, then **Install**
at project or user scope. A team admin can use **Dashboard → Plugins & MCPs →
Add Marketplace → Import from Repo** with `https://github.com/Claudfather/clauDNA`.
Team marketplaces support **Refresh**, or **Auto Refresh** for supported GitHub
imports. A running Cloud Agent retains its starting version; start a new agent
after an update. Manage removal in **Customize** at the installed scope; a
team-required plugin cannot be uninstalled by its members. These flows are
documented in [Cursor's plugin guide](https://cursor.com/docs/plugins).

No per-user pin/rollback interface is qualified here. Team branch selection and
refresh do not prove an immutable package pin. The public marketplace submission
remains separate from team/private availability. Local copies are a development
path described in [README](../../README.md#cursor), not a second updater.

### Codex

Use the installed host's plugin marketplace interface. The bundled CLI
`0.163.0-alpha.11.1` exposes the following help-verified forms (2026-11-04):

```sh
codex plugin marketplace add Claudfather/clauDNA
codex plugin add claudna@Claudfather
codex plugin marketplace upgrade Claudfather
codex plugin remove claudna@Claudfather
```

`marketplace upgrade` refreshes the configured snapshot; that alone does not
prove that an installed plugin or running session adopted the new bytes. Use
the host's installed-plugin view and inspect its version/content. Help also
offers `marketplace add <source> --ref <ref>` for selecting a Git ref; an immutable
pin and rollback lifecycle have not been qualified. There is no help-advertised
`plugin update` or `plugin rollback` command in this measured CLI. Check your
version's `codex plugin --help` before applying these forms. Help inspection is
interface evidence only, not an executed installation/removal receipt.

Hook trust remains a separate operator action; installation is not permission to
execute hooks. Role prompts need actual same-host spawn/wait controls. See
[Codex setup](../../SETUP_GUIDE.md#codex-workflows-and-continuity) and the
[tool mapping](../../skills/_shared/codex-tools.md). No global settings, feature
flags or native agent registrations are needed from clauDNA to simulate support.

## Privacy, retained data and support

New Claude Code and Codex sessions default to bounded, redacted prompt capture,
summaries and draft harvesting. Summaries use the existing Claude runner and send
redacted transcript prose to that model provider; they are not entirely offline.
Artifacts stay local and clauDNA adds no analytics uploader. Set choices before
opening a session; recorded opt-outs survive resumes. The full behavior and
retention contract is [SETUP_GUIDE §3.7](../../SETUP_GUIDE.md#37-session-store-capture-summaries-and-harvest-on-by-default).

- `CLAUDNA_SESSION_STORE=0` disables store hooks. Claude's separate compatibility
  telemetry can still be explicitly enabled with `CLAUDNA_TELEMETRY=1`.
- `CLAUDNA_SESSION_SUMMARY=0` disables automatic model summaries;
  `CLAUDNA_HARVEST=0` disables draft harvesting and normally automatic summaries.
- `CLAUDNA_CAPTURE_PROMPTS=0` omits prompt text, but does not itself disable
  summaries reading the host transcript. `CLAUDNA_SKILL_LOG=0` opts out of skill
  identity records. `CLAUDNA_SESSION_BRIEFING=0` disables startup context.
- Marking a session private suppresses subsequent activity, summaries and harvest;
  it does not erase earlier records. A Codex procedure-entry record proves only
  agent-attested procedure entry; missing records mean unobserved activity.

Native uninstall removes the host installation, not clauDNA's separately stored
history in `~/.claudna/`, Claude's compatibility telemetry in
`~/.claude/telemetry/skill-events.jsonl`, or project `.claude/session.md` handoffs.
Overrides may place data elsewhere. Retained historical state from pre-0.22
installs may also exist at `${XDG_STATE_HOME:-~/.local/state}/claudna/`. Review
these locations before explicitly deleting personal history. Preserve unrelated
plugins and project files; removal never requires deleting a shared marketplace.

For an installation problem, use the existing `using-claudna health` skill where
selected. Its pipeline view is the read-only
`python3 "<loaded-plugin-root>/lib/claudna/session_store" health --json` command.
Use the loaded root, not a newer source checkout. Cursor hook capture is
unsupported. For support, [open an issue](https://github.com/Claudfather/clauDNA/issues)
with host/version, package version, selected manifest and hashes, expected versus
observed behavior, and a redacted diagnostic excerpt. Do not publish tokens,
environment values, transcript/prompt text, raw session logs or personal paths.

## Maintaining this projection

Edit the existing manifests and skill frontmatter for inventory changes.
[host-policy.json](../../lib/claudna/package_support/host-policy.json) owns only
host paths, baseline prerequisites, capabilities and evidence limits, with no
second skill roster. Then run `python3 scripts/generate_package_support.py` and
commit [catalog.json](../../lib/claudna/package_support/catalog.json) plus the
generated table above. `make check-package-support` (also in `make check`) fails
on drift without writing. Development parsing reuses `plugin_scope.py` and
`skill_checks.py`; the shipped projection has no runtime YAML dependency.

The `claudna.package-support/1` JSON contains `package_version`, `hosts`, `skills`
and `sources`. Source paths are relative to the package root; `sources` maps each
policy, manifest, hook configuration and complete `SKILL.md` to its SHA-256.
Consumers must verify hashes and canonical skill-file membership before trusting
the projection. Hashes establish consistency with those inputs, not authenticity
or native execution. Added/removed skills also require regeneration.
