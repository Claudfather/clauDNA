# Red Flags and Common Rationalizations

## Red Flags — STOP

If you catch yourself thinking any of these during the Challenge Round (Step 3), STOP — you are about to rubber-stamp the plan:

- "The plan looks fine" / "No concerns" — Plans always have concerns. If you found none, you didn't look hard enough. Re-read the Engineering Principles and challenge each step against them.
- "This is a minor change, skip the challenge" — Minor changes are where bugs hide. The challenge round scales to the PR — a small plan means a fast challenge, not no challenge.
- "The user already approved this in product-enhance" — Planning approval is NOT implementation approval. The plan was written without seeing the current codebase state. Step 2 exists because plans drift.
- "Let me just start coding to see if it works" — Code-first defeats the purpose of having a plan. If the plan isn't clear enough to challenge, it isn't clear enough to implement.
- "I'll challenge as I go" — Deferred review is no review. Challenges discovered mid-implementation cost 10x more to fix than challenges caught before coding begins.
- Asking fewer than 3 challenge questions on a non-trivial plan — The minimum bar is 3-5 questions per batch. If the plan is genuinely perfect, the questions will be fast to resolve. If you can't find 3 questions, you haven't read the plan carefully.
- Skipping the "Plan vs. Codebase" comparison table in Step 2 — The table isn't optional formatting. It's the evidence that you actually checked. No table = no verification.
- Jumping to Step 5 (Branch & Implement) without user confirmation — "Ready to build?" requires a response. Silence is not consent.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "The plan looks fine" | "Looks fine" is not a challenge. Name ONE specific concern or you haven't reviewed it. |
| "No concerns" | There are always concerns. Re-read with the Engineering Philosophy checklist. |
| "This is a minor change" | Minor changes get a minor challenge round — not zero challenge round. |
| "The user already approved this" | Planning approval != implementation approval. Codebase may have drifted. |
| "Let me just start coding" | Code-first is plan-last. Challenge BEFORE building. |
| "I'll challenge as I go" | "As I go" means "never." Challenge round is Step 3, not Step 5. |
| "The plan is from a trusted source" | Trust is not a substitute for verification. Even good plans have stale references. |
| "I already know this codebase" | Familiarity breeds assumptions. Check the files anyway. |
| "The challenge round is slowing us down" | Rework from unchallenged plans is what slows you down. |
