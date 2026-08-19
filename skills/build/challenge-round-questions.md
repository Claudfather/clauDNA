# Challenge Round — Question Matrix & Evaluation Criteria

> **Violating the letter of this review is violating the spirit. If the plan looks "fine", you haven't looked hard enough.**

Review every aspect of the plan through the lens of the Engineering Principles (`engineering-principles.md`). For each concern, **ask the user directly** — don't silently accept or reject.

## Question Matrix

| Area | Question to ask |
|------|----------------|
| **Necessity** | "Does this change earn its complexity? Could we achieve the same outcome with less?" |
| **Modularity** | "This change touches N files across M concerns — can we narrow the blast radius?" |
| **Simplicity** | "The plan adds [abstraction/layer/pattern] — is it justified by current needs, or is it speculative?" |
| **Separation** | "This mixes [concern A] with [concern B] in [file] — should these be separate?" |
| **First principles** | "The plan assumes [X] — is that actually true in this codebase? What if we started from scratch?" |
| **Stale references** | "These references drifted — here are the corrections. Anything else I should know about recent changes?" |
| **Missing coverage** | "The plan doesn't mention [edge case/error path/test scenario] — should it?" |
| **Over-engineering** | "This could be done in [simpler way] — is there a reason the plan chose the more complex approach?" |

## Rules for the Challenge Round

- Ask questions in batches of 3-5. Don't overwhelm.
- For each question, propose a concrete alternative if you have one.
- Accept the user's judgment when they explain the reasoning — don't argue in circles.
- If the user agrees with a challenge, **update the plan document immediately** using the Edit tool. Don't defer edits.
- If a challenge results in a significant redesign, re-run the affected parts of Step 2 to verify the new plan.
- The minimum bar is 3-5 questions per batch. If the plan is genuinely perfect, the questions will be fast to resolve. If you can't find 3 questions, you haven't read the plan carefully.

## After Challenges Are Resolved

Show the user what changed:

```
Plan Updates
═══════════════════════════════════════════════════════════════════════════
  Line 23:  Updated file path src/api/handler.py L45 → L52
  Line 41:  Replaced utils.format() → utils.fmt()
  Line 58:  Simplified — removed intermediate DataTransformer class
  Line 72:  Added error handling for empty input edge case
  Lines 90-95:  New — added test case for concurrent access
═══════════════════════════════════════════════════════════════════════════
```

Ask: **"Plan looks solid now. Ready to build?"**

Do NOT proceed to implementation until the user confirms.
