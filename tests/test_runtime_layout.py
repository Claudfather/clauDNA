"""Structural gates for runtime Python under lib/claudna/ (see lib/CLAUDE.md).

Three rules, each enforced by an AST scan rather than review — review alone
misses import-direction drift, and a runtime import that only exists on a
developer's machine fails silently inside a hook on a user's:

1. **Stdlib only.** Every import in lib/ is the standard library or claudna
   itself. Dev dependencies (pyyaml, pytest, ruff) are installed for CI, never
   for users.
2. **One-way layering.** Inside session_store, a module imports only from
   strictly lower layers, so the pure core never grows a dependency on the
   write API or the CLI.
3. **One sys.path shim.** Only an entry point (``__main__.py``) may touch
   ``sys.path``; library modules never do.

Scanning covers function-level imports too. Each detector is self-tested on a
known-bad snippet so a broken scanner can't pass an empty result.
"""

from __future__ import annotations

import ast
import fnmatch
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB = REPO_ROOT / "lib"
PACKAGE = "claudna"
MAKEFILE = REPO_ROOT / "Makefile"

# Keep discovery bounded to known runtime/hook test families, plus user-facing
# helper scripts whose test names do not share those families. Static prose
# checks inside test_scratch_paths.py stay in the floor selection too.
RUNTIME_TEST_PATTERNS = (
    "test_*_hook.py",
    "test_*_hook_without_jq.py",
    "test_gh_guard_*.py",
    "test_git_output_guard.py",
    "test_hook_input_hardening.py",
    "test_precompact_defer.py",
    "test_session_store*.py",
    "test_session_continuity.py",
    "test_*scratch*.py",
)
RUNTIME_TEST_HELPERS = {
    "test_claudna_root_resolution.py",
    "test_claudron_contract.py",
    "test_crawl_page.py",
    "test_env_from_file.py",
    "test_resolve_memory_dir.py",
    "test_skill_usefulness.py",
    "test_host_context_scoping.py",
}

# Deliberate exclusions with their scope boundary; neither belongs to the
# offline Python 3.9 user-runtime test target.
RUNTIME_COVERAGE_EXCLUDED = {
    "tests/test_maintainer_scratch.py": "maintainer ownership tests stay in the full test suite",
    "tests/test_claudron_live.py": "requires a live Claudron engine; its contract leg owns execution",
}


def runtime_test_paths(makefile: Path = MAKEFILE) -> set[str]:
    """Read the test paths from the real continued Makefile assignment."""
    lines = makefile.read_text().splitlines()
    assignment = next(i for i, line in enumerate(lines) if line.startswith("RUNTIME_TESTS ="))
    line = lines[assignment]
    value = [line.split("=", 1)[1]]
    index = assignment + 1
    while line.rstrip().endswith("\\"):
        line = lines[index]
        value.append(line)
        index += 1
    return set(re.findall(r"tests/test_[A-Za-z0-9_.-]+\.py", " ".join(value)))


def runtime_coverage_gaps(selected: set[str]) -> set[str]:
    return runtime_coverage_candidates() - selected


def runtime_coverage_candidates() -> set[str]:
    """The bounded, existing user-runtime families this floor must select."""
    tests = REPO_ROOT / "tests"
    candidates = {
        f"tests/{path.name}"
        for path in tests.glob("test_*.py")
        if any(fnmatch.fnmatch(path.name, pattern) for pattern in RUNTIME_TEST_PATTERNS)
    }
    candidates.update(f"tests/{name}" for name in RUNTIME_TEST_HELPERS)
    return candidates - set(RUNTIME_COVERAGE_EXCLUDED)

#: session_store's layers, lowest first. A module may import only strictly lower ranks.
SESSION_STORE_LAYERS = {
    "schema": 0,
    "paths": 1,
    "fsio": 2,
    "claudron": 1,
    "transcript": 1,
    "lineage": 3,
    "events": 3,
    "project": 4,
    "digest": 6,
    "filing": 6,
    "ops": 3,
    "store": 5,
    "rollup": 5,
    "continuity": 6,
    "activity": 1,
    "telemetry": 3,
    "summarize": 6,
    "readers": 6,
    "retention": 6,
    "export": 6,
    "unclosed": 6,
    "harvest": 7,
    "health": 7,
    "host": 6,
    "host_claude": 7,
    "host_codex": 7,
    "boundaries": 8,
    "cli": 9,
    "__main__": 10,
}

PACKAGE_SUPPORT_LAYERS = {"catalog": 0, "doctor": 1, "__main__": 2}


def lib_modules() -> list[Path]:
    return sorted(p for p in (LIB / PACKAGE).rglob("*.py") if "__pycache__" not in p.parts)


def imports_of(source: str, module: str) -> list[tuple[str, int]]:
    """Every import in ``source`` as (absolute dotted name, line), relative ones resolved.

    ``module`` is the importing module's dotted name (``claudna.session_store.store``).
    """
    package = module.rsplit(".", 1)[0]  # the containing package, for __init__ and plain modules alike
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                prefix = ".".join(base)
                if node.module:
                    found.append((f"{prefix}.{node.module}", node.lineno))
                else:
                    found.extend((f"{prefix}.{alias.name}", node.lineno) for alias in node.names)
            else:
                found.append((node.module or "", node.lineno))
    return found


def touches_sys_path(source: str) -> list[int]:
    """Lines that reference ``sys.path`` in any form."""
    return sorted(node.lineno for node in ast.walk(ast.parse(source))
                  if isinstance(node, ast.Attribute) and node.attr == "path"
                  and isinstance(node.value, ast.Name) and node.value.id == "sys")


def dotted(path: Path) -> str:
    return ".".join(path.relative_to(LIB).with_suffix("").parts)


# ── detector self-tests ──────────────────────────────────────────────────────


def test_import_scanner_sees_every_form():
    src = "import os\nfrom . import events\nfrom .fsio import x\nfrom .. import y\ndef f():\n    import yaml\n"
    names = {n for n, _ in imports_of(src, "claudna.session_store.store")}
    assert names == {"os", "claudna.session_store.events", "claudna.session_store.fsio", "claudna.y", "yaml"}


def test_sys_path_scanner_sees_mutation_and_reads():
    assert touches_sys_path("import sys\nsys.path.insert(0, 'x')\nprint(sys.path)\n") == [2, 3]
    assert touches_sys_path("import os\nos.path.join('a')\n") == []


def test_there_is_something_to_scan():
    assert len(lib_modules()) >= 9  # a scanner over an empty tree passes vacuously


def test_python39_floor_selects_runtime_and_hook_suites():
    selected = runtime_test_paths()
    required = runtime_coverage_candidates()
    missing = runtime_coverage_gaps(selected)
    assert not missing, f"Python 3.9 runtime test suites missing from Makefile RUNTIME_TESTS: {sorted(missing)}"
    excluded_selected = selected & set(RUNTIME_COVERAGE_EXCLUDED)
    assert not excluded_selected, "; ".join(
        f"{path}: {RUNTIME_COVERAGE_EXCLUDED[path]}" for path in sorted(excluded_selected)
    )
    missing_files = required - {
        path for path in required if (REPO_ROOT / path).is_file()
    }
    assert not missing_files, f"runtime coverage list refers to missing tests: {sorted(missing_files)}"


def test_runtime_coverage_guard_detects_a_removed_matrix_entry(tmp_path):
    removed = "tests/test_notify_hook.py"
    source = MAKEFILE.read_text()
    assert source.count(f"{removed} ") == 1
    incomplete_makefile = tmp_path / "Makefile"
    incomplete_makefile.write_text(source.replace(f"{removed} ", "", 1))
    selected = runtime_test_paths(incomplete_makefile)
    assert runtime_coverage_gaps(selected) == {removed}


# ── the rules ────────────────────────────────────────────────────────────────


def stdlib_names() -> frozenset[str]:
    """Top-level stdlib module names. ``sys.stdlib_module_names`` is 3.10+; the
    runtime floor is 3.9 (spec §10), so fall back to listing the stdlib dir."""
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return frozenset(names)
    import sysconfig

    found = set(sys.builtin_module_names)
    for base in {Path(sysconfig.get_paths()[key]) for key in ("stdlib", "platstdlib")}:
        for folder in (base, base / "lib-dynload"):
            if folder.is_dir():
                found.update(e.name.split(".")[0] for e in folder.iterdir() if e.name != "site-packages")
    return frozenset(found)


def test_the_stdlib_list_knows_the_basics():
    assert {"json", "os", "subprocess", "fcntl", "hashlib"} <= stdlib_names()
    assert "yaml" not in stdlib_names() and "pytest" not in stdlib_names()


@pytest.mark.parametrize("path", lib_modules(), ids=lambda p: dotted(p))
def test_runtime_imports_are_stdlib_or_claudna(path):
    stdlib = stdlib_names()
    bad = [(name, line) for name, line in imports_of(path.read_text(), dotted(path))
           if name.split(".")[0] not in stdlib and name.split(".")[0] != PACKAGE]
    assert not bad, f"{path}: non-stdlib runtime imports {bad}"


@pytest.mark.parametrize(
    "path", sorted((LIB / PACKAGE / "session_store").glob("*.py")), ids=lambda p: p.stem
)
def test_session_store_imports_only_lower_layers(path):
    assert path.stem in SESSION_STORE_LAYERS or path.stem == "__init__", f"unranked module {path.stem}"
    rank = SESSION_STORE_LAYERS.get(path.stem, -1)
    prefix = f"{PACKAGE}.session_store."
    for name, line in imports_of(path.read_text(), dotted(path)):
        if not name.startswith(prefix):
            continue
        target = name[len(prefix):].split(".")[0]
        assert SESSION_STORE_LAYERS[target] < rank, (
            f"{path.name}:{line} imports {target} (layer {SESSION_STORE_LAYERS[target]}) "
            f"from layer {rank} — imports must point strictly downward"
        )


@pytest.mark.parametrize(
    "path", sorted((LIB / PACKAGE / "package_support").glob("*.py")), ids=lambda p: p.stem
)
def test_package_support_imports_only_lower_layers(path):
    assert path.stem in PACKAGE_SUPPORT_LAYERS or path.stem == "__init__"
    rank = PACKAGE_SUPPORT_LAYERS.get(path.stem, -1)
    for name, line in imports_of(path.read_text(), dotted(path)):
        if name.startswith("claudna.package_support."):
            target = name.split(".")[2]
            assert PACKAGE_SUPPORT_LAYERS[target] < rank, f"{path.name}:{line} imports upward"
        if name.startswith("claudna.session_store."):
            assert path.stem == "doctor" and name.split(".")[2] in {"health", "store"}


@pytest.mark.parametrize("path", lib_modules(), ids=lambda p: dotted(p))
def test_only_entry_points_touch_sys_path(path):
    if path.name == "__main__.py":
        return
    assert not touches_sys_path(path.read_text()), f"{path}: library modules must not touch sys.path"
