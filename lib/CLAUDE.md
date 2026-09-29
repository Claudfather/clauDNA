# lib/ — runtime Python

`lib/claudna/` is the **runtime**: Python that runs on a user's machine, called by hooks and skills under a bare `python3`. Dev and CI tooling does not live here.

## What may live here

- Importable packages under `lib/claudna/` (e.g. `session_store/`), each a set of single-concern modules with a docstring stating the concern.
- Data a package needs at runtime, beside its code (e.g. `session_store/schemas/`).
- Nothing that only CI or a maintainer runs — validators, release tooling, and gates belong outside `lib/`.

## Rules (each enforced by `tests/test_runtime_layout.py`)

1. **Stdlib only.** Imports are the standard library or `claudna.*`. No dev dependency (pyyaml, pytest) may leak into runtime; it would fail inside a hook, silently.
2. **Imports point downward.** Inside a package, a module imports only strictly lower layers (`session_store`: schema/paths/fsio → events → project → store → cli). Need to call up? Invert it — pass a callback.
3. **One `sys.path` shim, at the entry point.** Only `__main__.py` may touch `sys.path`; library modules never do.

## How it's invoked

- Preferred: `python3 -m claudna.session_store <verb>` with `lib/` on `PYTHONPATH` — a hook wrapper sets `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/lib"`.
- Also works: `python3 "${CLAUDE_PLUGIN_ROOT}/lib/claudna/session_store" <verb>`.
- A hook's error handling must never swallow an `ImportError` silently: fail open for the session, but log it where it can be seen.

Tests live in `tests/`; fixtures in `tests/fixtures/`.
