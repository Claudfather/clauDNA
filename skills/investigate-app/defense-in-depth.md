# Defense in Depth

After finding a root cause, identify unprotected failure boundaries and choose prevention and verification proportionate to the risk. The four layers below are options; each proposed layer needs a concrete failure it would prevent.

## The 4-Layer Pattern

### Layer 1: Entry Point Validation

Reject invalid input at the API/function boundary. Fail fast with clear errors.

```python
# API boundary — reject early
def create_workspace(project_dir: str, name: str):
    if not project_dir:
        raise ValueError("project_dir is required")
    if not os.path.isabs(project_dir):
        raise ValueError(f"project_dir must be absolute: {project_dir}")
```

```typescript
// API boundary — reject early
function createWorkspace(projectDir: string, name: string) {
  if (!projectDir) throw new Error("projectDir is required");
  if (!path.isAbsolute(projectDir))
    throw new Error(`projectDir must be absolute: ${projectDir}`);
}
```

### Layer 2: Business Logic Validation

Ensure data makes sense for the operation. Check invariants.

```python
# Business logic — verify preconditions
def initialize_worktree(config):
    assert config.project_dir, "project_dir missing from config"
    target = os.path.join(config.project_dir, config.name)
    assert not os.path.exists(target), f"worktree already exists: {target}"
```

### Layer 3: Environment Guards

Prevent dangerous operations in specific contexts (tests, CI, staging).

```python
# Environment guard — protect against dangerous operations
def delete_directory(path: str):
    if os.environ.get("CI") and path.startswith("/"):
        raise RuntimeError(f"Refusing to delete absolute path in CI: {path}")
    if path in ("/", "/tmp", os.path.expanduser("~")):
        raise RuntimeError(f"Refusing to delete protected path: {path}")
```

### Layer 4: Debug Instrumentation

Capture context for forensics when things go wrong.

```python
import logging

logger = logging.getLogger(__name__)

def process_request(request):
    logger.debug("process_request called", extra={
        "request_id": request.id,
        "user_id": request.user_id,
        "path": request.path,
    })
    # ... processing ...
```

## Application Process

1. **Map data flow and existing controls** — trace the path from input to the failure and identify what already protects it.
2. **Choose prevention** — add a check where a concrete failure remains unprotected; reuse adequate controls. Preserve valid safeguards and required project checks.
3. **Choose verification** — name what needs proving. Existing checks, static tracing, a focused reproduction or manual evidence may suffice. Add or update tests when needed to protect an uncovered behavior or regression; name the failure they catch.
4. **Verify relevant interactions** — use a focused integration or end-to-end check when the risk crosses boundaries that narrower evidence cannot establish. Report failed/unrun checks and remaining verification limits before handoff.

## When to Use

After finding a root cause, ask: "Which boundary could prevent this failure, and what evidence proves the fix?" If existing controls and verification are sufficient, no additional layer or test is needed.

## Key Principle

**Evidence and risk determine sufficient protection.** Add independent layers where they cover distinct failures. Keep valid checks intact; a layer count or a missing test file is not itself a reason to add work or weaken protection.
