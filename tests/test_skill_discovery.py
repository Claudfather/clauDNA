"""Manifest path classification and filesystem discovery need no YAML package."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_discovery_and_plugin_scope_work_without_site_packages(tmp_path):
    for name in ("demo", "_shared", "empty-directory"):
        (tmp_path / "skills" / name).mkdir(parents=True)
    for name in ("demo", "_shared"):
        (tmp_path / "skills" / name / "SKILL.md").write_text("# Fixture\n")
    plugin = tmp_path / ".cursor-plugin"
    plugin.mkdir()
    (plugin / "plugin.json").write_text(json.dumps({"skills": "./skills/"}))

    # -I ignores ambient PYTHONPATH, and -S removes installed site packages.
    # Exercise the real paths in a fresh process so prior test imports cannot
    # hide a transitive dependency on PyYAML or the validation policy module.
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", """
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
assert importlib.util.find_spec("yaml") is None
from plugin_scope import declared_skills
from skill_discovery import skill_dirs, walk_gate_files

root = Path(sys.argv[2])
assert [path.name for path in skill_dirs(root / "skills")] == ["demo"]
assert root / "skills/demo/SKILL.md" in walk_gate_files(root)
names, explicit, _ = declared_skills(root / ".cursor-plugin")
assert names == {"demo", "empty-directory"}
assert explicit is False
assert "skill_checks" not in sys.modules
assert "yaml" not in sys.modules
""", str(ROOT / "scripts"), str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
