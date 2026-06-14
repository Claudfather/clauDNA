---
name: ironclad
description: "Use when a PR needs structured multi-lens review before merge. Applies to plan PRs (post-/forge), implementation PRs, and mixed PRs."
argument-hint: "<pr-url> [--auto]"
requires:
  - cli: gh
    reason: "Reads PR diff and metadata, scans PR comments for fork state, and posts the aggregated review comment via the GitHub API."
---

# Ironclad

`/ironclad` runs a panel of independent review lenses against a pull request, aggregates their findings into one comment, and reports whether the PR is converged — no open blockers, and (for plan PRs) all decision forks locked.

This skill is **subagent-only**: each lens runs as a parallel `general-purpose` subagent on the current machine. Fleet deployments override the dispatch step via a compositor-injected protocol (see the dispatch preamble below); the skill itself contains no fleet concepts (no tmux, no `[BOTREPORT]`, no `fleet-state.json`).

## Dispatch preamble — read before Phase 4

Before dispatching lenses, check whether your composed `CLAUDE.md` contains a **`fleet-dispatch-capability`** protocol. This is an *explicit* override hook, not an implicit one:

- **Protocol present →** follow its dispatch instructions instead of Phase 4 — it *substitutes* the dispatch path, it does not add behavior alongside it (a distinct override pattern, not an ordinary additive protocol). Run mode is `fleet`.
- **Protocol absent →** use the subagent dispatch in Phase 4. Run mode is `subagent`.
- **`FLEET_STATE_PATH` set but no `fleet-dispatch-capability` protocol found →** this is a misconfiguration (a fleet bot that would silently run subagents instead of distributing to workers). Emit the warning `FLEET_STATE_PATH is set but no fleet-dispatch-capability protocol found — falling back to subagent mode.` and run in `subagent` mode.

**Mode indicator (required in every run, both modes).** When you dispatch, emit a visible line and make it the first line under the PR comment header:

`Dispatching <N> lenses via <fleet|subagent> mode.`

Never dispatch silently — the indicator is what makes a misconfigured fleet bot detectable. In the plain standalone case (no protocol, no `FLEET_STATE_PATH`) it must read `via subagent mode`, with no warning.

## Pre-flight

Run `gh auth status`. If the GitHub CLI is not authenticated, stop immediately with a clear error — every phase reads or writes GitHub through it. Standalone users may have `gh` installed but not logged in; do not continue past this check.

## Procedure

### Phase 1: Read the PR and classify

1. Extract `owner/repo` and the PR number from the `<pr-url>` argument.
2. Fetch the diff with `gh pr diff <pr-url>` and metadata with `gh pr view <pr-url> --json title,body`.
3. **Classify:**
   - **Plan PR** — the diff modifies plan markdown (under `docs/`, `planning/`, `documentation/`, or `shared/planning/`) with plan structure (phases, decision forks). Read the full plan content **and any files it links to** (transitive reference reading) so lenses see the complete picture.
   - **Implementation PR** — the diff modifies source, config, scripts, or tests.
   - **Mixed** — both; all lenses apply and convergence follows the plan rules.
4. Record the PR title, type, and a one-line summary.

If the PR cannot be fetched, report the error verbatim and stop.

### Phase 2: Prepare the scratch directory

Create a scratch directory at `/tmp/ironclad-<YYYY-MM-DD_HHMMSS>/` (referred to as `<scratch>` below). Use the Write tool to create files inside it (auto-creates parents, so no `mkdir`, per the scratch-dir convention in `skills/_shared/orchestration-guide.md`). Write `<scratch>/source.md` with the PR metadata, type, and the full (transitively-resolved) plan or diff summary the lenses will review. Lay out per-lens result paths as `<scratch>/lenses/<lens>/result.md`.

**Cycle is always `1` in subagent mode** — `/tmp` is ephemeral, so there is no prior-run state to scan.

### Phase 3: Select lenses

Subagents are always available — there is no executor-availability step. Pick the lenses that apply from the PR type:

| Lens | Skill | Applies to | Status |
|------|-------|-----------|--------|
| Adversarial Review | `adversarial-review` | plan, implementation, mixed | Active |
| First Principles | `first-principles` | plan, mixed | Active |
| Extension Check | `extension-check` | implementation, mixed | Active |
| Precedent Check | `precedent-check` | plan, implementation, mixed | Active |
| Plan Health Audit | `plan-health-audit` | plan, mixed | Active |
| Cost-Benefit | `cost-benefit` | plan, implementation, mixed | Active |

Dispatch only the lenses whose **Applies to** matches the PR type. New lenses plug in by adding a row.

### Phase 4: Dispatch lenses as parallel subagents

Skip this phase entirely if the dispatch preamble routed you to a `fleet-dispatch-capability` protocol.

Launch one `general-purpose` subagent per applicable lens, all in parallel (`run_in_background: true`). Use `general-purpose` (not a read-only explorer) — the subagent needs the Write tool to emit its result. Launch prompt per lens:

```
Read skills/<lens>/SKILL.md
Apply the skill with --dispatch to: <SOURCE_PATH>
Write your result to: <scratch>/lenses/<lens>/result.md
Operate non-interactively: do not enter plan mode, do not prompt for input.
Emit structured markdown per skills/_shared/contracts/lens-result-contract.md.
```

Substitute `<SOURCE_PATH>` with the `<scratch>/source.md` path (or the PR URL for codebase-reading lenses such as extension-check and precedent-check), `<scratch>` with the scratch dir, and `<lens>` with each lens directory name.

### Phase 5: Collect results

Collect subagent completions **one at a time** — never gather multiple in a single step. For each completed lens, read **only the frontmatter** (first ~15 lines) of its `<scratch>/lenses/<lens>/result.md` to check `status` and `severity`. Do not read the full result into this orchestrator context; the aggregation phase reads the files. Queue any failed or missing lens for one retry.

### Phase 6: Retry failed lenses

Retry each failed lens **once**, as a fresh `general-purpose` subagent on the same machine (there is no alternative worker in subagent mode). If the retry also fails, proceed with partial results — a single lens failure does not block the run or convergence.

### Phase 7: Aggregate and deduplicate

Read every `<scratch>/lenses/<lens>/result.md`. Deduplicate: findings sharing the same file/line and the same concern collapse to one, keeping the higher severity and noting both contributing lenses. Preserve lens attribution. Sort findings into sections in this order — **Blockers, Risks, Gaps, Questions, Observations** — and omit any empty section.

### Phase 8: Post the aggregated comment

Post a **single** aggregated comment to the PR. A PR comment is an issue comment in GitHub's API; write the markdown body to a temp file (with the Write tool) and post it with `-F body=@<file>` so multi-line markdown stays intact:

```
gh api --method POST repos/<owner>/<repo>/issues/<pr-number>/comments -F body=@<body-file>
```

Comment format:

```
## Ironclad Review: <PR title>

Dispatching <N> lenses via <fleet|subagent> mode.

**Cycle:** <N> · **PR type:** <plan|implementation|mixed> · **Lenses:** <completed>/<failed>

<merged findings, by severity section; empty sections omitted>

---
*Reviewed by /ironclad — cycle <N>*
```

Prior-comment minimization is skipped in subagent mode (cycle is always 1).

### Phase 9: Convergence check

Decide whether the PR is converged:

- **Plan or mixed PRs:** converged when there are **zero open Blockers** AND all decision forks are locked. Determine fork state by scanning the PR's comments (`gh pr view <pr-url> --json comments`) for `[FORK-LOCK F<N>]` and `[FORK-REOPEN F<N>]` markers — the most recent marker per fork wins. This scan is self-contained in this skill and needs no external protocol. In fleet contexts the `decision-fork-lifecycle` protocol adds richer fork management, but the basic check here stands alone for standalone users. Note the difference: standalone fork checking does not enforce ratifier identity or reopen validation — acceptable for a solo user doing everything themselves; a fleet gets the stricter rules from its protocol.
- **Implementation PRs:** converged when there are **zero open Blockers**.
- A partial lens failure does not block convergence.

**If converged:** end the comment with the convergence line `[IRONCLAD] PR reviewed — no open blockers. Ready for implementation.`

**If not converged:** state the open items — unresolved blockers, open forks, and any failed lenses — with counts, so the author knows exactly what remains.

## `--auto` mode

With `--auto`, run the full procedure non-interactively (no plan mode, no prompting) and emit a single fenced JSON **structured-result** block as the final output, per `skills/_shared/orchestration-guide.md` §10.C. Emit nothing after it — no chat summary. Shape:

```json
{
  "skill": "ironclad",
  "outcome": "completed",
  "artifacts": {
    "pr_url": "<pr-url>",
    "comment_url": "<posted comment URL>",
    "pr_type": "plan|implementation|mixed",
    "cycle": 1,
    "mode": "subagent",
    "lenses_run": 0,
    "lenses_failed": 0,
    "converged": true,
    "blockers_open": 0,
    "forks_open": 0
  },
  "summary": "<one-line digest of the review outcome>",
  "next": null,
  "errors": [],
  "blocker_description": null
}
```

`outcome` mapping: `completed` when the review ran and the comment posted (converged or not — convergence is reported in `artifacts.converged`); `partial` when some lenses failed but the comment still posted; `blocked` when a pre-flight or fetch error stopped the run (put the reason in `blocker_description`). There is no manager to report to in subagent mode — the structured-result block is the only machine output, and callers parse it directly.

## Constraints

- **Read-only on the PR's code.** Never edit files in the PR, never merge. The only write is the single aggregated review comment.
- **Centralized posting.** Lenses write to the scratch dir; only `/ironclad` posts to the PR.
- **No self-review loops.** Do not dispatch `/ironclad` from within a lens.
- **Idempotent.** Re-running posts a fresh aggregated comment; in subagent v1 (cycle 1) prior comments are left in place rather than minimized.
