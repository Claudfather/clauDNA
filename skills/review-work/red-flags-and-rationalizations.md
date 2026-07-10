# Red Flags and Common Rationalizations

## Red Flags -- STOP

If you catch yourself thinking any of these during PR review, STOP -- you are about to approve without adequate scrutiny:

- "The PR is well-structured" -- Structure is not correctness. A beautifully organized PR can contain logic errors, missing edge cases, and security holes. Structure is Step 1 of review, not the whole review.
- "Tests pass" -- Tests passing means the *existing* tests pass. It does NOT mean the change is tested. Check: are there NEW tests for the NEW behavior? Do the existing tests actually cover the changed code paths?
- "The author is experienced" -- Experience does not prevent bugs. Experienced engineers ship security vulnerabilities, off-by-one errors, and race conditions. Review the code, not the resume.
- "This is a refactor, low risk" -- Refactors are among the highest-risk changes. They touch many files, change behavior boundaries, and break assumptions. A "safe refactor" still needs line-by-line review.
- "I've seen this pattern before" -- Familiarity is not review. The specific instance may have a bug even if the pattern is sound.
- Producing a review with zero Blockers AND zero Suggestions -- Either the PR is genuinely flawless (rare) or you didn't look hard enough. If your review is all Nits and Questions, re-examine Correctness, Edge Cases, and Error Handling from Step 4.
- Skipping Step 3 (Understand Intent) -- Jumping to critique without understanding purpose leads to wrong feedback. Read the PR description, linked issues, and plan docs FIRST.
- Posting "Approve" with a one-line summary -- Approval requires evidence. Show what you checked. A review that says "LGTM" is a review that didn't happen.
- Quoting a raw secret into a finding -- a diff line, `gh`/CLI output, or a connection string can carry a live credential (bot token, API key). Before findings leave the subagent, scrub the findings file with the clauDNA redactor (`scripts/redact.py` -- see orchestration-guide §7 "Redacting credentials in CLI output"). A review that surfaces a live credential is a security incident, not a review.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "The PR is well-structured" | Structure != correctness. Review the logic, not the formatting. |
| "Tests pass" | Passing tests may not cover the change. Check for NEW tests on NEW behavior. |
| "The author is experienced" | Experience != infallibility. Review code, not credentials. |
| "This is a refactor, low risk" | Refactors break things. They touch many files and shift assumptions. |
| "It's a small PR" | Small PRs get proportional review -- not no review. Check correctness, edge cases, security. |
| "I've seen this pattern before" | Pattern familiarity != instance correctness. Check THIS implementation. |
| "The plan was already approved" | Plans can be implemented incorrectly. Review against the plan AND against correctness. |
| "No security concerns in this area" | Did you actually check? Injection, auth bypass, and data exposure hide in unexpected places. |
| "LGTM" | "LGTM" is not a review. Name what you verified. |
| "I'll just paste the diff/CLI output" | Raw output can carry a live credential. Scrub findings with `scripts/redact.py` (orchestration-guide §7) before they leave the subagent. |
