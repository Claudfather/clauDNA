Invoked by /claudna:claudron in lookup mode — the detection ladder (claudron-engine.md §1) has already run. `lookup` needs **present-with-vault**. Read-only — never gates.

# Lookup

Search the shared vault for existing notes via `claudron lookup`. Read-only. Follow these steps in order.

## Step 0: Gate on the vault verdict

- **present-with-vault** → continue.
- **present-no-vault** / **absent** → there is nothing to search. Emit the standard degradation notice (`claudron-engine.md` §3.1 — the `/claudna:claudron` row, whose `<fallback>` is "no fallback — reporting the verdict and stopping"), add the no-vault remedy `claudron init <path> --personal` where the verdict is `present-no-vault`, and stop. In `--auto`, emit the structured result with `outcome: "blocked"`, the notice in `blocker_description`, and the same line in `errors[]`.

## Step 1: Run the search

```bash
claudron lookup --json -- "$(cat <terms-file>)"
```

Write the search terms, joined by spaces, to `<terms-file>`, a file in `<scratch>` (`../_shared/orchestration-guide.md` §1), with the Write tool first; they never go into the command itself. Optional scoping: `--project <name>`, `--fleet <name>`, `--limit <n>`, `--include-archived`, `--include-expired`.

## Step 2: Envelope + results

Validate the envelope (claudron-engine.md §2): `data.query` and `data.results` (a list).

- **Results present** → render each entry (title, path, tier, and score), most-relevant first. (The result shape is `title` / `score` / `match_type` / `tier` / `path` / `tags` — there is no `status` field.)
- **Empty `results`** (exit 0) → report **"no results for '<terms>'"**. Claudron has no nearest-title / "did-you-mean" fallback — do **not** fabricate candidates. Suggest broadening the terms or adding `--include-archived`.

Optionally, for a single clearly-top match, read and show its note body from that entry's `path` (resolve relative to the vault `root` already in the pre-flight status envelope — claudron-engine.md §1; no fresh `claudron status` call).

## Step 3: Report

Interactive — a compact list:

```
Vault lookup: "<terms>"  (N results)
  1. <title>   <path>   (fleet · score 42)
  2. …
```

`--auto` — emit the structured result (orchestration-guide.md "Structured Result Shape"): `artifacts.engine: "claudron"` and a `results` count in `artifacts`; `outcome: "completed"` (a search that ran is complete, even with zero hits); any degradation in `errors[]`.
