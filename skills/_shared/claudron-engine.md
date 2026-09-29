# Claudron Engine Contract

The Claudron-specific engine behavior, layered on `../_shared/infra-cli-contract.md`. One place defines how clauDNA skills talk to the `claudron` CLI and what they do when it is degraded or absent. Referenced by the `/claudron` engine skill and by every consumer that reads or writes the shared vault — `/claudna:recall` (read) and `/claudna:capture` (write) on the engine, and `/claudna:publish --to vault`.

`claudron` is a pre-1.0 external CLI. Two rules follow from that and govern everything below: **validate its envelope on every call** (never parse-and-guess an unrecognized shape), and **degrade loudly** (a fallback taken or an error hit is always visible, never silent).

**Verb vocabulary.** clauDNA's vault-facing verbs are named for Claudron's CLI verbs — one word per concept, extending the deference #199 set for the frontmatter *vocabulary* (output-guide §3). `/claudna:claudron`'s verbs mirror the CLI commands they wrap (the §2 table); `/claudna:recall` and `/claudna:capture` share their names with Claudron's `recall` and `capture` — the read and write doors. The other vault-writing occasion-workflow (documentation-standard §10's which-door table — `publish`) keeps a clauDNA-native name: it terminates in `capture`, it doesn't rename it.

**Layer boundary.** clauDNA is the skills / presentation / reasoning layer; `claudron` is the CLI / fetch layer it wraps when available. A skill consumes the CLI's `--json` data and owns the presentation on top of it (e.g. `/claudna:recall` labels tiers and picks the adaptive lead from `recall --json`). Claudron's *own* rendered output — `recall`'s human brief via `render_brief` — is for consumers with **no clauDNA skill in the loop**, most concretely the SessionStart hook injecting a token-budgeted brief. A skill reaches for `--json`, never the bare rendered form; the two are separate presentation surfaces over one fetched dataset, not a duplication to reconcile.

## 1. The detection ladder

Run before any engine call, as separate Bash calls (never chained — infra-cli-contract §5). Three terminal verdicts:

| Probe | Result | Verdict |
|---|---|---|
| `command -v claudron` | not found | **absent** |
| `claudron status --json` | exit 0 | **present-with-vault** — engine usable; `data` carries vault health |
| `claudron status --json` | exit 3 (stderr `no vault found`) | **present-no-vault** — installed but unconfigured |
| `claudron status --json` | other non-zero | **engine failure** (§3) — surface stderr |

**Vault resolution is Claudron's contract, not ours** — see `documentation-standard.md` §10 ("locating the root"), which owns the clauDNA-side statement and cites the owner. Not restated here. This ladder only *acts* on it: it never sets env (no clauDNA skill does), and it flags the one divergence §10's mismatch rule does not reach — §10 pairs env against the section, but once the engine is present the binding pair is **engine vs section**: a `## Shared Documentation` section path that differs from `data.root` in `claudron status --json`. Report both paths; the engine's is the one in force for every engine call.

**Identity, then capability.** On **present-with-vault**, `data.engine_version` (Claudron ≥ 0.3.0) says which engine is here: identity, read off the envelope rather than an install pin. Absent ⇒ pre-0.3.0. It is **not a feature gate**. A feature the engine declares is gated on `data.capabilities` (Claudron CLI_CONTRACT §Capability probe): `/claudna:claudron doctor` gates on `"doctor"` there. Absent `capabilities` means an engine that predates the list, which is the right answer for every capability in it. (`/claudna:capture`'s provenance-flags gate still reads `engine_version`; moving it is clauDNA#334.)

Verdict → action:
- **present-with-vault** → use the engine.
- **present-no-vault** → remedy is `claudron init <path> --personal` (a positional path, not a flag). Never reported as "not installed."
- **absent** → the engine is unavailable; consumers with a fallback take it (§3), `/claudron` itself fails loudly.

**Every consumer declares the dependency.** A skill whose body invokes `claudron` carries `requires: [{cli: claudron…}]` in its frontmatter, with a `reason` that says whether the dependency is hard or soft and which path needs it. `scripts/validate-skills.py` enforces this (a body that invokes `claudron` with no declaration is a hard error), so the declared set and the invoking set cannot drift apart.

**But `requires:` is not this gate.** A consuming skill's `requires: [{cli: claudron}]` frontmatter is documentation, validated by `scripts/validate-skills.py` — Claude Code ignores it at runtime (it is not a recognized field: the description loads and the skill stays invocable regardless of whether `claudron` is installed). **This ladder is the only runtime gate.** A skill that shells to `claudron` runs it every time; it cannot lean on the frontmatter to keep itself from running when `claudron` is absent.

## 2. The envelope — validate every call

Every `--json` invocation prints exactly one envelope on stdout (diagnostics go to stderr):

```json
{ "ok": true, "command": "capture", "data": { }, "warnings": [], "errors": [] }
```

Assert on every call: top-level `ok` (bool) / `command` (matches the verb) / `data` (object) / `warnings` / `errors` are present, then the inner `data` shape for the verb:

| Verb → CLI | `data` keys asserted |
|---|---|
| `capture` → `capture` | `action`, `path`, `reason` |
| `lookup` → `lookup` | `query`, `results` (list) |
| `recall` → `recall` | `project`, `query`, `conventions`, `notes` (list) |
| `status` → `status` | `root`, `tiers`, `total_docs`, `total_stale`, `projects`, `fleets`, `quarantined`, `index_present`, `index_fresh`, `warnings` |
| `doctor` → `doctor` | `vault_format`, `engine_format`, `pending` (list), `fixable` (list); after `--fix` also `applied`, `commit` |

A missing top-level key, a `command` mismatch, or an absent expected `data` key is an **unrecognized envelope** → engine failure (§3). Do not parse a partial or guessed shape.

For `lookup`, each entry in `data.results` is `title` / `score` / `match_type` / `tier` / `path` / `tags` (no `status`). For `recall`, each entry in `data.notes` carries `title` / `path` (vault-relative) / `tier` / `type` / `status` / `maturity` / `updated` / `summary` / `score`, where `score` is `null` on project-tier notes (membership, not relevance) and an integer on fleet/shared-tier notes — the null is the tier signal.

The `capture` `action` value drives the capture flow — its five values and their meaning (the source of truth; consumers branch on these, they don't redefine them):

| `action` | Meaning | `path` |
|---|---|---|
| `created` | new note written | absolute |
| `updated` | addendum appended (only via `capture --update`) | absolute |
| `suggest_update` | a **current** note already covers this | vault-relative |
| `suggest_supersede` | the near-duplicate is **stale** | vault-relative |
| `rejected` | validation failed; nothing written (exit 1) | — |

The engine always stamps a new note `draft`; **consumers never set or promote `maturity`** — promotion is Claudron curation.

## 3. Failure posture — branch on the exit code, then degrade loudly

| Exit | Meaning | Posture |
|---|---|---|
| **0** | success | parse the envelope; if `ok:false` with `errors[]`, surface them |
| **1** | application refusal — `rejected` capture, or note already exists | surface `data.reason` + `errors[]`; deterministic, never retry |
| **2** | usage / bad input — malformed args or stdin JSON | the skill built the call wrong — a bug; surface stderr verbatim; never retry |
| **3** | environment — no vault, or `SyncError` (not a git repo / git missing / timeout) | the **degrade** case (below) |

`doctor` is the one verb whose exit **1** is a completed result, not a refusal: it means at least one finding is an error (Claudron §Exit codes). `doctor.md` continues from it.

Transient exit-3 conditions get a **bounded retry — 2 attempts, short backoff** (a deliberate widening of infra-cli-contract §7's single retry) — then degrade. (`capture` is an unlocked local write in v0.2.0, so there is no lock contention to retry — cross-machine serialization is git's job in `sync`.)

**Degrade loudly** on exit 3 or an unrecognized envelope — whether the ladder returned a non-usable verdict *or* a usable verdict turned into a failure mid-call:
- **Writing consumer** (`/claudna:capture`, `publish --to vault`): take the frozen raw-tree path (write + `/claudna:index`) and **say so**, using the standard notice below. The *vault* is never written unguarded; the raw tree is the compat holding pen, not a second vault door.
- **Reading consumer** (`/claudron lookup`, `/claudron status`, `/claudron doctor`): nothing to fall back to — report the verdict + remedy (init pointer for no-vault; the git remedy for `SyncError`) and stop. `/claudna:recall` is the exception: its frozen fallback is the INDEX.md scan (§4).

### 3.1 The standard degradation notice

Every branch in every consumer that finds Claudron missing or unusable emits **this one line first**, before anything else it prints:

> **`Claudron unavailable (<verdict>) — <fallback>. Install / configure: https://github.com/Claudfather/Claudron (clauDNA-side setup: SETUP_GUIDE §7 "Claudron Integration").`**

`<verdict>` is the §1 ladder verdict the branch acted on — `absent` (the CLI is not on PATH) or `present-no-vault` (installed, unconfigured) — or `engine failure` when a usable verdict failed mid-call. `<fallback>` is the consumer's row below, and it names the path *actually taken*, never a generic "degraded":

| Consumer | `<fallback>` |
|---|---|
| `/claudna:capture` | `wrote to the raw tree; run /claudna:index` |
| `/claudna:publish --to vault` | `writing the raw tree; run /claudna:index` |
| `/claudna:recall` | `scanning the raw tree's INDEX.md instead` |
| `/claudna:index` | `treating the target as a raw tree, since engine-managed roots cannot be confirmed` |
| `/claudna:init-project` (Step 6.5) | `offering a raw-tree scaffold instead of a vault` (absent), or `printing the vault-init remedy and writing nothing` (present-no-vault) |
| `/claudna:claudron` (`lookup`, `status`, `doctor`) | `no fallback — reporting the verdict and stopping` |

Consumers quote their row rather than wording it themselves. One shape is the point: a user who has seen the notice once recognizes it from any skill, and a literal prefix stays greppable across transcripts — which an improvised sentence per skill is not.

**In `--auto`, the notice is not optional and not only prose.** The same line goes into `errors[]`, and writing consumers set `artifacts.engine: "fallback"`. **No silent fallback exists**: a branch that takes a fallback without emitting the notice is a defect, not a quiet success, and a run that prints nothing is indistinguishable from a run where the engine worked.

One carve-out, and only one: **`/claudron status` prints the notice but leaves `errors[]` empty.** Reporting the verdict is that verb's entire purpose, so absence there is a successful result rather than a degradation — it carries the verdict in `artifacts.verdict` instead. Every other consumer in the table above is degrading when it prints the notice, and records it.

**`--auto` result vocabulary** (the block itself is orchestration-guide.md's "Structured Result Shape"): writing consumers carry `artifacts.engine` — `"claudron"` on the engine path, `"fallback"` when degraded to the raw tree; reporting verbs (`status`) carry the ladder outcome in `artifacts.verdict` — `absent` / `present-no-vault` / `present-with-vault`. Any degradation lands in `errors[]`. Silence is the only forbidden outcome.

## 4. Fallback-freeze

The raw-tree paths are **frozen** compatibility behavior — the vault write + `/claudna:index` on the write side (`/claudna:capture`, `publish`), and the INDEX.md scan on the read side (`/claudna:recall`). No new capability lands on them; new features go on the engine path only.
