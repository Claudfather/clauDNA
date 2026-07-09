Invoked by /claudna:claudron in lookup mode — the detection ladder (claudron-engine.md §1) has already run. `lookup` needs **present-with-vault**. Read-only — never gates.

# Lookup

Search the shared vault for existing notes via `claudron lookup`. Read-only. Follow these steps in order.

## Step 0: Gate on the vault verdict

- **present-with-vault** → continue.
- **present-no-vault** / **absent** → there is nothing to search. Report the verdict + remedy (`claudron init <path> --personal`, or install Claudron per SETUP_GUIDE) and stop. In `--auto`, emit the structured result with `outcome: "blocked"` and the remedy in `blocker_description`.

## Step 1: Run the search

```bash
claudron lookup <terms...> --json
```

`<terms...>` are positional (one or more words). Optional scoping: `--project <name>`, `--fleet <name>`, `--limit <n>`, `--include-archived`, `--include-expired`.

## Step 2: Envelope + results

Validate the envelope (claudron-engine.md §2): `data.query` and `data.results` (a list).

- **Results present** → render each entry (title, path, status, and score if present), most-relevant first.
- **Empty `results`** (exit 0) → report **"no results for '<terms>'"**. Claudron has no nearest-title / "did-you-mean" fallback — do **not** fabricate candidates. Suggest broadening the terms or adding `--include-archived`.

Optionally, for a single clearly-top match, read and show its note body from that entry's `path` (resolve relative to the vault `root` reported by `claudron status`).

## Step 3: Report

Interactive — a compact list:

```
Vault lookup: "<terms>"  (N results)
  1. <title>   <path>   (status: current)
  2. …
```

`--auto` — emit the structured result (orchestration-guide.md "Structured Result Shape"): `artifacts.engine: "claudron"` and a `results` count in `artifacts`; `outcome: "completed"` (a search that ran is complete, even with zero hits); any degradation in `errors[]`.
