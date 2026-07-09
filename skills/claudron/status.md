Invoked by /claudna:claudron in status mode — this verb runs the detection ladder itself and reports the verdict. Read-only; it never errors on a missing CLI or vault — reporting that state is its whole purpose.

# Status

Report Claudron / vault health, or the fact that neither is configured. Read-only. Follow these steps in order.

## Step 1: Resolve the verdict (claudron-engine.md §1)

Run the detection ladder as separate Bash calls:

```bash
command -v claudron
```

```bash
claudron status --json
```

Classify by result: **absent** (`command -v` fails) / **present-no-vault** (`status` exits 3 with `no vault found` on stderr) / **present-with-vault** (`status` exits 0 with an envelope).

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
    Or point at: export CLAUDRON_VAULT=<path>
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

Emit the structured result (orchestration-guide.md "Structured Result Shape"): `artifacts.engine` = `"claudron"` (present-with-vault) / `"fallback"` (present-no-vault) / `"absent"`; `artifacts.verdict` = the ladder verdict. `outcome: "completed"` in **all three** states — a status report that ran is complete, and absence is a valid, non-error result, so `errors[]` stays empty for a clean absent / no-vault verdict. Only a malformed envelope or an unexpected non-zero exit populates `errors[]`.
