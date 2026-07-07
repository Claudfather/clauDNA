---
name: verify-completion
user-invocable: true
description: "Use when about to claim work is complete, fixed, or passing -- requires running verification commands and confirming output before making any success claims."
---

# Verify Completion

## The Iron Law

NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE

Claiming work is complete without verification is dishonesty, not efficiency.

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Gate Function

Before claiming any status or expressing satisfaction:

1. IDENTIFY -- What command proves this claim?
2. RUN     -- Execute the FULL command (fresh, complete)
3. READ    -- Full output, check exit code, count failures
4. VERIFY  -- Does output confirm the claim?
     If NO  -> State actual status with evidence
     If YES -> State claim WITH evidence
5. CLAIM   -- Only now make the claim

Skip any step = lying, not verifying.

<HARD-GATE>
Do NOT claim work is complete, fixed, passing, or done until you have:
1. Identified the verification command
2. Run it fresh in this message
3. Read the full output
4. Confirmed the output supports your claim
No exceptions. No shortcuts. Evidence before claims, always.
</HARD-GATE>

### When you can't verify

If you cannot run the verification -- build broke, a dependency is missing, you couldn't reach a state where the change is observable -- that is BLOCKED, not done. Say so plainly and name exactly where it stopped. "I couldn't verify because X" is honest; a success claim you couldn't back is not.

**When in doubt, FAIL.** A false "it works" ships broken code; a false "it doesn't" costs one more look. Ambiguous output is a non-claim, not a pass -- show the raw output and let the reader judge.

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, "logs look good" |
| Bug fixed | Test original symptom: resolved | Code changed, assumed fixed |
| Feature works end-to-end | Run the app to where the change executes; observe behavior | Green tests, "tests cover it" |
| Requirements met | Line-by-line checklist verified | Tests passing alone |
| Agent completed | VCS diff shows expected changes | Agent reports "success" |

## Evidence Matches the Claim

Not all evidence is equal -- the command must prove *this* claim:

- **Behavioral claims** ("the feature works", "the bug is fixed") -- the proof is the **running app at its surface** (CLI output, HTTP response, rendered UI), not a green test suite. Passing tests show CI runs; re-running them to "verify" behavior is re-running CI. For these, run the app to where the change executes (see `/verify`).
- **Mechanical claims** ("tests pass", "build clean", "linter clean") -- the proof is that exact command's fresh output.

A behavioral claim backed only by "tests pass" is unverified.

## Red Flags — STOP

If you catch yourself doing any of these, STOP and run verification:

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!")
- About to commit, push, or create a PR without verification
- Trusting a subagent's success report without checking its output
- Relying on partial verification (linter passed != tests passed)
- Thinking "just this once"
- ANY wording implying success without having run verification

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence != evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter != compiler != tests |
| "Agent said success" | Verify independently |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

Tests:  [Run test command] -> [See: N/N pass] -> "All tests pass"
Build:  [Run build] -> [See: exit 0] -> "Build succeeds"
Reqs:   Re-read plan -> Checklist each item -> Verify each -> Report

## Verify the Full Change

Check the work against its full scope, not a stale or partial view. Establish the complete range before judging "done":

    git diff @{u}.. --stat          # full branch range, not just HEAD~1
    git diff origin/HEAD... --stat  # no upstream: committed vs base
    gh pr diff                      # in a PR context

The diff is ground truth; any description of it is a claim. A checklist verified against a stale tree or a single commit can read "complete" while the actual change is not.

## When to Apply

ALWAYS before: any success/completion/satisfaction claim, committing, PR creation, task completion, moving to next task, reporting subagent results.

## Cross-References

- `/claudna:implement-plan` Step 6 -- applies this discipline to deliverable audit
- `/claudna:review-work` (changes mode) -- run verification before recommending "commit"
- `/claudna:quick-commit` -- run verification before staging and committing
- `/verify` (built-in Claude Code) -- the runtime-observation protocol for *behavioral* verification: build, run the app, drive it to the change, capture what you see. This skill gates *whether you may claim done*; `/verify` is *how* you produce behavioral evidence.
