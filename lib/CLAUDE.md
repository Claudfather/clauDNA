# lib/ — runtime Python

`lib/claudna/` is the **runtime**: Python that runs on a user's machine, called by hooks and skills under a bare `python3`. Dev and CI tooling does not live here.

## What may live here

- Importable packages under `lib/claudna/` (e.g. `session_store/`), each a set of single-concern modules with a docstring stating the concern.
- Data a package needs at runtime, beside its code (e.g. `session_store/schemas/`).
- Nothing that only CI or a maintainer runs — validators, release tooling, and gates belong outside `lib/`.

## Rules (each enforced by `tests/test_runtime_layout.py`)

1. **Stdlib only.** Imports are the standard library or `claudna.*`. No dev dependency (pyyaml, pytest) may leak into runtime; it would fail inside a hook, silently.
2. **Imports point downward.** Inside a package, a module imports only strictly lower layers (`session_store`: schema → paths/fsio/transcript/activity → events/lineage/telemetry → project → store → summarize/unclosed → harvest → boundaries → cli; the ranks are `SESSION_STORE_LAYERS` in the test). Need to call up? Invert it — pass a callback.
3. **One `sys.path` shim, at the entry point.** Only `__main__.py` may touch `sys.path`; library modules never do.

## How it's invoked

- **Hooks use the directory form:** `python3 "${CLAUDE_PLUGIN_ROOT}/lib/claudna/session_store" <verb>`. Hooks run in the user's project, and `python3 -m` puts the current directory first on `sys.path`, so a project's `json.py` would shadow the stdlib. (`-P` fixes that only from Python 3.11; the floor is 3.9.)
- `python3 -m claudna.session_store <verb>` with `PYTHONPATH=lib` is fine from this repo — tests and local debugging — never from a hook.
- POSIX only: the store locks with `fcntl`, so it runs on macOS and Linux, not Windows. The stdlib-only gate can't see that.
- The floor is **Python 3.9** (stock macOS): the `runtime-floor` CI leg runs the runtime suites on it (`make test-runtime`).
- A hook's error handling must never swallow an `ImportError` silently: fail open for the session, but log it where it can be seen.

Tests live in `tests/`; fixtures in `tests/fixtures/`.
