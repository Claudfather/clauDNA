# Claudron Engine Contract

The Claudron-specific engine behavior, layered on `skills/_shared/infra-cli-contract.md`. One place defines how clauDNA skills talk to the `claudron` CLI and what they do when it is degraded or absent. Referenced by the `/claudron` engine skill and by every fallback consumer that writes or reads the shared vault — `/claudna:publish --to vault` today, `/claudna:remember` / `/claudna:learn` / `/claudna:reflect` as epic #197 lands them.

`claudron` is a pre-1.0 external CLI. Two rules follow from that and govern everything below: **validate its envelope on every call** (never parse-and-guess an unrecognized shape), and **degrade loudly** (a fallback taken or an error hit is always visible, never silent).

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
| `write` → `capture` | `action`, `path`, `reason` |
| `lookup` → `lookup` | `query`, `results` (list) |
| `status` → `status` | `root`, `tiers`, `total_docs`, `total_stale`, `projects`, `fleets`, `quarantined`, `index_present`, `index_fresh`, `warnings` |

A missing top-level key, a `command` mismatch, or an absent expected `data` key is an **unrecognized envelope** → engine failure (§3). Do not parse a partial or guessed shape.

The `capture` `action` value drives the write flow — its five values and their meaning (the source of truth; consumers branch on these, they don't redefine them):

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
- **Consumer has a fallback** (`publish --to vault`, and later `learn`/`reflect`): take the raw-tree path and **say so** — "Claudron vault unavailable — wrote to the raw tree; run `/claudna:index`."
- **Consumer has none** (`/claudron write`): fail with the explicit reason + remedy (init pointer for no-vault; the git remedy for `SyncError`). There is no raw-tree fallback for `/claudron write` by design — an unguarded write door recreates the noise the vault avoids.

**`--auto` result vocabulary** (the block itself is orchestration-guide.md's "Structured Result Shape"): writing consumers carry `artifacts.engine` — `"claudron"` on the engine path, `"fallback"` when degraded to the raw tree; reporting verbs (`status`) carry the ladder outcome in `artifacts.verdict` — `absent` / `present-no-vault` / `present-with-vault`. Any degradation lands in `errors[]`. Silence is the only forbidden outcome.

## 4. Fallback-freeze

The raw-tree path is **frozen** compatibility behavior: the vault write + `/claudna:index` that runs when the engine is absent. No new capability lands on it — new features go on the engine path only.
