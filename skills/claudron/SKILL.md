---
name: claudron
user-invocable: true
description: "Use to deliberately save knowledge to the shared fleet vault, look it up, or check vault health — the capture, lookup, and status verbs over the Claudron CLI. Requires the Claudron CLI; without it, save to the vault via /claudna:publish. For recalling prior knowledge before starting work, use /claudna:recall; for distilling the current session's learnings, use /claudna:reflect."
argument-hint: "[capture|lookup|status] [--type t] [--title s] [--project p] [--tags a,b] [--auto]"
requires:
  - cli: claudron>=0.2
    reason: "Claudron CLI — vault capture, search (lookup), and health (status) verbs; v0.2.0 is the envelope/exit-code contract this engine targets"
---

# Claudron

One engine for the shared knowledge vault — `capture`, `lookup`, and `status` as verb modes over the `claudron` CLI. Shared engine behavior lives in `skills/_shared/infra-cli-contract.md`; the Claudron-specific detection ladder, envelope validation, and degrade-loudly posture live in `skills/_shared/claudron-engine.md`. This file supplies only routing and the Claudron deltas.

## Mode dispatch (contract §3)

Arguments to dispatch (first token = verb, the rest belong to the verb): $ARGUMENTS

No verb token → infer only when the request wording is unambiguous ("save this to the vault" → `capture`; "what does the vault know about X" → `lookup`); otherwise print this table and stop — never guess `capture`, it mutates.

| Verb | When | Depth file |
|------|------|------------|
| `capture` | Deliberately save a note to the fleet vault — knowledge, decision, runbook, plan, audit, or review | `capture.md` |
| `lookup` | Search the vault for existing notes by term | `lookup.md` |
| `status` | Vault health — tiers, doc counts, staleness — or whether Claudron is installed and configured at all | `status.md` |

For the selected verb, read ONLY its depth file in this skill directory and follow it exactly — never load another verb's depth (contract §1, §3).

## Pre-flight deltas (contract §4)

Each verb resolves its state through the **detection ladder in `skills/_shared/claudron-engine.md` §1** — it replaces the generic CLI-installed / auth / target-discovery pre-flight and yields one of three verdicts (present-with-vault / present-no-vault / absent). `capture` and `lookup` run it at pre-flight and require present-with-vault; `status` runs it as its own Step 1 and reports the verdict in all three states. Each verb gates on the verdict in its depth file's Step 0. Every `--json` call is envelope-validated per §2; failures follow the exit-code posture in §3.

**Door note (F1).** clauDNA ships no MCP servers — this engine *is* the CLI. If Claudron's own MCP tools are configured in the session, they are the same engine with equivalent semantics; the CLI is the contract floor this skill targets.

## Structured result (`--auto`)

In `--auto`, each verb's final output is the single **structured result** JSON block defined in `skills/_shared/orchestration-guide.md` ("Structured Result Shape") — writing verbs carry `artifacts.engine`, `status` carries `artifacts.verdict` (per claudron-engine.md §3), any degradation in `errors[]`, and no interactive prompts. Per-verb fields are defined in the depth files.

`capture` is this engine's mutating verb — its confirmation gate lives in `capture.md`; `lookup` and `status` are read-only and never gate.
