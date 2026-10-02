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
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB = REPO_ROOT / "lib"
PACKAGE = "claudna"

#: session_store's layers, lowest first. A module may import only strictly lower ranks.
SESSION_STORE_LAYERS = {
    "schema": 0,
    "paths": 1,
    "fsio": 1,
    "claudron": 1,
    "transcript": 1,
    "lineage": 2,
    "events": 2,
    "project": 3,
    "digest": 5,
    "filing": 5,
    "ops": 2,
    "store": 4,
    "rollup": 4,
    "activity": 1,
    "telemetry": 2,
    "summarize": 5,
    "readers": 5,
    "retention": 5,
    "export": 5,
    "unclosed": 5,
    "harvest": 6,
    "boundaries": 7,
    "cli": 8,
    "__main__": 9,
}


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


@pytest.mark.parametrize("path", lib_modules(), ids=lambda p: dotted(p))
def test_only_entry_points_touch_sys_path(path):
    if path.name == "__main__.py":
        return
    assert not touches_sys_path(path.read_text()), f"{path}: library modules must not touch sys.path"
