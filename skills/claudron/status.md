Invoked by /claudna:claudron in status mode — this verb runs the detection ladder itself and reports the verdict. Read-only; it never errors on a missing CLI or vault — reporting that state is its whole purpose.

# Status

Report Claudron / vault health, or the fact that neither is configured. Read-only. Follow these steps in order.

## Step 1: Resolve the verdict (claudron-engine.md §1)

`status` runs the detection ladder as its own body — as separate Bash calls:

```bash
command -v claudron
```

```bash
claudron status --json
```

Classify strictly by the **§1 verdict table** (absent / present-no-vault / present-with-vault / engine-failure). Don't restate the criteria here — they can't be allowed to drift from §1.

## Step 2: Report the verdict

- **absent** →

  ```
  Claudron: not installed
    The /claudron engine and vault features are unavailable.
    Install:    see SETUP_GUIDE (Claudron integration)
    Meanwhile:  /claudna:publish --to vault writes the raw tree.
  ```

- **present-no-vault** →

  ```
  Claudron: installed, no vault configured
    Create one:  claudron init <path> --personal
    Or point at: export CLAUDRON_VAULT_PATH=<path>
  ```

- **present-with-vault** → parse `data` (envelope §2) and render:

  ```
  Claudron vault: <root>
    Docs:    <total_docs>    Stale: <total_stale>
    Tiers:   <tier> <docs>/<stale> …
    Scope:   projects <…>   fleets <…>
    Index:   present=<index_present> fresh=<index_fresh>
    Health:  quarantined <count>   warnings <count>
  ```

  Surface any `data.warnings` and `data.quarantined` entries verbatim — they are the actionable health signals.

## Step 3: `--auto`

Emit the structured result (orchestration-guide.md "Structured Result Shape") with `artifacts.verdict` = the ladder verdict (`absent` / `present-no-vault` / `present-with-vault`). `status` reports state and never falls back, so it carries no `artifacts.engine` (claudron-engine.md §3). `outcome: "completed"` in **all three** states — a status report that ran is complete, and absence is a valid, non-error result, so `errors[]` stays empty for a clean verdict. Only a malformed envelope or an unexpected non-zero exit populates `errors[]`.
