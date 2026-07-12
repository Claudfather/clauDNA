# Claudron Engine Contract

The Claudron-specific engine behavior, layered on `skills/_shared/infra-cli-contract.md`. One place defines how clauDNA skills talk to the `claudron` CLI and what they do when it is degraded or absent. Referenced by the `/claudron` engine skill and by every consumer that reads or writes the shared vault — `/claudna:recall` (read) and `/claudna:capture` (write) on the engine, and `/claudna:publish --to vault`.

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

The CLI resolves the vault from `CLAUDRON_VAULT` or a walk-up from cwd; **which env var wins, and the section-vs-env precedence + mismatch behavior, live once in `documentation-standard.md` §10** ("locating the root"). The ladder only *acts* on that: it never sets env (no clauDNA skill does), and it flags a root the CLI can't see — a `## Shared Documentation` section or `CLAUDRON_VAULT_PATH` set while the bare `CLAUDRON_VAULT` the CLI reads is unset.

Verdict → action:
- **present-with-vault** → use the engine.
- **present-no-vault** → remedy is `claudron init <path> --personal` (a positional path, not a flag). Never reported as "not installed."
- **absent** → the engine is unavailable; consumers with a fallback take it (§3), `/claudron` itself fails loudly.

**`requires:` is not this gate.** A consuming skill's `requires: [{cli: claudron}]` frontmatter is documentation, validated by `scripts/validate-skills.py` — Claude Code ignores it at runtime (it is not a recognized field: the description loads and the skill stays invocable regardless of whether `claudron` is installed). **This ladder is the only runtime gate.** A skill that shells to `claudron` runs it every time; it cannot lean on the frontmatter to keep itself from running when `claudron` is absent.

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

Transient exit-3 conditions get a **bounded retry — 2 attempts, short backoff** (a deliberate widening of infra-cli-contract §7's single retry) — then degrade. (`capture` is an unlocked local write in v0.2.0, so there is no lock contention to retry — cross-machine serialization is git's job in `sync`.)

**Degrade loudly** on exit 3 or an unrecognized envelope — whether the ladder returned a non-usable verdict *or* a usable verdict turned into a failure mid-call:
- **Writing consumer** (`/claudna:capture`, `publish --to vault`): take the frozen raw-tree path (write + `/claudna:index`) and **say so** — "Claudron vault unavailable — wrote to the raw tree; run `/claudna:index`." The *vault* is never written unguarded; the raw tree is the compat holding pen, not a second vault door.
- **Reading consumer** (`/claudron lookup`, `/claudron status`): nothing to fall back to — report the verdict + remedy (init pointer for no-vault; the git remedy for `SyncError`) and stop. `/claudna:recall` is the exception: its frozen fallback is the INDEX.md scan (§4).

**`--auto` result vocabulary** (the block itself is orchestration-guide.md's "Structured Result Shape"): writing consumers carry `artifacts.engine` — `"claudron"` on the engine path, `"fallback"` when degraded to the raw tree; reporting verbs (`status`) carry the ladder outcome in `artifacts.verdict` — `absent` / `present-no-vault` / `present-with-vault`. Any degradation lands in `errors[]`. Silence is the only forbidden outcome.

## 4. Fallback-freeze

The raw-tree paths are **frozen** compatibility behavior — the vault write + `/claudna:index` on the write side (`/claudna:capture`, `publish`), and the INDEX.md scan on the read side (`/claudna:recall`). No new capability lands on them; new features go on the engine path only.
