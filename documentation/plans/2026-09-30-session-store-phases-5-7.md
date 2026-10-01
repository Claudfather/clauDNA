# Session store, phases 5–7: harvest (clauDNA side), readers and export, the ops log — design notes

**Status:** built, 2026-09-30, on top of phase 4 (#386).
**Spec:** `documentation/specs/2026-09-28-session-store-design.md` §6.7 (rollup), §7.2 (harvest), §8 (readers and export), §9 (retention), §12 items 5–7.

These are the three phases the spec lists after activity, built in one pass because each is small once phases 1–4 exist:
- **Phase 6** (readers and export) comes first because nothing blocks it, and it's the first time the store's records are visible.
- **Phase 5** is built as far as Claudron allows.
- **Phase 7** is a small ops log.

## Phase 6: readers, the rollup, the export door, retention

- **The rollup (§6.7)**, `rollup.py`: `sessions/<sid>/summary.json` from the `done` segment summaries, with the merge rules declared as data.
  - `title`, `intent` and `outcome` come from the latest segment.
  - `arc`, `done`, `blocks` and `procedures` are a union deduplicated on normalized text, with blocks keyed on home + subject + claim. Each item keeps `from_seg`.
  - `in_progress` and `next` are the latest segment's only.
  - A stale `done` summary (the segment was re-sealed since) is left out.
  - The summarizer refreshes the rollup after every `summary.completed`, under its own lock, so two workers can't write it out of order.
  - **Addition:** retention moves a retired segment's summary to `sessions/<sid>/summaries/seg-NNN.json`, and the rollup reads those too, so knowledge outlives its segment directory and the rollup stays a pure function of the files on disk. §6.7 predates retention and didn't say.
- **Readers (§8)**, `readers.py`: `list`, `show`, `timeline`, `failures [--group]`, as `session_store` verbs and as `/claudna:session` verbs (`history.md`).
  - They're read-only. A projection that is missing, fails its schema, or is behind its log is folded from its log in memory and never written. `show` also computes a missing rollup in memory; `list` reads the rollup file only, so it stays one read per session.
  - `failures --group` folds by signature across sessions and carries the newest occurrence's `tool_use_id`, so the full error can be read in the transcript. The store keeps a pointer, not a copy (phase 4).
- **Export (§8)**, `export.py`: `session_store export --consumer <name> [--since-seg N] [--limit N] [--json]`, and `--ack --sid <sid> --through <seg>`.
  - The envelope is `claudna.export/1`: `{consumer, items: [{sid, seg, session, summary}], next: {sid: through}}`. `session` is a fixed subset of `session.json`.
  - Per session, a final `done` segment is an item, a `skipped` one passes, and so does one whose summary will never come (its last attempt spent, or a retry in a session harvest never runs for). Anything still in flight stops that session. The verdict is harvest's own (`project.summary_verdict`), so a cursor never skips work still coming and never waits on work that isn't.
  - Private sessions are never exported. Acks go through `SessionHandle.ack`, so there's one writer and a cursor never moves back. An ack can't go past the session's last segment, and `harvest` is a reserved consumer name.
- **Retention (§9)**, `retention.py`, run by the detached sweep (at most every 6 hours, bounded per run):
  - A final segment is retired once every *registered* consumer (anyone who has acked the session) acked it, or past `CLAUDNA_RETAIN_DAYS` (30; `0` turns the age cap off).
  - Retiring archives the summary, appends `segment.retired {reason: acked|age}` and removes the directory; then, once per session per run, it refreshes the rollup and rebuilds the projections. `session.json.segments.retired` counts retirements.
  - **Deviation from §9: a floor for acked segments,** `CLAUDNA_RETAIN_ACKED_DAYS` (7). §9 retires an acked segment at once. Harvest acks as soon as it captures, so without a floor a harvested segment would disappear minutes after its session ended, taking `timeline` and `show` with it. The age cap is unchanged.

## Phase 5: harvest, complete, the clauDNA side

§7.2's full pipeline needs Claudron pipes that don't exist yet. Claudron 0.6.1 has no `subjects`, `resolve`, `revert-run` or `--include-drafts` ([Claudron#200](https://github.com/Claudfather/Claudron/issues/200)). What doesn't need them is built:

- **The ledger**, `harvest/ledger.jsonl`: one line per capture. Each line has the session, the segment, the note's path made vault-relative (`capture` answers with an absolute `data.path`; `claudron promote` takes a vault-relative one), the vault root, who asserted it, and a **claim key** (the rollup's block key). Held person facts carry the key too.
- **Evidence**: the distinct sessions per claim key. That is §7.2's "recurring across ≥ 2 sessions" signal, counted locally.
- **The promotion digest** (§7.2, "a digest capped at ~5 items, most-reinforced first, surfaced as one SessionStart line, never blocking"): `digest.py`, `session_store digest`, and `/claudna:capture --review`.
  - It lists unreviewed drafts by sessions of evidence, user-asserted first on a tie, then the most recent. Held person facts come after.
  - A person chooses each item:
    - **promote** runs `claudron promote --to verified --by user`;
    - **discard** or **skip** takes the item out of the digest without promoting it;
    - a **person** fact is captured normally.
  - clauDNA never promotes on its own. `harvest/review.txt` is the SessionStart line (`Memory, to review: …`), rewritten after each harvest run and each review.

**Still blocked on Claudron#200, and not here:** subject resolution and the harvest plan model; section-targeted writes and one commit per run; `revert-run`; the risk tiers; the inbox and ambiguous queues, with their thresholds and 90-day archive; and Claudron-side draft filtering in `lookup`. Each needs a Claudron verb to exist first. The ledger and claim keys are shaped so a plan model can consume them when it lands.

## Phase 7: the ops log

`ops.py`: one line per background run in `<root>/runs/runs.jsonl`:

```json
{"run_id", "kind": "summarize|harvest|sweep", "started_at", "duration_ms", "outcome", "sessions": [...], "detail": {...}}
```

- The worker verbs write it (`summarize`, `harvest`, `sweep`). A write failure never fails the run, and the log rotates at 1 MiB.
- It's read with `session_store runs [--kind] [--since] [--json]`.
- "Mirroring `.claudron/`" turned out to mean little: Claudron keeps an index, a write lock and a `hooks.log` for failures, not a per-run log. So this is clauDNA's own small design.
- Per-session history stays the lifecycle log, which already records every summary job, retirement and close. A run's `sessions` list is the cross-reference.
- It never loads on the hook path. A test pins that `cli` doesn't import it: `uuid` alone cost ~5 ms, so the run id is `os.urandom`.

## Owner decisions (2026-09-30)

1. **The retention floor:** kept at 7 days for an acked segment. Spec §9 records it as built.
2. **Export consumers:** anyone who acks a session is registered for it. A consumer that never ran can't hold data back, and one that stops is caught by the 30-day cap. Claudron's side of the export door is Claudron's to build, against `claudna.export/1`.
