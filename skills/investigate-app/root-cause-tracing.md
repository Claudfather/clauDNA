# Root Cause Tracing

Trace bugs backward through the call stack to find the original trigger. Fix at source, not symptom.

## The 5-Step Backward Trace

### Step 1: Observe the Symptom

What exactly is failing? Capture the full error message, stack trace, and context.

```
Example: "Error: ENOENT: no such file or directory '/tmp/worktrees/'"
```

### Step 2: Find the Immediate Cause

Look at the line that threw. What variable/value is wrong?

```
Example: projectDir is empty string "" → path resolves to "/tmp/worktrees/"
         instead of "/tmp/worktrees/my-project/"
```

### Step 3: Ask — What Called This?

Follow the stack trace one frame up. What passed the bad value?

```
Example: createWorktree(projectDir) was called with ""
         ← called by initializeWorkspace(config)
         ← config.projectDir was never set
```

### Step 4: Keep Tracing Up

Continue until you find where the correct value should have been set but wasn't.

```
Example: initializeWorkspace(config)
         ← Session.create(options)
         ← options.projectDir missing from test setup
         ← test helper doesn't set projectDir
```

### Step 5: Fix at Source

The root cause is where the value should have been set. Fix THERE, not at the symptom.

```
Bad fix:  Add fallback in createWorktree: projectDir || "/default"
Good fix: Require projectDir in Session.create, validate in test helper
```

## When to Use

- Error is deep in the call stack
- Same error keeps appearing in different places
- Fix at the error site doesn't stick
- You're tempted to add a defensive check instead of understanding why

## Instrumentation Tips

When the trace is unclear, add temporary logging at suspicious boundaries:

```
// Temporary — trace where bad value originates
console.error(`[TRACE] functionName called with:`, {
  param,
  stack: new Error().stack
});
```

Remove after finding root cause. Never ship trace logging.

## Common Mistakes

| Mistake | Why It Fails |
|---------|-------------|
| Fix at symptom site | Masks the real bug, breaks elsewhere later |
| Add null check instead of tracing | Hides the source of the null |
| Stop at first "plausible" cause | Often a deeper root exists |
| Skip frames in the stack trace | Miss the actual trigger point |

## Key Principle

**The root cause is almost never where the error appears.** The error is a symptom. Trace backward until you find where the correct value should have been set — that's where your fix belongs.
