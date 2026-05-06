# Defense in Depth

After finding a root cause, add validation at multiple layers so the same class of bug can't recur undetected.

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

1. **Map data flow** — trace the path from input to where the bug appeared
2. **Validate each layer** — add appropriate checks at each boundary
3. **Test layers independently** — each validation should have its own test
4. **Verify together** — end-to-end test that exercises the full chain

## When to Use

After fixing a root cause, ask: "What layers could have caught this before it reached the failure point?" Add validation at each layer that was missing it.

## Key Principle

**One check is never enough.** Entry validation catches malformed input. Business logic catches invalid state. Environment guards catch dangerous contexts. Instrumentation catches what you didn't predict. Each layer is independent — if one fails, the others still protect.
