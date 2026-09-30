Invoked by /claudna:claudron in doctor mode. This verb runs the detection ladder itself (claudron-engine.md §1), because the vault that most needs a doctor may be one walk-up no longer finds. `claudron doctor` itself is read-only; the ladder's `claudron status --json` may refresh the engine's index. The one write, `claudron doctor --fix`, runs only after the user confirms.

# Doctor

Check the vault against the rules of the installed engine and explain what it found. Only when the user says yes, apply the engine's own migrations. **Every check is the engine's.** This verb runs `claudron doctor` and explains its output; it never inspects the vault itself. Follow these steps in order.

## Step 1: Resolve the vault (claudron-engine.md §1)

With an explicit `--vault <path>` argument, the user has named the vault. **If that path is the user's home directory or `/`, stop before any engine call and say why:** migrating it would make every repo beneath it bind as the vault (Claudron #202), and even `claudron status` writes into the directory it is given. If that directory really is their vault, they can run `claudron doctor --vault <path>` themselves. Otherwise skip the walk-up: run `claudron status --json --vault <path>` and pass `--vault <path>` on every later call.

Otherwise, run the detection ladder as separate Bash calls:

```bash
command -v claudron
```

```bash
claudron status --json
```

Classify strictly by the §1 verdict table, then:

- **present-with-vault** → the vault is `data.root`. Continue with this envelope.
- **present-no-vault** → read stderr.
  - If it names a directory that "looks like a vault without its identity file", that directory is a vault from before the identity file. The engine migrates it only by explicit address. Show the path and ask the user whether it is their vault.
  - **If the path is the user's home directory or `/`, say so and do not offer it.** A stray `shared/` there is not a vault, and migrating it would make every repo beneath it bind as the vault (Claudron #202).
  - On a yes, run `claudron status --json --vault <path>` and continue with that envelope, passing `--vault <path>` on every later call.
  - Otherwise, emit the standard degradation notice (claudron-engine.md §3.1, the `/claudna:claudron` row), add the remedy `claudron init <path> --personal`, and stop.
- **absent** or **engine failure** → the §3.1 notice, then stop. For an engine failure, also surface stderr verbatim.

## Step 2: Gate on the capability, never the version

Only an engine that declares `doctor` has it. Check for `"doctor"` in `data.capabilities` from the Step 1 envelope. That is the gate Claudron's CLI contract names (§Capability probe).

- **Present** → continue.
- **Absent**, or no `capabilities` field → report "this Claudron predates `doctor`; upgrade the engine to diagnose and migrate the vault", show `data.engine_version` for identification only, and stop.

Never decide this from `engine_version`. A version floor cannot express it: a development build sorts before its own release. The capability list is the engine's own declaration.

## Step 3: Diagnose (read-only)

```bash
claudron doctor --json
```

Add `--vault <path>` when Step 1 resolved the vault by explicit address.

Without `--fix`, doctor writes nothing: no file, no index, no journal.

It can take a long time on a vault whose root also holds large ignored trees, such as bot checkouts (Claudron #201). Give the Bash call a long timeout. If it still does not return, say so and stop; never guess its findings.

Exit codes (Claudron's §Exit codes):

| Exit | Meaning | Then |
|---|---|---|
| 0 | No error findings; there may be warnings | Continue |
| 1 | At least one finding is an error. This is a completed diagnosis, not a failure | Continue |
| 2 | The call was malformed, which is a bug in this skill | Surface stderr verbatim; stop |
| 3 | No vault resolved | The §3.1 notice; stop |

Validate the envelope (claudron-engine.md §2): `command` is `doctor`, and `data` carries `vault_format`, `engine_format`, `pending` and `fixable`.

## Step 4: Explain each finding

Each finding is a `Finding` in the envelope's `errors[]` or `warnings[]`, with `code`, `severity`, `path` and `message`. For each one:

- show its code, severity and path;
- quote the engine's `message` verbatim;
- add one plain-language line on what it means for the user.

The engine's message is authoritative. This table only adds the next step. This verb runs none of these commands itself; they are what to hand the user.

| Code | In plain terms | What to do |
|---|---|---|
| `D001` | The vault's format is older than the engine's: a migration is pending, or, with nothing pending, only the recorded format is behind | `--fix` applies it, or records the format (Step 6) |
| `D002` | Some notes break the schema; the finding carries only a count | `claudron validate` has the detail. `--fix` never touches notes |
| `D003` | The search index has drifted from the notes | `claudron index` |
| `D004` | Git is not clean, ahead or behind: for example conflicted, mid-rebase, or on a side branch | `claudron sync --check`, then fix it in git |
| `D005` | `--fix` only. A migration needs a human decision, so the chain stopped | Read the message, decide, then run doctor again |
| `D006` | `--fix` only. A migration ran but is still needed, so the chain stopped | Report it: this is an engine bug |
| `D007` | The identity file is unreadable (error), or records a newer format than this engine knows (warning) | Repair the file, or upgrade the engine |
| `D008` | Files the ignore rules now cover are still tracked, so every sync keeps committing them | A human decides, per file: `git rm --cached <path>` |
| `S1`–`S4` | The vault's directory structure, as `validate` reports it | `--fix` repairs the ones `data.fixable` lists |

For a code not in this table, show the engine's message verbatim and say this skill does not know the code. Never guess what it means.

Also report the format line: `vault format <vault_format>, engine format <engine_format>`. The vault is current when the two are equal.

## Step 5: Show what `--fix` would change

`--fix` acts only on what `data.fixable` lists:

- the migrations in `data.pending`, in order: show each one's `id` and `title`;
- the structure findings that `data.fixable` names.

With a `D001` finding and nothing pending, only the vault's recorded format is behind: `--fix` records the engine's format in the identity file; with `data.fixable` empty, that is the whole commit.

Say plainly what `--fix` will **not** do:
- it never deletes a note;
- it never untracks a file, so a `D008` stays a human's call;
- it never changes schema findings (`D002`);
- it lands everything as one local commit, `migrate(<ids>): claudron doctor --fix`.

If `data.fixable` is empty and there is no `D001` finding, there is nothing to apply: report the diagnosis and stop.

## Step 6: Apply, only after the user confirms

Ask the user one question: whether to apply exactly the list from Step 5. Only on an explicit yes, run:

```bash
claudron doctor --fix --json
```

Add `--vault <path>` when Step 1 used one. Then report:

- `data.applied`: the migration ids, in order;
- `data.repairs`: one line per change the run made or skipped. For a format-only `D001`, one of them records the format, and `data.applied` is empty;
- `data.commit`: its `message` when `committed` is true, or its `error` verbatim when not. A clone that is mid-rebase gets the files but not the commit;
- what is still pending (`data.pending` after the run is `[]` on success), and every finding the run still carries.

The commit is local. Say so: other clones get it after the next push, or the next scheduled sync where one runs.

With no answer, an unclear answer, or no human in the session, do not run `--fix`. Report the diagnosis and the Step 5 plan, and stop.

## Step 7: `--auto`

`--auto` never runs `--fix`, because there is no one to confirm it.

Emit the structured result (orchestration-guide.md "Structured Result Shape") after Step 5, with:
- `artifacts.verdict`: the ladder verdict;
- `artifacts.pending`: the pending migration ids;
- `artifacts.fixable`: `data.fixable`;
- `outcome: "completed"`, because a diagnosis that ran is complete, whatever it found.

A §3.1 degradation goes into `errors[]`, with `outcome: "blocked"`.

Step 1's question about a vault from before the identity file cannot be asked in `--auto` either. Name the candidate path in `blocker_description` and stop with `outcome: "blocked"`.
