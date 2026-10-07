# Pre-registration: session-end summarizer comparison

**Withdrawn:** 2026-10-04 — Claudlobby#2145 F15; the battery period never started; the digest retires in #2145 P3. Below is the document as ratified and frozen on 2026-09-30; nothing else in it changes.

**Status:** ratified by the owner as written, 2026-09-30, and frozen: any change is a new pre-registration with its own date. Arm B is therefore pinned to Claudlobby `main` as of 2026-09-30; its SHA goes in the results doc. The 3 battery bots are still to be named before the period starts.
**Context:** session store spec §1.1 rule 4; [Claudlobby#1961](https://github.com/Claudfather/Claudlobby/issues/1961).

## Why pre-register

Two components summarize the same session at SessionEnd with `claude -p`: clauDNA's segment summarizer and Claudlobby's `transcript-digest.sh`. For an observation period both run, siloed. One owner is then chosen on evidence. If the battery, metrics and thresholds are picked after the results are in, the result can be read either way, so they are fixed here first.

## Arms

| Arm | Component | Pinned at |
|---|---|---|
| A | clauDNA `session_store summarize` (prompt `segment-summary/1`, model `haiku`) | the clauDNA commit that merges phase 2 |
| B | Claudlobby `transcript-digest.sh` | the Claudlobby `main` commit on the day this is ratified |

Pins are recorded as commit SHAs in the results doc. A change to either arm's prompt or model during the period ends that arm's data at the change.

## Battery

- **Bots:** 3 fleet bots with different workloads, named at ratification. Both arms are on for these bots (`CLAUDNA_SESSION_SUMMARY=1`, digest enabled) and off for every other bot.
- **The arms must not interact.** Arm B runs its own `claude -p` at the bot's SessionEnd, and that child inherits the bot's session id. Arm A ignores hooks from any `claude` process but the one that opened the session (`CLAUDE_PID`, recorded at open; #373 review). Before the period starts, one canary session per battery bot confirms that Arm B's child records nothing in the bot's session. If it does, the period waits for the child marker in [Claudlobby#1961](https://github.com/Claudfather/Claudlobby/issues/1961).
- **Sessions:** every session those bots end during the period, with no cherry-picking. Sessions that are **trivial** (no user turn) or **private** are excluded from quality scoring, but still count toward coverage.
- **Gold labels:** a random sample of 30 sessions, stratified 10 per bot. A reviewer reads each transcript and lists the durable facts a teammate would want next month. The reviewer does this **before** seeing either arm's output, and without knowing which arm produced what when judging.

## Metrics

| Metric | Definition |
|---|---|
| **Precision** | Share of an arm's extracted facts (A: `blocks`; B: its fact items) that the reviewer marks durable **and** correct. |
| **Recall** | Share of the gold-labelled durable facts that appear, in substance, in the arm's output. |
| **Fabrication rate** | Share of extracted facts the transcript does not support. |
| **Journey usefulness** | Reviewer rating 1–3: could someone resume the work from this summary alone? |
| **Coverage** | Share of the battery's non-trivial sessions for which the arm produced a usable artifact. Covers failures, timeouts and missing transcripts, and whether a skipped row was recorded when it skipped. |
| **Cost** | Median and p95 USD per session. |
| **Latency** | Median and p95 wall time from SessionEnd to artifact. |

## Decision rule

The winner is the arm that is **not worse on fabrication** (difference ≤ 2 points) and is better on **precision + recall**, summed. Ties go to the lower median cost. An arm is disqualified if:
- its fabrication rate exceeds 10%, or
- its coverage is below 90%, or
- it ever writes into a session other than its own, or blocks a session.

If neither arm is disqualified and the precision + recall difference is under 5 points, keep the cheaper arm and move the other's best prompt ideas into it.

## Stopping rule

The period ends at **4 weeks** or **60 battery sessions per bot**, whichever comes first. It ends early only for a disqualifying event, which is recorded with its evidence. There's no peeking: quality scoring happens once, after the period ends.

## After

The results doc (`documentation/plans/<date>-summarizer-comparison-results.md`) reports every metric per arm with the pinned SHAs and the gold set's session ids. The losing component is then retired through its own repo's normal removal process.
