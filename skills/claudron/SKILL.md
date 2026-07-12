---
name: claudron
user-invocable: true
description: "Use to search the shared fleet vault by term, or check vault health — the lookup and status verbs over the Claudron CLI. Requires the Claudron CLI. To save knowledge to the vault (a note, external content, or the current session's learnings), use /claudna:capture; to recall prior knowledge before starting work, use /claudna:recall."
argument-hint: "[lookup|status] [--project p] [--fleet f] [--limit n] [--auto]"
requires:
  - cli: claudron>=0.2
    reason: "Claudron CLI — vault search (lookup) and health (status) verbs; v0.2.0 is the envelope/exit-code contract this engine targets"
---

# Claudron

One engine for reading the shared knowledge vault — `lookup` and `status` as verb modes over the `claudron` CLI. Shared engine behavior lives in `skills/_shared/infra-cli-contract.md`; the Claudron-specific detection ladder, envelope validation, and degrade-loudly posture live in `skills/_shared/claudron-engine.md`. This file supplies only routing and the Claudron deltas. (Writing to the vault is `/claudna:capture` — one write door, off the engine.)

## Mode dispatch (contract §3)

Arguments to dispatch (first token = verb, the rest belong to the verb): $ARGUMENTS

No verb token → infer only when the request wording is unambiguous ("what does the vault know about X" → `lookup`; "is the vault healthy / is Claudron installed" → `status`); otherwise print this table and stop.

| Verb | When | Depth file |
|------|------|------------|
| `lookup` | Search the vault for existing notes by term | `lookup.md` |
| `status` | Vault health — tiers, doc counts, staleness — or whether Claudron is installed and configured at all | `status.md` |

For the selected verb, read ONLY its depth file in this skill directory and follow it exactly — never load another verb's depth (contract §1, §3).

## Pre-flight deltas (contract §4)

Each verb resolves its state through the **detection ladder in `skills/_shared/claudron-engine.md` §1** — it replaces the generic CLI-installed / auth / target-discovery pre-flight and yields one of three verdicts (present-with-vault / present-no-vault / absent). `lookup` runs it at pre-flight and requires present-with-vault; `status` runs it as its own Step 1 and reports the verdict in all three states. Each verb gates on the verdict in its depth file's Step 0. Every `--json` call is envelope-validated per §2; failures follow the exit-code posture in §3.

**Door note (F1).** clauDNA ships no MCP servers — this engine *is* the CLI. If Claudron's own MCP tools are configured in the session, they are the same engine with equivalent semantics; the CLI is the contract floor this skill targets.

## Structured result (`--auto`)

In `--auto`, each verb's final output is the single **structured result** JSON block defined in `skills/_shared/orchestration-guide.md` ("Structured Result Shape") — `status` carries `artifacts.verdict` (per claudron-engine.md §3), any degradation in `errors[]`, and no interactive prompts. Per-verb fields are defined in the depth files.

`lookup` and `status` are both read-only and never gate — this engine no longer mutates. The vault's write door is `/claudna:capture`.
