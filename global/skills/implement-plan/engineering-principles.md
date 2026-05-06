# Engineering Principles

Every decision during plan review and implementation is filtered through these principles:

- **First principles over convention.** Don't accept a plan step because it looks reasonable — ask *why*. If the underlying reason doesn't hold, challenge it. Strip problems to their fundamentals before building solutions.
- **Simple design.** The best code is the code you didn't write. Prefer the smallest change that solves the problem. If a plan adds machinery, ask whether the machinery earns its complexity.
- **Modular code.** Each unit does one thing. Functions are short. Modules have clear boundaries. Dependencies point in one direction. If a change touches everything, the design is wrong.
- **Clean implementation.** No "we'll fix it later" code. No commented-out blocks. No dead imports. No magic numbers. The code that lands should be the code you'd want to read in six months.
- **Separation of concerns.** Data access doesn't know about presentation. Business logic doesn't know about transport. Config doesn't live in code. If a plan muddles these, flag it.

These aren't aspirational — they're the bar. Code that doesn't meet them doesn't merge.

## Applying During Implementation

Before writing a function: "Is this the simplest way? Does it do exactly one thing?"
Before adding a dependency: "Is this necessary? Can the standard library handle it?"
Before creating a file: "Does this belong here? Does the module structure make sense?"
Before adding an abstraction: "Is this pulling its weight? Would a direct implementation be clearer?"
After writing code: "Would I understand this in six months with no context?"
