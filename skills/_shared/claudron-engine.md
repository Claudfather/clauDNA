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

`CLAUDRON_VAULT` (bare — the only var the CLI reads; `CLAUDRON_VAULT_PATH` is a clauDNA consumer alias the CLI does **not** honor) or a walk-up from cwd is how the CLI resolves the vault; the ladder never sets it (no clauDNA skill sets env — documentation-standard §10). If a `## Shared Documentation` section or `CLAUDRON_VAULT_PATH` names a root but `CLAUDRON_VAULT` is unset, the CLI will not see it — note the mismatch and point at `CLAUDRON_VAULT`.

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
| `write` → `capture` | `action` ∈ {`created`,`updated`,`suggest_update`,`suggest_supersede`,`rejected`}, `path`, `reason` |
| `lookup` → `lookup` | `query`, `results` (list) |
| `status` → `status` | `root`, `tiers`, `total_docs`, `total_stale`, `projects`, `fleets`, `quarantined`, `index_present`, `index_fresh`, `warnings` |

A missing top-level key, a `command` mismatch, or an absent expected `data` key is an **unrecognized envelope** → engine failure (§3). Do not parse a partial or guessed shape.

`path` is **absolute** for `created`/`updated` but **vault-relative** for `suggest_*` — resolve accordingly.

## 3. Failure posture — branch on the exit code, then degrade loudly

| Exit | Meaning | Posture |
|---|---|---|
| **0** | success | parse the envelope; if `ok:false` with `errors[]`, surface them |
| **1** | application refusal — `rejected` capture, or note already exists | surface `data.reason` + `errors[]`; **deterministic, never retry** |
| **2** | usage / bad input — malformed args or stdin JSON | the skill built the call wrong — a **bug**; surface stderr verbatim, loud; never retry |
| **3** | environment — no vault, or `SyncError` (not a git repo / git missing / timeout) | the **degrade** case (below) |

Transient failures (a retryable environment op) get a **bounded retry — 2 attempts, short backoff — then degrade**. `capture` is a local write with no lock in v0.2.0 (single-writer-per-machine; cross-machine serialization is git's job in `sync`), so retry targets genuinely transient exit-3 conditions — not lock contention (there is none), and never the deterministic exits 1/2.

**Degrade loudly** on exit 3 or an unrecognized envelope:
- **Consumer has a fallback** (`publish --to vault`, and later `learn`/`reflect`): take the raw-tree path and **say so** in the same breath — "Claudron vault unavailable — wrote to the raw tree; run `/claudna:index`."
- **Consumer has none** (`/claudron write`): fail with the explicit reason + remedy (init pointer for no-vault; the git remedy for `SyncError`). There is no raw-tree fallback for `/claudron write` by design — an unguarded write door recreates the noise problem the vault exists to avoid.

**In `--auto`** (orchestration-guide.md "Structured Result Shape"): any degradation lands in `errors[]`, and a taken fallback sets `artifacts.engine: "fallback"` (vs `"claudron"` on the engine path). Silence is the only forbidden outcome.

## 4. Fallback-freeze

The raw-tree path is **frozen** compatibility behavior: the vault write + `/claudna:index` that runs when the engine is absent. No new capability lands on it — new features go on the engine path only. When the ladder says present-with-vault, prefer the engine; the raw tree is for degrade and absence, nothing else.
